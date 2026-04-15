# APIv2 — Cog REST API para Red-DiscordBot

## ¿Qué es esto?

Un cog para Red-DiscordBot que levanta un servidor HTTP embebido (aiohttp) dentro del proceso del bot, exponiendo una API REST autenticada que permite ejecutar acciones del bot y de otros cogs desde cualquier servicio externo (webs, scripts, automatizaciones, integraciones, etc.) sin depender del Dashboard web.

---

## Contexto: arquitectura actual

```
Browser / Usuario
      │
      ▼
Dashboard-Trini (Flask, puerto 5000)
      │  WebSocket JSON-RPC
      ▼
Red-DiscordBot  ──►  Cog "Dashboard" (RPC bridge)
      │
      ▼
Cogs: TicketsTrini, Suggestions, AutoNick, etc.
```

El canal actual **solo funciona si el Dashboard está corriendo** y usa sesión de usuario (OAuth Discord). No hay forma de que un script externo, un webhook personalizado, una app móvil o un panel propio llame directamente al bot.

---

## Propuesta: APIv2

```
Cualquier cliente HTTP (script, web, app)
      │
      │  HTTP REST  API Key en header
      ▼
APIv2 (aiohttp, puerto 8080)  ◄── corre DENTRO del proceso del bot
      │
      │  acceso directo
      ▼
self.bot  →  guilds, members, channels, config de cogs
```

### Principio clave

aiohttp ya es una dependencia de Red-DiscordBot (lo usa para las peticiones HTTP del bot a Discord). El servidor HTTP del cog corre en el **mismo bucle asyncio** que el bot, por lo que tiene acceso directo y sin overhead a todos los objetos live de Discord.

---

## Viabilidad técnica: ✅ Alta

| Aspecto | Valoración | Notas |
|---|---|---|
| Compatibilidad con Red | ✅ Nativa | aiohttp ya está instalado; asyncio compartido |
| Acceso a datos del bot | ✅ Directo | `self.bot`, `guild.members`, `config`, etc. en tiempo real |
| No bloquea el bot | ✅ | aiohttp sirve requests async sin bloquear el event loop |
| Seguridad | ⚠️ Requiere cuidado | API keys, HTTPS por nginx, rate limiting necesario |
| Extensibilidad a otros cogs | ✅ | Decorador tipo `@api_route` que los cogs registran |
| Hot reload | ✅ Posible | `cog_load` / `cog_unload` arrancan/apagan el servidor |
| Pruebas locales | ✅ Simple | `curl` o Postman contra `localhost:8080` |

---

## Comparación con alternativas

### Opción A: Extender el RPC existente del Dashboard ❌
- Requiere que el Dashboard esté corriendo
- Ligado a sesión web / OAuth
- No diseñado para acceso externo programático

### Opción B: Servicio separado (FastAPI en otro proceso) ⚠️
- Necesita IPC (pipes, Redis, etc.)
- Más complejidad operacional
- No tiene acceso directo a objetos Discord live

### Opción C: aiohttp embebido en el cog ✅ **ELEGIDA**
- Sin dependencias nuevas
- Acceso directo y en tiempo real a todos los datos del bot  
- Se instala/desinstala con `[p]cog load/unload apiv2`
- Un solo proceso, un solo puerto adicional

---

## Seguridad

### Autenticación: API Keys
- Cada key se genera con `secrets.token_urlsafe(32)` y se guarda en `config` de Red (cifrada con Fernet)
- Se envía en el header: `Authorization: Bearer <API_KEY>`
- Keys tienen: nombre, scopes, creado_en, último_uso, activo/inactivo

### Scopes (permisos por key)
```
read:guilds        — info de servidores
read:members       — info de miembros
read:tickets       — leer tickets (TicketsTrini)
write:tickets      — cerrar/gestionar tickets
read:suggestions   — ver sugerencias
write:suggestions  — cambiar estado de sugerencias
read:servers       — monitor de servidores (GameServerMonitor)
send:messages      — enviar mensajes a canales
admin              — todo (solo para owner del bot)
```

