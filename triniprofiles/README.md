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
