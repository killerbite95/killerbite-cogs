# APIv2 — Cog REST API para Red-DiscordBot

## ¿Qué es esto?

Un cog para Red-DiscordBot que levanta un servidor HTTP embebido (aiohttp) dentro del proceso del bot, exponiendo una API REST autenticada que permite controlar el bot completo desde cualquier servicio externo (webs, scripts, automatizaciones, integraciones, etc.).

**Objetivo:** El bot debe ser 100% operable desde la API. Todo lo que se puede hacer desde Discord, se puede hacer desde HTTP.

---

## Arquitectura

```
WildRhynos.com / Script externo / cualquier cliente HTTP
      │
      │  HTTPS  →  Authorization: Bearer <API_KEY>
      ▼
nginx (reverse proxy, TLS)
      │
      │  HTTP interno
      ▼
APIv2 (aiohttp, puerto 8742) ◄── corre DENTRO del proceso del bot
      │
      │  acceso directo en el mismo event loop asyncio
      ▼
self.bot → guilds, members, roles, channels, cogs live
      │
      ├── TicketsTrini    (si está cargado)
      ├── Suggestions     (si está cargado)
      ├── GameServerMonitor (si está cargado)
      └── AutoNick, etc.  (auto-discovery)
```

### Principio clave

aiohttp ya es dependencia de Red-DiscordBot. El servidor HTTP del cog corre en el **mismo bucle asyncio** que el bot — acceso directo y sin overhead a todos los objetos live de Discord. Sin IPC, sin Redis, sin proceso separado.

---

## Entorno de producción

- **Python:** 3.11.2
- **discord.py:** 2.6.3
- **Red-DiscordBot:** 3.5.22
- **Puerto:** `8742` (por defecto, configurable)
- **Bind:** `127.0.0.1` por defecto — nginx hace el proxy público

---

## Viabilidad técnica: ✅ Alta

| Aspecto | Valoración | Notas |
|---|---|---|
| Compatibilidad con Red | ✅ Nativa | aiohttp ya está instalado; asyncio compartido |
| Acceso a datos del bot | ✅ Directo | `self.bot`, `guild.members`, `config`, etc. en tiempo real |
| No bloquea el bot | ✅ | aiohttp sirve requests async sin bloquear el event loop |
| Seguridad | ⚠️ Requiere cuidado | API key + HTTPS nginx + rate limiting |
| Auto-discovery de cogs | ✅ | Rutas se registran/eliminan según cogs cargados |
| Hot reload | ✅ | `cog_load`/`cog_unload` arrancan/apagan el servidor |
| Pruebas locales | ✅ | `curl` o Postman contra `localhost:8742` |

---

## Seguridad

### Autenticación: API Key única de owner
- Generada con `secrets.token_urlsafe(32)` al hacer `[p]apiv2 key create`
- Guardada en `config` de Red (sin cifrado adicional — Red ya protege su config)
- Enviada en header: `Authorization: Bearer <API_KEY>`
- Datos guardados por key: `nombre`, `creado_en`, `ultimo_uso`, `activo`
- Solo el owner del bot puede crear/revocar keys

### Medidas adicionales
- **Rate limiting en memoria**: 200 req/min por key (configurable)
- **Logs de acceso**: cada request → key, IP, método, endpoint, status, timestamp
- **Bind a 127.0.0.1**: nunca expuesto directo a internet — nginx hace TLS
- **Errores no propagan al bot**: todo el servidor en try/except aislado

---

## Arquitectura del cog

```
apiv2/
├── __init__.py       — entry point del cog
├── apiv2.py          — Cog principal, comandos, arranque/parada del servidor
├── server.py         — App aiohttp, middlewares (auth, logging, rate limit)
├── auth.py           — Validación de API keys
├── discovery.py      — Auto-discovery de cogs cargados y registro de rutas
├── routes/
│   ├── core.py       — /health, /info, /guilds, /members, /roles, /channels
│   ├── moderation.py — kick, ban, unban, timeout, nickname
│   ├── messaging.py  — enviar mensajes y embeds a canales
│   ├── tickets.py    — TicketsTrini (solo si está cargado)
│   ├── suggestions.py — Suggestions (solo si está cargado)
│   └── servers.py    — GameServerMonitor (solo si está cargado)
└── PLAN.md
```

