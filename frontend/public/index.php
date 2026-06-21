<?php

declare(strict_types=1);

use App\Frontend\ApiClient;
use App\Frontend\Config;
use App\Frontend\Controller\LogController;
use App\Frontend\Controller\ProjectController;
use App\Frontend\Controller\SearchController;
use App\Frontend\TemplateRenderer;
use Slim\Factory\AppFactory;

require dirname(__DIR__) . '/vendor/autoload.php';

$config = Config::fromEnvironment();
$apiClient = new ApiClient($config);
$renderer = new TemplateRenderer(dirname(__DIR__) . '/templates', $config);

$projectController = new ProjectController($apiClient, $renderer);
$searchController = new SearchController($apiClient, $renderer);
$logController = new LogController($apiClient, $renderer);

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
$app->get('/search', [$searchController, 'index']);
$app->get('/logs', [$logController, 'index']);

$app->run();
