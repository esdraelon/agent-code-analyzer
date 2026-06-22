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
     * @param array<string,mixed>|list<mixed> $data
     */
    protected function json(ResponseInterface $response, array $data, int $status = 200): ResponseInterface
    {
        $response->getBody()->write(json_encode($data, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE));

        return $response
            ->withStatus($status)
            ->withHeader('Content-Type', 'application/json; charset=utf-8');
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

    /**
     * @return array<int, array{line_no:string, html:string}>
     */
    protected function formatExcerptRows(string $content, string $language, string $filePath): array
    {
        if ($content === '') {
            return [];
        }

        $isPhp = strtolower($language) === 'php' || str_ends_with(strtolower($filePath), '.php');
        $rows = [];
        foreach (explode("\n", $content) as $line) {
            $lineNo = '';
            $lineText = $line;
            if (preg_match('/^(\d+):\s?(.*)$/', $line, $matches) === 1) {
                $lineNo = $matches[1];
                $lineText = $matches[2];
            }

            $rows[] = [
                'line_no' => $lineNo !== '' ? $lineNo : '·',
                'html' => $isPhp ? $this->highlightPhpLine($lineText) : $this->escapeHtml($lineText),
            ];
        }

        return $rows;
    }

    protected function highlightPhpLine(string $lineText): string
    {
        $tokens = token_get_all('<?php ' . $lineText);
        $html = '';
        $keywordNames = [
            'T_FUNCTION', 'T_CLASS', 'T_INTERFACE', 'T_TRAIT', 'T_ENUM', 'T_IF', 'T_ELSE', 'T_ELSEIF', 'T_ENDIF', 'T_FOR',
            'T_FOREACH', 'T_WHILE', 'T_DO', 'T_SWITCH', 'T_CASE', 'T_DEFAULT', 'T_RETURN', 'T_THROW', 'T_TRY', 'T_CATCH',
            'T_FINALLY', 'T_NEW', 'T_EXTENDS', 'T_IMPLEMENTS', 'T_PUBLIC', 'T_PROTECTED', 'T_PRIVATE', 'T_STATIC',
            'T_ABSTRACT', 'T_FINAL', 'T_READONLY', 'T_CONST', 'T_USE', 'T_NAMESPACE', 'T_INCLUDE', 'T_INCLUDE_ONCE',
            'T_REQUIRE', 'T_REQUIRE_ONCE', 'T_INSTANCEOF', 'T_AS', 'T_YIELD', 'T_FROM', 'T_MATCH', 'T_ECHO', 'T_PRINT',
        ];

        foreach ($tokens as $token) {
            if (!is_array($token)) {
                $html .= $this->wrapSyntaxToken($token, 'operator');
                continue;
            }

            [$id, $text] = $token;
            $tokenName = token_name($id);
            if ($tokenName === 'T_OPEN_TAG' || $tokenName === 'T_OPEN_TAG_WITH_ECHO') {
                continue;
            }

            $tokenType = match ($tokenName) {
                'T_COMMENT', 'T_DOC_COMMENT' => 'comment',
                'T_CONSTANT_ENCAPSED_STRING', 'T_ENCAPSED_AND_WHITESPACE' => 'string',
                'T_LNUMBER', 'T_DNUMBER' => 'number',
                'T_VARIABLE' => 'variable',
                default => in_array($tokenName, $keywordNames, true) ? 'keyword' : ($tokenName === 'T_STRING' ? 'ident' : 'operator'),
            };

            $html .= $this->wrapSyntaxToken($text, $tokenType);
        }

        return $html;
    }

    protected function wrapSyntaxToken(string $text, string $class): string
    {
        return '<span class="tok-' . $class . '">' . $this->escapeHtml($text) . '</span>';
    }

    protected function escapeHtml(string $value): string
    {
        return htmlspecialchars($value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
    }
}
