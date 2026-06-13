<?php

declare(strict_types=1);

namespace Killerbite95\APIv2;

/**
 * Verify HMAC-SHA256 signatures sent by APIv2 outgoing webhooks.
 *
 * The bot sends the header `X-APIv2-Signature: sha256=<hex>` computed
 * from the raw request body using the secret returned by `webhook create`.
 *
 * Usage:
 *   $body = file_get_contents('php://input');
 *   $sig  = $_SERVER['HTTP_X_APIV2_SIGNATURE'] ?? '';
 *   if (!WebhookVerifier::verify($body, $sig, $secret)) { http_response_code(401); exit; }
 *   $event = json_decode($body, true);
 */
final class WebhookVerifier
{
    public static function sign(string $body, string $secret): string
    {
        return 'sha256=' . hash_hmac('sha256', $body, $secret);
    }

    public static function verify(string $body, string $signatureHeader, string $secret): bool
    {
        $expected = self::sign($body, $secret);
        return hash_equals($expected, $signatureHeader);
    }
}
