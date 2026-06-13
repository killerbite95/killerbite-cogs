<?php

declare(strict_types=1);

namespace Killerbite95\APIv2\Resources;

use Killerbite95\APIv2\Client;

final class Webhooks
{
    public function __construct(private readonly Client $client) {}

    public function list(): array
    {
        return $this->client->get('/webhooks');
    }

    /**
     * @param array<int,string> $events e.g. ['member_join','member_ban','message']
     */
    public function create(string $name, string $url, array $events, string|int|null $guildId = null): array
    {
        return $this->client->post('/webhooks', [
            'name'     => $name,
            'url'      => $url,
            'events'   => $events,
            'guild_id' => $guildId,
        ]);
    }

    public function delete(string $name): array
    {
        return $this->client->delete('/webhooks/' . rawurlencode($name));
    }

    public function test(string $name): array
    {
        return $this->client->post('/webhooks/' . rawurlencode($name) . '/test');
    }
}
