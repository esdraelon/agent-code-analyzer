<?php

declare(strict_types=1);

namespace App\Frontend\Controller;

use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;

final class SearchController extends AbstractController
{
    public function index(ServerRequestInterface $request, ResponseInterface $response): ResponseInterface
    {
        $query = $request->getQueryParams();
        $mode = (string) ($query['mode'] ?? 'unified');
        $project = trim((string) ($query['project'] ?? ''));
        $searchQuery = trim((string) ($query['query'] ?? ''));
        $filePath = trim((string) ($query['file_path'] ?? ''));
        $directory = trim((string) ($query['directory'] ?? ''));
        $scopeType = trim((string) ($query['scope_type'] ?? ''));
        $symbolPath = trim((string) ($query['symbol_path'] ?? ''));
        $pageSize = max(1, min(50, (int) ($query['page_size'] ?? $query['limit'] ?? 10)));
        $page = max(1, (int) ($query['page'] ?? 1));
        $offset = ($page - 1) * $pageSize;
        $results = [];
        $projects = [];
        $apiQuery = [];
        $error = '';
        $totalHits = 0;

        try {
            $projectsPayload = $this->api->get('/api/projects');
            $projects = $projectsPayload['data']['projects'] ?? [];
        } catch (\Throwable $throwable) {
            $error = $throwable->getMessage();
        }

        try {
            if (in_array($mode, ['tree-sitter', 'ast'], true)) {
                if ($project !== '' && $filePath !== '') {
                    $payload = $this->api->get('/api/search/' . rawurlencode($mode), [
                        'project' => $project,
                        'file_path' => $filePath,
                    ]);
                    $results = $payload['data']['results'] ?? [];
                    $totalHits = (int) ($payload['data']['query']['total_count'] ?? count($results));
                }
            } elseif ($searchQuery !== '') {
                $apiQuery = [
                    'query' => $searchQuery,
                    'project' => $project !== '' ? $project : null,
                    'scope_type' => $scopeType !== '' ? $scopeType : null,
                    'directory' => $directory !== '' ? $directory : null,
                    'symbol_path' => $symbolPath !== '' ? $symbolPath : null,
                    'limit' => $pageSize,
                    'offset' => $offset,
                ];
                $apiQuery = array_filter($apiQuery, static fn (mixed $value): bool => $value !== null && $value !== '');
                $payload = $this->api->get('/api/search/' . rawurlencode($mode), $apiQuery);
                $results = $this->annotateSearchResults($payload['data']['results'] ?? []);
                $totalHits = (int) ($payload['data']['query']['total_count'] ?? count($results));
            }
        } catch (\Throwable $throwable) {
            $error = $error !== '' ? $error . ' · ' . $throwable->getMessage() : $throwable->getMessage();
        }

        return $this->html($response, 'search', [
            'pageTitle' => 'Search',
            'mode' => $mode,
            'project' => $project,
            'query' => $searchQuery,
            'filePath' => $filePath,
            'directory' => $directory,
            'scopeType' => $scopeType,
            'symbolPath' => $symbolPath,
            'pageSize' => $pageSize,
            'page' => $page,
            'offset' => $offset,
            'hasPreviousPage' => $page > 1,
            'hasNextPage' => count($results) >= $pageSize,
            'results' => $results,
            'projects' => $projects,
            'error' => $error,
            'activePage' => 'search',
            'apiBaseUrl' => $this->api->baseUrl(),
            'totalHits' => $totalHits,
        ]);
    }

    /**
     * @param array<int, array<string,mixed>> $results
     * @return array<int, array<string,mixed>>
     */
    private function annotateSearchResults(array $results): array
    {
        foreach ($results as &$result) {
            $filePath = (string) ($result['file_path'] ?? '');
            $language = (string) ($result['languages'][0] ?? $result['language'] ?? '');
            $result['excerptRows'] = $this->buildSearchPreviewRows($result, $language, $filePath);
        }
        unset($result);

        return $results;
    }

    /**
     * @param array<string,mixed> $result
     * @return array<int, array{line_no:string, html:string}>
     */
    private function buildSearchPreviewRows(array $result, string $language, string $filePath): array
    {
        $excerpt = $result['excerpt'] ?? [];
        if (is_array($excerpt) && trim((string) ($excerpt['content'] ?? '')) !== '') {
            return $this->formatExcerptRows((string) $excerpt['content'], $language, $filePath);
        }

        $previewContent = (string) ($result['chunk_text'] ?? $result['content_text'] ?? '');
        if (trim($previewContent) !== '') {
            return $this->formatExcerptRows($this->numberPreviewLines($previewContent, $this->previewStartLine($result)), $language, $filePath);
        }

        $sourceLink = $result['source_link'] ?? null;
        if (is_array($sourceLink)) {
            $project = (string) ($sourceLink['project'] ?? $result['project_name'] ?? $result['project'] ?? '');
            $linkedFilePath = (string) ($sourceLink['file_path'] ?? $filePath);
            $startLine = max(1, (int) ($sourceLink['start_line'] ?? $this->previewStartLine($result)));
            $endLine = max($startLine, min((int) ($sourceLink['end_line'] ?? ($startLine + 2)), $startLine + 2));
            if ($project !== '' && $linkedFilePath !== '') {
                try {
                    $encodedFilePath = implode('/', array_map('rawurlencode', explode('/', $linkedFilePath)));
                    $payload = $this->api->get('/api/projects/' . rawurlencode($project) . '/files/' . $encodedFilePath, [
                        'start_line' => $startLine,
                        'end_line' => $endLine,
                    ]);
                    $excerptFromSource = (string) ($payload['data']['excerpt']['content'] ?? '');
                    if (trim($excerptFromSource) !== '') {
                        return $this->formatExcerptRows($excerptFromSource, $language, $linkedFilePath);
                    }
                } catch (\Throwable) {
                    // Ignore preview fallback errors; the result card still renders without a sample.
                }
            }
        }

        return [];
    }

    /**
     * @param array<string,mixed> $result
     */
    private function previewStartLine(array $result): int
    {
        $startRow = $result['start_row'] ?? null;
        if (is_int($startRow) && $startRow >= 0) {
            return $startRow + 1;
        }

        $sourceLink = $result['source_link'] ?? null;
        if (is_array($sourceLink) && isset($sourceLink['start_line']) && is_numeric($sourceLink['start_line'])) {
            return max(1, (int) $sourceLink['start_line']);
        }

        return 1;
    }

    private function numberPreviewLines(string $content, int $startLine): string
    {
        $lines = array_slice(explode("\n", $content), 0, 3);
        $numbered = [];
        foreach ($lines as $index => $line) {
            $numbered[] = ($startLine + $index) . ': ' . $line;
        }

        return implode("\n", $numbered);
    }
}
