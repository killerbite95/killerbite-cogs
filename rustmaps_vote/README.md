# RustMaps Vote

Votaciones de mapas de Rust con botones, usando la API de rustmaps.com.

> Prefijo de ejemplo `!` (el de La Trini). Si un comando es hibrido tambien funciona con `/` tras `!slash enablecog <cog>` y `!slash sync`.

## Instalacion

```
!repo update killerbite-cogs
!cog install killerbite-cogs rustmaps_vote
!load rustmaps_vote
```

**Requisitos:** Una API key de [rustmaps.com](https://rustmaps.com). Solo administradores.

## Puesta en marcha paso a paso

1. Configura la API key (una vez para todo el bot): `!votemap setapi <tu_api_key>`.
2. Canal por defecto de las votaciones: `!votemap setchannel #votacion-mapas`.
3. Cuantos mapas puede votar cada persona: `!votemap maxvotes 1`.
4. Añade los candidatos pegando su URL de rustmaps: `!votemap add https://rustmaps.com/map/...` (repite con cada mapa). Revisalos con `!votemap list` y quita alguno con `!votemap remove <id>`.
5. Abre la votacion: `!votemap start`.
6. Cierrala y anuncia el ganador: `!votemap end` (o `!votemap cancel` para anularla sin ganador).
7. Revisa la configuracion con `!votemap settings`.

## Referencia completa de comandos

Prefijo `!` como ejemplo. `<obligatorio>` · `[opcional]` · `[x=valor]` valor por defecto.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!votemap add <url>` | Añade un mapa a la votación actual. | Admin o permiso Administrator |
| `!votemap cancel` | Cancela la votación o la preparación actual sin anunciar ganador. | Admin o permiso Administrator |
| `!votemap end` | Termina la votación, limpia los mensajes anteriores y anuncia al ganador. | Admin o permiso Administrator |
| `!votemap list` | Muestra los mapas de la votación actual. | Todos |
| `!votemap maxvotes <amount>` | Define cuántos mapas puede votar cada persona por votación (por defecto 1). | Admin o permiso Administrator |
| `!votemap remove <map_id>` | Quita un mapa de la votación actual (antes de empezar). | Admin o permiso Administrator |
| `!votemap setapi <key>` | Configura la API key global de RustMaps. | Admin o permiso Administrator |
| `!votemap setchannel [channel]` | Define el canal por defecto de las votaciones. | Admin o permiso Administrator |
| `!votemap settings` | Muestra la configuración de las votaciones. | Admin o permiso Administrator |
| `!votemap start` | Inicia la votación con embeds y botones. | Admin o permiso Administrator |
