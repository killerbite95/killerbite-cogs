<?php

declare(strict_types=1);

namespace Killerbite95\APIv2;

use RuntimeException;
use Throwable;

class ApiException extends RuntimeException
{
    public function __construct(
        string $message,
        public readonly int $statusCode = 0,
        public readonly string $errorCode = 'error',
        public readonly ?array $response = null,
        public readonly ?string $method = null,
        public readonly ?string $path = null,
        ?Throwable $previous = null,
    ) {
        parent::__construct($message, $statusCode, $previous);
    }

    public function isUnauthorized(): bool
    {
        return $this->statusCode === 401;
    }

    public function isForbidden(): bool
    {
        return $this->statusCode === 403;
    }

    public function isNotFound(): bool
    {
        return $this->statusCode === 404;
    }

    public function isValidationError(): bool
    {
        return $this->statusCode === 422;
    }

    public function isCogUnavailable(): bool
    {
        return $this->statusCode === 503;
    }
}
