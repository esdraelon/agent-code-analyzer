<?php

declare(strict_types=1);

namespace App\Frontend;

final class TemplateRenderer
{
    public function __construct(
        private readonly string $templatesDir,
        private readonly Config $config,
    ) {
    }

    /**
     * @param array<string,mixed> $data
     */
    public function renderPage(string $template, array $data = []): string
    {
        $body = $this->renderTemplate($template, $data);

        return $this->renderTemplate('layout', $data + [
            'content' => $body,
            'pageTitle' => $data['pageTitle'] ?? $this->config->appName,
            'appName' => $this->config->appName,
            'activePage' => $data['activePage'] ?? '',
        ]);
    }

    /**
     * @param array<string,mixed> $data
     */
    private function renderTemplate(string $template, array $data = []): string
    {
        $templateFile = rtrim($this->templatesDir, DIRECTORY_SEPARATOR) . DIRECTORY_SEPARATOR . $template . '.php';
        if (!is_file($templateFile)) {
            throw new \RuntimeException(sprintf('Template not found: %s', $templateFile));
        }

        $escape = static function (mixed $value): string {
            return htmlspecialchars((string) $value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
        };

        extract($data, EXTR_SKIP);
        ob_start();
        include $templateFile;

        return (string) ob_get_clean();
    }
}
