<?php

declare(strict_types=1);

namespace Killerbite95\APIv2\Resources;

use Killerbite95\APIv2\Client;

final class Suggestions
{
    public const VALID_STATUSES = [
        'pending', 'in_review', 'planned', 'in_progress',
        'approved', 'implemented', 'denied', 'duplicate', 'wont_do',
    ];

    public function __construct(private readonly Client $client) {}

    public function list(string|int $guildId, ?string $status = null, int $limit = 50, int $offset = 0): array
    {
        return $this->client->get("/guilds/$guildId/suggestions", [
            'status' => $status,
            'limit'  => $limit,
            'offset' => $offset,
        ]);
    }

    public function get(string|int $guildId, int $suggestionId): array
    {
        return $this->client->get("/guilds/$guildId/suggestions/$suggestionId");
    }

    /**
     * Update a suggestion status.
     *
     * @param string      $status     One of self::VALID_STATUSES
     * @param string|null $reason     Optional reason shown publicly
     * @param int|null    $changedBy  Discord user ID of the staff member that triggered the change
     */
    public function update(
        string|int $guildId,
        int $suggestionId,
        string $status,
        ?string $reason = null,
        ?int $changedBy = null,
    ): array {
        return $this->client->patch("/guilds/$guildId/suggestions/$suggestionId", [
            'status'     => $status,
            'reason'     => $reason,
            'changed_by' => $changedBy ?? 0,
        ]);
    }
}
