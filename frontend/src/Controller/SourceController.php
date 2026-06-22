<?php

declare(strict_types=1);

namespace App\Frontend\Controller;

use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;

final class SourceController extends AbstractController
{
    public function show(ServerRequestInterface $request, ResponseInterface $response): ResponseInterface
    {
        $query = $request->getQueryParams();
        $project = trim((string) ($query['project'] ?? ''));
        $filePath = trim((string) ($query['file_path'] ?? ''));
        $symbolName = trim((string) ($query['symbol_name'] ?? ''));
        $startLine = max(1, (int) ($query['start_line'] ?? 1));
        $endLine = max($startLine, (int) ($query['end_line'] ?? ($startLine + 199)));
        $summary = [];
        $excerpt = [
            'start_line' => $startLine,
            'end_line' => $endLine,
            'content' => '',
        ];
        $astImageDataUrl = '';
        $error = '';

        if ($project === '' || $filePath === '') {
            $error = 'Project and file path are required.';
        } else {
            try {
                $encodedFilePath = implode('/', array_map('rawurlencode', explode('/', $filePath)));
                $payload = $this->api->get('/api/projects/' . rawurlencode($project) . '/files/' . $encodedFilePath, [
                    'start_line' => $startLine,
                    'end_line' => $endLine,
                ]);
                $summary = $payload['data']['summary'] ?? [];
                $excerpt = $payload['data']['excerpt'] ?? $excerpt;
                if (!empty($summary['ast_svg'])) {
                    $astImageDataUrl = 'data:image/svg+xml;base64,' . base64_encode((string) $summary['ast_svg']);
                }
            } catch (\Throwable $throwable) {
                $error = $throwable->getMessage();
            }
        }

        $excerptRows = $this->formatExcerptRows((string) ($excerpt['content'] ?? ''), (string) ($summary['language'] ?? ''), $filePath);

        return $this->html($response, 'source', [
            'pageTitle' => $filePath !== '' ? $filePath . ' · Source' : 'Source',
            'project' => $project,
            'filePath' => $filePath,
            'symbolName' => $symbolName,
            'startLine' => $startLine,
            'endLine' => $endLine,
            'summary' => $summary,
            'excerpt' => $excerpt,
            'astImageDataUrl' => $astImageDataUrl,
            'error' => $error,
            'excerptRows' => $excerptRows,
            'activePage' => 'search',
        ]);
    }
}
