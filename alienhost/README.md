# AlienHost

Controla tus servidores de AlienHost (Pelican) desde Discord usando **tu propia clave API de cliente**.

> Prefijo de ejemplo `!` (el de La Trini). Todos los comandos son hibridos: tambien funcionan como `/` si activas los slash con `[p]slash enablecog <cog>` y `[p]slash sync`.

## Vincular
1. En el panel (`https://pelican.alienhost.es`) ve a **Perfil → Claves API → Crear** (puedes limitarla a la IP del bot).
2. En Discord: `!alienhost link` → pulsa **Conectar cuenta** y se abre un **formulario privado** (modal) con la URL del panel y la clave. Nunca se escriben en el chat.
3. La clave se valida contra `/api/client/account` y se guarda **cifrada** (Fernet, llave en archivo aparte con permisos 600).

Con `!`, las respuestas con datos de tu cuenta (servidores, backups, alertas…) no se publican: aparece un boton **Ver en privado** que las muestra solo a ti.

Si alguien pega una clave `pacc_`/`papp_` en cualquier canal, el bot la borra y avisa para revocarla.

Solo se aceptan paneles de la lista permitida (`!alienhost set panels list`), evitando que el bot envie claves a hosts arbitrarios.

## Comandos
| Comando | Descripcion |
|---|---|
| `!alienhost servers` | Lista con estado y selector → panel con Iniciar/Reiniciar/Detener/Kill, Backups, Actualizar, Alertas. |
| `!alienhost server <srv>` · `power <srv> <start|stop|restart|kill>` | Stop/restart/kill piden confirmacion. Limite: 1 accion/10 s y 20/hora por usuario. |
| `!alienhost backups <srv>` | Ultimos backups y boton para crear uno (sin descargas desde Discord). |
| `!alienhost alerts [srv]` | Alertas por DM: offline, RAM > 90 % 10 min, CPU > 95 % 10 min, backup fallido, reinicio. |
| `!alienhost account` · `unlink` | Estado de la vinculacion / borrar la clave. |
| `!alienhost admin setkey` (owner) · `nodes` · `incidents` · `server` · `user` | Administracion con clave de aplicacion (`papp_`), tambien pedida en formulario. Requiere rol configurado (+ Trusted Admin de TriniSecurity si `require_trusted`). |
| `!alienhost set panels|pollinterval|logchannel|adminrole|show` | Configuracion. Las acciones se registran en el canal de auditoria. |

Usa la Client API de Pelican: `GET /api/client`, `/servers/{uuid}`, `/resources`, `POST /power`, `GET|POST /backups`, `GET /account`. No se expone la consola.
