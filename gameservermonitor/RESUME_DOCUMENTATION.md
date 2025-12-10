# GameServerMonitor v2.1.0 - Quick Reference Guide
# GameServerMonitor v2.1.0 - Guía de Referencia Rápida

---

## 🇬🇧 English

### Description

**GameServerMonitor** is a cog for Red Discord Bot that monitors game server status in real-time. It displays server information through Discord embeds that update automatically, showing player count, map, connection status, and more.

### Supported Games

| Game | Key | Default Port |
|------|-----|--------------|
| Counter-Strike 2 | `cs2` | 27015 |
| Counter-Strike: Source | `css` | 27015 |
| Garry's Mod | `gmod` | 27015 |
| Rust | `rust` | 28015 |
| Minecraft | `minecraft` | 25565 |
| DayZ Standalone | `dayz` | 2302 |

### Features

- ✅ Automatic server status monitoring
- ✅ Real-time player count and map display
- ✅ Server latency/ping display
- ✅ Player history with ASCII graphs (24h)
- ✅ Live player list with connection time
- ✅ Game thumbnails in embeds
- ✅ Uptime statistics
- ✅ Custom connection URLs
- ✅ Private IP replacement with public IP

---

### Commands

#### Configuration Commands (Admin Only)

| Command | Description |
|---------|-------------|
| `[p]settimezone <timezone>` | Sets the timezone for timestamps. Example: `Europe/Madrid`, `America/New_York` |
| `[p]setpublicip [ip]` | Sets a public IP to replace private IPs in embeds. Leave empty to disable. |
| `[p]setconnecturl <url>` | Sets the connection URL template. Use `{ip}` as placeholder. Example: `https://alienhost.ovh/connect?ip={ip}` |
| `[p]refreshtime <seconds>` | Sets the update interval in seconds (minimum 10). |
| `[p]gameservermonitordebug <true/false>` | Enables or disables debug mode for troubleshooting. |

#### Server Management Commands (Admin Only)

| Command | Description |
|---------|-------------|
| `[p]addserver <ip:port> <game> [#channel] [domain]` | Adds a server to monitor. If no channel specified, uses current channel. |
| `[p]addserver <ip> dayz <game_port> <query_port> [#channel] [domain]` | Special syntax for DayZ servers that require separate ports. |
| `[p]removeserver <ip:port>` | Removes a server from monitoring. |

#### Information Commands (Everyone)

| Command | Description |
|---------|-------------|
| `[p]listaserver` | Lists all monitored servers with their status and configuration. |
| `[p]forzarstatus` | Forces an immediate status update for servers in the current channel. |
| `[p]serverstats <ip:port>` | Shows detailed statistics: uptime, total queries, last online/offline times. |
| `[p]gsmhistory <ip:port> [hours]` | Shows player history with an ASCII graph. Default: 24 hours, max: 168 hours (1 week). |
| `[p]gsmplayers <ip:port>` | Shows the list of currently connected players with name, score, and connection time. |
| `[p]gsmversion` | Shows the current cog version. |

---

### Usage Examples

```
# Add a CS2 server
[p]addserver 178.33.160.187:27015 cs2 #server-status

# Add a Minecraft server (uses default port 25565)
[p]addserver play.myserver.com minecraft

# Add a DayZ server with specific ports and private IP.
[p]addserver 10.0.0.1 dayz 2302 27016 #dayz-status

# Set timezone to Madrid
[p]settimezone Europe/Madrid

# Set public IP (replaces private IPs in embeds)
[p]setpublicip 178.33.160.187

# View player history for last 12 hours
[p]gsmhistory 178.33.160.187:27015 12

# View connected players
[p]gsmplayers 178.33.160.187:27015
```

---

### Embed Information Display

When a server is **online**, the embed shows:
- 🔐 Status (Online/Maintenance if passworded)
- 🎮 Game name
- 🔗 Connect button (clickable link)
- 📌 IP address
- 🗺️ Current map
- 👥 Players (current/max with percentage)
- 📶 Ping (latency in ms)
- Game thumbnail image

When a server is **offline**, the embed shows:
- 🔴 Offline status
- 🎮 Game name
- 📌 IP address

---

### Player History Graph

The `gsmhistory` command generates an ASCII graph showing player activity:

```
📊 Player history (24h)
──────────────────────────
Max:  32 │▁▂▃▅▆▇█▇▆▅▄▃▂▁░░▁▂▃▄▅▆▇█│
     0 │────────────────────────│
──────────────────────────
      -24h                  Now

📈 Peak: 28 | 📊 Average: 15.3
```

- `█` = High player count
- `░` = Zero players
- Shows peak and average for the period

---

### Permissions Required

The bot needs these permissions in the channel:
- Send Messages
- Embed Links
- Read Message History

---

---

## 🇪🇸 Español

### Descripción

**GameServerMonitor** es un cog para Red Discord Bot que monitoriza el estado de servidores de juegos en tiempo real. Muestra la información del servidor mediante embeds de Discord que se actualizan automáticamente, mostrando cantidad de jugadores, mapa, estado de conexión y más.

### Juegos Soportados