### Otras medidas
- **Rate limiting**: configurable por key (ej. 100 req/min)
- **Whitelist de IPs**: opcional, configurable por key
- **HTTPS obligatorio en producción**: nginx como reverse proxy (igual que el Dashboard)
- **Logs de acceso**: cada request logueado con key, IP, endpoint, timestamp
- **No exponer en 0.0.0.0 por defecto**: bind a `127.0.0.1`, nginx hace el proxy

---

## Arquitectura del cog

```
apiv2/
├── __init__.py          — entry point del cog
├── apiv2.py             — Cog principal, arranca/apaga el servidor
├── server.py            — Configuración aiohttp, middlewares
├── auth.py              — Validación de API keys, rate limiting
├── router.py            — Registro dinámico de rutas desde otros cogs
├── routes/
│   ├── core.py          — Rutas base: /health, /info, /guilds
│   ├── tickets.py       — Rutas de TicketsTrini
│   ├── suggestions.py   — Rutas de Suggestions
│   ├── servers.py       — Rutas de GameServerMonitor
│   └── messaging.py     — Enviar mensajes a canales
└── PLAN.md              — Este archivo
```

---

## Endpoints propuestos (v1 del plan)

### Sistema

```
GET  /api/v2/health
→ { "status": "ok", "bot": "Trini", "guilds": 5, "latency_ms": 42 }

GET  /api/v2/info
→ { "bot_id": 123, "name": "Trini", "version": "1.0.0", "cogs": [...] }
```

### Servidores (guilds)

```
GET  /api/v2/guilds
→ Lista de servidores donde está el bot

GET  /api/v2/guilds/{guild_id}
→ Info del servidor (nombre, icono, miembros, canales)

GET  /api/v2/guilds/{guild_id}/members
→ Lista de miembros (paginada)

GET  /api/v2/guilds/{guild_id}/members/{user_id}
→ Info de un miembro específico
```

### Mensajes

```
POST /api/v2/guilds/{guild_id}/channels/{channel_id}/messages
Body: { "content": "Hola", "embed": {...} }
→ Envía un mensaje al canal
```

### TicketsTrini

```
GET  /api/v2/guilds/{guild_id}/tickets
→ Lista de tickets abiertos

GET  /api/v2/guilds/{guild_id}/tickets/{ticket_id}
→ Info de un ticket específico

POST /api/v2/guilds/{guild_id}/tickets/{ticket_id}/close
Body: { "reason": "Resuelto" }
→ Cierra el ticket

GET  /api/v2/guilds/{guild_id}/tickets/panels
→ Lista de paneles configurados
```

### Suggestions

```
GET  /api/v2/guilds/{guild_id}/suggestions
QueryParams: ?status=pending&limit=50&offset=0
→ Lista de sugerencias con filtros

GET  /api/v2/guilds/{guild_id}/suggestions/{id}
→ Info de una sugerencia

PATCH /api/v2/guilds/{guild_id}/suggestions/{id}
Body: { "status": "approved", "reason": "Muy buena idea" }
→ Cambia el estado de la sugerencia
```

### GameServerMonitor

```
GET  /api/v2/guilds/{guild_id}/game-servers
→ Estado de todos los servidores de juego del guild

GET  /api/v2/guilds/{guild_id}/game-servers/{server_key}
→ Estado detallado de un servidor específico
```

---

## Registro de rutas desde otros cogs (extensibilidad)

El diseño permite que cada cog registre sus propias rutas con un decorador, sin modificar el cog APIv2:

```python
# En ticketstrini/api_integration.py

class APIIntegration:
    async def cog_load(self):
        api_cog = self.bot.get_cog("APIv2")
        if api_cog:
            api_cog.router.register(self)

    @api_route(
        path="/guilds/{guild_id}/tickets",
        method="GET",
        scopes=["read:tickets"],
        description="Lista tickets abiertos"
    )
    async def api_get_tickets(self, request, guild_id: int):
        guild = self.bot.get_guild(guild_id)
        # ... lógica ...
        return web.json_response({"tickets": [...]})
```

