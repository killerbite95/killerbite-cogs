<?php

declare(strict_types=1);

namespace Killerbite95\APIv2;

class RateLimitException extends ApiException
{
    public function __construct(
        string $message,
        public readonly int $retryAfter,
        ?array $response = null,
        ?string $method = null,
        ?string $path = null,
    ) {
        parent::__construct(
            message: $message,
            statusCode: 429,
            errorCode: 'rate_limited',
            response: $response,
            method: $method,
            path: $path,
        );
    }
}
