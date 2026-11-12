# EquiposRoles

Solicitudes de rol de equipo confirmadas por el propio equipo. El jugador pide el rol desde un panel, la petición llega al canal privado de ese equipo y sus miembros la confirman o rechazan. El bot solo entrega el rol cuando el equipo confirma, así nadie depende del staff y ningún rol se da a ciegas.

> Prefijo de ejemplo `!` (el de La Trini). Es un cog híbrido: también funciona con `/` tras `!slash enablecog equipos_roles` y `!slash sync`.

## Cómo funciona

Todo funciona con paneles y botones, sin escribir comandos.

1. Un admin registra cada equipo (rol + canal privado) desde el **panel de administración**.
2. El admin publica el panel en el canal de solicitudes.
3. El jugador pulsa **Pedir rol de equipo** y elige su equipo en un desplegable.
4. El bot publica una tarjeta visual en el canal privado del equipo, con su estado y sus botones.
5. Cualquier miembro que ya tenga el rol del equipo pulsa **Confirmar** o **Rechazar**.
6. Al confirmar, el bot asigna el rol, actualiza la tarjeta y avisa al jugador por mensaje directo.

La petición **no da el rol por sí sola**: siempre necesita la confirmación del equipo.

## Instalación

```
!repo add killerbite-cogs https://github.com/killerbite95/killerbite-cogs
!cog install killerbite-cogs equipos_roles
!load equipos_roles
```

**Requisitos:** `embed_links` y `manage_roles`. El rol del bot debe estar **por encima** de los roles de equipo, y el bot necesita poder escribir y embeber en el canal de cada equipo y en el canal de logs.

## Puesta en marcha paso a paso

1. Abre el panel de administración: `!teamroles admin` (o `/teamroles admin`).
2. Pulsa **Registrar equipo**: escribe el nombre y elige el rol y el canal con los desplegables.
3. Pulsa **Publicar panel** y elige el canal de solicitudes.
4. Puedes quitarlo cuando quieras con **Eliminar panel** (borra el mensaje y limpia los ids).
5. Los jugadores pulsan el botón y eligen su equipo.
6. El equipo confirma o rechaza en su canal privado.

También puedes hacerlo por comandos: `!teamroles add "La Trini" @RolLaTrini #canal-la-trini` y `!teamroles panel #pedir-rol`.

Todo se puede consultar en el dashboard, página **EquiposRoles → equipos_roles** (solo lectura, para mods/admins).

## Referencia completa de comandos

Prefijo `!` como ejemplo. `<obligatorio>` · `[opcional]`.

| Comando | Descripción | Permiso |
|---|---|---|
| `!teamroles pedir [equipo]` | Pide el rol de un equipo. Sin argumento abre el desplegable. | Todos |
| `!teamroles lista` | Lista los equipos registrados con su rol y su canal. | Todos |
| `!teamroles admin` | Abre el panel de administración (publicar panel, registrar/eliminar equipos, ajustes y solicitudes, todo con botones). | Admin |
| `!teamroles panel [canal]` | Publica (o reemplaza) el panel de solicitudes. | Admin |
| `!teamroles add <nombre> <rol> <canal>` | Registra un equipo con su rol y su canal privado. | Admin |
| `!teamroles remove <nombre>` | Elimina un equipo y cancela sus solicitudes pendientes. | Admin |
| `!teamroles config [canal_panel] [canal_log] [cooldown] [caducidad] [quitar_log]` | Muestra o cambia los ajustes. `cooldown` en minutos, `caducidad` en horas. | Admin |
| `!teamroles solicitudes [estado]` | Lista solicitudes por estado: `pending`, `approved`, `rejected`, `expired`, `cancelled` o `all`. | Admin |
| `!teamroles cancelar <id>` | Cancela una solicitud pendiente. | Admin |

## Límites y detalles

- **Sin capitanes:** cualquier miembro con el rol del equipo puede confirmar o rechazar. También puede hacerlo un admin o moderador del bot (los de `!set addadmin` / `!set addmod`), sin pertenecer al equipo.
- **Anti-spam:** una sola solicitud pendiente por usuario y una espera configurable entre solicitudes (60 minutos por defecto). El límite se aplica aunque la anterior se haya rechazado.
- **Caducidad:** 48 horas por defecto. Al caducar se desactivan los botones y la solicitud queda como `expired`.
- **Auditoría:** si configuras `canal_log`, cada creación, aprobación, rechazo, caducidad y cancelación deja un embed con quién la resolvió.
- **Persistencia:** las vistas son persistentes y el cog barre las solicitudes al cargarse, así que un reload o un reinicio no deja tarjetas muertas.
- Si un equipo pierde su rol o su canal, sus solicitudes fallan con un aviso claro y un admin puede cancelarlas.
