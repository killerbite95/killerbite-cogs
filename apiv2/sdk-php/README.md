# APIv2 PHP SDK

Cliente PHP para la API REST embebida del bot Red-DiscordBot **APIv2**.
Pensado para integrarse con webs en PHP que necesiten hablar con el bot: gestionar miembros, mandar embeds, mover tickets, leer sugerencias, manejar ColaCoins, etc.

- **PHP 8.1+**
- **Sin dependencias externas** — usa solo cURL y JSON, viene en cualquier hosting.
- Autoload PSR-4 vía Composer **o** `autoload.php` manual (sin Composer).
- Cobertura completa de los endpoints de [apiv2](../) en clases por categoría.
- Reintentos en errores 5xx y de red, espera opcional en `429`.
- Verificación HMAC-SHA256 para webhooks salientes.

---

## Instalación

### Con Composer

```bash
composer require killerbite95/apiv2-php
```

(Si todavía no está en Packagist, basta con un `repositories` apuntando a este directorio o al repo.)

### Sin Composer

Copia la carpeta `sdk-php/` a tu proyecto e incluye el autoload manual:

```php
require __DIR__ . '/sdk-php/autoload.php';
```

---

## Uso básico

```php
use Killerbite95\APIv2\Client;
use Killerbite95\APIv2\ApiException;
use Killerbite95\APIv2\RateLimitException;

$api = new Client(
    baseUrl: 'https://trini.alienhost.ovh',   // sin /api/v2 al final
    apiKey:  $_ENV['APIV2_KEY'],              // creada con [p]apiv2 key create
    options: [
        'timeout'                  => 15,
        'connect_timeout'          => 5,
        'max_retries'              => 2,
        'auto_retry_on_rate_limit' => true,   // duerme y reintenta en 429
        'verify_ssl'               => true,
    ],
);

try {
    $health = $api->core()->health();
    // ['status' => 'ok', 'bot' => 'Trini', 'guilds' => 2, ...]
} catch (RateLimitException $e) {
    echo "Espera $e->retryAfter segundos";
} catch (ApiException $e) {
    echo "Error {$e->statusCode}: {$e->getMessage()}";
}
```

El cliente añade automáticamente el prefijo `/api/v2` — pasa las rutas tal cual aparecen en la doc del cog.

---

## Recursos disponibles

| Accesor | Cubre | Cog requerido |
|---|---|---|
| `$api->core()` | health, info, guilds | — |
| `$api->members()` | miembros, roles, nickname | — |
| `$api->moderation()` | kick, ban, unban, timeout | — |
| `$api->messaging()` | canales, send message, reacciones | — |
| `$api->tickets()` | tickets, paneles | TicketsTrini |
| `$api->suggestions()` | sugerencias y cambios de estado | SimpleSuggestions |
| `$api->gameServers()` | estado de servidores | GameServerMonitor |
| `$api->economy()` | bank de Red + costes de comandos | — / ExtendedEconomy |
| `$api->warnings()` | warns, cases, security, modlog | Mod / Security / ExtendedModLog |
| `$api->community()` | giveaways, tags, rolesbuttons, rolesyncer | Giveaways / Tags / RolesButtons / RoleSyncer |
| `$api->utilities()` | welcome, sticky, voicelogs, autonick, mover | Cogs equivalentes |
| `$api->colaCoins()` | ColaCoins (custom) | ColaCoins |
| `$api->webhooks()` | gestionar webhooks salientes del bot | — |

Si un recurso necesita un cog que no está cargado, la API responde `503` y el SDK lanza `ApiException` con `isCogUnavailable() === true`.

---

## Ejemplos

### Mandar un embed

```php
$api->messaging()->sendMessage($guildId, $channelId, [
    'content' => 'Resultados del torneo:',
    'embed' => [
        'title'       => '🏆 Torneo finalizado',
        'description' => 'Ganador: **PlayerX**',
        'color'       => 0xFFCC00,
        'fields'      => [
            ['name' => 'Premio', 'value' => '1000 ColaCoins', 'inline' => true],
            ['name' => 'Fecha',  'value' => '2026-05-26',     'inline' => true],
        ],
        'footer' => ['text' => 'WildRhynos'],
    ],
]);
```

### Asignar un rol y ver si el usuario sigue en el server

```php
try {
    $member = $api->members()->get($guildId, $userId);
    $api->members()->addRole($guildId, $userId, $roleId);
} catch (ApiException $e) {
    if ($e->isNotFound()) {
        echo 'El usuario no está en el servidor';
    }
}
```

### Cambiar el estado de una sugerencia desde un panel web

