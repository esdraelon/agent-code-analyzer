<?php

declare(strict_types=1);

namespace App\Frontend\Controller;

use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;

final class ProjectController extends AbstractController
{
    private const PATHS_CACHE_TTL = 300;

    public function index(ServerRequestInterface $request, ResponseInterface $response): ResponseInterface
    {
        $message = (string) ($request->getQueryParams()['message'] ?? '');
        $error = '';

        return $this->html($response, 'projects', [
            'pageTitle' => 'Projects',
            'message' => $message,
            'error' => $error,
            'activePage' => 'projects',
        ]);
    }

    public function paths(ServerRequestInterface $request, ResponseInterface $response, array $args): ResponseInterface
    {
        $project = (string) ($args['project'] ?? '');
        $query = $request->getQueryParams();
        $kind = strtolower(trim((string) ($query['kind'] ?? 'all')));
        $prefix = trim(str_replace('\\', '/', (string) ($query['prefix'] ?? '')));
        $prefix = ltrim(rtrim($prefix, '/'), '/');
        $limit = max(1, min(100, (int) ($query['limit'] ?? 25)));

        if ($project === '') {
            return $this->json($response, ['ok' => false, 'error' => 'Project is required.'], 400);
        }

        if (mb_strlen($prefix) < 2) {
            return $this->json($response, [
                'ok' => true,
                'project' => $project,
                'kind' => $kind,
                'prefix' => $prefix,
                'paths' => [],
                'root_path' => null,
                'indexed_at' => null,
                'cached' => false,
            ]);
        }

        try {
            $status = $this->api->get('/api/projects/' . rawurlencode($project) . '/status');
        } catch (\Throwable $throwable) {
            return $this->json($response, ['ok' => false, 'error' => $throwable->getMessage()], 502);
        }

        $projectData = $status['data']['project'] ?? [];
        $rootPath = trim((string) ($projectData['root_path'] ?? ''));
        $indexedAt = trim((string) ($projectData['indexed_at'] ?? ''));
        $cacheKey = $this->pathsCacheKey($project, $kind, $prefix, $limit, $indexedAt);

        $cached = $this->cacheFetch($cacheKey);
        if (is_array($cached)) {
            $cached['cached'] = true;
            return $this->json($response, $cached, 200);
        }

        try {
            $payload = $this->api->get('/api/projects/' . rawurlencode($project) . '/paths', [
                'kind' => $kind,
                'prefix' => $prefix,
                'limit' => $limit,
            ]);
        } catch (\Throwable $throwable) {
            return $this->json($response, ['ok' => false, 'error' => $throwable->getMessage()], 502);
        }

        $body = $payload['data'];
        if (is_array($body) && ($body['ok'] ?? false) === true) {
            $body['root_path'] = $rootPath !== '' ? $rootPath : null;
            $body['indexed_at'] = $indexedAt !== '' ? $indexedAt : null;
            $body['cached'] = false;
            $this->cacheStore($cacheKey, $body, self::PATHS_CACHE_TTL);
        }

        return $this->json($response, $body, (int) ($payload['status'] ?? 200));
    }

    private function pathsCacheKey(string $project, string $kind, string $prefix, int $limit, string $indexedAt): string
    {
        return 'agent-code-analyzer:paths:' . sha1(implode('|', [$project, $kind, $prefix, (string) $limit, $indexedAt]));
    }

    private function cacheFetch(string $key): mixed
    {
        if (!$this->apcuAvailable()) {
            return null;
        }

        $success = false;
        $value = apcu_fetch($key, $success);
        return $success ? $value : null;
    }

    private function cacheStore(string $key, mixed $value, int $ttl): void
    {
        if (!$this->apcuAvailable()) {
            return;
        }

        apcu_store($key, $value, $ttl);
    }

    private function apcuAvailable(): bool
    {
        if (!function_exists('apcu_fetch') || !function_exists('apcu_store')) {
            return false;
        }

        return filter_var((string) ini_get('apc.enabled'), FILTER_VALIDATE_BOOLEAN);
    }

    public function show(ServerRequestInterface $request, ResponseInterface $response, array $args): ResponseInterface
    {
        $project = (string) ($args['project'] ?? '');
        $status = ['data' => ['project' => ['name' => $project]]];
        $jobs = ['data' => ['jobs' => []]];
        $error = '';

        try {
            $status = $this->api->get('/api/projects/' . rawurlencode($project) . '/status');
        } catch (\Throwable $throwable) {
            $error = $throwable->getMessage();
        }

        try {
            $jobs = $this->api->get('/api/projects/' . rawurlencode($project) . '/jobs');
        } catch (\Throwable $throwable) {
            $error = $error !== '' ? $error . ' · ' . $throwable->getMessage() : $throwable->getMessage();
        }

        return $this->html($response, 'project-detail', [
            'pageTitle' => $project . ' · Project',
            'projectName' => $project,
            'message' => (string) ($request->getQueryParams()['message'] ?? ''),
            'error' => $error,
            'activePage' => 'projects',
            'project' => $status['data']['project'] ?? [],
            'jobs' => $jobs['data']['jobs'] ?? [],
        ]);
    }

    public function projectsJson(ServerRequestInterface $request, ResponseInterface $response): ResponseInterface
    {
        try {
            $payload = $this->api->get('/api/projects');
        } catch (\Throwable $throwable) {
            return $this->json($response, ['ok' => false, 'error' => $throwable->getMessage()], 502);
        }

        return $this->json($response, $payload['data'], (int) ($payload['status'] ?? 200));
    }

