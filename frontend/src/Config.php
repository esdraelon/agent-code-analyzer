<?php

declare(strict_types=1);

namespace App\Frontend;

final class Config
{
    public function __construct(
        public readonly string $appName,
        public readonly string $apiBaseUrl,
        public readonly bool $debug,
    ) {
    }

    public static function fromEnvironment(): self
    {
        $appName = self::env('APP_NAME', 'Introspect');
        $apiBaseUrl = rtrim(self::env('CONTROL_API_BASE_URL', 'http://127.0.0.1:8010'), '/');
        $debug = self::boolEnv('APP_DEBUG', false);

        return new self($appName, $apiBaseUrl, $debug);
    }

    public function apiUrl(string $path): string
    {
        return $this->apiBaseUrl . '/' . ltrim($path, '/');
    }

    private static function env(string $name, string $default): string
    {
        $value = getenv($name);
        if ($value === false || trim($value) === '') {
            return $default;
        }

        return trim($value);
    }

    private static function boolEnv(string $name, bool $default): bool
    {
        $value = getenv($name);
        if ($value === false || trim($value) === '') {
            return $default;
        }

        return !in_array(strtolower(trim($value)), ['0', 'false', 'no', 'off'], true);
    }
}
