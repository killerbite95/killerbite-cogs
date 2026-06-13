<?php

declare(strict_types=1);

namespace Killerbite95\APIv2\Resources;

use Killerbite95\APIv2\Client;

final class Tickets
{
    public function __construct(private readonly Client $client) {}

    /**
     * @param string|null $status open, closed, etc. — null returns all
     */
    public function list(string|int $guildId, ?string $status = null, int $limit = 50, int $offset = 0): array
    {
        return $this->client->get("/guilds/$guildId/tickets", [
            'status' => $status,
            'limit'  => $limit,
            'offset' => $offset,
        ]);
    }

    public function get(string|int $guildId, string|int $channelId): array
    {
        return $this->client->get("/guilds/$guildId/tickets/$channelId");
    }

    public function listPanels(string|int $guildId): array
    {
        return $this->client->get("/guilds/$guildId/tickets/panels");
    }

    public function close(string|int $guildId, string|int $channelId, ?string $reason = null): array
    {
        return $this->client->post("/guilds/$guildId/tickets/$channelId/close", [
            'reason' => $reason,
        ]);
    }

    public function sendMessage(string|int $guildId, string|int $channelId, string $content): array
    {
        return $this->client->post("/guilds/$guildId/tickets/$channelId/message", [
            'content' => $content,
        ]);
    }
}
