# TriniSecurity

Capa defensiva encima del servidor. No es otro automod ni logger: audita permisos, protege roles, detecta nukes y reconstruye incidentes.

> Necesita **View Audit Log** (atribuye cada accion con `on_audit_log_entry_create`), ademas de Manage Roles/Webhooks/Channels y Kick para poder revertir.

> Prefijo de ejemplo `!` (el de La Trini). Todos los comandos son hibridos: tambien funcionan como `/` si activas los slash con `[p]slash enablecog <cog>` y `[p]slash sync`.

## Puesta en marcha paso a paso

1. Da al bot **View Audit Log**, Manage Roles, Manage Channels, Manage Webhooks, Kick Members y Manage Server, y sube su rol por encima de los roles a proteger.
2. Canal y rol de alertas: `!security config logchannel #seguridad` y `!security config alertrole @Staff`.
3. Primera revision: `!security audit` y `!security health`. Corrige primero los 🔴.
4. Autoridad: `!security authority add @usuario extra_owner` (solo Owner) y `!security authority add @usuario trusted_admin`.
5. Roles criticos: `!security protectedrole add @Administrador` (repite con cada rol importante).
6. Bots legitimos a la whitelist **antes** de Anti-Nuke: `!security whitelist add bots @MiBot`.
7. Activa la vigilancia: `!security watch enable` y `!security antinuke enable`.
8. (Opcional) Resumen semanal: `!security digest enable #seguridad`.
9. En una emergencia: `!security lockdown enable` → `!security timeline 15m` → `!security incident list` → `!security lockdown disable`.

> Tutorial completo de todos los modulos: [docs/GUIA_LA_TRINI.md](../docs/GUIA_LA_TRINI.md)

## Modulos
| Area | Comandos |
|---|---|
| Security Audit | `audit`, `health`, `user`, `role`, `channel`, `bot`, `webhooks`, `invites` — incluye origen real de cada permiso y escaladas de privilegios. |
| Authority | `authority add @u extra_owner/trusted_admin`, `remove`, `list`. Owner > Extra Owners > Trusted Admins > admins normales. |
| Protected Roles | `protectedrole add/remove/list/config`. Asignaciones no autorizadas se revierten. |
| Whitelists | `whitelist add/remove <users/roles/bots/webhooks/channels/invites> <objetivo>`, `whitelist temp @rol @usuario 1h`. |
| Security Watch | `watch enable/disable/level` — Administrator otorgado, @everyone, webhooks, bots, canales privados, jerarquia, invitaciones permanentes, cambios de config. |
| Anti-Nuke | `antinuke enable/status/threshold/score/levels/window/trustedimmune/reset`. Respuesta: 0-29 log · 30-49 alerta · 50-69 bloqueo (revierte) · 70+ quarantine. |
| Quarantine | `quarantine list/add/release` — retira roles peligrosos y los guarda. |
| Emergency Lockdown | `lockdown enable/disable/status` — bots, webhooks, roles protegidos e invitaciones bloqueados. Solo Owner/Extra Owners lo desactivan. |
| Timeline e incidentes | `timeline 15m [@u]`, `incident view/list/close/report`. Botones: comparar con backup, informe, liberar. |
| Digest y auditoria interna | `digest enable/disable/now`, `settingslog`, `status`. |

Otros cogs pueden aportar hallazgos a la auditoria implementando `trini_security_findings(guild)`.

## Dashboard

Pagina **status** (solo lectura): Watch, Anti-Nuke, lockdown, incidentes, cuarentena y ultimos eventos. Solo admins. Las acciones siguen haciendose en Discord.

## Referencia completa de comandos

Prefijo `!` como ejemplo. `<obligatorio>` · `[opcional]` · `[x=valor]` valor por defecto.

Niveles: **Staff de seguridad** = Administrador/Gestionar servidor o cualquier nivel de autoridad Trini · **Trusted Admin+**, **Extra Owner+**, **Owner** segun `!security authority`. El owner del bot cuenta como Extra Owner.

### `!security` — Trini Security: auditoria y proteccion del servidor.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!security audit` | Auditoria completa de seguridad del servidor. | Staff de seguridad |
| `!security bot <bot>` | Auditoria de un bot: permisos, whitelist y quien lo añadio. | Staff de seguridad |
| `!security channel <channel>` | Auditoria de un canal: overwrites, visibilidad y herencia. | Staff de seguridad |
| `!security health` | Health Score con sus penalizaciones y mejoras. | Staff de seguridad |
| `!security invites` | Listar invitaciones, marcando las permanentes. | Staff de seguridad |
| `!security role <role>` | Auditoria de un rol: permisos, jerarquia y roles que puede modificar. | Staff de seguridad |
| `!security settingslog` | Quien cambio la configuracion de Security (y de otros modulos Trini). | Staff de seguridad |
| `!security status` | Estado de todos los modulos de Trini Security. | Staff de seguridad |
| `!security timeline [period=15m] [member]` | Timeline de eventos de seguridad. Ej: `security timeline 15m @usuario`. | Staff de seguridad |
| `!security user <member>` | Permisos efectivos de un usuario y su origen real. | Staff de seguridad |
| `!security webhooks` | Listar webhooks del servidor y su estado de whitelist. | Staff de seguridad |

