<?php

declare(strict_types=1);

/**
 * Basic example: health check + send a message to a channel.
 * Run from CLI: php examples/basic.php
 */

require __DIR__ . '/../autoload.php';

use Killerbite95\APIv2\ApiException;
use Killerbite95\APIv2\Client;

$api = new Client(
    baseUrl: 'https://trini.alienhost.ovh',
    apiKey: getenv('APIV2_KEY') ?: 'your-api-key-here',
    options: [
        'timeout'                  => 15,
        'max_retries'              => 2,
        'auto_retry_on_rate_limit' => true,
    ],
);

try {
    $health = $api->core()->health();
    echo "Bot: {$health['bot']}, guilds: {$health['guilds']}, latency: {$health['latency_ms']}ms\n";

    $guildId   = '796742145121714227';
    $channelId = '987654321';

    $sent = $api->messaging()->sendMessage($guildId, $channelId, [
        'content' => 'Hello from PHP!',
        'embed'   => [
            'title'       => '🏆 Torneo finalizado',
            'description' => 'Ganador: **PlayerX**',
            'color'       => 0xFFCC00,
            'fields'      => [
                ['name' => 'Premio', 'value' => '1000 ColaCoins', 'inline' => true],
            ],
        ],
    ]);
    echo "Sent message {$sent['message_id']}\n";
} catch (ApiException $e) {
    fwrite(STDERR, sprintf(
        "[%d %s] %s\n",
        $e->statusCode,
        $e->errorCode,
        $e->getMessage(),
    ));
    exit(1);
}
