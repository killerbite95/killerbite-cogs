<?php

declare(strict_types=1);

/**
 * Moderation example: lookup member, assign role, warn, kick.
 */

require __DIR__ . '/../autoload.php';

use Killerbite95\APIv2\ApiException;
use Killerbite95\APIv2\Client;

$api = new Client('https://trini.alienhost.ovh', getenv('APIV2_KEY') ?: '');

$guildId = '796742145121714227';
$userId  = '258711926304014336';
$roleId  = '1234567890';

try {
    $member = $api->members()->get($guildId, $userId);
    echo "Found: {$member['display_name']}\n";

    $api->members()->addRole($guildId, $userId, $roleId);
    echo "Role assigned.\n";

    $warning = $api->warnings()->add($guildId, $userId, 'Spam in #general', moderatorId: 1, weight: 1);
    echo "Warning {$warning['id']} created.\n";

    $api->moderation()->timeout($guildId, $userId, 600, 'Cool off');
    echo "10-minute timeout applied.\n";
} catch (ApiException $e) {
    if ($e->isNotFound()) {
        fwrite(STDERR, "Member not in guild.\n");
        exit(2);
    }
    fwrite(STDERR, "API error [{$e->statusCode}]: {$e->getMessage()}\n");
    exit(1);
}
