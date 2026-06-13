<?php

declare(strict_types=1);

namespace Killerbite95\APIv2\Resources;

use Killerbite95\APIv2\Client;

/** Welcome, Sticky, VoiceLogs, AutoNick and Mover. */
final class Utilities
{
    public function __construct(private readonly Client $client) {}

    // ─── Welcome ───

    public function welcome(string|int $guildId): array
    {
        return $this->client->get("/guilds/$guildId/welcome");
    }

    /** @param array{enabled?:bool,channel?:?string} $changes */
    public function updateWelcome(string|int $guildId, array $changes): array
    {
        return $this->client->patch("/guilds/$guildId/welcome", $changes);
    }

    /** @param string $event join|leave|ban|unban */
    public function welcomeMessages(string|int $guildId, string $event): array
    {
        return $this->client->get("/guilds/$guildId/welcome/$event/messages");
    }

    public function addWelcomeMessage(string|int $guildId, string $event, string $content): array
    {
        return $this->client->post("/guilds/$guildId/welcome/$event/messages", [
            'content' => $content,
        ]);
    }

    public function deleteWelcomeMessage(string|int $guildId, string $event, int $index): array
    {
        return $this->client->delete("/guilds/$guildId/welcome/$event/messages/$index");
    }

    public function welcomeWhisper(string|int $guildId): array
    {
        return $this->client->get("/guilds/$guildId/welcome/join/whisper");
    }

    public function updateWelcomeWhisper(string|int $guildId, array $changes): array
    {
        return $this->client->patch("/guilds/$guildId/welcome/join/whisper", $changes);
    }

    // ─── Sticky ───

    public function listStickies(string|int $guildId): array
    {
        return $this->client->get("/guilds/$guildId/stickies");
    }

    public function getSticky(string|int $guildId, string|int $channelId): array
    {
        return $this->client->get("/guilds/$guildId/channels/$channelId/sticky");
    }

    public function setSticky(
        string|int $guildId,
        string|int $channelId,
        string $content,
        bool $headerEnabled = true,
    ): array {
        return $this->client->put("/guilds/$guildId/channels/$channelId/sticky", [
            'content'        => $content,
            'header_enabled' => $headerEnabled,
        ]);
    }

    public function deleteSticky(string|int $guildId, string|int $channelId): array
    {
        return $this->client->delete("/guilds/$guildId/channels/$channelId/sticky");
    }

    public function updateStickyHeader(string|int $guildId, string|int $channelId, bool $headerEnabled): array
    {
        return $this->client->patch("/guilds/$guildId/channels/$channelId/sticky", [
            'header_enabled' => $headerEnabled,
        ]);
    }

    // ─── VoiceLogs ───

    public function voiceLogsSettings(string|int $guildId): array
    {
        return $this->client->get("/guilds/$guildId/voicelogs/settings");
    }

    public function setVoiceLogsEnabled(string|int $guildId, bool $enabled): array
    {
        return $this->client->patch("/guilds/$guildId/voicelogs/settings", [
            'enabled' => $enabled,
        ]);
    }

    public function voiceLogsForUser(string|int $guildId, string|int $userId): array
    {
        return $this->client->get("/guilds/$guildId/voicelogs/users/$userId");
    }

    public function voiceLogsForChannel(string|int $guildId, string|int $channelId): array
    {
        return $this->client->get("/guilds/$guildId/voicelogs/channels/$channelId");
    }

    // ─── AutoNick ───

    public function autoNickSettings(string|int $guildId): array
    {
        return $this->client->get("/guilds/$guildId/autonick/settings");
    }

    /** @param array{channel?:?string,cooldown?:int} $changes */
    public function updateAutoNickSettings(string|int $guildId, array $changes): array
    {
        return $this->client->patch("/guilds/$guildId/autonick/settings", $changes);
    }

    /** Global forbidden-names list (not per-guild). */
    public function autoNickForbiddenNames(): array
    {
        return $this->client->get('/autonick/forbidden-names');
    }

    public function addAutoNickForbiddenName(string $word): array
    {
        return $this->client->post('/autonick/forbidden-names', ['word' => $word]);
    }

    public function deleteAutoNickForbiddenName(string $word): array
    {
        return $this->client->delete('/autonick/forbidden-names/' . rawurlencode($word));
    }

    // ─── Mover ───

    /**
     * Move every voice member from $sourceChannelId (or all voice channels if null)
     * to $targetChannelId.
     */
    public function massMove(
        string|int $guildId,
        string|int $targetChannelId,
        string|int|null $sourceChannelId = null,
    ): array {
        return $this->client->post("/guilds/$guildId/voice/massmove", [
            'target_channel_id' => (string) $targetChannelId,
            'source_channel_id' => $sourceChannelId !== null ? (string) $sourceChannelId : null,
        ]);
    }
}