### `!security antinuke` — Deteccion de nukes por thresholds y risk score.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!security antinuke disable` | Desactivar Anti-Nuke. | Extra Owner+ |
| `!security antinuke enable` | Activar Anti-Nuke. | Extra Owner+ |
| `!security antinuke levels <alert> <block> <quarantine>` | Umbrales de respuesta: alerta, bloqueo y quarantine. | Extra Owner+ |
| `!security antinuke reset` | Restaurar thresholds, puntuaciones y niveles por defecto. | Extra Owner+ |
| `!security antinuke score <action> <points>` | Cambiar los puntos de riesgo de una accion. | Extra Owner+ |
| `!security antinuke status` | Ver thresholds, puntuaciones y niveles. | Staff de seguridad |
| `!security antinuke threshold <action> <per_minute> [per_hour=0]` | Cambiar threshold de una accion (0 = sin limite). | Extra Owner+ |
| `!security antinuke trustedimmune <enabled>` | Si los Trusted Admins son inmunes a Anti-Nuke. | Extra Owner+ |
| `!security antinuke window <duration>` | Ventana de acumulacion del risk score. Ej: `10m`. | Extra Owner+ |

### `!security authority` — Modelo de confianza: Owner, Extra Owners y Trusted Admins.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!security authority add <member> <extra_owner/trusted_admin>` | Añadir un Extra Owner (solo Owner) o Trusted Admin (Extra Owner+). | Owner (extra_owner) · Extra Owner+ (trusted_admin) |
| `!security authority list` | Listar la jerarquia de confianza. | Staff de seguridad |
| `!security authority remove <member>` | Quitar autoridad a un usuario. | Owner (quitar Extra Owner) · Extra Owner+ (quitar Trusted Admin) |

### `!security config` — Configuracion general de Trini Security.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!security config alertrole [role]` | Rol a mencionar en alertas criticas. | Extra Owner+ |
| `!security config botpolicy <kick/alert>` | Que hacer con bots no incluidos en whitelist (con Anti-Nuke activo). | Extra Owner+ |
| `!security config logchannel [channel]` | Canal de alertas de seguridad. | Extra Owner+ |
| `!security config quarantinerole [role]` | Rol opcional que se añade a los usuarios en quarantine. | Extra Owner+ |

### `!security digest` — Resumen semanal de seguridad.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!security digest disable` | Desactivar el digest semanal. | Extra Owner+ |
| `!security digest enable [channel]` | Activar el digest semanal (en el canal indicado o en el de alertas). | Extra Owner+ |
| `!security digest now [days=7]` | Ver el digest de los ultimos N dias. | Staff de seguridad |

### `!security incident` — Incidentes reconstruidos por Anti-Nuke.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!security incident close <incident_id>` | Cerrar un incidente. | Trusted Admin+ |
| `!security incident list` | Listar incidentes recientes. | Staff de seguridad |
| `!security incident report <incident_id>` | Generar informe en texto de un incidente. | Staff de seguridad |
| `!security incident view <incident_id>` | Ver un incidente. | Staff de seguridad |

### `!security lockdown` — Emergency Lockdown.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!security lockdown disable` | Salir del modo emergencia (Owner / Extra Owners). | Extra Owner+ |
| `!security lockdown enable [pause_invites=True]` | Activar el modo emergencia. | Trusted Admin+ |
| `!security lockdown status` | Estado del lockdown. | Staff de seguridad |

### `!security protectedrole` — Roles criticos que solo pueden gestionar usuarios autorizados.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!security protectedrole add <role>` | Proteger un rol. | Extra Owner+ |
| `!security protectedrole config <role> [allowed/self_assign/bots/temporary_whitelist/allow_user/allow_role] [value]` | Configurar un rol protegido. Sin opcion muestra la configuracion. allowed: niveles permitidos, ej. `extra_owner,trusted_admin` self_assign / bots / temporary_whitelist: true/false allow_user / allow_role: añade o quita (toggle) un usuario o rol autorizado | Staff (ver) · Extra Owner+ (cambiar) |
| `!security protectedrole list` | Listar roles protegidos. | Staff de seguridad |
| `!security protectedrole remove <role>` | Dejar de proteger un rol. | Extra Owner+ |

### `!security quarantine` — Usuarios en quarantine.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!security quarantine add <member> [reason=Manual]` | Poner manualmente a un usuario en quarantine (retira roles peligrosos). | Trusted Admin+ |
| `!security quarantine list` | Listar usuarios en quarantine. | Staff de seguridad |
| `!security quarantine release <user>` | Liberar a un usuario y restaurar sus roles. | Trusted Admin+ |

### `!security watch` — Vigilancia de cambios administrativos sensibles.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!security watch disable` | Desactivar Security Watch. | Extra Owner+ |
| `!security watch enable` | Activar Security Watch. | Extra Owner+ |
| `!security watch level <normal/max>` | Nivel de vigilancia. | Extra Owner+ |

### `!security whitelist` — Whitelists por tipo: users, roles, bots, webhooks, channels, invites.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!security whitelist add <users/roles/bots/webhooks/channels/invites> <target>` | Añadir a una whitelist. Ej: `security whitelist add bots @MiBot`. | Extra Owner+ |
| `!security whitelist list` | Ver todas las whitelists. | Staff de seguridad |
| `!security whitelist remove <users/roles/bots/webhooks/channels/invites> <target>` | Quitar de una whitelist. | Extra Owner+ |
| `!security whitelist temp <role> <member> [duration=1h]` | Whitelist temporal de un rol protegido. Ej: `security whitelist temp @Admin @Pepe 1h`. | Trusted Admin+ |

Alias de grupos: `!security protectedrole` → `protected-role`, `prole`.
