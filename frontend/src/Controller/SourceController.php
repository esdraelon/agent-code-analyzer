<?php

declare(strict_types=1);

namespace App\Frontend\Controller;

use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;

final class SourceController extends AbstractController
{
    public function show(ServerRequestInterface $request, ResponseInterface $response): ResponseInterface
    {
        $query = $request->getQueryParams();
        $project = trim((string) ($query['project'] ?? ''));
        $filePath = trim((string) ($query['file_path'] ?? ''));
        $symbolName = trim((string) ($query['symbol_name'] ?? ''));
        $startLine = max(1, (int) ($query['start_line'] ?? 1));
        $endLine = max($startLine, (int) ($query['end_line'] ?? ($startLine + 199)));
        $summary = [];
        $excerpt = [
            'start_line' => $startLine,
            'end_line' => $endLine,
            'content' => '',
        ];
        $astImageDataUrl = '';
        $error = '';

        if ($project === '' || $filePath === '') {
            $error = 'Project and file path are required.';
        } else {
            try {
                $encodedFilePath = implode('/', array_map('rawurlencode', explode('/', $filePath)));
                $payload = $this->api->get('/api/projects/' . rawurlencode($project) . '/files/' . $encodedFilePath, [
                    'start_line' => $startLine,
                    'end_line' => $endLine,
                ]);
                $summary = $payload['data']['summary'] ?? [];
                $excerpt = $payload['data']['excerpt'] ?? $excerpt;
                if (!empty($summary['ast_svg'])) {
                    $astImageDataUrl = 'data:image/svg+xml;base64,' . base64_encode((string) $summary['ast_svg']);
                }
            } catch (\Throwable $throwable) {
                $error = $throwable->getMessage();
            }
        }

        $excerptRows = $this->formatExcerptRows((string) ($excerpt['content'] ?? ''), (string) ($summary['language'] ?? ''), $filePath);

        return $this->html($response, 'source', [
            'pageTitle' => $filePath !== '' ? $filePath . ' · Source' : 'Source',
            'project' => $project,
            'filePath' => $filePath,
            'symbolName' => $symbolName,
            'startLine' => $startLine,
            'endLine' => $endLine,
            'summary' => $summary,
            'excerpt' => $excerpt,
            'astImageDataUrl' => $astImageDataUrl,
            'error' => $error,
            'excerptRows' => $excerptRows,
            'activePage' => 'search',
        ]);
    }

    /**
     * @return array<int, array{line_no:string, html:string}>
     */
    private function formatExcerptRows(string $content, string $language, string $filePath): array
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

    private function highlightPhpLine(string $lineText): string
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

    private function wrapSyntaxToken(string $text, string $class): string
    {
        return '<span class="tok-' . $class . '">' . $this->escapeHtml($text) . '</span>';
    }

    private function escapeHtml(string $value): string
    {
        return htmlspecialchars($value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
    }
}
