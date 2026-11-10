# ScrimsLoL

Board de scrims de League of Legends por servidor. Primera entrega: equipos con capitán, roster de titulares y suplentes. Sobre estas tablas se construye la board de scrims (posts, apuntados, cierre de partida y fotos).

> Prefijo de ejemplo `!` (el de La Trini). Es un cog híbrido: también funciona con `/` tras `!slash enablecog scrims_lol` y `!slash sync`.

## Instalación

```
!repo add killerbite-cogs https://github.com/killerbite95/killerbite-cogs
!cog install killerbite-cogs scrims_lol
!load scrims_lol
```

**Requisitos:** permiso `embed_links`. No hay gate de roles: cualquiera puede crear un equipo.

## Puesta en marcha paso a paso

1. Crea tu equipo: `!scrims team create "La Trini" LT` (o `/scrims team create`). Eres el capitán.
2. Añade titulares y suplentes: `!scrims team add @usuario` (titular) o `/scrims team add`, eligiendo Titular/Suplente en el desplegable.
3. Consulta la tarjeta: `!scrims team info` (la tuya) o `!scrims team info @usuario`.
4. Todos los equipos del servidor: `!scrims team list`.
5. Gestiona el equipo: `!scrims team transfer @usuario` (cede la capitanía), `!scrims team leave` (salir) o `!scrims team delete` (borrar, con confirmación).

Todo está también en el dashboard, página **ScrimsLoL → teams** (solo lectura, para mods/admins).

## Referencia completa de comandos

Prefijo `!` como ejemplo. `<obligatorio>` · `[opcional]`.

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

**Nota:** un usuario pertenece como mucho a un equipo por servidor, pero puede jugar como invitado en cualquier scrim.

## Próximamente

Board de scrims: posts de `equipo`, `mix` o `abierto`, apuntados gestionados por el bot, TTL, hilo privado, y cierre de partida con marcador obligatorio y fotos opcionales.
