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
        $pageSize = max(1, min(50, (int) ($query['page_size'] ?? $query['limit'] ?? 10)));
        $page = max(1, (int) ($query['page'] ?? 1));
        $offset = ($page - 1) * $pageSize;
        $results = [];
        $projects = [];
        $apiQuery = [];
        $error = '';

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
                }
            } elseif ($searchQuery !== '') {
                $apiQuery = [
                    'query' => $searchQuery,
                    'project' => $project !== '' ? $project : null,
                    'scope_type' => $scopeType !== '' ? $scopeType : null,
                    'directory' => $directory !== '' ? $directory : null,
                    'limit' => $pageSize,
                    'offset' => $offset,
                ];
                $apiQuery = array_filter($apiQuery, static fn (mixed $value): bool => $value !== null && $value !== '');
                $payload = $this->api->get('/api/search/' . rawurlencode($mode), $apiQuery);
                $results = $this->annotateSearchResults($payload['data']['results'] ?? []);
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
        ]);
    }

    /**
     * @param array<int, array<string,mixed>> $results
     * @return array<int, array<string,mixed>>
     */
    private function annotateSearchResults(array $results): array
    {
        foreach ($results as &$result) {
            $excerpt = $result['excerpt'] ?? [];
            if (!is_array($excerpt)) {
                $excerpt = [];
            }
            $filePath = (string) ($result['file_path'] ?? '');
            $language = (string) ($result['languages'][0] ?? $result['language'] ?? '');
            $result['excerptRows'] = $this->formatExcerptRows((string) ($excerpt['content'] ?? ''), $language, $filePath);
        }
        unset($result);

        return $results;
    }
}
