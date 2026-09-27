# TriniEvents

Gestor de actividades: inscripciones, reservas, recordatorios y logistica. No gestiona brackets (eso sigue en ArenCup).

| Comando | Descripcion |
|---|---|
| `/event create [canal] [rol_requerido] [tipo]` | Formulario: nombre, fecha, plazas, duracion, descripcion. Botones ✅ Participar · ❌ Cancelar plaza · 🔔 Recordarme · ✋ Check-in. |
| `/event arencup [canal]` | Publica un torneo con check-in, inicio, equipos y boton **Ver torneo**. |
| `/event list` · `info` · `participants` | Consultar. |
| `/event edit` · `cancel` · `clone <id> <fecha>` · `repeat <id> weekly viernes 22:00` | Gestion. |
| `/event attend` · `remove` | Asistencia manual y quitar participantes (entra la reserva). |
| `/event stats [@usuario]` | Asistencia, cancelaciones, no-shows, top eventos/usuarios y asistencia por tipo. |
| `/event settings …` | `channel`, `timezone`, `reminders 1440,60,15`, `staffrole`, `participantrole`, `autorole`, `rolelead`, `tempchannels true delete|archive`, `duration`, `checkin`, `show`. |

Fechas: `02/10/2026 22:00`, `02/10 22:00`, `viernes 22:00`, `mañana 21:30`, `+2h`. Recordatorios por DM solo a inscritos y a quien pulso Recordarme.
