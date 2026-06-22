<?php

declare(strict_types=1);

namespace App\Frontend\Controller;

use FilesystemIterator;
use RecursiveDirectoryIterator;
use RecursiveIteratorIterator;
use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;

final class ProjectController extends AbstractController
{
    public function index(ServerRequestInterface $request, ResponseInterface $response): ResponseInterface
    {
        $message = (string) ($request->getQueryParams()['message'] ?? '');
        $projects = [];
        $error = '';

        try {
            $payload = $this->api->get('/api/projects');
            $projects = $payload['data']['projects'] ?? [];
        } catch (\Throwable $throwable) {
            $error = $throwable->getMessage();
        }

        return $this->html($response, 'projects', [
            'pageTitle' => 'Projects',
            'projects' => $projects,
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

        try {
            $status = $this->api->get('/api/projects/' . rawurlencode($project) . '/status');
        } catch (\Throwable $throwable) {
            return $this->json($response, ['ok' => false, 'error' => $throwable->getMessage()], 502);
        }

        $rootPath = trim((string) ($status['data']['project']['root_path'] ?? ''));
        if ($rootPath === '' || !is_dir($rootPath)) {
            return $this->json($response, ['ok' => false, 'error' => sprintf('Project root is unavailable: %s', $rootPath)], 502);
        }

        try {
            $paths = $this->collectPaths($rootPath, $prefix, $kind, $limit);
        } catch (\Throwable $throwable) {
            return $this->json($response, ['ok' => false, 'error' => $throwable->getMessage()], 502);
        }

        return $this->json($response, [
            'ok' => true,
            'project' => $project,
            'root_path' => $rootPath,
            'kind' => $kind,
            'prefix' => $prefix,
            'paths' => $paths,
        ]);
    }

    /**
     * @return list<string>
     */
    private function collectPaths(string $rootPath, string $prefix, string $kind, int $limit): array
    {
        $rootPath = rtrim($rootPath, DIRECTORY_SEPARATOR);
        $normalizedPrefix = trim(str_replace('\\', '/', $prefix), '/');
        $matches = [];

        $iterator = new RecursiveIteratorIterator(
            new RecursiveDirectoryIterator($rootPath, FilesystemIterator::SKIP_DOTS | FilesystemIterator::FOLLOW_SYMLINKS),
            RecursiveIteratorIterator::SELF_FIRST,
        );

        foreach ($iterator as $item) {
            /** @var string $absolutePath */
            $absolutePath = $item->getPathname();
            $relativePath = ltrim(str_replace('\\', '/', substr($absolutePath, strlen($rootPath))), '/');
            if ($relativePath === '') {
                continue;
            }
            if (preg_match('/(^|\/)\./', $relativePath) === 1) {
                continue;
            }
            if (!$this->pathMatchesPrefix($relativePath, $normalizedPrefix)) {
                continue;
            }
            if ($kind === 'directory' && !$item->isDir()) {
                continue;
            }
            if ($kind === 'file' && !$item->isFile()) {
                continue;
            }

            $matches[] = $item->isDir() ? $relativePath . '/' : $relativePath;
            if (count($matches) >= $limit * 8) {
                break;
            }
        }

        sort($matches, SORT_NATURAL | SORT_FLAG_CASE);

        if ($kind === 'directory') {
            $matches = array_values(array_filter($matches, static fn (string $path): bool => str_ends_with($path, '/')));
        } elseif ($kind === 'file') {
            $matches = array_values(array_filter($matches, static fn (string $path): bool => !str_ends_with($path, '/')));
        }

        return array_slice($matches, 0, $limit);
    }

    private function pathMatchesPrefix(string $relativePath, string $normalizedPrefix): bool
    {
        $relativePath = trim(str_replace('\\', '/', $relativePath), '/');
        $normalizedPrefix = strtolower(trim(str_replace('\\', '/', $normalizedPrefix), '/'));
        if ($normalizedPrefix === '') {
            return true;
        }

        $relativePathLower = strtolower($relativePath);
        if (str_starts_with($relativePathLower, $normalizedPrefix)) {
            return true;
        }

        if (str_contains($normalizedPrefix, '/')) {
            return false;
        }

        foreach (explode('/', $relativePathLower) as $segment) {
            if (str_starts_with($segment, $normalizedPrefix)) {
                return true;
            }

            foreach (preg_split('/[._-]+/', $segment) ?: [] as $token) {
                if ($token !== '' && str_starts_with($token, $normalizedPrefix)) {
                    return true;
                }
            }
        }

        return false;
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
            'project' => $status['data']['project'] ?? [],
            'jobs' => $jobs['data']['jobs'] ?? [],
            'message' => (string) ($request->getQueryParams()['message'] ?? ''),
            'error' => $error,
            'activePage' => 'projects',
        ]);
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
            $this->api->post('/api/projects', [
                'name' => $project,
                'root_path' => $rootPath,
                'mode' => $mode === '' ? 'directory' : $mode,
                'description' => $description,
            ]);
        } catch (\Throwable $throwable) {
            return $this->redirect($response, '/?message=' . rawurlencode($throwable->getMessage()));
        }

        return $this->redirect($response, '/projects/' . rawurlencode($project) . '?message=' . rawurlencode('Project created.'));
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
}
