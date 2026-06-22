<?php

declare(strict_types=1);

namespace App\Frontend\Controller;

use App\Frontend\ApiClient;
use App\Frontend\TemplateRenderer;
use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;

abstract class AbstractController
{
    public function __construct(
        protected readonly ApiClient $api,
        protected readonly TemplateRenderer $renderer,
    ) {
    }

    protected function html(ResponseInterface $response, string $template, array $data = [], int $status = 200): ResponseInterface
    {
        $response->getBody()->write($this->renderer->renderPage($template, $data));

        return $response
            ->withStatus($status)
            ->withHeader('Content-Type', 'text/html; charset=utf-8');
    }

    /**
     * @return array<string,mixed>
     */
    protected function bodyParams(ServerRequestInterface $request): array
    {
        $parsed = $request->getParsedBody();
        return is_array($parsed) ? $parsed : [];
    }

    protected function redirect(ResponseInterface $response, string $location): ResponseInterface
    {
        return $response->withStatus(303)->withHeader('Location', $location);
    }
}
