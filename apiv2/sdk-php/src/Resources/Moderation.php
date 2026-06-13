<?php

declare(strict_types=1);

namespace Killerbite95\APIv2\Resources;

use Killerbite95\APIv2\Client;

final class Moderation
{
    public function __construct(private readonly Client $client) {}

    public function kick(string|int $guildId, string|int $userId, ?string $reason = null): array
    {
        return $this->client->post("/guilds/$guildId/members/$userId/kick", [
            'reason' => $reason,
        ]);
    }

    public function ban(
        string|int $guildId,
        string|int $userId,
        ?string $reason = null,
        int $deleteMessageDays = 0,
    ): array {
        return $this->client->post("/guilds/$guildId/members/$userId/ban", [
            'reason' => $reason,
            'delete_message_days' => $deleteMessageDays,
        ]);
    }

    public function unban(string|int $guildId, string|int $userId): array
    {
        return $this->client->delete("/guilds/$guildId/bans/$userId");
    }

    public function timeout(
        string|int $guildId,
        string|int $userId,
        int $durationSeconds,
        ?string $reason = null,
    ): array {
        return $this->client->post("/guilds/$guildId/members/$userId/timeout", [
            'duration_seconds' => $durationSeconds,
            'reason' => $reason,
        ]);
    }

    public function removeTimeout(string|int $guildId, string|int $userId): array
    {
        return $this->client->delete("/guilds/$guildId/members/$userId/timeout");
    }
}
