<?php

declare(strict_types=1);

namespace Killerbite95\APIv2\Resources;

use Killerbite95\APIv2\Client;

final class Economy
{
    public function __construct(private readonly Client $client) {}

    // ─── Red bank ───

    public function getCurrency(string|int $guildId): array
    {
        return $this->client->get("/guilds/$guildId/economy/currency");
    }

    /**
     * @param array{name?:string,default_balance?:int,max_balance?:int} $changes
     */
    public function updateCurrency(string|int $guildId, array $changes): array
    {
        return $this->client->patch("/guilds/$guildId/economy/currency", $changes);
    }

    public function getBalance(string|int $guildId, string|int $userId): array
    {
        return $this->client->get("/guilds/$guildId/economy/balance/$userId");
    }

    public function setBalance(string|int $guildId, string|int $userId, int $balance): array
    {
        return $this->client->patch("/guilds/$guildId/economy/balance/$userId", [
            'balance' => $balance,
        ]);
    }

    public function transfer(
        string|int $guildId,
        string|int $fromUserId,
        string|int $toUserId,
        int $amount,
    ): array {
        return $this->client->post("/guilds/$guildId/economy/transfer", [
            'from_user_id' => (string) $fromUserId,
            'to_user_id'   => (string) $toUserId,
            'amount'       => $amount,
        ]);
    }

    public function leaderboard(string|int $guildId, int $limit = 10, int $offset = 0): array
    {
        return $this->client->get("/guilds/$guildId/economy/leaderboard", [
            'limit'  => $limit,
            'offset' => $offset,
        ]);
    }

    public function prune(string|int $guildId): array
    {
        return $this->client->post("/guilds/$guildId/economy/prune", ['confirm' => true]);
    }

    // ─── ExtendedEconomy (command costs) ───

    public function listCosts(string|int $guildId): array
    {
        return $this->client->get("/guilds/$guildId/economy/costs");
    }

    /**
     * @param array{
     *     command:string,
     *     cost?:int,
     *     duration?:int,
     *     level?:string,
     *     prompt?:string,
     *     modifier?:string,
     *     value?:float,
     * } $cost
     */
    public function createCost(string|int $guildId, array $cost): array
    {
        return $this->client->post("/guilds/$guildId/economy/costs", $cost);
    }

    /** @param array<string,mixed> $changes */
    public function updateCost(string|int $guildId, string $command, array $changes): array
    {
        return $this->client->patch("/guilds/$guildId/economy/costs/" . rawurlencode($command), $changes);
    }

    public function deleteCost(string|int $guildId, string $command): array
    {
        return $this->client->delete("/guilds/$guildId/economy/costs/" . rawurlencode($command));
    }

    public function getLogChannels(string|int $guildId): array
    {
        return $this->client->get("/guilds/$guildId/economy/log-channels");
    }

    /** @param array<string,?string> $channelMap */
    public function updateLogChannels(string|int $guildId, array $channelMap): array
    {
        return $this->client->patch("/guilds/$guildId/economy/log-channels", $channelMap);
    }
}
