# TriniBackups

Snapshots estructurales comparables. No promete restaurar todo Discord: guarda estructura, compara y restaura **sin borrar nada**.

> Prefijo de ejemplo `!` (el de La Trini). Todos los comandos son hibridos: tambien funcionan como `/` si activas los slash con `[p]slash enablecog <cog>` y `[p]slash sync`.

## Puesta en marcha paso a paso

1. Da al bot Manage Roles y Manage Channels, con su rol por encima de los roles que quieras poder restaurar.
2. Primer backup: `!backup create Estado inicial`.
3. Backups automaticos: `!backup schedule daily 4` (04:00 UTC) y `!backup retention 7 4 6`.
4. Comprueba cambios cuando quieras: `!backup diff` (ultimo backup vs ahora).
5. Si algo sale mal: `!backup list` → `!backup restore <id>` → elige que restaurar en los botones → **Continuar**. Nunca borra nada.

> Tutorial completo de todos los modulos: [docs/GUIA_LA_TRINI.md](../docs/GUIA_LA_TRINI.md)

| Comando | Descripcion |
|---|---|
| `!backup create [nombre]` | Roles, categorias, canales, foros, overwrites, bots y configuracion de modulos Trini. |
| `!backup list` · `inspect` · `status` · `export` | Consultar y descargar. |
| `!backup diff [id]` | Diferencias del backup (por defecto el ultimo) con el estado actual. |
| `!backup compare <a> <b>` | Diferencias entre dos backups. |
| `!backup schedule daily/weekly/off [hora UTC]` | Backups automaticos. Retencion GFS con `!backup retention 7 4 6`. |
| `!backup restore <id>` | Previsualizacion con opciones (roles, canales, permisos, jerarquia, config Trini) y confirmacion. Crea un backup `pre-restore` antes. Solo crea y modifica. |
| `!backup delete <id>` | Con confirmacion. |

Los archivos se guardan comprimidos en la carpeta de datos del cog. Restaurar requiere Owner/Extra Owner/Trusted Admin si TriniSecurity esta cargado.

## Dashboard

Pagina **backups**: listar, crear y programar backups. Hace falta *Administrador*, como en los comandos. Restaurar solo desde Discord, con previsualizacion.

## Referencia completa de comandos

Prefijo `!` como ejemplo. `<obligatorio>` · `[opcional]` · `[x=valor]` valor por defecto.

### `!backup` — Snapshots estructurales del servidor.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!backup compare <old> <new>` | Comparar dos backups entre si. | Administrador |
| `!backup create [name]` | Crear un snapshot. Ej: `backup create Antes del torneo`. | Administrador |
| `!backup delete <snapshot>` | Eliminar un backup. | Administrador |
| `!backup diff [snapshot]` | Comparar un backup (por defecto el ultimo) con el estado actual. | Administrador |
| `!backup export [snapshot]` | Descargar un backup en JSON. | Administrador |
| `!backup inspect [snapshot]` | Ver el contenido de un backup. | Administrador |
| `!backup list` | Listar backups. | Administrador |
| `!backup restore <snapshot>` | Restauracion segura: previsualiza y solo crea/modifica, nunca elimina. | Owner / Extra Owner / Trusted Admin (Admin sin Security) |
| `!backup retention <daily> <weekly> <monthly>` | Politica de retencion de backups automaticos. | Administrador |
| `!backup schedule <mode> [hour]` | Backups automaticos: `off`, `daily` o `weekly`, a una hora UTC (0-23). | Administrador |
| `!backup status` | Estado de los backups del servidor. | Administrador |
