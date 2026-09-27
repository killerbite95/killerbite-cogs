# TriniSecurity

Capa defensiva encima del servidor. No es otro automod ni logger: audita permisos, protege roles, detecta nukes y reconstruye incidentes.

> Necesita **View Audit Log** (atribuye cada accion con `on_audit_log_entry_create`), ademas de Manage Roles/Webhooks/Channels y Kick para poder revertir.

> Prefijo de ejemplo `!` (el de La Trini). Todos los comandos son hibridos: tambien funcionan como `/` si activas los slash con `[p]slash enablecog <cog>` y `[p]slash sync`.

## Inicio rapido
```
!security config logchannel #seguridad
!security config alertrole @Staff
!security audit
!security protectedrole add @Administrador
!security watch enable
!security antinuke enable
```

## Modulos
| Area | Comandos |
|---|---|
| Security Audit | `audit`, `health`, `user`, `role`, `channel`, `bot`, `webhooks`, `invites` — incluye origen real de cada permiso y escaladas de privilegios. |
| Authority | `authority add @u extra_owner|trusted_admin`, `remove`, `list`. Owner > Extra Owners > Trusted Admins > admins normales. |
| Protected Roles | `protectedrole add/remove/list/config`. Asignaciones no autorizadas se revierten. |
| Whitelists | `whitelist add/remove <users|roles|bots|webhooks|channels|invites> <objetivo>`, `whitelist temp @rol @usuario 1h`. |
| Security Watch | `watch enable/disable/level` — Administrator otorgado, @everyone, webhooks, bots, canales privados, jerarquia, invitaciones permanentes, cambios de config. |
| Anti-Nuke | `antinuke enable/status/threshold/score/levels/window/trustedimmune/reset`. Respuesta: 0-29 log · 30-49 alerta · 50-69 bloqueo (revierte) · 70+ quarantine. |
| Quarantine | `quarantine list/add/release` — retira roles peligrosos y los guarda. |
| Emergency Lockdown | `lockdown enable/disable/status` — bots, webhooks, roles protegidos e invitaciones bloqueados. Solo Owner/Extra Owners lo desactivan. |
| Timeline e incidentes | `timeline 15m [@u]`, `incident view/list/close/report`. Botones: comparar con backup, informe, liberar. |
| Digest y auditoria interna | `digest enable/disable/now`, `settingslog`, `status`. |

Otros cogs pueden aportar hallazgos a la auditoria implementando `trini_security_findings(guild)`.
