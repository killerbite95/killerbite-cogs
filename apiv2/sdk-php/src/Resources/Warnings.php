<?php

declare(strict_types=1);

namespace Killerbite95\APIv2\Resources;

use Killerbite95\APIv2\Client;

/**
 * Warnings (Red Mod), modlog cases, Security cog and ExtendedModLog.
 */
final class Warnings
{
    public function __construct(private readonly Client $client) {}

    // ─── Warnings (Red Mod) ───

    public function list(string|int $guildId, string|int $userId): array
    {
        return $this->client->get("/guilds/$guildId/warnings/$userId");
    }

    public function add(
        string|int $guildId,
        string|int $userId,
        string $reason,
        string|int|null $moderatorId = null,
        int $weight = 1,
    ): array {
        return $this->client->post("/guilds/$guildId/warnings/$userId", [
            'reason'       => $reason,
            'moderator_id' => $moderatorId !== null ? (string) $moderatorId : null,
            'weight'       => $weight,
        ]);
    }

    public function delete(string|int $guildId, string|int $userId, string $warningId): array
    {
        return $this->client->delete("/guilds/$guildId/warnings/$userId/" . rawurlencode($warningId));
    }

    public function clear(string|int $guildId, string|int $userId): array
    {
        return $this->client->delete("/guilds/$guildId/warnings/$userId", ['confirm' => true]);
    }

    // ─── Red modlog cases ───

    public function listCases(string|int $guildId, ?string $type = null, int $limit = 20, int $offset = 0): array
    {
        return $this->client->get("/guilds/$guildId/cases", [
            'type'   => $type,
            'limit'  => $limit,
            'offset' => $offset,
        ]);
    }

    public function getCase(string|int $guildId, int $caseNumber): array
    {
        return $this->client->get("/guilds/$guildId/cases/$caseNumber");
    }

    // ─── Security cog ───

    public function securitySettings(string|int $guildId): array
    {
        return $this->client->get("/guilds/$guildId/security/settings");
    }

    public function updateSecuritySettings(string|int $guildId, array $changes): array
    {
        return $this->client->patch("/guilds/$guildId/security/settings", $changes);
    }

    public function listSecurityModules(string|int $guildId): array
    {
        return $this->client->get("/guilds/$guildId/security/modules");
    }

    public function updateSecurityModule(string|int $guildId, string $module, array $changes): array
    {
        return $this->client->patch("/guilds/$guildId/security/modules/" . rawurlencode($module), $changes);
    }

    public function listQuarantined(string|int $guildId): array
    {
        return $this->client->get("/guilds/$guildId/security/quarantined");
    }

    public function quarantine(string|int $guildId, string|int $userId, ?string $reason = null): array
    {
        return $this->client->post("/guilds/$guildId/security/quarantine/$userId", [
            'reason' => $reason,
        ]);
    }

    public function unquarantine(string|int $guildId, string|int $userId, ?string $reason = null): array
    {
        return $this->client->delete("/guilds/$guildId/security/quarantine/$userId", [
            'reason' => $reason,
        ]);
    }

    /** @param string $objectType member|role|channel */
    public function getWhitelist(string|int $guildId, string $objectType, string|int $objectId): array
    {
        return $this->client->get("/guilds/$guildId/security/whitelist/$objectType/$objectId");
    }

    public function updateWhitelist(
        string|int $guildId,
        string $objectType,
        string|int $objectId,
        array $whitelist,
    ): array {
        return $this->client->patch(
            "/guilds/$guildId/security/whitelist/$objectType/$objectId",
            $whitelist,
        );
    }

    // ─── ExtendedModLog ───

    public function modlogSettings(string|int $guildId): array
    {
        return $this->client->get("/guilds/$guildId/modlog/settings");
    }

    public function updateModlogSettings(string|int $guildId, array $changes): array
    {
        return $this->client->patch("/guilds/$guildId/modlog/settings", $changes);
    }

    public function listIgnoredChannels(string|int $guildId): array
    {
        return $this->client->get("/guilds/$guildId/modlog/ignored-channels");
    }

    public function addIgnoredChannel(string|int $guildId, string|int $channelId): array
    {
        return $this->client->post("/guilds/$guildId/modlog/ignored-channels", [
            'channel_id' => (string) $channelId,
        ]);
    }

    public function removeIgnoredChannel(string|int $guildId, string|int $channelId): array
    {
        return $this->client->delete("/guilds/$guildId/modlog/ignored-channels/$channelId");
    }
}
