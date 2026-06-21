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
        $scopeType = trim((string) ($query['scope_type'] ?? ''));
        $limit = (int) ($query['limit'] ?? 10);
        $results = [];
        $apiQuery = [];
        $error = '';

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
                    'limit' => $limit,
                ];
                $apiQuery = array_filter($apiQuery, static fn (mixed $value): bool => $value !== null && $value !== '');
                $payload = $this->api->get('/api/search/' . rawurlencode($mode), $apiQuery);
                $results = $payload['data']['results'] ?? [];
            }
        } catch (\Throwable $throwable) {
            $error = $throwable->getMessage();
        }

        return $this->html($response, 'search', [
            'pageTitle' => 'Search',
            'mode' => $mode,
            'project' => $project,
            'query' => $searchQuery,
            'filePath' => $filePath,
            'scopeType' => $scopeType,
            'limit' => $limit,
            'results' => $results,
            'error' => $error,
            'activePage' => 'search',
        ]);
    }
}
