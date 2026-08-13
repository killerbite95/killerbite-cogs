# GameServerMonitor v2.2.0 - Documentación Completa

## Índice

1. [Descripción General](#descripción-general)
2. [Novedades en v2.1.0](#novedades-en-v210)
3. [Requisitos y Dependencias](#requisitos-y-dependencias)
4. [Instalación](#instalación)
5. [Arquitectura del Proyecto](#arquitectura-del-proyecto)
6. [Configuración](#configuración)
7. [Comandos Disponibles](#comandos-disponibles)
8. [Juegos Soportados](#juegos-soportados)
9. [Sistema de Embeds](#sistema-de-embeds)
10. [Sistema de Eventos](#sistema-de-eventos)
11. [Sistema de Caché](#sistema-de-caché)
12. [Sistema de Historial](#sistema-de-historial)
13. [Integración con Dashboard](#integración-con-dashboard)
14. [Sistema de Logging](#sistema-de-logging)
15. [Patrones de Diseño](#patrones-de-diseño)
16. [Estructura de Datos](#estructura-de-datos)
17. [Manejo de Errores](#manejo-de-errores)
18. [Extensibilidad](#extensibilidad)
19. [Migración desde v1.x](#migración-desde-v1x)
20. [FAQ y Troubleshooting](#faq-y-troubleshooting)
21. [Changelog](#changelog)

---

## Descripción General

**GameServerMonitor** es un cog avanzado para **Red Discord Bot v3.5.22+** que permite monitorizar el estado de servidores de juegos en tiempo real, mostrando información actualizada en canales de Discord mediante embeds.

### Características Principales

- ✅ Monitorización automática de servidores de juegos
- ✅ Soporte para múltiples protocolos (Source Query, Minecraft Status)
- ✅ Sistema de caché para optimizar queries
- ✅ Estadísticas de uptime por servidor
- ✅ Historial de jugadores con gráficos ASCII
- ✅ Lista de jugadores conectados en tiempo real
- ✅ **Botones interactivos en embeds** (NUEVO v2.2.0)
- ✅ **Comandos slash con autocompletado** (NUEVO v2.2.0)
- ✅ **Respuestas ephemeral (privadas)** (NUEVO v2.2.0)
- ✅ Sistema de eventos para integración con otros cogs
- ✅ Configuración dinámica (IP pública, URL de conexión)
- ✅ Validación de permisos de canal
- ✅ Thumbnails de juegos en embeds
- ✅ Internacionalización (i18n) preparada
- ✅ Integración completa con Red-Dashboard
- ✅ Arquitectura modular con patrones de diseño

### Autor

- **Killerbite95**

---

## Novedades en v2.2.0

### Nuevas Funcionalidades

| Característica | Descripción |
|----------------|-------------|
| 🔘 Botones en embeds | **NUEVO** - Botones Players/Stats/History en embeds de servidor |
| ⌨️ Slash Commands | **NUEVO** - `/serverstats`, `/gsmhistory`, `/gsmplayers` con autocompletado |
| 👁️ Respuestas ephemeral | **NUEVO** - Respuestas privadas solo visibles para quien interactúa |
| 🆔 server_id estable | **NUEVO** - UUID para routing de botones que sobrevive reinicios |
| ⏱️ CooldownManager | **NUEVO** - Anti-spam 5s por usuario/acción |
| 📁 views.py | **NUEVO** - Módulo de componentes UI persistentes |

### Funcionalidades de v2.1.0

| Característica | Descripción |
|----------------|-------------|
| 📊 `gsmhistory` | Historial de jugadores con gráfico ASCII |
| 👥 `gsmplayers` | Lista de jugadores conectados |
| 📈 Historial 24h | Almacena datos de jugadores de las últimas 24 horas |
| 📉 Gráficos ASCII | Visualización de actividad del servidor |

### Funcionalidades de v2.0.0

| Característica | Descripción |
|----------------|-------------|
| 🔧 `setpublicip` | Configurar IP pública dinámica |
| 🔧 `setconnecturl` | URL de conexión personalizable |
| 📊 `serverstats` | Estadísticas detalladas por servidor |
| 📡 Sistema de Eventos | `on_gameserver_online`, `on_gameserver_offline` |
| 💾 Sistema de Caché | Evita queries redundantes |
| 🖼️ Thumbnails | Imágenes de juegos en embeds |
| 📶 Latencia | Muestra ping del servidor |
| ✅ Validación de Permisos | Verifica permisos antes de actuar |

### Mejoras de Arquitectura

- **Patrón Strategy** para handlers de query
- **Dataclasses** para estructuración de datos
- **Enums** para estados y tipos de juego
- **Excepciones personalizadas** para mejor manejo de errores
- **Type hints completos** (PEP 484)
- **Separación de responsabilidades** en módulos

---

## Requisitos y Dependencias

### Dependencias Python

```
opengsq>=2.0.0    # Librería para queries de servidores
pytz>=2023.0      # Manejo de zonas horarias
```

### Versión Mínima

- **Red-DiscordBot**: 3.5.0+
- **Python**: 3.9.0+

### Instalación de dependencias

```bash
pip install opengsq pytz
```

---

## Instalación

### Método 1: Desde repositorio

```
[p]repo add killerbite-cogs https://github.com/killerbite95/killerbite-cogs
[p]cog install killerbite-cogs gameservermonitor
[p]load gameservermonitor
```

### Método 2: Manual

1. Clonar/copiar la carpeta `gameservermonitor` al directorio de cogs
2. Instalar dependencias: `pip install opengsq pytz`
3. Cargar: `[p]load gameservermonitor`

---

## Arquitectura del Proyecto

### Estructura de Archivos

```
gameservermonitor/
├── __init__.py                 # Punto de entrada, setup()
├── gameservermonitor.py        # Cog principal (comandos, lógica)
├── views.py                    # UI Components (botones, views) - NUEVO v2.2.0
├── models.py                   # Dataclasses, Enums
├── query_handlers.py           # Handlers de query (Strategy Pattern)
├── exceptions.py               # Excepciones personalizadas
├── dashboard_integration.py    # Integración con Red-Dashboard
├── info.json                   # Metadatos del cog
└── DOCUMENTATION.md            # Esta documentación
```

### Diagrama de Clases

```
┌─────────────────────────────┐
│     DashboardIntegration    │
│─────────────────────────────│
│ + on_dashboard_cog_add()    │
│ + create_html_table()       │
│ + success_response()        │
│ + error_response()          │
└──────────────┬──────────────┘
               │ hereda
               ▼
┌─────────────────────────────────────────────────────────────┐
│                    GameServerMonitor                         │
│─────────────────────────────────────────────────────────────│
│ - bot: Red                                                   │
│ - config: Config                                             │
│ - query_service: QueryService                                │
│─────────────────────────────────────────────────────────────│
│ + set_timezone(), set_public_ip(), set_connect_url()        │
│ + add_server(), remove_server(), list_servers()             │
│ + force_status(), server_stats(), refresh_time()            │
│ + update_server_status()                                     │
│ + _create_online_embed(), _create_offline_embed()           │
│ + _dispatch_status_event()                                   │
│ + rpc_callback_servers(), rpc_add_server(), rpc_config()    │
└─────────────────────────────────────────────────────────────┘
                              │ usa
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      QueryService                            │
│─────────────────────────────────────────────────────────────│
│ - _cache: QueryCache                                         │
│ - _debug: bool                                               │
│─────────────────────────────────────────────────────────────│
│ + query_server(host, port, game, **kwargs)                  │
│ + clear_cache(), cleanup_cache()                             │
└──────────────────────────────┬──────────────────────────────┘
                               │ usa
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                   QueryHandlerFactory                        │
│─────────────────────────────────────────────────────────────│
│ + get_handler(game: GameType) -> QueryHandler               │
│ + register_handler(game, handler_class)                     │
└──────────────────────────────┬──────────────────────────────┘
                               │ crea
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
┌───────────────┐    ┌─────────────────┐    ┌────────────────┐
│ SourceQuery   │    │ MinecraftQuery  │    │   DayZQuery    │
│   Handler     │    │    Handler      │    │    Handler     │
└───────────────┘    └─────────────────┘    └────────────────┘
```

---

## Configuración

### Configuración por Defecto (Guild)

```python
default_guild = {
    "servers": {},                                              # Servidores monitoreados
    "timezone": "UTC",                                          # Zona horaria
    "refresh_time": 60,                                         # Segundos entre updates
    "public_ip": None,                                          # IP pública para reemplazo
    "connect_url_template": "https://example.com?ip={ip}",      # URL de conexión
    "embed_config": {
        "show_thumbnail": True,                                 # Mostrar imagen del juego
        "show_connect_button": True,                            # Mostrar botón conectar
        "color_online": None,                                   # Color personalizado
        "color_offline": None,
        "color_maintenance": None
    },
    "player_history": {},                                       # Historial de jugadores
    "interaction_features": {                                   # NUEVO v2.2.0
        "enabled": True,                                        # Habilitar interacciones
        "buttons_enabled": True,                                # Mostrar botones en embeds
        "ephemeral_default": True,                              # Respuestas privadas por defecto
        "delete_after_prefix_seconds": 20,                      # Auto-eliminar respuestas de prefijo
        "history_default_hours": 24,                            # Horas por defecto para historial
        "history_max_hours": 168                                # Máximo de horas (1 semana)
    }
}
```

---

## Comandos Disponibles

### Comandos de Configuración

| Comando | Permisos | Descripción |
|---------|----------|-------------|
| `[p]settimezone <tz>` | Admin | Establece zona horaria |
| `[p]setpublicip [ip]` | Admin | Establece IP pública (sin args para desactivar) |
| `[p]setconnecturl <url>` | Admin | Establece URL de conexión (usar `{ip}`) |
| `[p]refreshtime <seg>` | Admin | Tiempo de actualización (mín: 10s) |
| `[p]gameservermonitordebug <bool>` | Admin | Activa/desactiva debug |

### Comandos de Servidores

| Comando | Permisos | Descripción |
|---------|----------|-------------|
| `[p]addserver <ip> <juego> [...]` | Admin | Añade servidor |
| `[p]removeserver <clave>` | Admin | Elimina servidor |
| `[p]deadservers [días]` | Admin | Lista servidores sin responder (solo lectura) |
| `[p]purgeservers [días]` | Admin | Elimina los servidores sin responder, con confirmación |
| `[p]listaserver` | Todos | Lista servidores |
| `[p]forzarstatus` | Todos | Fuerza actualización |
| `[p]serverstats <clave>` | Todos | Estadísticas del servidor |
| `[p]gsmhistory <clave> [horas]` | Todos | Historial con gráfico |
| `[p]gsmplayers <clave>` | Todos | Lista de jugadores |
| `[p]gsmversion` | Todos | Muestra versión del cog |

### Comandos Híbridos (Slash + Prefijo) - NUEVO v2.2.0

Los siguientes comandos ahora funcionan tanto con prefijo como con slash:

| Slash Command | Prefijo Equivalente | Descripción |
|---------------|---------------------|-------------|
| `/serverstats` | `[p]serverstats` | Estadísticas con autocompletado de servidor |
| `/gsmhistory` | `[p]gsmhistory` | Historial con autocompletado y selector de horas |
| `/gsmplayers` | `[p]gsmplayers` | Lista de jugadores con autocompletado |

**Características de Slash Commands:**
- ✅ Autocompletado de servidores al escribir
- ✅ Respuestas ephemeral (solo visibles para ti)
- ✅ Validación de parámetros automática

### Botones Interactivos en Embeds - NUEVO v2.2.0

Los embeds de estado de servidor ahora incluyen botones interactivos:

| Botón | Emoji | Acción |
|-------|-------|--------|
| **Players** | 👥 | Muestra lista de jugadores conectados |
| **Stats** | 📈 | Muestra estadísticas del servidor |
| **History** | 📊 | Muestra historial de jugadores (24h por defecto) |

**Características de los botones:**
- ✅ Respuestas ephemeral (privadas, solo las ve quien pulsa)
- ✅ Cooldown de 5 segundos por usuario/acción
- ✅ Funcionan incluso después de reiniciar el bot
- ✅ Routing estable mediante `server_id` (UUID)

```
┌─────────────────────────────────────────┐
│           [Embed del Servidor]          │
│                  ...                    │
├─────────────────────────────────────────┤
│  [👥 Players]  [📈 Stats]  [📊 History] │
└─────────────────────────────────────────┘
```

### Comandos de Historial y Jugadores (NUEVO en v2.1.0)

#### gsmhistory
Muestra el historial de jugadores de un servidor con un gráfico ASCII de actividad.

```
[p]gsmhistory <ip:puerto> [horas]
```

**Ejemplos:**
```
!gsmhistory 192.168.1.1:27015          # Últimas 24 horas
!gsmhistory 192.168.1.1:27015 12       # Últimas 12 horas
!gsmhistory 192.168.1.1:27015 168      # Última semana
```

**Salida de ejemplo:**
```
📊 Historial de jugadores (24h)
──────────────────────────
Max:  25 │▂▃▄▅▆▇▇▆▅▄▃▂▁░░▁▂▃▄▅▆▇█▇│
     0 │────────────────────────│
──────────────────────────
      -24h                  Ahora

📈 Peak: 23 | 📊 Promedio: 12.5
```

#### gsmplayers
Muestra la lista de jugadores actualmente conectados a un servidor.

```
[p]gsmplayers <ip:puerto>
```

**Ejemplo:**
```
!gsmplayers 192.168.1.1:27015
```

**Salida de ejemplo:**
```
👥 Jugadores - Mi Servidor de GMod

Juego: Garry's Mod
Mapa: rp_downtown_v4c
Jugadores: 15/32

📋 Lista de Jugadores
┌────────────────────────────────────────┐
│ Nombre               Puntos    Tiempo  │
│ ────────────────────────────────────── │
│ Player1                  150     2h 30m│
│ Player2                   85     1h 15m│
│ Player3                   42       45m │
│ ...                                    │
└────────────────────────────────────────┘

📶 Ping: 25ms
```

### Sintaxis de addserver

```
# Juegos estándar
[p]addserver <ip[:puerto]> <juego> [#canal] [dominio]

# DayZ (requiere puertos explícitos)
[p]addserver <ip> dayz <game_port> [query_port] [#canal] [dominio]
```

**Ejemplos:**
```
!addserver 192.168.1.1:27015 cs2 #server-status
!addserver play.example.com minecraft
!addserver 10.0.0.5 dayz 2302 27016 #dayz-status myserver.com
```

---

## Juegos Soportados

| Juego | Identificador | Puerto Default | Protocolo | Thumbnail |
|-------|---------------|----------------|-----------|-----------|
| Counter-Strike 2 | `cs2` | 27015 | Source | ✅ |
| Counter-Strike: Source | `css` | 27015 | Source | ✅ |
| Garry's Mod | `gmod` | 27015 | Source | ✅ |
| Rust | `rust` | 28015 | Source | ✅ |
| Minecraft | `minecraft` | 25565 | MC Status | ✅ |
| DayZ Standalone | `dayz` | Variable | Source | ✅ |

---

## Sistema de Embeds

### Estados del Servidor (Enum: ServerStatus)

| Estado | Color | Emoji | Descripción |
|--------|-------|-------|-------------|
| `ONLINE` | 🟢 Verde | ✅ | Servidor accesible |
| `OFFLINE` | 🔴 Rojo | 🔴 | No responde |
| `MAINTENANCE` | 🟠 Naranja | 🔐 | Online con contraseña |
| `UNKNOWN` | ⚪ Gris | ❓ | Estado desconocido |

### Estructura del Embed Online

```
┌─────────────────────────────────────────┐
│ 🖼️ [Thumbnail del juego]               │
│ [Hostname] - Server Status              │
├─────────────────────────────────────────┤
│ ✅ Status    │ Online                   │
│ 🎮 Game      │ Counter-Strike 2         │
├─────────────────────────────────────────┤
│ 🔗 Connect   │ [Connect](url)           │
├─────────────────────────────────────────┤
│ 📌 IP        │ 192.168.1.1:27015        │
│ 🗺️ Map       │ de_dust2                 │
│ 👥 Players   │ 12/24 (50%)              │
│ 📶 Ping      │ 45ms                     │
├─────────────────────────────────────────┤
│ Footer: Last update: 2025-12-10 15:30   │
└─────────────────────────────────────────┘
```

---

## Sistema de Eventos

El cog dispara eventos personalizados que otros cogs pueden escuchar:

### Eventos Disponibles

```python
# Cuando un servidor pasa a online
@commands.Cog.listener()
async def on_gameserver_online(self, guild, server_key):
    print(f"Servidor {server_key} está online!")

# Cuando un servidor pasa a offline
@commands.Cog.listener()
async def on_gameserver_offline(self, guild, server_key):
    print(f"Servidor {server_key} está offline!")

# Cualquier cambio de estado
@commands.Cog.listener()
async def on_gameserver_status_change(self, guild, server_key, old_status, new_status):
    print(f"Servidor {server_key}: {old_status} -> {new_status}")
```

### Ejemplo de Uso en Otro Cog

```python
class NotificationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_gameserver_offline(self, guild, server_key):
        # Enviar alerta cuando un servidor se cae
        channel = guild.get_channel(ALERT_CHANNEL_ID)
        await channel.send(f"⚠️ ¡El servidor {server_key} está offline!")
```

---

## Sistema de Caché

### Funcionamiento

- **Duración**: 5 segundos por defecto
- **Clave**: `{game}:{host}:{port}`
- **Limpieza**: Automática en cada ciclo de monitoreo

### Beneficios

1. Evita queries redundantes durante force_status
2. Reduce carga en servidores monitoreados
3. Mejora rendimiento con múltiples guilds

### Invalidación Manual

```python
# Dentro del cog
self.query_service._cache.invalidate(host, port, game_type)
self.query_service.clear_cache()  # Limpiar toda la caché
```

---

## Integración con Dashboard

### Páginas Disponibles

| Página | Ruta | Métodos | Descripción |
|--------|------|---------|-------------|
| servers | `/servers` | GET | Lista de servidores |
| add_server | `/add_server` | GET, POST | Añadir servidor |
| remove_server | `/remove_server` | GET, POST | Eliminar servidor |
| config | `/config` | GET, POST | Configuración general |

### Registro Automático

El cog se registra automáticamente cuando se carga Red-Dashboard mediante el listener `on_dashboard_cog_add`.

---

## Sistema de Logging

### Logger

```python
logger = logging.getLogger("red.killerbite95.gameservermonitor")
```

### Subloggers

- `red.killerbite95.gameservermonitor.query` - Queries
- `red.killerbite95.gameservermonitor.dashboard` - Dashboard

### Niveles Utilizados

| Nivel | Uso |
|-------|-----|
| DEBUG | Respuestas raw (modo debug) |
| INFO | Queries exitosas DayZ |
| WARNING | Servidor no encontrado, timezone inválido |
| ERROR | Errores de query, permisos, HTTP |

---

## Patrones de Diseño

### Strategy Pattern (Query Handlers)

Permite añadir nuevos protocolos de query sin modificar el código existente:

```python
# Añadir soporte para nuevo juego
class ARKQueryHandler(QueryHandler):
    @property
    def supported_games(self):
        return [GameType.ARK]
    
    async def query(self, host, port, **kwargs):
        # Implementar query específico
        ...

# Registrar el handler
QueryHandlerFactory.register_handler(GameType.ARK, ARKQueryHandler)
```

### Factory Pattern

`QueryHandlerFactory` crea y cachea instancias de handlers según el tipo de juego.

### Dataclasses

- `QueryResult`: Resultado de query
- `ServerData`: Configuración de servidor
- `EmbedConfig`: Configuración de embeds
- `ServerStats`: Estadísticas
- `CacheEntry`: Entrada de caché

---

## Estructura de Datos

### ServerData (Almacenado en Config)

```python
{
    "192.168.1.1:27015": {
        "game": "cs2",
        "channel_id": 123456789,
        "message_id": 987654321,
        "domain": "myserver.com",
        "total_queries": 150,
        "successful_queries": 145,
        "last_online": "2025-12-10T15:30:00",
        "last_offline": "2025-12-09T10:00:00",
        "last_status": "ONLINE"
    }
}
```

### ServerData DayZ

```python
{
    "192.168.1.1:2302": {
        "game": "dayz",
        "channel_id": 123456789,
        "message_id": 987654321,
        "domain": "dayz.myserver.com",
        "game_port": 2302,
        "query_port": 27016,
        "total_queries": 100,
        "successful_queries": 95,
        "last_online": "2025-12-10T15:30:00",
        "last_offline": null,
        "last_status": "ONLINE"
    }
}
```

---

## Manejo de Errores

### Excepciones Personalizadas

| Excepción | Uso |
|-----------|-----|
| `GameServerMonitorError` | Base para todas |
| `QueryTimeoutError` | Timeout en query |
| `QueryConnectionError` | Error de conexión |
| `InvalidPortError` | Puerto fuera de rango |
| `ServerNotFoundError` | Servidor no en config |
| `ServerAlreadyExistsError` | Duplicado |
| `UnsupportedGameError` | Juego no soportado |
| `ChannelNotFoundError` | Canal no existe |
| `InsufficientPermissionsError` | Sin permisos |
| `InvalidTimezoneError` | Timezone inválido |

### Validación de Permisos

Antes de enviar mensajes, se verifican:
- `send_messages`
- `embed_links`
- `read_message_history`

---

## Extensibilidad

### Añadir Nuevo Juego

1. Añadir entrada en `GameType` enum (models.py)
2. Crear handler en `query_handlers.py`
3. Registrar en `QueryHandlerFactory`

### Ejemplo Completo

```python
# En models.py
class GameType(Enum):
    # ... existentes ...
    ARK = "ark"
    
    @property
    def default_port(self):
        # Añadir
        if self == GameType.ARK:
            return 27015

# En query_handlers.py
class ARKQueryHandler(QueryHandler):
    @property
    def supported_games(self):
        return [GameType.ARK]
    
    async def query(self, host, port, **kwargs):
        # Implementación
        ...

# Registrar
QueryHandlerFactory._handlers[GameType.ARK] = ARKQueryHandler
```

---

## Migración desde v1.x

### Compatibilidad

- ✅ Los datos de configuración existentes son compatibles
- ✅ Los comandos mantienen la misma sintaxis
- ✅ Los servidores existentes seguirán funcionando

### Nuevos Campos Automáticos

Los servidores existentes recibirán automáticamente:
- `total_queries`: 0
- `successful_queries`: 0
- `last_online`: null
- `last_offline`: null
- `last_status`: null

Estos campos se poblaran con el uso normal.

---

## FAQ y Troubleshooting

### El servidor aparece siempre offline

1. Verificar que el puerto de query es correcto
2. Para DayZ, probar diferentes query_ports (27016, game_port+1)
3. Activar debug: `[p]gameservermonitordebug true`

### Los embeds no se actualizan

1. Verificar permisos del bot en el canal
2. Comprobar que el mensaje no fue eliminado
3. Usar `[p]forzarstatus` para recrear

### La IP privada no se reemplaza

1. Configurar IP pública: `[p]setpublicip 123.45.67.89`
2. Verificar que la IP del servidor está en rango privado

### Error de zona horaria

Usar formato estándar: `Europe/Madrid`, `America/New_York`, `UTC`

---

## Changelog

### v2.2.0 (2025-12-22)

**Nuevas características:**
- Botones interactivos en embeds de servidor (Players/Stats/History)
- Comandos híbridos con soporte slash (`/serverstats`, `/gsmhistory`, `/gsmplayers`)
- Autocompletado de servidores en comandos slash
- Respuestas ephemeral (privadas) para botones y slash commands
- Sistema `server_id` basado en UUID para routing estable de botones
- CooldownManager para anti-spam (5s por usuario/acción)
- Nuevo módulo `views.py` con componentes UI persistentes
- Configuración `interaction_features` para personalizar comportamiento

**Mejoras de arquitectura:**
- Payload builders reutilizables (`_build_players_payload`, etc.)
- Migración automática de `server_id` para servidores existentes
- Views persistentes que sobreviven reinicios del bot

### v2.1.0 (2025-12-15)

**Nuevas características:**
- Comando `gsmhistory` para historial de jugadores con gráfico ASCII
- Comando `gsmplayers` para lista de jugadores conectados
- Almacenamiento de historial de las últimas 168 horas
- Gráficos ASCII de actividad del servidor

### v2.0.0 (2025-12-10)

**Nuevas características:**
- Sistema de caché para queries
- Comando `serverstats` para estadísticas
- Comando `setpublicip` para IP dinámica
- Comando `setconnecturl` para URL personalizable
- Sistema de eventos (`on_gameserver_online`, etc.)
- Thumbnails de juegos en embeds
- Indicador de latencia/ping
- Validación de permisos de canal

**Mejoras de arquitectura:**
- Patrón Strategy para handlers de query
- Dataclasses para estructuración de datos
- Enums para estados y tipos
- Excepciones personalizadas
- Type hints completos
- Módulos separados por responsabilidad

**Correcciones:**
- IP hardcodeada ahora es configurable
- URL de conexión ahora es configurable
- Mejor manejo de errores en queries DayZ

### v1.0.0

- Versión inicial
- Soporte para CS2, CSS, GMOD, Rust, Minecraft, DayZ
- Integración con Red-Dashboard

---

## Licencia

Este proyecto forma parte del repositorio **killerbite-cogs** bajo la licencia especificada en el archivo LICENSE del repositorio principal.

---

*Documentación actualizada: 22 de Diciembre de 2025*  
*Versión: 2.2.0*  
*Compatible con: Red-DiscordBot 3.5.22+*
