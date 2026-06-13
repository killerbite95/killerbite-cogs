<?php

declare(strict_types=1);

namespace Killerbite95\APIv2\Resources;

use Killerbite95\APIv2\Client;

final class Members
{
    public function __construct(private readonly Client $client) {}

    /**
     * @return array{members:array<int,array>,count:int,total:?int}
     */
    public function list(string|int $guildId, int $limit = 100, int $after = 0): array
    {
        return $this->client->get("/guilds/$guildId/members", [
            'limit' => $limit,
            'after' => $after,
        ]);
    }

    public function get(string|int $guildId, string|int $userId): array
    {
        return $this->client->get("/guilds/$guildId/members/$userId");
    }

    /** Change nickname. Pass null to clear. */
    public function setNickname(string|int $guildId, string|int $userId, ?string $nickname): array
    {
        return $this->client->patch("/guilds/$guildId/members/$userId", ['nickname' => $nickname]);
    }

    // ─── roles ───

    public function listRoles(string|int $guildId): array
    {
        return $this->client->get("/guilds/$guildId/roles");
    }

    public function addRole(string|int $guildId, string|int $userId, string|int $roleId): array
    {
        return $this->client->put("/guilds/$guildId/members/$userId/roles/$roleId");
    }

    public function removeRole(string|int $guildId, string|int $userId, string|int $roleId): array
    {
        return $this->client->delete("/guilds/$guildId/members/$userId/roles/$roleId");
    }

    /**
     * Replace the member's manageable roles with exactly $roleIds.
     *
     * @param array<int,string|int> $roleIds
     */
    public function setRoles(string|int $guildId, string|int $userId, array $roleIds): array
    {
        return $this->client->post("/guilds/$guildId/members/$userId/roles", [
            'role_ids' => array_map(static fn ($id) => (int) $id, $roleIds),
        ]);
    }
}
