<?php

declare(strict_types=1);

namespace Killerbite95\APIv2\Resources;

use Killerbite95\APIv2\Client;

final class Messaging
{
    public function __construct(private readonly Client $client) {}

    public function listChannels(string|int $guildId): array
    {
        return $this->client->get("/guilds/$guildId/channels");
    }

    /**
     * Send a message (content and/or embed).
     *
     * @param array{
     *     content?: ?string,
     *     embed?: array{
     *         title?: ?string,
     *         description?: ?string,
     *         color?: ?int,
     *         url?: ?string,
     *         fields?: array<int,array{name:string,value:string,inline?:bool}>,
     *         footer?: array{text:string},
     *         thumbnail?: string,
     *         image?: string,
     *     },
     * } $payload
     */
    public function sendMessage(string|int $guildId, string|int $channelId, array $payload): array
    {
        return $this->client->post("/guilds/$guildId/channels/$channelId/messages", $payload);
    }

    /** Convenience helper for plain-content messages. */
    public function sendText(string|int $guildId, string|int $channelId, string $content): array
    {
        return $this->sendMessage($guildId, $channelId, ['content' => $content]);
    }

    /** Convenience helper for embed-only messages. */
    public function sendEmbed(string|int $guildId, string|int $channelId, array $embed): array
    {
        return $this->sendMessage($guildId, $channelId, ['embed' => $embed]);
    }

    public function addReaction(
        string|int $guildId,
        string|int $channelId,
        string|int $messageId,
        string $emoji,
    ): array {
        return $this->client->post(
            "/guilds/$guildId/channels/$channelId/messages/$messageId/react",
            ['emoji' => $emoji],
        );
    }
}