### Auto-discovery de cogs

Al arrancar (y en cada `[p]reload`), el servidor recorre los cogs conocidos y registra sus rutas **solo si ese cog está cargado**:

```python
COG_ROUTE_MODULES = {
    "TicketsTrini":       "apiv2.routes.tickets",
    "SimpleSuggestions":  "apiv2.routes.suggestions",
    "GameServerMonitor":  "apiv2.routes.servers",
}

async def build_app(bot) -> web.Application:
    app = web.Application(middlewares=[auth_middleware, log_middleware])
    register_core_routes(app, bot)
    for cog_name, module_path in COG_ROUTE_MODULES.items():
        if bot.get_cog(cog_name):
            register_cog_routes(app, bot, module_path)
    return app
```

Si un cog no está cargado, sus endpoints devuelven `503 Service Unavailable` en lugar de no existir — así los clientes saben que el cog existe pero está caído.

---

## Endpoints completos

### Sistema

```
GET  /api/v2/health
→ { "status": "ok", "bot": "Trini", "guilds": 2, "latency_ms": 41, "uptime_s": 86400 }

GET  /api/v2/info
→ { "bot_id": "123", "name": "Trini", "red_version": "3.5.22",
    "cogs_loaded": ["TicketsTrini", "SimpleSuggestions", ...] }
```

### Guilds

```
GET  /api/v2/guilds
→ [{ "id", "name", "icon_url", "member_count", "owner_id" }, ...]

GET  /api/v2/guilds/{guild_id}
→ { "id", "name", "icon_url", "member_count", "owner_id",
    "channels": [...], "roles": [...] }
```

### Miembros

```
GET  /api/v2/guilds/{guild_id}/members?limit=100&after=0
→ Lista paginada de miembros

GET  /api/v2/guilds/{guild_id}/members/{user_id}
→ { "id", "username", "display_name", "avatar_url",
    "roles": [...], "joined_at", "is_bot" }

PATCH /api/v2/guilds/{guild_id}/members/{user_id}
Body: { "nickname": "NuevoNick" }
→ Cambia el nickname del miembro
```

### Roles

```
GET  /api/v2/guilds/{guild_id}/roles
→ Lista de todos los roles del servidor

PUT  /api/v2/guilds/{guild_id}/members/{user_id}/roles/{role_id}
→ Asigna el rol al miembro

DELETE /api/v2/guilds/{guild_id}/members/{user_id}/roles/{role_id}
→ Quita el rol al miembro

POST /api/v2/guilds/{guild_id}/members/{user_id}/roles
Body: { "role_ids": [123, 456] }
→ Establece exactamente estos roles (reemplaza los actuales gestionables)
```

### Moderación

```
POST /api/v2/guilds/{guild_id}/members/{user_id}/kick
Body: { "reason": "..." }

POST /api/v2/guilds/{guild_id}/members/{user_id}/ban
Body: { "reason": "...", "delete_message_days": 0 }

DELETE /api/v2/guilds/{guild_id}/bans/{user_id}
→ Desbanea al usuario

POST /api/v2/guilds/{guild_id}/members/{user_id}/timeout
Body: { "duration_seconds": 300, "reason": "..." }
→ Aplica timeout (mute temporal)

DELETE /api/v2/guilds/{guild_id}/members/{user_id}/timeout
→ Quita el timeout
```

### Canales y mensajes

```
GET  /api/v2/guilds/{guild_id}/channels
→ Lista de canales con tipo, categoría y permisos básicos

POST /api/v2/guilds/{guild_id}/channels/{channel_id}/messages
Body: { "content": "...", "embed": { "title": "...", "description": "...",
        "color": 0xFF0000, "fields": [...] } }
→ Envía un mensaje (content y/o embed)

POST /api/v2/guilds/{guild_id}/channels/{channel_id}/messages/{message_id}/react
Body: { "emoji": "✅" }
→ Añade una reacción a un mensaje
```

### TicketsTrini *(requiere cog cargado)*

