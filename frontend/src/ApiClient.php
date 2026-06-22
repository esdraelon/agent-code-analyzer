<?php

declare(strict_types=1);

namespace App\Frontend;

use RuntimeException;

final class ApiClient
{
    public function __construct(
        private readonly Config $config,
        private readonly int $timeoutSeconds = 20,
    ) {
    }

    public function baseUrl(): string
    {
        return $this->config->apiBaseUrl;
    }

    /**
     * @return array{status:int, data:array<string,mixed>, raw:string}
     */
    public function get(string $path, array $query = []): array
    {
        return $this->request('GET', $path, $query, null);
    }

    /**
     * @return array{status:int, data:array<string,mixed>, raw:string}
     */
    public function post(string $path, array $payload = []): array
    {
        return $this->request('POST', $path, [], $payload);
    }

    /**
     * @return array{status:int, data:array<string,mixed>, raw:string}
     */
    public function delete(string $path): array
    {
        return $this->request('DELETE', $path, [], null);
    }

    /**
     * @return array{status:int, data:array<string,mixed>, raw:string}
     */
    private function request(string $method, string $path, array $query, ?array $payload): array
    {
        $url = $this->config->apiUrl($path);
        if ($query !== []) {
            $url .= '?' . http_build_query($query);
        }

        $headers = [
            'Accept: application/json',
        ];
        $options = [
            'http' => [
                'method' => $method,
                'timeout' => $this->timeoutSeconds,
                'ignore_errors' => true,
                'header' => implode("\r\n", $headers),
            ],
        ];

        if ($payload !== null) {
            $options['http']['header'] .= "\r\nContent-Type: application/json";
            $options['http']['content'] = json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
        }

        $context = stream_context_create($options);
        $raw = @file_get_contents($url, false, $context);
        $responseHeaders = $http_response_header ?? [];
        $status = $this->statusFromHeaders($responseHeaders);
        if ($raw === false) {
            throw new RuntimeException(sprintf('Request to %s failed', $url));
        }

        $decoded = json_decode($raw, true);
        if (!is_array($decoded)) {
            throw new RuntimeException(sprintf('Invalid JSON response from %s', $url));
        }

        if ($status >= 400) {
            $message = (string) ($decoded['error'] ?? $decoded['message'] ?? ('HTTP ' . $status));
            throw new RuntimeException($message);
        }

        return [
            'status' => $status,
            'data' => $decoded,
            'raw' => $raw,
        ];
    }

    /**
     * @param list<string> $headers
     */
    private function statusFromHeaders(array $headers): int
    {
        $statusLine = $headers[0] ?? '';
        if (preg_match('/^HTTP\/\S+\s+(\d{3})/', $statusLine, $matches) !== 1) {
            return 0;
        }

        return (int) $matches[1];
    }
}
