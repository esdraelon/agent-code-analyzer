<?php

declare(strict_types=1);

namespace App\Frontend\Controller;

use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;

final class LogController extends AbstractController
{
    public function index(ServerRequestInterface $request, ResponseInterface $response): ResponseInterface
    {
        $query = $request->getQueryParams();
        $selectedProject = trim((string) ($query['project'] ?? ''));

        return $this->html($response, 'logs', [
            'pageTitle' => 'Jobs',
            'selectedProject' => $selectedProject,
            'message' => (string) ($query['message'] ?? ''),
            'error' => '',
            'activePage' => 'logs',
        ]);
    }

    public function jobsJson(ServerRequestInterface $request, ResponseInterface $response): ResponseInterface
    {
        $query = $request->getQueryParams();
        $selectedProject = trim((string) ($query['project'] ?? ''));
        $projects = [];
        $jobs = [];

        try {
            $projectsPayload = $this->api->get('/api/projects');
            $projects = $projectsPayload['data']['projects'] ?? [];
        } catch (\Throwable $throwable) {
            return $this->json($response, ['ok' => false, 'error' => $throwable->getMessage()], 502);
        }

        try {
            if ($selectedProject !== '') {
                $jobsPayload = $this->api->get('/api/projects/' . rawurlencode($selectedProject) . '/jobs');
                $jobs = $jobsPayload['data']['jobs'] ?? [];
            } else {
                foreach ($projects as $project) {
                    $projectName = (string) ($project['name'] ?? '');
                    if ($projectName === '') {
                        continue;
                    }
                    $jobsPayload = $this->api->get('/api/projects/' . rawurlencode($projectName) . '/jobs');
                    foreach (($jobsPayload['data']['jobs'] ?? []) as $job) {
                        $jobs[] = $job;
                    }
                }
            }
        } catch (\Throwable $throwable) {
            return $this->json($response, ['ok' => false, 'error' => $throwable->getMessage()], 502);
        }

        return $this->json($response, [
            'ok' => true,
            'projects' => $projects,
            'selectedProject' => $selectedProject,
            'jobs' => $jobs,
        ]);
    }
}
