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
        $payload = $this->api->get('/api/projects');

        return $this->html($response, 'projects', [
            'pageTitle' => 'Projects',
            'projects' => $payload['data']['projects'] ?? [],
            'message' => $message,
            'activePage' => 'projects',
        ]);
    }

    public function show(ServerRequestInterface $request, ResponseInterface $response, array $args): ResponseInterface
    {
        $project = (string) ($args['project'] ?? '');
        $status = $this->api->get('/api/projects/' . rawurlencode($project) . '/status');
        $jobs = $this->api->get('/api/projects/' . rawurlencode($project) . '/jobs');

        return $this->html($response, 'project-detail', [
            'pageTitle' => $project . ' · Project',
            'project' => $status['data']['project'] ?? [],
            'jobs' => $jobs['data']['jobs'] ?? [],
            'message' => (string) ($request->getQueryParams()['message'] ?? ''),
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

        $this->api->post('/api/projects', [
            'name' => $project,
            'root_path' => $rootPath,
            'mode' => $mode === '' ? 'directory' : $mode,
            'description' => $description,
        ]);

        return $this->redirect($response, '/projects/' . rawurlencode($project) . '?message=' . rawurlencode('Project created.'));
    }

    public function reingest(ServerRequestInterface $request, ResponseInterface $response, array $args): ResponseInterface
    {
        $project = (string) ($args['project'] ?? '');
        $params = $this->bodyParams($request);
        $mode = trim((string) ($params['mode'] ?? 'refresh'));
        $refresh = !in_array(strtolower((string) ($params['refresh'] ?? 'true')), ['0', 'false', 'no', 'off'], true);

        $this->api->post('/api/projects/' . rawurlencode($project) . '/reingest', [
            'mode' => $mode,
            'refresh' => $refresh,
        ]);

        return $this->redirect($response, '/projects/' . rawurlencode($project) . '?message=' . rawurlencode('Reingest queued.'));
    }

    public function delete(ServerRequestInterface $request, ResponseInterface $response, array $args): ResponseInterface
    {
        $project = (string) ($args['project'] ?? '');
        $this->api->delete('/api/projects/' . rawurlencode($project));

        return $this->redirect($response, '/projects?message=' . rawurlencode(sprintf('Project %s removed.', $project)));
    }
}
