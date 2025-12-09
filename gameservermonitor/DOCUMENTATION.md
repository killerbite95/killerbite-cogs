# GameServerMonitor - Documentación Completa

## Índice

1. [Descripción General](#descripción-general)
2. [Requisitos y Dependencias](#requisitos-y-dependencias)
3. [Instalación](#instalación)
4. [Arquitectura del Proyecto](#arquitectura-del-proyecto)
5. [Configuración](#configuración)
6. [Comandos Disponibles](#comandos-disponibles)
7. [Juegos Soportados](#juegos-soportados)
8. [Sistema de Embeds](#sistema-de-embeds)
9. [Integración con Dashboard](#integración-con-dashboard)
10. [Sistema de Logging](#sistema-de-logging)
11. [Flujo de Datos](#flujo-de-datos)
12. [Estructura de Datos Almacenados](#estructura-de-datos-almacenados)
13. [Manejo de Errores](#manejo-de-errores)
14. [Limitaciones Conocidas](#limitaciones-conocidas)
15. [Changelog](#changelog)

---

## Descripción General

**GameServerMonitor** es un cog (módulo) para **Red Discord Bot v3.5.22+** que permite monitorizar el estado de servidores de juegos en tiempo real, mostrando la información en canales de Discord mediante embeds actualizados automáticamente.

### Características Principales

- ✅ Monitorización automática de servidores de juegos
- ✅ Soporte para múltiples protocolos de query (Source, Minecraft)
- ✅ Actualización periódica configurable
- ✅ Soporte para zonas horarias personalizadas
- ✅ Integración con Red-Dashboard (panel web)
- ✅ Embeds informativos con estados Online/Offline/Maintenance
- ✅ Soporte especial para DayZ con múltiples puertos de query

### Autor

- **Killerbite95**

---

## Requisitos y Dependencias

### Dependencias Python

```python
discord.py          # Incluido con Red-DiscordBot
redbot.core         # Framework Red-DiscordBot >= 3.5.22
opengsq             # Librería para queries de servidores de juegos
pytz                # Manejo de zonas horarias
```

### Versión de Red-DiscordBot

- **Mínimo**: Red-DiscordBot 3.5.22 (2025-09-05)

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

1. Clonar/copiar la carpeta `gameservermonitor` a la carpeta de cogs de Red
2. Cargar el cog: `[p]load gameservermonitor`

---

## Arquitectura del Proyecto

### Estructura de Archivos

```
gameservermonitor/
├── __init__.py                 # Punto de entrada del cog
├── gameservermonitor.py        # Lógica principal del cog (644 líneas)
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
└──────────────┬──────────────┘
               │ hereda
               ▼
┌─────────────────────────────┐
│     GameServerMonitor       │
│─────────────────────────────│
│ - bot: Red                  │
│ - config: Config            │
│ - debug: bool               │
│─────────────────────────────│
│ + set_timezone()            │
│ + add_server()              │
│ + remove_server()           │
│ + force_status()            │
│ + list_servers()            │
│ + refresh_time()            │
│ + gameservermonitordebug()  │
│ + server_monitor()          │ ◄─── @tasks.loop
│ + update_server_status()    │
│ + rpc_callback_servers()    │ ◄─── @dashboard_page
│ + rpc_add_server()          │ ◄─── @dashboard_page
│ + rpc_remove_server()       │ ◄─── @dashboard_page
└─────────────────────────────┘
```

---

## Configuración

### Configuración por Defecto (Guild)

```python
default_guild = {
    "servers": {},           # Dict de servidores monitorizados
    "timezone": "UTC",       # Zona horaria para timestamps
    "refresh_time": 60       # Segundos entre actualizaciones
}
```

### Identificador de Configuración

```python
Config.get_conf(self, identifier=1234567890, force_registration=True)
```

---

## Comandos Disponibles

### `[p]settimezone <timezone>`

**Permisos**: Administrador  
**Descripción**: Establece la zona horaria para las actualizaciones de estado.

**Ejemplo**:
```
!settimezone Europe/Madrid
!settimezone America/New_York
```

---

### `[p]addserver <server_ip> <game> [game_port] [query_port] [#canal] [dominio]`

**Permisos**: Administrador  
**Descripción**: Añade un servidor para monitorear su estado.

**Parámetros**:
| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| server_ip | str | ✅ | IP o IP:puerto del servidor |
| game | str | ✅ | Tipo de juego (cs2, css, gmod, rust, minecraft, dayz) |
| game_port | int | ❌ (DayZ: ✅) | Puerto del juego (solo DayZ) |
| query_port | int | ❌ | Puerto de query (solo DayZ) |
| channel | TextChannel | ❌ | Canal donde mostrar el estado (default: canal actual) |
| domain | str | ❌ | Dominio personalizado para mostrar |

**Ejemplos**:
```
# CS2/CSS/GMOD/Rust
!addserver 192.168.1.1:27015 cs2 #server-status
!addserver 192.168.1.1 gmod #status dominio.com

# Minecraft
!addserver play.example.com minecraft #minecraft-status

# DayZ (requiere game_port)
!addserver 192.168.1.1 dayz 2302 27016 #dayz-status
```

---

### `[p]removeserver <server_key>`

**Permisos**: Administrador  
**Descripción**: Elimina el monitoreo de un servidor.

**Ejemplo**:
```
!removeserver 192.168.1.1:27015
```

---

### `[p]forzarstatus`

**Permisos**: Todos  
**Descripción**: Fuerza una actualización de estado en el canal actual.

---

### `[p]listaserver`

**Permisos**: Todos  
**Descripción**: Lista todos los servidores monitoreados con su información.

---

### `[p]refreshtime <seconds>`

**Permisos**: Administrador  
**Descripción**: Establece el tiempo de actualización en segundos (mínimo: 10).

**Ejemplo**:
```
!refreshtime 120
```

---

### `[p]gameservermonitordebug <true/false>`

**Permisos**: Administrador  
**Descripción**: Activa o desactiva el modo debug para logging detallado.

---

## Juegos Soportados

### Tabla de Juegos y Puertos

| Juego | Identificador | Puerto Default | Protocolo |
|-------|---------------|----------------|-----------|
| Counter-Strike 2 | `cs2` | 27015 | Source Query |
| Counter-Strike: Source | `css` | 27015 | Source Query |
| Garry's Mod | `gmod` | 27015 | Source Query |
| Rust | `rust` | 28015 | Source Query |
| Minecraft | `minecraft` | 25565 | Minecraft Status |
| DayZ Standalone | `dayz` | Variable | Source Query |

### Protocolos Utilizados

#### Source Query Protocol (opengsq.protocols.Source)
- Usado para: CS2, CSS, GMOD, Rust, DayZ
- Métodos: `get_info()`
- Datos obtenidos: players, max_players, map, name, visibility

#### Minecraft Status Protocol (opengsq.protocols.Minecraft)
- Usado para: Minecraft
- Métodos: `get_status()`
- Datos obtenidos: players.online, players.max, description, version.name

---

## Sistema de Embeds

### Estados del Servidor

| Estado | Color | Emoji | Condición |
|--------|-------|-------|-----------|
| Online | 🟢 Verde | ✅ | Query exitoso, sin contraseña |
| Maintenance | 🟠 Naranja | 🔐 | Query exitoso, con contraseña |
| Offline | 🔴 Rojo | 🔴 | Query fallido |

### Campos del Embed

#### Embed Online/Maintenance
```
┌─────────────────────────────────────────┐
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
├─────────────────────────────────────────┤
│ Game Server Monitor by Killerbite95     │
│ Last update: 2025-12-10 15:30:00        │
└─────────────────────────────────────────┘
```

#### Embed Offline
```
┌─────────────────────────────────────────┐
│ Game Server - ❌ Offline                │
├─────────────────────────────────────────┤
│ Status       │ 🔴 Offline               │
│ 🎮 Game      │ Counter-Strike 2         │
│ 📌 IP        │ 192.168.1.1:27015        │
├─────────────────────────────────────────┤
│ 🔗 Connect   │ [Connect](url)           │
├─────────────────────────────────────────┤
│ Game Server Monitor by Killerbite95     │
└─────────────────────────────────────────┘
```

### Límite de Título

El título del embed está limitado a **256 caracteres** según Discord. La función `truncate_title()` maneja esto automáticamente.

---

## Integración con Dashboard

### Archivo: `dashboard_integration.py`

Proporciona integración con **Red-Dashboard** mediante:

1. **Decorador `@dashboard_page`**: Marca métodos como páginas del dashboard
2. **Clase `DashboardIntegration`**: Clase base que registra el cog en el dashboard

### Páginas del Dashboard

| Página | Ruta | Métodos | Descripción |
|--------|------|---------|-------------|
| servers | `/servers` | GET | Lista servidores monitorizados |
| add_server | `/add_server` | GET, POST | Formulario para añadir servidor |
| remove_server | `/remove_server` | GET, POST | Formulario para eliminar servidor |

### Listener de Registro

```python
@commands.Cog.listener()
async def on_dashboard_cog_add(self, dashboard_cog):
    dashboard_cog.rpc.third_parties_handler.add_third_party(self)
```

---

## Sistema de Logging

### Logger Configurado

```python
logger = logging.getLogger("red.trini.gameservermonitor")
```

### Niveles de Log Utilizados

| Nivel | Uso |
|-------|-----|
| `DEBUG` | Respuestas raw de queries (solo con debug=True) |
| `INFO` | Conexiones exitosas de DayZ |
| `WARNING` | Servidor no encontrado en config |
| `ERROR` | Errores de query, canal no encontrado, zona horaria inválida |

---

## Flujo de Datos

### Diagrama de Flujo - Actualización de Estado

```
┌─────────────────┐
│  server_monitor │ (cada X segundos)
│    @tasks.loop  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Para cada     │
│     guild       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Para cada     │
│    servidor     │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────┐
│  update_server_status()     │
└────────┬────────────────────┘
         │
         ├──► Minecraft ──► Minecraft.get_status()
         │
         ├──► Source ──► Source.get_info()
         │
         └──► DayZ ──► _try_dayz_query()
                       (múltiples intentos)
         │
         ▼
┌─────────────────────────────┐
│  Crear/Actualizar Embed     │
└────────┬────────────────────┘
         │
         ├──► first_time=True ──► channel.send()
         │
         └──► first_time=False ──► message.edit()
```

### Lógica Especial para DayZ

DayZ tiene una lógica de fallback para encontrar el puerto de query correcto:

1. Intenta `game_port` (ej: 2302)
2. Si falla, intenta `query_port` configurado
3. Si falla, intenta puertos candidatos: `[27016, game_port+1, game_port+2]`

---

## Estructura de Datos Almacenados

### Servidor Estándar

```python
{
    "192.168.1.1:27015": {
        "game": "cs2",
        "channel_id": 123456789012345678,
        "message_id": 123456789012345678,  # None si no enviado
        "domain": "myserver.com"           # Opcional
    }
}
```

### Servidor DayZ

```python
{
    "192.168.1.1:2302": {
        "game": "dayz",
        "channel_id": 123456789012345678,
        "message_id": 123456789012345678,
        "domain": "dayzserver.com",
        "game_port": 2302,
        "query_port": 27016  # Opcional
    }
}
```

---

## Manejo de Errores

### Errores Manejados

| Error | Manejo |
|-------|--------|
| Query timeout/fallo | Muestra embed "Offline" |
| Canal no encontrado | Log de error, skip servidor |
| Zona horaria inválida | Fallback a UTC |
| Mensaje no encontrado | Crea nuevo mensaje |
| Puerto inválido | Rechaza comando con mensaje |

### Mapeo de IP Privada

El cog detecta IPs privadas que empiezan con `10.0.0.` y las reemplaza con `178.33.160.187` (IP pública configurada).

```python
public_ip = "178.33.160.187" if host.startswith("10.0.0.") else host
```

---

## Limitaciones Conocidas

1. **IP Hardcodeada**: La IP pública de fallback (`178.33.160.187`) está hardcodeada
2. **Un mensaje por servidor**: Solo se mantiene un mensaje de estado por servidor
3. **Sin histórico**: No se guarda histórico de estados
4. **Refresh global**: El tiempo de refresh es el mismo para todos los servidores del guild
5. **Sin validación de permisos de canal**: No verifica si el bot puede escribir en el canal
6. **URL de conexión fija**: La URL de conexión usa `alienhost.ovh` hardcodeado

---

## Changelog

### Versión Actual

- Soporte para CS2, CSS, GMOD, Rust, Minecraft, DayZ
- Integración con Red-Dashboard
- Sistema de fallback para queries de DayZ
- Zonas horarias configurables
- Modo debug para troubleshooting

---

## Licencia

Este proyecto forma parte del repositorio **killerbite-cogs** bajo la licencia especificada en el archivo LICENSE del repositorio principal.

---

*Documentación generada el 10 de Diciembre de 2025*
*Para Red-DiscordBot v3.5.22+*