---

## Plan de implementación por fases

### Fase 1 — Núcleo (esqueleto funcional)
- [ ] Cog base: arranca/apaga servidor aiohttp en `cog_load`/`cog_unload`
- [ ] Middleware de autenticación por API key
- [ ] Rate limiting básico (contador en memoria)
- [ ] Comandos de bot: `[p]apiv2 key create <nombre>`, `[p]apiv2 key list`, `[p]apiv2 key revoke <nombre>`
- [ ] Endopints core: `/health`, `/info`, `/guilds`
- [ ] Logging de acceso

### Fase 2 — Rutas de cogs existentes
- [ ] TicketsTrini: leer tickets, cerrar ticket
- [ ] Suggestions: listar, cambiar estado
- [ ] GameServerMonitor: estado de servidores
- [ ] Mensajes: enviar mensaje a canal

### Fase 3 — Robustez y seguridad
- [ ] Scopes granulares por key
- [ ] IP whitelist por key
- [ ] Rate limiting persistente (en config de Red)
- [ ] Respuestas de error estándar (RFC 7807 Problem Details)
- [ ] Documentación OpenAPI/Swagger automática (aiohttp-swagger)

### Fase 4 — Extensibilidad
- [ ] Decorador `@api_route` para que otros cogs registren sus rutas
- [ ] Webhooks salientes: el bot llama a una URL externa cuando ocurren eventos (ticket abierto, sugerencia nueva, etc.)

---

## Configuración nginx (producción)

```nginx
# Añadir a la config existente del dashboard
location /api/v2/ {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Así la API queda en `https://trini.alienhost.ovh/api/v2/` con HTTPS del mismo certificado.

---

## Ejemplo de uso real (cliente externo)

```bash
# Obtener estado de servidores de juego
curl -H "Authorization: Bearer mi_api_key_aqui" \
     https://trini.alienhost.ovh/api/v2/guilds/796742145121714227/game-servers

# Cerrar un ticket
curl -X POST \
     -H "Authorization: Bearer mi_api_key_aqui" \
     -H "Content-Type: application/json" \
     -d '{"reason": "Resuelto por admin web"}' \
     https://trini.alienhost.ovh/api/v2/guilds/796742145121714227/tickets/1234/close

# Aprobar sugerencia
curl -X PATCH \
     -H "Authorization: Bearer mi_api_key_aqui" \
     -H "Content-Type: application/json" \
     -d '{"status": "approved", "reason": "Implementado en la v2.3"}' \
     https://trini.alienhost.ovh/api/v2/guilds/796742145121714227/suggestions/42
```

---

## Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| API key comprometida | Revocación instantánea con `[p]apiv2 key revoke` |
| DDoS al puerto de la API | Rate limiting + nginx limitando conexiones |
| Operaciones destructivas sin querer | Scopes separados read/write; confirmación en operaciones críticas |
| El cog crashea el bot | Server en try/except; errores no propagan al evento loop del bot |
| Puerto en conflicto | Puerto configurable con `[p]apiv2 set port` |

---

## Conclusión

**Viabilidad: Alta.** La implementación no requiere dependencias externas nuevas, se integra limpiamente con la arquitectura de Red-DiscordBot, y resuelve un gap real: poder automatizar e integrar el bot con sistemas externos sin pasar por la interfaz web del Dashboard.

La Fase 1 (núcleo funcional con auth y rutas básicas) es implementable de forma relativamente directa. Las fases posteriores añaden valor progresivamente sin romper lo anterior.

**Siguiente paso cuando se decida implementar:** empezar por `apiv2.py` + `auth.py` + comandos de gestión de keys, con el endpoint `/health` como primer smoke test.
