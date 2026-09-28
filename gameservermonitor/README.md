# GameServerMonitor

Monitoriza servidores de juego (CS2, CSS, GMod, Rust, Minecraft, DayZ, Valheim, ARK, TF2, L4D2, 7DTD, Palworld) con un mensaje de estado que se actualiza solo, botones y comandos de jugadores, mapa e historial.

> Prefijo de ejemplo `!` (el de La Trini). Si un comando es hibrido tambien funciona con `/` tras `!slash enablecog <cog>` y `!slash sync`.

## Instalacion

```
!repo update killerbite-cogs
!cog install killerbite-cogs gameservermonitor
!load gameservermonitor
```

**Requisitos:** Dependencias `opengsq` y `pytz` (se instalan con el cog). Solo administradores configuran.

## Puesta en marcha paso a paso

1. Zona horaria de los mensajes: `!settimezone Europe/Madrid`.
2. (Opcional) Si tus servidores usan IPs privadas, la IP publica que se mostrara: `!setpublicip 51.77.10.20`.
3. (Opcional) Plantilla del boton "Conectar": `!setconnecturl https://alienhost.ovh/connect.php?ip={ip}`.
4. Añade cada servidor en el canal donde quieras su estado:
   - General: `!addserver 51.77.10.20:25565 minecraft #estado-servidores`
   - Con puerto de consultas aparte (Rust): `!addserver 51.77.10.20:28015 rust 28015 28017 #estado-servidores`
   - DayZ: `!addserver 51.77.10.20 dayz 2302 27016 #estado-servidores`
   - Con dominio visible: añade el dominio al final, p. ej. `... #estado-servidores mc.alienhost.es`
5. Ajusta la frecuencia de actualizacion: `!refreshtime 60` (segundos).
6. Comprueba la lista con `!listservers`. Para quitar uno: `!removeserver <clave>` (la clave sale en la lista).
7. Los usuarios pueden usar `!serverstats`, `!gsmplayers`, `!gsmmap` y `!gsmhistory <servidor> 24`.
8. Mantenimiento: `!deadservers 7` lista los que no responden desde hace 7 dias y `!purgeservers 7` los elimina (con confirmacion).
9. (Opcional) Avisos extra por servidor (sustituyen al cog MapTrack):
   - Cambio de mapa: `!gsmalerts map 51.77.10.20:28015 #cambios-de-mapa`. Avisa con el mapa anterior, el nuevo, los jugadores y como conectarse.
   - Caidas y vuelta a online: `!gsmalerts status 51.77.10.20:28015 #estado-servidores`.
   - Para quitar un aviso, repite el comando sin canal. Revisalos con `!gsmalerts list`.
   - Si usabas MapTrack: `!gsmalerts importmaptrack` copia sus canales a los servidores que ya monitorizas, y despues puedes hacer `!unload maptrack`.

Mas detalle en [DOCUMENTATION.md](DOCUMENTATION.md).

## Referencia completa de comandos

Prefijo `!` como ejemplo. `<obligatorio>` · `[opcional]` · `[x=valor]` valor por defecto.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!addserver <server_ip> <game> [game_port] [query_port] [channel] [domain]` | Adds a server to monitor its status. | Admin o permiso Administrator |
| `!deadservers [days]` | Lists servers that stopped responding, without removing anything. Alias: `serversmuertos`. | Admin o permiso Administrator |
| `!forcestatus` | Forces a status update in the current channel. Alias: `forzarstatus`. | Todos |
| `!gameservermonitordebug <state>` | Enables or disables debug mode. | Admin o permiso Administrator |
| `!gsmhistory <server> [hours=24]` | Shows the player history of a server with an ASCII graph. | Todos |
| `!gsmmap <server>` | Shows the current map of a server. | Todos |
| `!gsmplayers <server>` | Shows the list of players connected to a server. | Todos |
| `!gsmversion` | Shows the current GameServerMonitor cog version. | Todos |
| `!listservers` | Lists all monitored servers. Alias: `listaserver`. | Todos |
| `!gsmalerts map <servidor> [canal]` | Aviso de cambio de mapa del servidor en un canal o hilo (sin canal lo quita). Alias del grupo: `gsmavisos`. | Admin o permiso Administrator |
| `!gsmalerts status <servidor> [canal]` | Aviso cuando el servidor se cae o vuelve a estar online (sin canal lo quita). | Admin o permiso Administrator |
| `!gsmalerts list` | Avisos configurados y mapa actual de cada servidor. | Admin o permiso Administrator |
| `!gsmalerts importmaptrack` | Importa los canales de avisos de mapa del cog MapTrack. | Admin o permiso Administrator |
| `!purgeservers [days]` | Removes servers that stopped responding, after confirmation. Alias: `purgedeadservers`, `limpiarservers`. | Admin o permiso Administrator |
| `!refreshtime <seconds>` | Sets the refresh interval in seconds. | Admin o permiso Administrator |
| `!removeserver <server_key>` | Removes a server from monitoring. | Admin o permiso Administrator |
| `!serverstats <server>` | Shows detailed server statistics. | Todos |
| `!setconnecturl <url>` | Sets the connection URL template. | Admin o permiso Administrator |
| `!setpublicip [ip]` | Sets the public IP to replace private IPs in embeds. | Admin o permiso Administrator |
| `!settimezone <timezone>` | Sets the timezone for status updates. | Admin o permiso Administrator |
