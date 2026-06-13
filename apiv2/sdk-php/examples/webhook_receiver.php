<?php

declare(strict_types=1);

/**
 * Webhook receiver: validate the bot's HMAC-SHA256 signature
 * and react to events (member_join, member_ban, message, etc.).
 *
 * Drop this file on a publicly reachable URL, then register it with:
 *   [p]apiv2 webhook create mysite https://your-site.example/webhook member_join message
 */

require __DIR__ . '/../autoload.php';

use Killerbite95\APIv2\WebhookVerifier;

$secret = getenv('APIV2_WEBHOOK_SECRET') ?: '';
$body   = file_get_contents('php://input') ?: '';
$sig    = $_SERVER['HTTP_X_APIV2_SIGNATURE'] ?? '';

if ($secret === '' || !WebhookVerifier::verify($body, $sig, $secret)) {
    http_response_code(401);
    echo json_encode(['error' => 'invalid_signature']);
    return;
}

$event = json_decode($body, true);
if (!is_array($event)) {
    http_response_code(400);
    echo json_encode(['error' => 'invalid_payload']);
    return;
}

$type = $event['event'] ?? 'unknown';

switch ($type) {
    case 'member_join':
        // $event['data']['user']['id'], $event['data']['guild_id'], ...
        error_log("[APIv2] Member joined: " . ($event['data']['user']['username'] ?? '?'));
        break;
    case 'member_ban':
        error_log("[APIv2] Banned: " . ($event['data']['user']['username'] ?? '?'));
        break;
    case 'message':
        // ignore bot's own messages, log everything else
        $author = $event['data']['author']['username'] ?? '?';
        $text   = $event['data']['content'] ?? '';
        error_log("[APIv2] #{$event['data']['channel_name']} <$author> $text");
        break;
    default:
        error_log("[APIv2] Unhandled event: $type");
}

http_response_code(204);
