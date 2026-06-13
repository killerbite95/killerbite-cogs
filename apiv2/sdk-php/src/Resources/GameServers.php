<?php

declare(strict_types=1);

namespace Killerbite95\APIv2\Resources;

use Killerbite95\APIv2\Client;

final class GameServers
{
    public function __construct(private readonly Client $client) {}

    public function list(string|int $guildId): array
    {
        return $this->client->get("/guilds/$guildId/game-servers");
    }

    /**
     * @param string $serverKey Format: ip:port (e.g. "1.2.3.4:27015")
     *                          Includes a `live` field with current online state.
     */
    public function get(string|int $guildId, string $serverKey): array
    {
        return $this->client->get("/guilds/$guildId/game-servers/" . rawurlencode($serverKey));
    }
}
