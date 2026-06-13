<?php

declare(strict_types=1);

namespace Killerbite95\APIv2;

use Killerbite95\APIv2\Resources\ColaCoins;
use Killerbite95\APIv2\Resources\Community;
use Killerbite95\APIv2\Resources\Core;
use Killerbite95\APIv2\Resources\Economy;
use Killerbite95\APIv2\Resources\GameServers;
use Killerbite95\APIv2\Resources\Members;
use Killerbite95\APIv2\Resources\Messaging;
use Killerbite95\APIv2\Resources\Moderation;
use Killerbite95\APIv2\Resources\Suggestions;
use Killerbite95\APIv2\Resources\Tickets;
use Killerbite95\APIv2\Resources\Utilities;
use Killerbite95\APIv2\Resources\Warnings;
use Killerbite95\APIv2\Resources\Webhooks;

/**
 * APIv2 HTTP client.
 *
 * Example:
 *   $api = new Client('https://trini.alienhost.ovh', 'sk-xxxx');
 *   $health = $api->core()->health();
 *   $api->messaging()->sendMessage($guildId, $channelId, ['content' => 'Hi']);
 */
final class Client
{
    private const PREFIX = '/api/v2';

    private string $baseUrl;
    private ?string $apiKey;

    private int $timeout;
    private int $connectTimeout;
    private int $maxRetries;
    private bool $autoRetryOnRateLimit;
    private bool $verifySsl;
    private string $userAgent;

    private ?Core $core = null;
    private ?Members $members = null;
    private ?Moderation $moderation = null;
    private ?Messaging $messaging = null;
    private ?Tickets $tickets = null;
    private ?Suggestions $suggestions = null;
    private ?GameServers $gameServers = null;
    private ?Economy $economy = null;
    private ?Warnings $warnings = null;
    private ?Community $community = null;
    private ?Utilities $utilities = null;
    private ?ColaCoins $colaCoins = null;
    private ?Webhooks $webhooks = null;

    /**
     * @param string      $baseUrl Full base URL of the bot host (e.g. https://trini.alienhost.ovh)
     *                             The /api/v2 prefix is appended automatically.
     * @param string|null $apiKey  Bearer token. May be null to call public endpoints only (health, docs).
     * @param array{
     *     timeout?: int,
     *     connect_timeout?: int,
     *     max_retries?: int,
     *     auto_retry_on_rate_limit?: bool,
     *     verify_ssl?: bool,
     *     user_agent?: string,
     * } $options
     */
    public function __construct(string $baseUrl, ?string $apiKey = null, array $options = [])
    {
        $this->baseUrl = rtrim($baseUrl, '/');
        $this->apiKey = $apiKey;
        $this->timeout = $options['timeout'] ?? 30;
        $this->connectTimeout = $options['connect_timeout'] ?? 5;
        $this->maxRetries = max(0, $options['max_retries'] ?? 2);
        $this->autoRetryOnRateLimit = $options['auto_retry_on_rate_limit'] ?? false;
        $this->verifySsl = $options['verify_ssl'] ?? true;
        $this->userAgent = $options['user_agent'] ?? 'killerbite95-apiv2-php/1.0';
    }

    public function setApiKey(?string $apiKey): void
    {
        $this->apiKey = $apiKey;
    }

    // ─────────────── resource accessors ───────────────

    public function core(): Core
    {
        return $this->core ??= new Core($this);
    }

    public function members(): Members
    {
        return $this->members ??= new Members($this);
    }

    public function moderation(): Moderation
    {
        return $this->moderation ??= new Moderation($this);
    }

    public function messaging(): Messaging
    {
        return $this->messaging ??= new Messaging($this);
    }

    public function tickets(): Tickets
    {
        return $this->tickets ??= new Tickets($this);
    }

    public function suggestions(): Suggestions
    {
        return $this->suggestions ??= new Suggestions($this);
    }

    public function gameServers(): GameServers
    {
        return $this->gameServers ??= new GameServers($this);
    }

    public function economy(): Economy
    {
        return $this->economy ??= new Economy($this);
    }

    public function warnings(): Warnings
    {
        return $this->warnings ??= new Warnings($this);
    }

    public function community(): Community
    {
        return $this->community ??= new Community($this);
    }

    public function utilities(): Utilities
    {
        return $this->utilities ??= new Utilities($this);
    }

    public function colaCoins(): ColaCoins
    {
        return $this->colaCoins ??= new ColaCoins($this);
    }

    public function webhooks(): Webhooks
    {
        return $this->webhooks ??= new Webhooks($this);
    }

    // ─────────────── HTTP verbs (generic) ───────────────

    public function get(string $path, array $query = []): mixed
    {
        return $this->request('GET', $path, query: $query);
    }

    public function post(string $path, ?array $body = null, array $query = []): mixed
    {
        return $this->request('POST', $path, body: $body, query: $query);
    }

    public function put(string $path, ?array $body = null, array $query = []): mixed
    {
        return $this->request('PUT', $path, body: $body, query: $query);
    }

    public function patch(string $path, ?array $body = null, array $query = []): mixed
    {
        return $this->request('PATCH', $path, body: $body, query: $query);
    }

    public function delete(string $path, ?array $body = null, array $query = []): mixed
    {
        return $this->request('DELETE', $path, body: $body, query: $query);
    }

