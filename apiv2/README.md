# APIv2

Servidor REST embebido en el bot para integraciones externas (webs, scripts, paneles). Autenticacion por API key, rate limit y webhooks salientes.

> Prefijo de ejemplo `!` (el de La Trini). Si un comando es hibrido tambien funciona con `/` tras `!slash enablecog <cog>` y `!slash sync`.

## Instalacion

```
!repo update killerbite-cogs
!cog install killerbite-cogs apiv2
!load apiv2
```

**Requisitos:** Solo el owner del bot. Se recomienda un proxy inverso con HTTPS (nginx) delante.

## Puesta en marcha paso a paso

1. Carga el cog y mira el estado: `!apiv2 status`. Por defecto escucha en `127.0.0.1:8742` (solo accesible desde la propia maquina).
2. Crea una clave: `!apiv2 key create web`. El token llega **por DM**; guardalo, se usa asi:
   `Authorization: Bearer <token>`.
3. (Opcional) Cambia direccion o puerto: `!apiv2 set host 0.0.0.0` / `!apiv2 set port 8742` y aplica con `!apiv2 restart`.
4. Publicalo con HTTPS: pon nginx (u otro proxy) delante apuntando a `127.0.0.1:8742`. No expongas el puerto directamente.
5. Comprueba que responde: `https://tu-dominio/api/v2/health` (publico) y la documentacion en `/api/v2/docs`.
6. (Opcional) Limite por clave: `!apiv2 key ratelimit web 120` (peticiones/minuto; por defecto 200).
7. (Opcional) Webhooks salientes: `!apiv2 webhook create avisos https://mi-web/hook` y pruebalo con `!apiv2 webhook test avisos`.
8. Si una clave se filtra: `!apiv2 key revoke web` (efecto inmediato).

Mas detalle tecnico en [PLAN.md](PLAN.md).

## Dashboard

Pagina principal (solo owner del bot): estado del servidor HTTP, claves (nunca los tokens) y webhooks.

## Referencia completa de comandos

Prefijo `!` como ejemplo. `<obligatorio>` · `[opcional]` · `[x=valor]` valor por defecto.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!apiv2 key create <name>` | Create a new API key. The key will be sent via DM. | Owner del bot |
| `!apiv2 key list` | List all API keys. | Owner del bot |
| `!apiv2 key ratelimit <name> [limit]` | Set a custom rate limit for a key (requests/min). | Owner del bot |
| `!apiv2 key revoke <name>` | Revoke an API key (immediate effect). | Owner del bot |
| `!apiv2 key show <name>` | Show the token for a key (sent via DM). | Owner del bot |
| `!apiv2 restart` | Restart the API server. | Owner del bot |
| `!apiv2 set host <host>` | Change the API server bind address. Requires restart. | Owner del bot |
| `!apiv2 set port <port>` | Change the API server port. Requires restart. | Owner del bot |
| `!apiv2 status` | Show the API server status. | Owner del bot |
| `!apiv2 webhook create <name> <url> [events...]` | Create an outgoing webhook. | Owner del bot |
| `!apiv2 webhook delete <name>` | Delete an outgoing webhook. | Owner del bot |
| `!apiv2 webhook list` | List all outgoing webhooks. | Owner del bot |
| `!apiv2 webhook test <name>` | Send a test ping to a webhook. | Owner del bot |
