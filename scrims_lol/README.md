# ScrimsLoL

Board de scrims de League of Legends por servidor. Incluye equipos con capitán, roster de titulares y suplentes, y la board completa de scrims: posts de `equipo`, `mix` o `abierto`, apuntados, TTL, hilo privado al emparejar, cierre con marcador obligatorio y fotos opcionales por partida.

> Prefijo de ejemplo `!` (el de La Trini). Es un cog híbrido: también funciona con `/` tras `!slash enablecog scrims_lol` y `!slash sync`.

## Mensajes privados y post público

Los mensajes de gestión (crear equipo, ver equipos, errores, confirmaciones) son **privados**: efímeros en slash y autoborrados a los 20 segundos en prefijo. Lo único que se publica en el canal es el **post de la scrim**.

## Instalación

```
!repo add killerbite-cogs https://github.com/killerbite95/killerbite-cogs
!cog install killerbite-cogs scrims_lol
!load scrims_lol
```

**Requisitos:** `embed_links`. Sin gate de roles: cualquiera puede crear un equipo y publicar una scrim.

## Puesta en marcha paso a paso

1. Crea tu equipo: `!scrims team create "La Trini" LT` (o `/scrims team create`). Eres el capitán.
2. Añade titulares y suplentes: `!scrims team add @usuario` (titular) o `/scrims team add`, eligiendo Titular/Suplente en el desplegable.
3. Publica una scrim: `!scrims create lado:mix busca:team cuando:+90`. Sale un post público con botones.
4. Rellena el rival:
   - Si `busca` es un equipo, un capitán pulsa **Aceptar como equipo**.
   - Si `busca` es mix o abierto, los jugadores pulsan **Apuntarme** hasta llegar a 5.
5. Al emparejar se crea un **hilo privado** con los dos lados, el contacto y el formato.
6. Al terminar, **Cerrar** (pide el marcador) y, si quieres, adjunta capturas con `!scrims photo`.
7. La scrim caduca sola: al llegar la hora, o 3 horas después si ya estaba emparejada.
8. (Opcional, admins) La hora se interpreta en la zona horaria del servidor (por defecto `Europe/Madrid`). Cámbiala con `!scrims timezone Europe/Madrid` o consulta la actual con `!scrims timezone`.

Todo está también en el dashboard, página **ScrimsLoL → teams** (solo lectura, para mods/admins).

## Referencia completa de comandos

Prefijo `!` como ejemplo. `<obligatorio>` · `[opcional]`.

### Scrims

| Comando | Descripción | Permiso |
|---|---|---|
| `!scrims create [lado] [busca] [cuando] [formato] [fearless] [rango] [contacto]` | Publica una scrim en el canal. `cuando`: `+90`, `+2h`, `21:00`, `15/11 21:00` o `2026-11-15 21:00`. | Todos |
| `!scrims list` | Scrims abiertas del servidor. | Todos |
| `!scrims info <id>` | Detalle de una scrim. | Todos |
| `!scrims join <id>` | Te apuntas al lado rival (mix/abierto). | Todos |
| `!scrims leave <id>` | Sales del lado rival. | Apuntados |
| `!scrims close <id> <marcador>` | Cierra con marcador (por ejemplo `2-1`). | Participantes o staff |
| `!scrims cancel <id>` | Cancela la scrim. | Autor o staff |
| `!scrims photo <id> <partida> [enlace]` | Guarda una captura. En prefijo puedes adjuntar la imagen al comando. | Participantes o staff |
| `!scrims timezone [zona]` | Muestra o fija la zona horaria para interpretar las horas. | Admins |

### Equipos

| Comando | Descripción | Permiso |
|---|---|---|
| `!scrims team create <nombre> [etiqueta]` | Crea un equipo y te hace capitán. | Todos |
| `!scrims team info [miembro]` | Tarjeta de un equipo (el tuyo si no indicas miembro). | Todos |
| `!scrims team list` | Lista los equipos del servidor. | Todos |
| `!scrims team add <miembro> [rol]` | Añade un miembro como titular o suplente. | Capitán |
| `!scrims team remove <miembro>` | Elimina un miembro del equipo. | Capitán |
| `!scrims team leave` | Sales de tu equipo. | Miembro (no capitán) |
| `!scrims team transfer <miembro>` | Cede la capitanía a otro miembro. | Capitán |
| `!scrims team delete` | Elimina el equipo (con confirmación). | Capitán |

**Notas:** un usuario pertenece como mucho a un equipo por servidor, pero puede jugar como invitado en cualquier scrim. Un lado de equipo se guarda como equipo; un lado mix o abierto se guarda con sus apuntados.