```php
$api->suggestions()->update(
    guildId:      $guildId,
    suggestionId: 42,
    status:       'approved',
    reason:       'Implementado en v2.3',
    changedBy:    $loggedInUserDiscordId,
);
```

### Ranking de ColaCoins para mostrar en la web

```php
$top = $api->colaCoins()->leaderboard($guildId, limit: 10);
foreach ($top['leaderboard'] as $row) {
    printf("#%d  %-20s  %d %s\n", $row['rank'], $row['username'], $row['balance'], $top['emoji']);
}
```

### Crear un giveaway

```php
$gw = $api->community()->createGiveaway($guildId, [
    'channel_id'        => $announceChannelId,
    'prize'             => 'Nitro Classic',
    'duration_seconds'  => 86_400,
    'winners'           => 1,
    'required_roles'    => [$participantRoleId],
    'min_join_days'     => 7,
]);
echo $gw['message_id'];
```

### Ejecutar un tag con variables

```php
$api->community()->invokeTag(
    guildId:    $guildId,
    name:       'bienvenida',
    channelId:  $welcomeChannelId,
    userId:     $newMemberId,
    variables:  ['language' => 'es', 'tier' => 'gold'],
);
```

### Banco de Red

```php
$api->economy()->transfer($guildId, $fromUser, $toUser, 250);
$balance = $api->economy()->getBalance($guildId, $userId);
echo "Tienes {$balance['balance']} {$balance['currency']}";
```

### Mover a todos a una sala de voz

```php
$api->utilities()->massMove($guildId, targetChannelId: $newVoiceId);
```

---

## Endpoints "raw"

Si necesitas un endpoint que aún no tenga helper, puedes llamarlo directo:

```php
$res = $api->get('/guilds/123/custom-endpoint', ['foo' => 'bar']);
$api->post('/guilds/123/custom-action', ['payload' => true]);
```

El cliente expone `get`, `post`, `put`, `patch`, `delete` y un `request($method, $path, $body, $query, $extraHeaders)` general.

---

## Manejo de errores

Todas las llamadas pueden lanzar `Killerbite95\APIv2\ApiException`.
`RateLimitException` (subclase) se lanza específicamente en 429.

```php
try {
    $api->moderation()->ban($guildId, $userId, 'spam');
} catch (RateLimitException $e) {
    sleep($e->retryAfter);
} catch (ApiException $e) {
    match (true) {
        $e->isUnauthorized()     => /* renovar API key */,
        $e->isForbidden()        => /* el bot no tiene permisos */,
        $e->isNotFound()         => /* recurso inexistente */,
        $e->isValidationError()  => /* error 422 con detalles en $e->response */,
        $e->isCogUnavailable()   => /* el cog asociado no está cargado */,
        default                  => /* registrar y reintentar más tarde */,
    };
}
```

El cuerpo decodificado del error (estructura `{error, message, status}` definida por APIv2) queda disponible en `$e->response`.

---

## Webhooks salientes

El bot puede mandar eventos a una URL externa con HMAC firmado. Verifica la firma con `WebhookVerifier`:

```php
use Killerbite95\APIv2\WebhookVerifier;

$body = file_get_contents('php://input');
$sig  = $_SERVER['HTTP_X_APIV2_SIGNATURE'] ?? '';

if (!WebhookVerifier::verify($body, $sig, $_ENV['APIV2_WEBHOOK_SECRET'])) {
    http_response_code(401);
    exit;
}

$event = json_decode($body, true);
// $event['event'] = 'member_join' | 'member_remove' | 'member_ban' | 'member_unban' | 'message'
```

Ver `examples/webhook_receiver.php` para un esqueleto completo.

---

## Ejecutar los ejemplos

```bash
cd apiv2/sdk-php
APIV2_KEY=sk-xxxxxxxx php examples/basic.php
APIV2_KEY=sk-xxxxxxxx php examples/moderation.php
```

---

## Layout

```
sdk-php/
├── composer.json
├── autoload.php             ← carga manual sin Composer
├── README.md
├── src/
│   ├── Client.php           ← punto de entrada principal
│   ├── ApiException.php
│   ├── RateLimitException.php
│   ├── WebhookVerifier.php  ← HMAC-SHA256 para webhooks
│   └── Resources/
│       ├── Core.php
│       ├── Members.php
│       ├── Moderation.php
│       ├── Messaging.php
│       ├── Tickets.php
│       ├── Suggestions.php
│       ├── GameServers.php
│       ├── Economy.php
│       ├── Warnings.php
│       ├── Community.php
│       ├── Utilities.php
│       ├── ColaCoins.php
│       └── Webhooks.php
└── examples/
    ├── basic.php
    ├── moderation.php
    └── webhook_receiver.php
```