```
GET  /api/v2/guilds/{guild_id}/tickets?status=open&limit=50&offset=0
→ Lista de tickets con filtros

GET  /api/v2/guilds/{guild_id}/tickets/{ticket_id}
→ { "id", "panel", "owner_id", "channel_id", "status",
    "created_at", "closed_at", "reason" }

POST /api/v2/guilds/{guild_id}/tickets/{ticket_id}/close
Body: { "reason": "Resuelto" }

POST /api/v2/guilds/{guild_id}/tickets/{ticket_id}/message
Body: { "content": "..." }
→ Envía un mensaje al canal del ticket como el bot

GET  /api/v2/guilds/{guild_id}/tickets/panels
→ Lista de paneles configurados
```

### Suggestions *(requiere cog cargado)*

```
GET  /api/v2/guilds/{guild_id}/suggestions?status=pending&limit=50&offset=0
→ Lista de sugerencias con filtros

GET  /api/v2/guilds/{guild_id}/suggestions/{id}
→ { "id", "content", "author_id", "status", "upvotes", "downvotes",
    "reason", "created_at", "history": [...] }

PATCH /api/v2/guilds/{guild_id}/suggestions/{id}
Body: { "status": "approved", "reason": "Implementado en v2.3" }
→ Cambia el estado (approved, denied, in_review, planned, implemented)
```

### GameServerMonitor *(requiere cog cargado)*

```
GET  /api/v2/guilds/{guild_id}/game-servers
→ Estado de todos los servidores del guild

GET  /api/v2/guilds/{guild_id}/game-servers/{server_key}
→ { "key", "name", "game", "ip", "port", "online",
    "players_current", "players_max", "map", "last_check" }
```

---

## Formato de errores estándar

Todos los errores usan el mismo formato:

```json
{
  "error": "not_found",
  "message": "Guild 123456 not found or bot is not a member",
  "status": 404
}
```

Códigos usados: `400 bad_request`, `401 unauthorized`, `403 forbidden`, `404 not_found`, `422 validation_error`, `429 rate_limited`, `503 cog_unavailable`, `500 internal_error`.

---

## Comandos del bot

```
[p]apiv2 key create <nombre>   — Genera una nueva API key
[p]apiv2 key list              — Lista todas las keys (nombre, fecha, último uso)
[p]apiv2 key revoke <nombre>   — Revoca una key
[p]apiv2 key show <nombre>     — Muestra el valor de la key (en DM, una vez)

[p]apiv2 set port <puerto>     — Cambia el puerto (default: 8742)
[p]apiv2 set host <host>       — Cambia el host (default: 127.0.0.1)
[p]apiv2 status                — Estado del servidor (corriendo/parado, uptime, req/min)
[p]apiv2 restart               — Reinicia el servidor HTTP
```

---

## Plan de implementación por fases

### Fase 1 — Núcleo funcional
- [ ] Cog base: arranca/apaga servidor aiohttp en `cog_load`/`cog_unload`
- [ ] Middleware de autenticación por API key
- [ ] Rate limiting en memoria (200 req/min por key)
- [ ] Logging de acceso
- [ ] Comandos: `key create`, `key list`, `key revoke`, `key show`, `status`
- [ ] Endpoints core: `/health`, `/info`
- [ ] Endpoints guilds: GET `/guilds`, GET `/guilds/{id}`

### Fase 2 — Control de miembros y roles
- [ ] GET/PATCH `/members`, GET `/members/{id}`
- [ ] PUT/DELETE `/members/{id}/roles/{role_id}`
- [ ] POST `/members/{id}/roles` (bulk)
- [ ] GET `/roles`
- [ ] PATCH `/members/{id}` (nickname)
- [ ] Moderación: kick, ban, unban, timeout

### Fase 3 — Canales, mensajes y cogs
- [ ] GET `/channels`
- [ ] POST `/channels/{id}/messages`
- [ ] TicketsTrini: listar, ver, cerrar, mensaje
- [ ] Suggestions: listar, ver, cambiar estado
- [ ] GameServerMonitor: estado de servidores

### Fase 4 — Robustez
- [ ] `[p]apiv2 set port/host` + restart
- [ ] Rate limiting configurable por key
- [ ] Respuestas de error estándar en todos los endpoints
- [ ] `/api/v2/info` con lista de endpoints disponibles (auto-generada)

