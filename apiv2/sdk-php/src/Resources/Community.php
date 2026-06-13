<?php

declare(strict_types=1);

namespace Killerbite95\APIv2\Resources;

use Killerbite95\APIv2\Client;

/** Giveaways, Tags, RolesButtons and RoleSyncer. */
final class Community
{
    public function __construct(private readonly Client $client) {}

    // ─── Giveaways ───

    public function listGiveaways(string|int $guildId, bool $includeEnded = false, int $limit = 20, int $offset = 0): array
    {
        return $this->client->get("/guilds/$guildId/giveaways", [
            'ended'  => $includeEnded ? 'true' : 'false',
            'limit'  => $limit,
            'offset' => $offset,
        ]);
    }

    public function getGiveaway(string|int $guildId, string|int $messageId): array
    {
        return $this->client->get("/guilds/$guildId/giveaways/$messageId");
    }

    /**
     * @param array{
     *     channel_id: string|int,
     *     prize: string,
     *     duration_seconds: int,
     *     winners?: int,
     *     required_roles?: array<int,string|int>,
     *     blacklist_roles?: array<int,string|int>,
     *     cost?: int,
     *     min_join_days?: int,
     * } $config
     */
    public function createGiveaway(string|int $guildId, array $config): array
    {
        return $this->client->post("/guilds/$guildId/giveaways", $config);
    }

    public function endGiveaway(string|int $guildId, string|int $messageId): array
    {
        return $this->client->post("/guilds/$guildId/giveaways/$messageId/end");
    }

    public function rerollGiveaway(string|int $guildId, string|int $messageId, int $winners = 1): array
    {
        return $this->client->post("/guilds/$guildId/giveaways/$messageId/reroll", [
            'winners' => $winners,
        ]);
    }

    public function deleteGiveaway(string|int $guildId, string|int $messageId): array
    {
        return $this->client->delete("/guilds/$guildId/giveaways/$messageId");
    }

    // ─── Tags ───

    public function listTags(string|int $guildId, ?string $search = null, int $limit = 50, int $offset = 0): array
    {
        return $this->client->get("/guilds/$guildId/tags", [
            'search' => $search,
            'limit'  => $limit,
            'offset' => $offset,
        ]);
    }

    public function getTag(string|int $guildId, string $name): array
    {
        return $this->client->get("/guilds/$guildId/tags/" . rawurlencode($name));
    }

    /** @param array<int,string> $aliases */
    public function createTag(string|int $guildId, string $name, string $tagscript, array $aliases = []): array
    {
        return $this->client->post("/guilds/$guildId/tags", [
            'name'      => $name,
            'tagscript' => $tagscript,
            'aliases'   => $aliases,
        ]);
    }

    /** @param array{tagscript?:string,aliases?:array<int,string>} $changes */
    public function updateTag(string|int $guildId, string $name, array $changes): array
    {
        return $this->client->put("/guilds/$guildId/tags/" . rawurlencode($name), $changes);
    }

    public function deleteTag(string|int $guildId, string $name): array
    {
        return $this->client->delete("/guilds/$guildId/tags/" . rawurlencode($name));
    }

    /**
     * Invoke (run + send) a tag.
     *
     * @param array<string,string> $variables String values injected as TagScript variables
     */
    public function invokeTag(
        string|int $guildId,
        string $name,
        string|int $channelId,
        string|int|null $userId = null,
        array $variables = [],
    ): array {
        $payload = [
            'channel_id' => (string) $channelId,
            'user_id'    => $userId !== null ? (string) $userId : null,
            'variables'  => $variables,
        ];
        return $this->client->post("/guilds/$guildId/tags/" . rawurlencode($name) . '/invoke', $payload);
    }

    // ─── RolesButtons ───

    public function listRolesButtons(string|int $guildId): array
    {
        return $this->client->get("/guilds/$guildId/rolesbuttons");
    }

    public function getRolesButtons(string|int $guildId, string|int $channelId, string|int $messageId): array
    {
        return $this->client->get("/guilds/$guildId/rolesbuttons/$channelId/$messageId");
    }

    public function addRoleButton(
        string|int $guildId,
        string|int $channelId,
        string|int $messageId,
        string|int $roleId,
        ?string $emoji = null,
    ): array {
        return $this->client->post("/guilds/$guildId/rolesbuttons/$channelId/$messageId", [
            'role_id' => (string) $roleId,
            'emoji'   => $emoji,
        ]);
    }

    public function deleteRoleButton(
        string|int $guildId,
        string|int $channelId,
        string|int $messageId,
        string $buttonId,
    ): array {
        return $this->client->delete("/guilds/$guildId/rolesbuttons/$channelId/$messageId/" . rawurlencode($buttonId));
    }

    /** @param string $mode One of add_or_remove|add_only|remove_only|replace */
    public function setRolesButtonsMode(
        string|int $guildId,
        string|int $channelId,
        string|int $messageId,
        string $mode,
    ): array {
        return $this->client->patch("/guilds/$guildId/rolesbuttons/$channelId/$messageId/mode", [
            'mode' => $mode,
        ]);
    }

    // ─── RoleSyncer ───

    public function listRoleSyncer(string|int $guildId): array
    {
        return $this->client->get("/guilds/$guildId/rolesyncer");
    }

    public function addOneSync(string|int $guildId, string|int $role1Id, string|int $role2Id): array
    {
        return $this->client->post("/guilds/$guildId/rolesyncer/onesync", [
            'role1_id' => (string) $role1Id,
            'role2_id' => (string) $role2Id,
        ]);
    }

    public function addTwoSync(string|int $guildId, string|int $role1Id, string|int $role2Id): array
    {
        return $this->client->post("/guilds/$guildId/rolesyncer/twosync", [
            'role1_id' => (string) $role1Id,
            'role2_id' => (string) $role2Id,
        ]);
    }

    public function deleteOneSync(string|int $guildId, int $index): array
    {
        return $this->client->delete("/guilds/$guildId/rolesyncer/onesync/$index");
    }

    public function deleteTwoSync(string|int $guildId, int $index): array
    {
        return $this->client->delete("/guilds/$guildId/rolesyncer/twosync/$index");
    }
}
