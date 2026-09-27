# TriniProfiles

Configuracion por perfiles de La Trini. Un perfil es una **plantilla inicial**, no un estado rigido: despues puedes cambiar cualquier modulo.

> Prefijo de ejemplo `!` (el de La Trini). Todos los comandos son hibridos: tambien funcionan como `/` si activas los slash con `[p]slash enablecog <cog>` y `[p]slash sync`.

## Comandos

| Comando | Descripcion |
|---|---|
| `!trini setup` | Asistente: Gaming, Esports/Torneos, Roleplay, Hosting/Soporte, General o Personalizado. Previsualiza y aplica (`Aplicar`, `+ recomendados` o `exacto`). |
| `!trini modules` | Panel para activar/desactivar modulos por categoria. |
| `!trini enable <modulo>` / `disable` | Activa (con sus dependencias) o desactiva (si nada depende de el). |
| `!trini status` · `securitylevel` · `syncred` · `log` | Estado, nivel de seguridad recomendado, sincronizacion con `enablecog/disablecog` de Red e historial. |
| `!profile save/apply/list/delete <nombre>` | Presets reutilizables entre servidores. |
| `!profile export` / `import` | JSON con modulos y configuracion de los cogs activos. Canales y roles se re-mapean por nombre al importar en otro servidor. |

## Integracion
- Al aplicar un perfil emite `trini_profile_applied`; TriniSecurity activa Watch (nivel `high`) o Watch + Anti-Nuke (`strict`).
- En modo *exacto* crea antes un snapshot con TriniBackups.
- Protocolo de exportacion para otros cogs: `trini_export(guild)` / `trini_import(guild, data, same_guild=...)`.

## Referencia completa de comandos

Prefijo `!` como ejemplo. `<obligatorio>` · `[opcional]` · `[x=valor]` valor por defecto.

### `!profile` — Presets personalizados y export/import de configuracion.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!profile apply <name>` | Aplicar un preset guardado. | Admin / Gestionar servidor |
| `!profile delete <name>` | Eliminar un preset guardado. | Admin / Gestionar servidor |
| `!profile export` | Exportar modulos y configuracion de los cogs activos a JSON. | Admin / Gestionar servidor |
| `!profile import [file (adjunto)]` | Importar un JSON generado con `profile export`. | Admin / Gestionar servidor |
| `!profile list` | Listar presets y perfiles predefinidos. | Admin / Gestionar servidor |
| `!profile save <name>` | Guardar la configuracion actual como preset reutilizable. | Admin / Gestionar servidor |

### `!trini` — Configuracion general de La Trini.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!trini disable <module>` | Desactivar un modulo (si nada depende de el). | Admin / Gestionar servidor |
| `!trini enable <module>` | Activar un modulo (y sus dependencias). | Admin / Gestionar servidor |
| `!trini log` | Historial de cambios de configuracion de Profiles. | Admin / Gestionar servidor |
| `!trini modules` | Ver y activar/desactivar modulos. | Admin / Gestionar servidor |
| `!trini securitylevel <level>` | Nivel de seguridad recomendado: standard, high o strict. | Admin / Gestionar servidor |
| `!trini setup` | Asistente inicial: elige como se utiliza este Discord. | Admin / Gestionar servidor |
| `!trini status` | Resumen del perfil del servidor. | Admin / Gestionar servidor |
| `!trini syncred <enabled>` | Sincronizar modulos con `enablecog`/`disablecog` de Red en este servidor. | Admin / Gestionar servidor |