### Fase 5 — Webhooks, extensibilidad y documentación
- [x] Webhooks salientes (bot llama a URL externa en eventos: member_join/remove/ban/unban, message)
- [x] Decorador `@api_route` para que cogs externos registren rutas propias (auto-discovery + hot reload)
- [x] Documentación OpenAPI/Swagger auto-generada (`/api/v2/docs`, `/api/v2/openapi.json`)

---

### Fase 6 — Economía (Red Bank + ExtendedEconomy) ✅

**Red bank (built-in `redbot.core.bank`)** — accesible sin cog adicional:

```
GET  /api/v2/guilds/{guild_id}/economy/currency
→ { "name": "Coins", "default_balance": 100, "max_balance": 999999 }

PATCH /api/v2/guilds/{guild_id}/economy/currency
Body: { "name": "Monedas", "default_balance": 200 }

GET  /api/v2/guilds/{guild_id}/economy/balance/{user_id}
→ { "user_id": "...", "balance": 1500, "currency": "Coins" }

PATCH /api/v2/guilds/{guild_id}/economy/balance/{user_id}
Body: { "balance": 5000, "reason": "Admin adjustment" }
→ Set balance to exact value

POST /api/v2/guilds/{guild_id}/economy/transfer
Body: { "from_user_id": "...", "to_user_id": "...", "amount": 100 }
→ Transfer credits between users

GET  /api/v2/guilds/{guild_id}/economy/leaderboard?limit=10&offset=0
→ [{ "rank": 1, "user_id": "...", "balance": 9999 }, ...]

POST /api/v2/guilds/{guild_id}/economy/prune
Body: { "confirm": true }
→ Remove bank accounts for users no longer in guild
```

**ExtendedEconomy** *(requiere cog cargado)*:

```
GET  /api/v2/guilds/{guild_id}/economy/costs
→ Lista de CommandCost configurados

POST /api/v2/guilds/{guild_id}/economy/costs
Body: { "command": "ping", "cost": 10, "level": "all",
        "prompt": "silent", "modifier": "static" }

PATCH /api/v2/guilds/{guild_id}/economy/costs/{command}
Body: { "cost": 20, "modifier": "exponential", "value": 2.0 }

DELETE /api/v2/guilds/{guild_id}/economy/costs/{command}

GET  /api/v2/guilds/{guild_id}/economy/log-channels
→ { "transfer_credits": "...", "set_balance": "...", ... }

PATCH /api/v2/guilds/{guild_id}/economy/log-channels
Body: { "transfer_credits": "channel_id", "set_balance": null }
```

---

### Fase 7 — Moderación avanzada (Warnings + Security + ExtendedModLog)

**Red Mod — Warnings** (built-in `redbot.core.modlog` + `Mod` cog):

```
GET  /api/v2/guilds/{guild_id}/warnings/{user_id}
→ Lista de avisos con { id, reason, moderator_id, created_at, weight }

POST /api/v2/guilds/{guild_id}/warnings/{user_id}
Body: { "reason": "Spam", "moderator_id": "...", "weight": 1 }
→ Añadir aviso (como hacen [p]warn)

DELETE /api/v2/guilds/{guild_id}/warnings/{user_id}/{warning_id}
→ Eliminar un aviso concreto

DELETE /api/v2/guilds/{guild_id}/warnings/{user_id}
Body: { "confirm": true }
→ Limpiar todos los avisos del usuario

GET  /api/v2/guilds/{guild_id}/cases?type=ban&limit=20&offset=0
→ Lista de modlog cases (ban, kick, warn, mute, etc.)

GET  /api/v2/guilds/{guild_id}/cases/{case_number}
→ { "case_number", "action_type", "user_id", "moderator_id",
    "reason", "created_at", "amended_by", "amended_reason" }
```

**Security** *(requiere cog cargado)*:

```
GET  /api/v2/guilds/{guild_id}/security/settings
→ { "quarantine_role", "modlog_channel", "modlog_ping_role" }

PATCH /api/v2/guilds/{guild_id}/security/settings
Body: { "quarantine_role": "role_id", "modlog_channel": "channel_id" }

GET  /api/v2/guilds/{guild_id}/security/modules
→ [{ "name": "anti_nuke", "enabled": true, "config": {...} }, ...]

PATCH /api/v2/guilds/{guild_id}/security/modules/{module}
Body: { "enabled": true, "config": { ... } }

GET  /api/v2/guilds/{guild_id}/security/quarantined
→ Lista de miembros en cuarentena con sus roles previos

POST /api/v2/guilds/{guild_id}/security/quarantine/{user_id}
Body: { "reason": "Sospechoso" }
→ Pone al usuario en cuarentena (quita roles, asigna quarantine_role)

DELETE /api/v2/guilds/{guild_id}/security/quarantine/{user_id}
→ Deshacer cuarentena (restaura roles anteriores)

GET  /api/v2/guilds/{guild_id}/security/whitelist/{object_type}/{object_id}
→ { "whitelist": { "anti_spam": true, "anti_links": false, ... } }

PATCH /api/v2/guilds/{guild_id}/security/whitelist/{object_type}/{object_id}
Body: { "anti_spam": true }
```

**ExtendedModLog** *(requiere cog cargado)*:

```
GET  /api/v2/guilds/{guild_id}/modlog/settings
→ Los 21 event configs: { event: { enabled, channel, colour, emoji, embed } }

PATCH /api/v2/guilds/{guild_id}/modlog/settings
Body: { "message_delete": { "enabled": true, "channel": "id", "bots": false } }
→ Update de uno o varios eventos de golpe

GET  /api/v2/guilds/{guild_id}/modlog/ignored-channels
→ ["channel_id_1", ...]

POST /api/v2/guilds/{guild_id}/modlog/ignored-channels
Body: { "channel_id": "..." }

DELETE /api/v2/guilds/{guild_id}/modlog/ignored-channels/{channel_id}
```

Eventos soportados (21): `message_edit`, `message_delete`, `user_change`, `role_change`, `role_create`, `role_delete`, `voice_change`, `user_join`, `user_left`, `channel_change`, `channel_create`, `channel_delete`, `thread_change`, `thread_create`, `thread_delete`, `guild_change`, `emoji_change`, `stickers_change`, `commands_used`, `invite_created`, `invite_deleted`

---

### Fase 8 — Contenido e interacción (Giveaways, Tags, RolesButtons, RoleSyncer)

**Giveaways** *(requiere cog cargado)*:

```
GET  /api/v2/guilds/{guild_id}/giveaways?ended=false&limit=20&offset=0
→ [{ "message_id", "channel_id", "prize", "endtime", "entrant_count",
     "winners": 1, "ended": false, "requirements": {...} }, ...]

GET  /api/v2/guilds/{guild_id}/giveaways/{message_id}
→ Detalle + lista completa de entrants

POST /api/v2/guilds/{guild_id}/giveaways
Body: { "channel_id": "...", "prize": "Nitro", "duration_seconds": 86400,
        "winners": 1, "required_roles": [], "blacklist_roles": [],
        "cost": null, "min_join_days": null }
→ Crea un giveaway nuevo en el canal indicado

POST /api/v2/guilds/{guild_id}/giveaways/{message_id}/end
→ Fuerza finalización inmediata y sortea ganador

POST /api/v2/guilds/{guild_id}/giveaways/{message_id}/reroll
Body: { "winners": 1 }
→ Re-sortea ganador de un giveaway finalizado

DELETE /api/v2/guilds/{guild_id}/giveaways/{message_id}
→ Cancela y elimina el giveaway
```

**Tags** *(requiere cog cargado)*:

```
GET  /api/v2/guilds/{guild_id}/tags?limit=50&offset=0&search=
→ [{ "name", "uses", "author_id", "created_at", "aliases": [] }, ...]

GET  /api/v2/guilds/{guild_id}/tags/{name}
→ { "name", "tagscript", "uses", "author_id", "created_at", "aliases" }

POST /api/v2/guilds/{guild_id}/tags
Body: { "name": "hola", "tagscript": "¡Hola {user}!", "aliases": [] }

PUT  /api/v2/guilds/{guild_id}/tags/{name}
Body: { "tagscript": "Nuevo contenido", "aliases": ["saludo"] }

DELETE /api/v2/guilds/{guild_id}/tags/{name}

POST /api/v2/guilds/{guild_id}/tags/{name}/invoke
Body: { "channel_id": "...", "user_id": "..." }
→ Ejecuta el tag en un canal como si lo invocase ese usuario
```

