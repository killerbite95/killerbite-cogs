# TriniEvents

Gestor de actividades: inscripciones, reservas, recordatorios y logistica. No gestiona brackets (eso sigue en ArenCup).

> Prefijo de ejemplo `!` (el de La Trini). Todos los comandos son hibridos: tambien funcionan como `/` si activas los slash con `[p]slash enablecog <cog>` y `[p]slash sync`.

## Puesta en marcha paso a paso

1. Zona horaria y canal: `!event settings timezone Europe/Madrid` y `!event settings channel #eventos`.
2. Recordatorios por DM: `!event settings reminders 1440,60,15`.
3. (Opcional) Staff: `!event settings staffrole @Staff true`.
4. (Opcional) Rol para inscritos: `!event settings participantrole @Participante` o `!event settings autorole true`.
5. (Opcional) Canales por evento: `!event settings tempchannels true delete`.
6. Crea el primer evento: `!event create` → **Abrir formulario** → nombre, fecha (`viernes 22:00`), plazas, duracion y descripcion.
7. Revisa todo con `!event settings show` y `!event list`.

> Tutorial completo de todos los modulos: [docs/GUIA_LA_TRINI.md](../docs/GUIA_LA_TRINI.md)

| Comando | Descripcion |
|---|---|
| `!event create [canal] [rol_requerido] [tipo]` | Formulario: nombre, fecha, plazas, duracion, descripcion. Botones ✅ Participar · ❌ Cancelar plaza · 🔔 Recordarme · ✋ Check-in. |
| `!event arencup [canal]` | Publica un torneo con check-in, inicio, equipos y boton **Ver torneo**. |
| `!event list` · `info` · `participants` | Consultar. |
| `!event edit` · `cancel` · `clone <id> <fecha>` · `repeat <id> weekly viernes 22:00` | Gestion. |
| `!event attend` · `remove` | Asistencia manual y quitar participantes (entra la reserva). |
| `!event stats [@usuario]` | Asistencia, cancelaciones, no-shows, top eventos/usuarios y asistencia por tipo. |
| `!event settings …` | `channel`, `timezone`, `reminders 1440,60,15`, `staffrole`, `participantrole`, `autorole`, `rolelead`, `tempchannels true delete/archive`, `duration`, `checkin`, `show`. |

Fechas: `02/10/2026 22:00`, `02/10 22:00`, `viernes 22:00`, `mañana 21:30`, `+2h`. Recordatorios por DM solo a inscritos y a quien pulso Recordarme.

## Referencia completa de comandos

Prefijo `!` como ejemplo. `<obligatorio>` · `[opcional]` · `[x=valor]` valor por defecto.

**Staff de eventos** = Gestionar eventos, Gestionar servidor, admin de Red o el rol de `!event settings staffrole`.

### `!event` — Trini Events: actividades de comunidad.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!event arencup [channel]` | Publicar un torneo de ArenCup (check-in, inicio, enlace y recordatorios). | Staff de eventos |
| `!event attend <event_id> <member>` | Marcar/desmarcar manualmente la asistencia de un participante. | Staff de eventos |
| `!event cancel <event_id> [reason]` | Cancelar un evento y avisar a los inscritos. | Staff de eventos |
| `!event clone <event_id> <when>` | Repetir un evento anterior en otra fecha. Ej: `event clone 12 viernes 22:00`. | Staff de eventos |
| `!event create [channel] [required_role] [tag]` | Crear un evento con formulario (nombre, fecha, plazas, duracion, descripcion). | Staff de eventos |
| `!event edit <event_id>` | Editar nombre, fecha, plazas, duracion y descripcion de un evento. | Staff de eventos |
| `!event info <event_id>` | Ver un evento. | Todos |
| `!event list` | Proximos eventos. | Todos |
| `!event participants <event_id>` | Participantes, reservas y check-in de un evento. | Todos |
| `!event remove <event_id> <member>` | Quitar a un participante (entra el primero de la lista de espera). | Staff de eventos |
| `!event repeat <event_id> <frequency> [weekday] [at]` | Hacer recurrente un evento: `event repeat 12 weekly friday 22:00`, `daily` o `off`. | Staff de eventos |
| `!event stats [member]` | Estadisticas de asistencia (del servidor o de un usuario). | Todos |

### `!event settings` — Configuracion de Trini Events.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!event settings autorole <enabled>` | Crear un rol temporal por evento (si no hay rol de participante fijo). | Admin / Gestionar servidor |
| `!event settings channel [channel]` | Canal donde se publican los eventos por defecto. | Admin / Gestionar servidor |
| `!event settings checkin <minutes>` | Minutos antes del inicio en los que se abre el check-in. | Admin / Gestionar servidor |
| `!event settings duration <minutes>` | Duracion por defecto de los eventos. | Admin / Gestionar servidor |
| `!event settings participantrole [role]` | Rol fijo que se da a los inscritos antes del evento y se retira al acabar. | Admin / Gestionar servidor |
| `!event settings reminders <minutes>` | Recordatorios en minutos antes, separados por comas. Ej: `1440,60,15` o `none`. | Admin / Gestionar servidor |
| `!event settings rolelead <minutes>` | Minutos antes del evento para asignar el rol y crear canales. | Admin / Gestionar servidor |
| `!event settings show` | Ver la configuracion actual. | Admin / Gestionar servidor |
| `!event settings staffrole [role] [ping=False]` | Rol de staff de eventos (puede gestionarlos) y si se le avisa en los recordatorios. | Admin / Gestionar servidor |
| `!event settings tempchannels <enabled> [archive_mode]` | Crear categoria y canales temporales por evento. Al acabar: `delete` o `archive`. | Admin / Gestionar servidor |
| `!event settings timezone <timezone>` | Zona horaria IANA para interpretar fechas (ej. `Europe/Madrid`). | Admin / Gestionar servidor |
