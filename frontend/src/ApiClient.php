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

        $lastTransportError = null;
        foreach ($this->candidateBaseUrls() as $baseUrl) {
            $url = rtrim($baseUrl, '/') . '/' . ltrim($path, '/');
            if ($query !== []) {
                $url .= '?' . http_build_query($query);
            }

            $context = stream_context_create($options);
            $raw = @file_get_contents($url, false, $context);
            $responseHeaders = $http_response_header ?? [];
            $status = $this->statusFromHeaders($responseHeaders);
            if ($raw === false) {
                $lastTransportError = sprintf('Request to %s failed', $url);
                continue;
            }

            $decoded = json_decode($raw, true);
            if (!is_array($decoded)) {
                $lastTransportError = sprintf('Invalid JSON response from %s', $url);
                continue;
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

        throw new RuntimeException($lastTransportError ?? 'Request failed');
    }

    /**
     * @return list<string>
     */
    private function candidateBaseUrls(): array
    {
        $candidates = [$this->config->apiBaseUrl];
        $scheme = (string) (parse_url($this->config->apiBaseUrl, PHP_URL_SCHEME) ?: 'http');
        $port = parse_url($this->config->apiBaseUrl, PHP_URL_PORT);
        $host = (string) (parse_url($this->config->apiBaseUrl, PHP_URL_HOST) ?: '127.0.0.1');

        if (in_array($host, ['127.0.0.1', 'localhost'], true)) {
            $fallbackHosts = ['host.docker.internal', '172.17.0.1', $this->dockerGatewayAddress()];
            foreach ($fallbackHosts as $fallbackHost) {
                if ($fallbackHost === '' || $fallbackHost === $host) {
                    continue;
                }
                $candidate = $scheme . '://' . $fallbackHost;
                if ($port !== false && $port !== null) {
                    $candidate .= ':' . $port;
                }
                $candidates[] = $candidate;
            }
        }

        return array_values(array_unique($candidates));
    }

    private function dockerGatewayAddress(): string
    {
        $routeFile = '/proc/net/route';
        if (!is_readable($routeFile)) {
            return '';
        }

        $lines = @file($routeFile, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
        if (!is_array($lines)) {
            return '';
        }

        foreach (array_slice($lines, 1) as $line) {
            $parts = preg_split('/\s+/', trim($line));
            if (!is_array($parts) || count($parts) < 3) {
                continue;
            }

            if (($parts[1] ?? '') !== '00000000') {
                continue;
            }

            $gatewayHex = $parts[2] ?? '';
            if ($gatewayHex === '' || !ctype_xdigit($gatewayHex)) {
                continue;
            }

            $packed = @pack('V', hexdec($gatewayHex));
            if ($packed === false) {
                continue;
            }

            $address = @inet_ntop($packed);
            if (is_string($address) && $address !== '') {
                return $address;
            }
        }

        return '';
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