    /**
     * Perform an HTTP request and decode the JSON response.
     *
     * @return mixed Decoded JSON (associative array, scalar, or null on empty body).
     *
     * @throws ApiException
     * @throws RateLimitException
     */
    public function request(
        string $method,
        string $path,
        ?array $body = null,
        array $query = [],
        array $extraHeaders = [],
    ): mixed {
        $url = $this->buildUrl($path, $query);
        $payload = null;
        $headers = [
            'Accept: application/json',
            'User-Agent: ' . $this->userAgent,
        ];

        if ($this->apiKey !== null && $this->apiKey !== '') {
            $headers[] = 'Authorization: Bearer ' . $this->apiKey;
        }

        if ($body !== null) {
            $payload = json_encode($body, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
            if ($payload === false) {
                throw new ApiException(
                    'Failed to encode request body as JSON: ' . json_last_error_msg(),
                    method: $method,
                    path: $path,
                );
            }
            $headers[] = 'Content-Type: application/json';
        }

        foreach ($extraHeaders as $header) {
            $headers[] = $header;
        }

        $attempt = 0;
        while (true) {
            $attempt++;
            [$status, $rawBody, $responseHeaders, $curlErr] = $this->execute($method, $url, $headers, $payload);

            if ($curlErr !== null) {
                if ($attempt <= $this->maxRetries && $this->isTransient($curlErr)) {
                    usleep(200_000 * $attempt);
                    continue;
                }
                throw new ApiException(
                    'HTTP transport error: ' . $curlErr,
                    method: $method,
                    path: $path,
                );
            }

            $decoded = $this->decodeBody($rawBody);

            if ($status >= 200 && $status < 300) {
                return $decoded;
            }

            if ($status === 429) {
                $retryAfter = $this->parseRetryAfter($responseHeaders);
                if ($this->autoRetryOnRateLimit && $attempt <= $this->maxRetries) {
                    sleep(max(1, $retryAfter));
                    continue;
                }
                throw new RateLimitException(
                    message: is_array($decoded) ? ($decoded['message'] ?? 'Rate limit exceeded') : 'Rate limit exceeded',
                    retryAfter: $retryAfter,
                    response: is_array($decoded) ? $decoded : null,
                    method: $method,
                    path: $path,
                );
            }

            if ($status >= 500 && $status < 600 && $attempt <= $this->maxRetries) {
                usleep(300_000 * $attempt);
                continue;
            }

            $errorCode = is_array($decoded) ? ($decoded['error'] ?? 'http_error') : 'http_error';
            $message = is_array($decoded) ? ($decoded['message'] ?? $rawBody) : ($rawBody !== '' ? $rawBody : "HTTP $status");
            throw new ApiException(
                message: (string) $message,
                statusCode: $status,
                errorCode: (string) $errorCode,
                response: is_array($decoded) ? $decoded : null,
                method: $method,
                path: $path,
            );
        }
    }

    // ─────────────── internals ───────────────

    private function buildUrl(string $path, array $query): string
    {
        $path = '/' . ltrim($path, '/');
        if (!str_starts_with($path, self::PREFIX)) {
            $path = self::PREFIX . $path;
        }
        $url = $this->baseUrl . $path;
        if (!empty($query)) {
            $filtered = array_filter($query, static fn ($v) => $v !== null);
            if (!empty($filtered)) {
                $url .= '?' . http_build_query($filtered);
            }
        }
        return $url;
    }

    /**
     * @return array{0:int,1:string,2:array<string,string>,3:?string} [status, body, headers, curlError]
     */
    private function execute(string $method, string $url, array $headers, ?string $payload): array
    {
        $ch = curl_init();
        $responseHeaders = [];

        curl_setopt_array($ch, [
            CURLOPT_URL => $url,
            CURLOPT_CUSTOMREQUEST => $method,
            CURLOPT_HTTPHEADER => $headers,
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT => $this->timeout,
            CURLOPT_CONNECTTIMEOUT => $this->connectTimeout,
            CURLOPT_SSL_VERIFYPEER => $this->verifySsl,
            CURLOPT_SSL_VERIFYHOST => $this->verifySsl ? 2 : 0,
            CURLOPT_FOLLOWLOCATION => false,
            CURLOPT_HEADERFUNCTION => static function ($_ch, string $header) use (&$responseHeaders): int {
                $len = strlen($header);
                $parts = explode(':', $header, 2);
                if (count($parts) === 2) {
                    $responseHeaders[strtolower(trim($parts[0]))] = trim($parts[1]);
                }
                return $len;
            },
        ]);

        if ($payload !== null) {
            curl_setopt($ch, CURLOPT_POSTFIELDS, $payload);
        }

        $body = curl_exec($ch);
        $status = (int) curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
        $err = curl_errno($ch) !== 0 ? curl_error($ch) : null;
        curl_close($ch);

        return [$status, is_string($body) ? $body : '', $responseHeaders, $err];
    }

    private function decodeBody(string $body): mixed
    {
        if ($body === '') {
            return null;
        }
        $decoded = json_decode($body, true);
        if (json_last_error() !== JSON_ERROR_NONE) {
            return $body;
        }
        return $decoded;
    }

    private function parseRetryAfter(array $headers): int
    {
        $value = $headers['retry-after'] ?? null;
        if ($value === null) {
            return 60;
        }
        return max(1, (int) $value);
    }

    private function isTransient(string $curlError): bool
    {
        $needles = ['timed out', 'Could not resolve host', 'Connection reset', 'Empty reply', 'Connection refused'];
        foreach ($needles as $needle) {
            if (stripos($curlError, $needle) !== false) {
                return true;
            }
        }
        return false;
    }
}