    public function statusJson(ServerRequestInterface $request, ResponseInterface $response, array $args): ResponseInterface
    {
        $project = (string) ($args['project'] ?? '');
        try {
            $payload = $this->api->get('/api/projects/' . rawurlencode($project) . '/status');
        } catch (\Throwable $throwable) {
            return $this->json($response, ['ok' => false, 'error' => $throwable->getMessage()], 502);
        }

        return $this->json($response, $payload['data'], (int) ($payload['status'] ?? 200));
    }

    public function jobsJson(ServerRequestInterface $request, ResponseInterface $response, array $args): ResponseInterface
    {
        $project = (string) ($args['project'] ?? '');
        try {
            $payload = $this->api->get('/api/projects/' . rawurlencode($project) . '/jobs');
        } catch (\Throwable $throwable) {
            return $this->json($response, ['ok' => false, 'error' => $throwable->getMessage()], 502);
        }

        return $this->json($response, $payload['data'], (int) ($payload['status'] ?? 200));
    }

    public function create(ServerRequestInterface $request, ResponseInterface $response): ResponseInterface
    {
        $params = $this->bodyParams($request);
        $project = trim((string) ($params['name'] ?? ''));
        $rootPath = trim((string) ($params['root_path'] ?? ''));
        $mode = trim((string) ($params['mode'] ?? 'directory'));
        $description = trim((string) ($params['description'] ?? ''));

        if ($project === '' || $rootPath === '') {
            return $this->redirect($response, '/?message=' . rawurlencode('Project name and root path are required.'));
        }

        try {
            $result = $this->api->post('/api/projects', [
                'name' => $project,
                'root_path' => $rootPath,
                'mode' => $mode === '' ? 'directory' : $mode,
                'description' => $description,
            ]);
        } catch (\Throwable $throwable) {
            return $this->redirect($response, '/?message=' . rawurlencode($throwable->getMessage()));
        }

        $message = ((int) ($result['status'] ?? 0) === 202)
            ? 'Project created. Ingestion queued.'
            : 'Project created.';

        return $this->redirect($response, '/projects/' . rawurlencode($project) . '?message=' . rawurlencode($message));
    }

    public function createJson(ServerRequestInterface $request, ResponseInterface $response): ResponseInterface
    {
        $params = $this->bodyParams($request);
        $project = trim((string) ($params['name'] ?? ''));
        $rootPath = trim((string) ($params['root_path'] ?? ''));
        $mode = trim((string) ($params['mode'] ?? 'directory'));
        $description = trim((string) ($params['description'] ?? ''));

        if ($project === '' || $rootPath === '') {
            return $this->json($response, ['ok' => false, 'error' => 'Project name and root path are required.'], 400);
        }

        try {
            $payload = $this->api->post('/api/projects', [
                'name' => $project,
                'root_path' => $rootPath,
                'mode' => $mode === '' ? 'directory' : $mode,
                'description' => $description,
            ]);
        } catch (\Throwable $throwable) {
            return $this->json($response, ['ok' => false, 'error' => $throwable->getMessage()], 502);
        }

        return $this->json($response, $payload['data'], (int) ($payload['status'] ?? 200));
    }

    public function reingest(ServerRequestInterface $request, ResponseInterface $response, array $args): ResponseInterface
    {
        $project = (string) ($args['project'] ?? '');
        $params = $this->bodyParams($request);
        $mode = trim((string) ($params['mode'] ?? 'refresh'));
        $refresh = !in_array(strtolower((string) ($params['refresh'] ?? 'true')), ['0', 'false', 'no', 'off'], true);

        try {
            $this->api->post('/api/projects/' . rawurlencode($project) . '/reingest', [
                'mode' => $mode,
                'refresh' => $refresh,
            ]);
        } catch (\Throwable $throwable) {
            return $this->redirect($response, '/projects/' . rawurlencode($project) . '?message=' . rawurlencode($throwable->getMessage()));
        }

        return $this->redirect($response, '/projects/' . rawurlencode($project) . '?message=' . rawurlencode('Reingest queued.'));
    }

    public function reingestJson(ServerRequestInterface $request, ResponseInterface $response, array $args): ResponseInterface
    {
        $project = (string) ($args['project'] ?? '');
        $params = $this->bodyParams($request);
        $mode = trim((string) ($params['mode'] ?? 'refresh'));
        $refresh = !in_array(strtolower((string) ($params['refresh'] ?? 'true')), ['0', 'false', 'no', 'off'], true);

        try {
            $payload = $this->api->post('/api/projects/' . rawurlencode($project) . '/reingest', [
                'mode' => $mode,
                'refresh' => $refresh,
            ]);
        } catch (\Throwable $throwable) {
            return $this->json($response, ['ok' => false, 'error' => $throwable->getMessage()], 502);
        }

        return $this->json($response, $payload['data'], (int) ($payload['status'] ?? 200));
    }

    public function delete(ServerRequestInterface $request, ResponseInterface $response, array $args): ResponseInterface
    {
        $project = (string) ($args['project'] ?? '');

        try {
            $this->api->delete('/api/projects/' . rawurlencode($project));
        } catch (\Throwable $throwable) {
            return $this->redirect($response, '/projects?message=' . rawurlencode($throwable->getMessage()));
        }

        return $this->redirect($response, '/projects?message=' . rawurlencode(sprintf('Project %s removed.', $project)));
    }

    public function deleteJson(ServerRequestInterface $request, ResponseInterface $response, array $args): ResponseInterface
    {
        $project = (string) ($args['project'] ?? '');

        try {
            $payload = $this->api->delete('/api/projects/' . rawurlencode($project));
        } catch (\Throwable $throwable) {
            return $this->json($response, ['ok' => false, 'error' => $throwable->getMessage()], 502);
        }

        return $this->json($response, $payload['data'], (int) ($payload['status'] ?? 200));
    }
}
