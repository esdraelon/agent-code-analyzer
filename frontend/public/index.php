<?php

declare(strict_types=1);

if (PHP_SAPI === 'cli-server') {
    $requestPath = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/';
    $staticFile = __DIR__ . $requestPath;
    if ($requestPath !== '/' && is_file($staticFile)) {
        return false;
    }
}

use App\Frontend\ApiClient;
use App\Frontend\Config;
use App\Frontend\Controller\LogController;
use App\Frontend\Controller\ProjectController;
use App\Frontend\Controller\SearchController;
use App\Frontend\Controller\SourceController;
use App\Frontend\TemplateRenderer;
use Slim\Factory\AppFactory;

require dirname(__DIR__) . '/vendor/autoload.php';

$config = Config::fromEnvironment();
$apiClient = new ApiClient($config);
$renderer = new TemplateRenderer(dirname(__DIR__) . '/templates', $config);

$projectController = new ProjectController($apiClient, $renderer);
$searchController = new SearchController($apiClient, $renderer);
$logController = new LogController($apiClient, $renderer);
$sourceController = new SourceController($apiClient, $renderer);

$app = AppFactory::create();
$app->addBodyParsingMiddleware();
$app->addRoutingMiddleware();
$app->addErrorMiddleware($config->debug, true, true);

$app->get('/', [$projectController, 'index']);
$app->get('/projects', [$projectController, 'index']);
$app->post('/projects/create', [$projectController, 'create']);
$app->get('/projects/{project}', [$projectController, 'show']);
$app->post('/projects/{project}/reingest', [$projectController, 'reingest']);
$app->post('/projects/{project}/offboard', [$projectController, 'delete']);
$app->get('/api/projects', [$projectController, 'projectsJson']);
$app->post('/api/projects', [$projectController, 'createJson']);
$app->get('/api/projects/{project}/status', [$projectController, 'statusJson']);
$app->get('/api/projects/{project}/jobs', [$projectController, 'jobsJson']);
$app->post('/api/projects/{project}/reingest', [$projectController, 'reingestJson']);
$app->delete('/api/projects/{project}', [$projectController, 'deleteJson']);
$app->get('/api/projects/{project}/paths', [$projectController, 'paths']);
$app->get('/search', [$searchController, 'index']);
$app->get('/source', [$sourceController, 'show']);
$app->get('/logs', [$logController, 'index']);
$app->get('/api/logs', [$logController, 'jobsJson']);

$app->run();
