<?php

declare(strict_types=1);

namespace Killerbite95\APIv2\Resources;

use Killerbite95\APIv2\Client;

final class ColaCoins
{
    public function __construct(private readonly Client $client) {}

    public function getBalance(string|int $guildId, string|int $userId): array
    {
        return $this->client->get("/guilds/$guildId/colacoins/$userId");
    }

    public function setBalance(string|int $guildId, string|int $userId, int $balance): array
    {
        return $this->client->patch("/guilds/$guildId/colacoins/$userId", [
            'balance' => $balance,
        ]);
    }

    public function give(string|int $guildId, string|int $userId, int $amount): array
    {
        return $this->client->post("/guilds/$guildId/colacoins/$userId/give", [
            'amount' => $amount,
        ]);
    }

    public function remove(string|int $guildId, string|int $userId, int $amount): array
    {
        return $this->client->post("/guilds/$guildId/colacoins/$userId/remove", [
            'amount' => $amount,
        ]);
    }

    public function leaderboard(string|int $guildId, int $limit = 10, int $offset = 0): array
    {
        return $this->client->get("/guilds/$guildId/colacoins/leaderboard", [
            'limit'  => $limit,
            'offset' => $offset,
        ]);
    }

    public function settings(string|int $guildId): array
    {
        return $this->client->get("/guilds/$guildId/colacoins/settings");
    }
}