**RolesButtons** *(requiere cog cargado)*:

```
GET  /api/v2/guilds/{guild_id}/rolesbuttons
→ [{ "channel_id", "message_id", "mode", "buttons": [{ "id", "emoji", "role_id" }] }]

GET  /api/v2/guilds/{guild_id}/rolesbuttons/{channel_id}/{message_id}
→ Detalle de un mensaje: modo + lista de botones

POST /api/v2/guilds/{guild_id}/rolesbuttons/{channel_id}/{message_id}
Body: { "emoji": "🎮", "role_id": "..." }
→ Añade un botón al mensaje

DELETE /api/v2/guilds/{guild_id}/rolesbuttons/{channel_id}/{message_id}/{button_id}
→ Elimina un botón

PATCH /api/v2/guilds/{guild_id}/rolesbuttons/{channel_id}/{message_id}/mode
Body: { "mode": "single" }
→ Cambia el modo de asignación (single/multi)
```

**RoleSyncer** *(requiere cog cargado)*:

```
GET  /api/v2/guilds/{guild_id}/rolesyncer
→ { "onesync": [[role1, role2], ...], "twosync": [[role1, role2], ...] }

POST /api/v2/guilds/{guild_id}/rolesyncer/onesync
Body: { "role1_id": "...", "role2_id": "..." }
→ Añade regla: si role1 → role2

POST /api/v2/guilds/{guild_id}/rolesyncer/twosync
Body: { "role1_id": "...", "role2_id": "..." }
→ Añade regla bidireccional

DELETE /api/v2/guilds/{guild_id}/rolesyncer/onesync/{index}
DELETE /api/v2/guilds/{guild_id}/rolesyncer/twosync/{index}
```

---

### Fase 9 — Configuración y utilidades (Welcome, Sticky, VoiceLogs, AutoNick, Mover)

**Welcome** *(requiere cog cargado)*:

```
GET  /api/v2/guilds/{guild_id}/welcome
→ Config completa: { "enabled", "channel", events: { join, leave, ban, unban } }

PATCH /api/v2/guilds/{guild_id}/welcome
Body: { "enabled": true, "channel": "id" }

GET  /api/v2/guilds/{guild_id}/welcome/{event}/messages
→ Evento = join|leave|ban|unban: lista de plantillas

POST /api/v2/guilds/{guild_id}/welcome/{event}/messages
Body: { "content": "Bienvenido {mention} al servidor!" }

DELETE /api/v2/guilds/{guild_id}/welcome/{event}/messages/{index}

GET  /api/v2/guilds/{guild_id}/welcome/join/whisper
→ { "state": "dm", "message": "..." }

PATCH /api/v2/guilds/{guild_id}/welcome/join/whisper
Body: { "state": "dm", "message": "Bienvenido al servidor, {name}!" }
```

**Sticky** *(requiere cog cargado)*:

```
GET  /api/v2/guilds/{guild_id}/stickies
→ Lista de canales con sticky activo

GET  /api/v2/guilds/{guild_id}/channels/{channel_id}/sticky
→ { "content": "...", "header_enabled": true, "last_message_id": "..." }

PUT  /api/v2/guilds/{guild_id}/channels/{channel_id}/sticky
Body: { "content": "Mensaje permanente del canal", "header_enabled": true }

DELETE /api/v2/guilds/{guild_id}/channels/{channel_id}/sticky

PATCH /api/v2/guilds/{guild_id}/channels/{channel_id}/sticky
Body: { "header_enabled": false }
```

**VoiceLogs** *(requiere cog cargado)*:

```
GET  /api/v2/guilds/{guild_id}/voicelogs/settings
→ { "enabled": true }

PATCH /api/v2/guilds/{guild_id}/voicelogs/settings
Body: { "enabled": false }

GET  /api/v2/guilds/{guild_id}/voicelogs/users/{user_id}
→ [{ "channel_id", "channel_name", "joined_at", "left_at", "duration_s" }, ...]
Últimas 25 sesiones de voz del usuario

GET  /api/v2/guilds/{guild_id}/voicelogs/channels/{channel_id}
→ Actividad reciente en ese canal de voz (últimas entradas/salidas)
```

**AutoNick** *(requiere cog Killerbite95 cargado)*:

```
GET  /api/v2/guilds/{guild_id}/autonick/settings
→ { "channel": "channel_id", "cooldown": 60 }

PATCH /api/v2/guilds/{guild_id}/autonick/settings
Body: { "channel": "channel_id", "cooldown": 30 }

GET  /api/v2/autonick/forbidden-names
→ Lista global de palabras prohibidas

POST /api/v2/autonick/forbidden-names
Body: { "word": "ejemplo" }

DELETE /api/v2/autonick/forbidden-names/{word}
```

**Mover** *(requiere cog cargado)*:

```
POST /api/v2/guilds/{guild_id}/voice/massmove
Body: { "target_channel_id": "...", "source_channel_id": "..." }
→ Mueve todos los miembros de source a target
  source_channel_id es opcional: si no se envía, mueve desde todos los canales de voz
```

---

## Resumen de integraciones por fase

| Fase | Cogs | Endpoints nuevos |
|---|---|---|
| 6 | Red bank + ExtendedEconomy | 11 |
| 7 | Warnings/Modlog + Security + ExtendedModLog | 19 |
| 8 | Giveaways + Tags + RolesButtons + RoleSyncer | 20 |
| 9 | Welcome + Sticky + VoiceLogs + AutoNick + Mover | 17 |
| **Total** | **+10 cogs** | **+67 endpoints** |

---

## Configuración nginx (producción)

```nginx
location /api/v2/ {
    proxy_pass http://127.0.0.1:8742;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

La API queda accesible en `https://trini.alienhost.ovh/api/v2/`.

---

## Ejemplo de uso real

```bash
# Verificar si un usuario de Discord está en el servidor (WildRhynos login)
curl -H "Authorization: Bearer <KEY>" \
     https://trini.alienhost.ovh/api/v2/guilds/796742145121714227/members/258711926304014336

# Asignar rol "Participante Torneo" al usuario
curl -X PUT \
     -H "Authorization: Bearer <KEY>" \
     https://trini.alienhost.ovh/api/v2/guilds/796742145121714227/members/258711926304014336/roles/1234567890

# Enviar resultado del torneo al canal de anuncios
curl -X POST \
     -H "Authorization: Bearer <KEY>" \
     -H "Content-Type: application/json" \
     -d '{"embed": {"title": "🏆 Torneo finalizado", "description": "Ganador: **PlayerX**", "color": 16776960}}' \
     https://trini.alienhost.ovh/api/v2/guilds/796742145121714227/channels/987654321/messages

# Cambiar estado de sugerencia
curl -X PATCH \
     -H "Authorization: Bearer <KEY>" \
     -H "Content-Type: application/json" \
     -d '{"status": "approved", "reason": "Implementado en v2.3"}' \
     https://trini.alienhost.ovh/api/v2/guilds/796742145121714227/suggestions/42
```

---

## Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| API key comprometida | `[p]apiv2 key revoke` — efecto inmediato |
| DDoS | Rate limiting en middleware + nginx `limit_req` |
| El servidor crashea el bot | `try/except` aislado; errores del servidor no propagan al event loop |
| Puerto en conflicto | 8742 es inusual; además configurable con `[p]apiv2 set port` |
| Operación destructiva por error | Los endpoints destructivos requieren body explícito con `reason` |

---

## Conclusión

**Viabilidad: Alta.** Sin dependencias externas nuevas, integración limpia con Red, acceso directo a todos los datos live del bot. El objetivo es control total del bot desde HTTP — cualquier cosa que se pueda hacer desde Discord se pueda hacer desde la API.

**Primer paso al implementar:** `apiv2.py` + `auth.py` + comando `key create` + endpoint `/health` como smoke test.