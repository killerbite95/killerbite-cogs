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
| `!alienhost server <srv>` · `power <srv> <start/stop/restart/kill>` | Stop/restart/kill piden confirmacion. Limite: 1 accion/10 s y 20/hora por usuario. |
| `!alienhost backups <srv>` | Ultimos backups y boton para crear uno (sin descargas desde Discord). |
| `!alienhost alerts [srv]` | Alertas por DM: offline, RAM > 90 % 10 min, CPU > 95 % 10 min, backup fallido, reinicio. |
| `!alienhost account` · `unlink` | Estado de la vinculacion / borrar la clave. |
| `!alienhost admin setkey` (owner) · `nodes` · `incidents` · `server` · `user` | Administracion con clave de aplicacion (`papp_`), tambien pedida en formulario. Requiere rol configurado (+ Trusted Admin de TriniSecurity si `require_trusted`). |
| `!alienhost set panels/pollinterval/logchannel/adminrole/show` | Configuracion. Las acciones se registran en el canal de auditoria. |

Usa la Client API de Pelican: `GET /api/client`, `/servers/{uuid}`, `/resources`, `POST /power`, `GET|POST /backups`, `GET /account`. No se expone la consola.

## Referencia completa de comandos

Prefijo `!` como ejemplo. `<obligatorio>` · `[opcional]` · `[x=valor]` valor por defecto.

**Admin de AlienHost** = owner del bot, o miembro con el rol de `!alienhost set adminrole` (y Trusted Admin de TriniSecurity si `require_trusted` esta activo).

### `!alienhost` — AlienHost: tus servidores de juego desde Discord.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!alienhost account` | Ver el estado de tu vinculacion. | Todos (cuenta vinculada) |
| `!alienhost alerts [server]` | Configurar alertas por DM de un servidor (o ver las activas). | Todos (cuenta vinculada) |
| `!alienhost backups <server>` | Ver los ultimos backups de un servidor (y crear uno). | Todos (cuenta vinculada) |
| `!alienhost link` | Vincular tu cuenta con la URL del panel y una clave API de tu area cliente. | Todos |
| `!alienhost power <server> <signal>` | Enviar start, stop, restart o kill a un servidor. | Todos (cuenta vinculada) |
| `!alienhost server <server>` | Detalles de un servidor con acciones rapidas. | Todos (cuenta vinculada) |
| `!alienhost servers` | Listar tus servidores. | Todos (cuenta vinculada) |
| `!alienhost unlink` | Desvincular tu cuenta y borrar la clave guardada. | Todos (cuenta vinculada) |

### `!alienhost admin` — Administracion interna de AlienHost (clave de aplicacion).

| Comando | Descripcion | Permiso |
|---|---|---|
| `!alienhost admin incidents` | Servidores suspendidos, con instalacion fallida o nodos en mantenimiento. | Admin de AlienHost |
| `!alienhost admin nodes` | Estado de los nodos. | Admin de AlienHost |
| `!alienhost admin server <server_id>` | Ficha de un servidor (ID numerico o identificador). | Admin de AlienHost |
| `!alienhost admin setkey` | (Owner) Guardar la clave de aplicacion (papp_) mediante formulario privado. | Owner del bot |
| `!alienhost admin user <query>` | Buscar un cliente por email o usuario (o mencion de Discord vinculada). | Admin de AlienHost |

### `!alienhost set` — Configuracion de la integracion.

| Comando | Descripcion | Permiso |
|---|---|---|
| `!alienhost set adminrole [role] [require_trusted=True]` | Rol con acceso a `alienhost admin` y si ademas se exige Trusted Admin de Trini Security. | Administrador |
| `!alienhost set logchannel [channel]` | Canal donde se registran las acciones (power, backups, vinculaciones). | Admin / Gestionar servidor |
| `!alienhost set panels <action> [url]` | (Owner) Paneles permitidos: `add <url>`, `remove <url>`, `list`, `default <url>`. | Owner del bot |
| `!alienhost set pollinterval <seconds>` | (Owner) Cada cuanto se comprueban las alertas (minimo 60s). | Owner del bot |
| `!alienhost set show` | Ver la configuracion. | Todos |

Alias de grupos: `!alienhost` → `ah`.
