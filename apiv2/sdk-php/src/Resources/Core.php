<?php

declare(strict_types=1);

namespace Killerbite95\APIv2\Resources;

use Killerbite95\APIv2\Client;

final class Core
{
    public function __construct(private readonly Client $client) {}

    /** Public — no auth required. */
    public function health(): array
    {
        return $this->client->get('/health');
    }

    public function info(): array
    {
        return $this->client->get('/info');
    }

    /** @return array<int,array{id:string,name:string,member_count:?int,owner_id:string,icon_url:?string}> */
    public function listGuilds(): array
    {
        return $this->client->get('/guilds');
    }

    public function getGuild(string|int $guildId): array
    {
        return $this->client->get("/guilds/$guildId");
    }
}
