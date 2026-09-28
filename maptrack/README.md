# MapTrack (obsoleto)

> ⚠️ **MapTrack esta integrado en GameServerMonitor.** Usa `!gsmalerts map <servidor> #canal` (y `!gsmalerts status` para caidas). Si ya lo tenias configurado: `!gsmalerts importmaptrack` y despues `!unload maptrack`. Este cog se mantiene solo para instalaciones antiguas y ya no aparece en el repo.

Avisa en un canal o hilo cada vez que un servidor de juego cambia de mapa.

> Prefijo de ejemplo `!` (el de La Trini). Si un comando es hibrido tambien funciona con `/` tras `!slash enablecog <cog>` y `!slash sync`.

## Instalacion

```
!repo update killerbite-cogs
!cog install killerbite-cogs maptrack
!load maptrack
```

**Requisitos:** Dependencia `opengsq` (se instala con el cog). Solo administradores configuran.

## Puesta en marcha paso a paso

1. Añade el servidor (formato `IP:puerto`) y el canal (o hilo) de avisos: `!addmaptrack 51.77.10.20:27015 #cambios-de-mapa`.
2. Repite con cada servidor que quieras seguir.
3. Comprueba la lista: `!maptracks`.
4. Fuerza una comprobacion en el canal actual: `!forcemaptrack`.
5. Para quitar los seguimientos de un canal: `!removemaptrack #cambios-de-mapa`.

## Referencia completa de comandos

Prefijo `!` como ejemplo. `<obligatorio>` · `[opcional]` · `[x=valor]` valor por defecto.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!addmaptrack <server_ip> [channel]` | Adds a server to track map changes. Alias: `añadirmaptrack`. | Admin o permiso Administrator |
| `!forcemaptrack` | Forces a map tracking update in the current channel or thread. Alias: `forzarmaptrack`. | Mod o permiso Gestionar mensajes |
| `!maptracks` | Lists all servers with active map tracking. Alias: `listarmaptracks`. | Todos |
| `!removemaptrack <channel>` | Removes all map tracks from a channel or thread. Alias: `borrarmaptrack`. | Admin o permiso Administrator |
