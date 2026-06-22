<?php

declare(strict_types=1);

namespace App\Frontend\Controller;

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