| Juego | Clave | Puerto por Defecto |
|-------|-------|-------------------|
| Counter-Strike 2 | `cs2` | 27015 |
| Counter-Strike: Source | `css` | 27015 |
| Garry's Mod | `gmod` | 27015 |
| Rust | `rust` | 28015 |
| Minecraft | `minecraft` | 25565 |
| DayZ Standalone | `dayz` | 2302 |

### Características

- ✅ Monitorización automática del estado del servidor
- ✅ Muestra jugadores y mapa en tiempo real
- ✅ Muestra latencia/ping del servidor
- ✅ Historial de jugadores con gráficos ASCII (24h)
- ✅ Lista de jugadores en vivo con tiempo de conexión
- ✅ Miniaturas de juegos en embeds
- ✅ Estadísticas de uptime
- ✅ URLs de conexión personalizables
- ✅ Reemplazo de IP privada por IP pública
- ✅ Integración con panel web (dashboard)

---

### Comandos

#### Comandos de Configuración (Solo Admin)

| Comando | Descripción |
|---------|-------------|
| `[p]settimezone <zona_horaria>` | Establece la zona horaria para las marcas de tiempo. Ejemplo: `Europe/Madrid`, `America/Mexico_City` |
| `[p]setpublicip [ip]` | Establece una IP pública para reemplazar IPs privadas en los embeds. Dejar vacío para desactivar. |
| `[p]setconnecturl <url>` | Establece la plantilla de URL de conexión. Usar `{ip}` como marcador. Ejemplo: `https://misitio.com/conectar?ip={ip}` |
| `[p]refreshtime <segundos>` | Establece el intervalo de actualización en segundos (mínimo 10). |
| `[p]gameservermonitordebug <true/false>` | Activa o desactiva el modo debug para diagnóstico. |

#### Comandos de Gestión de Servidores (Solo Admin)

| Comando | Descripción |
|---------|-------------|
| `[p]addserver <ip:puerto> <juego> [#canal] [dominio]` | Añade un servidor para monitorizar. Si no se especifica canal, usa el canal actual. |
| `[p]addserver <ip> dayz <puerto_juego> <puerto_query> [#canal] [dominio]` | Sintaxis especial para servidores DayZ que requieren puertos separados. |
| `[p]removeserver <ip:puerto>` | Elimina un servidor del monitoreo. |

#### Comandos de Información (Todos)

| Comando | Descripción |
|---------|-------------|
| `[p]listaserver` | Lista todos los servidores monitorizados con su estado y configuración. |
| `[p]forzarstatus` | Fuerza una actualización inmediata de los servidores en el canal actual. |
| `[p]serverstats <ip:puerto>` | Muestra estadísticas detalladas: uptime, queries totales, últimas veces online/offline. |
| `[p]gsmhistory <ip:puerto> [horas]` | Muestra el historial de jugadores con un gráfico ASCII. Por defecto: 24 horas, máximo: 168 horas (1 semana). |
| `[p]gsmplayers <ip:puerto>` | Muestra la lista de jugadores conectados actualmente con nombre, puntuación y tiempo de conexión. |
| `[p]gsmversion` | Muestra la versión actual del cog. |

---

### Ejemplos de Uso

```
# Añadir un servidor de CS2
[p]addserver 192.168.1.1:27015 cs2 #estado-servidor

# Añadir un servidor de Minecraft (usa puerto por defecto 25565)
[p]addserver play.miservidor.com minecraft

# Añadir un servidor de DayZ con puertos específicos
[p]addserver 10.0.0.1 dayz 2302 27016 #estado-dayz

# Establecer zona horaria a Madrid
[p]settimezone Europe/Madrid

# Establecer IP pública (reemplaza IPs privadas en embeds)
[p]setpublicip 123.45.67.89

# Ver historial de jugadores de las últimas 12 horas
[p]gsmhistory 192.168.1.1:27015 12

# Ver jugadores conectados
[p]gsmplayers 192.168.1.1:27015
```

---

### Información Mostrada en Embeds

Cuando un servidor está **online**, el embed muestra:
- 🔐 Estado (Online/Mantenimiento si tiene contraseña)
- 🎮 Nombre del juego
- 🔗 Botón de conexión (enlace clickeable)
- 📌 Dirección IP
- 🗺️ Mapa actual
- 👥 Jugadores (actuales/máximo con porcentaje)
- 📶 Ping (latencia en ms)
- Imagen miniatura del juego

Cuando un servidor está **offline**, el embed muestra:
- 🔴 Estado Offline
- 🎮 Nombre del juego
- 📌 Dirección IP

---

### Gráfico de Historial de Jugadores

El comando `gsmhistory` genera un gráfico ASCII mostrando la actividad de jugadores:

```
📊 Historial de jugadores (24h)
──────────────────────────
Max:  32 │▁▂▃▅▆▇█▇▆▅▄▃▂▁░░▁▂▃▄▅▆▇█│
     0 │────────────────────────│
──────────────────────────
      -24h                  Ahora

📈 Peak: 28 | 📊 Promedio: 15.3
```

- `█` = Alta cantidad de jugadores
- `░` = Cero jugadores
- Muestra el pico y promedio del período

---

### Permisos Requeridos

El bot necesita estos permisos en el canal:
- Enviar Mensajes
- Insertar Enlaces
- Leer Historial de Mensajes

---

## Author / Autor

**Killerbite95**

## Version / Versión

**2.1.0**
