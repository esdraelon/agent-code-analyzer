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
        $projects = [];
        $projectsError = '';
        $jobs = [];
        $jobsError = '';

        try {
            $projectsPayload = $this->api->get('/api/projects');
            $projects = $projectsPayload['data']['projects'] ?? [];
        } catch (\Throwable $throwable) {
            $projectsError = $throwable->getMessage();
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
            $jobs = [];
            $jobsError = $throwable->getMessage();
        }

        return $this->html($response, 'logs', [
            'pageTitle' => 'Jobs',
            'projects' => $projects,
            'selectedProject' => $selectedProject,
            'jobs' => $jobs,
            'error' => trim($projectsError . ($projectsError !== '' && $jobsError !== '' ? ' · ' : '') . $jobsError),
            'message' => (string) ($query['message'] ?? ''),
            'activePage' => 'logs',
        ]);
    }
}
