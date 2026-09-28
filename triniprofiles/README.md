# TriniProfiles

Configuracion por perfiles de La Trini. Un perfil es una **plantilla inicial**, no un estado rigido: despues puedes cambiar cualquier modulo.

> Prefijo de ejemplo `!` (el de La Trini). Todos los comandos son hibridos: tambien funcionan como `/` si activas los slash con `[p]slash enablecog <cog>` y `[p]slash sync`.

## Puesta en marcha paso a paso

1. Mira el estado real de cada modulo: `!trini status`.
2. (Opcional) Aplica una plantilla: `!trini setup` → elige el tipo de servidor → **Aplicar** / **+ recomendados** / **exacto**.
3. Ajusta a mano: `!trini modules` (o `!trini enable <modulo>` / `!trini disable <modulo>`).
4. (Opcional) Guarda la seleccion de modulos: `!profile save <nombre>` y aplicala en otro servidor con `!profile apply <nombre>`.
5. Para copiar tambien la configuracion de los cogs a otro servidor: `!profile export` en el origen y `!profile import` (adjuntando el JSON) en el destino.

> Tutorial completo de todos los modulos: [docs/GUIA_LA_TRINI.md](../docs/GUIA_LA_TRINI.md)

## Comandos

| Comando | Descripcion |
|---|---|
| `!trini setup` | Asistente: Gaming, Esports/Torneos, Roleplay, Hosting/Soporte, General, Todo activado o Personalizado. Previsualiza y aplica (`Aplicar`, `+ recomendados` o `exacto`). |
| `!trini modules` | Panel para activar/desactivar modulos por categoria. |
| `!trini enable <modulo>` / `disable` | Activa (con sus dependencias) o desactiva (si nada depende de el). |
| `!trini status` · `securitylevel` · `syncred` · `log` | Estado, nivel de seguridad recomendado, sincronizacion con `enablecog/disablecog` de Red e historial. |
| `!profile save/apply/list/delete <nombre>` | Presets reutilizables entre servidores. |
| `!profile export` / `import` | JSON con modulos y configuracion de los cogs activos. Canales y roles se re-mapean por nombre al importar en otro servidor. |

## Catalogo de modulos

El catalogo (`triniprofiles/registry.py`) cubre 73 modulos, agrupados por su origen:

- **Trini** (`profiles`, `security`, `backups`, `events`, `alienhost`) y **killerbite-cogs** (`apiv2`, `gameservermonitor`, `tickets`, `suggestions`, `giveaways`, `honeypot`, `autonick`, `colacoins`, `adv_check`, `autoprune`, `blackjack`, `day_counter`, `listroles`, `maptrack`, `rustmaps`, `trickortreat`): nombre de clase conocido con certeza.
- **Red** (`mod`, `warnings`, `reports`, `modlog`, `mutes`, `filter`, `cleanup`, `admin`, `alias`, `customcom`, `general`, `trivia`, `image`, `audio`, `streams`, `economy`, `downloader`, `permissions`): vienen de serie con Red-DiscordBot.
- **Terceros** (30 cogs: `captcha`, `welcome`, `rolesbuttons`, `roleutils`, `autoroom`, `sticky`, `linkwarner`, `youtube`, `assistant`, `tags`, `reminders`, `frases`, `easterhunt`...): nombre de clase y paquete tomados de sus cogs reales. Se buscan primero por clase y, si no, por el paquete del que viene el cog cargado.
- **Conceptuales** (`applications`, `forms`, `status`, `incidents`, `arencup`): categorias del roadmap para las que aun no hay un cog concreto asignado; se muestran siempre como no cargadas hasta que edites `registry.py` con el paquete real que uses.

`!trini status` y `!trini modules` muestran el **estado real** de cada modulo en el servidor, preguntando a Red (no solo al apunte de Profiles):

| Icono | Significado |
|---|---|
| 🟢 | Cargado y habilitado en este servidor: sus comandos funcionan. |
| 🔴 | Cargado pero desactivado en este servidor (`disablecog`, por Profiles o a mano). |
| 🟠 | Activado en Profiles pero el cog no esta cargado en el bot. |
| ⚫ | No cargado. |

Aplicar un perfil vuelve a habilitar en Red todos sus modulos, aunque alguien los hubiera desactivado a mano con `disablecog`. Si un modulo aparece como no cargado, el mensaje indica como conseguirlo segun su origen (instalar de killerbite-cogs, cargarlo porque ya viene con Red, o instalar el repo de terceros correspondiente).

## Perfil "Todo activado"

`all_on` (🟢) es un preset predefinido que marca **todos los modulos no-core como ON**. Pensado para probar el bot entero o para servidores que quieren tenerlo todo disponible desde el primer dia; aparece junto al resto en `!trini setup` y `!profile list`. Como con cualquier perfil, es solo el punto de partida: despues ajustas con `!trini modules`.

## Exportar cogs de terceros

Los cogs de terceros no implementan el protocolo Trini, asi que `!profile export` copia su configuracion tal cual, sin los datos que se generan solos (historiales, contadores, caches...). Para los que guardan cosas especiales hay adaptadores en `triniprofiles/third_party.py`, sacados de su configuracion real:

| Cog | Que se hace |
|---|---|
| Welcome | No copia el ultimo mensaje ni los contadores de entradas y salidas; conserva los del servidor destino. |
| Sticky | Copia el mensaje fijado de cada canal (se guarda por canal), sin el ultimo mensaje enviado. |
| LinkWarner | Copia tambien las excepciones por canal. |
| AutoRoom | Copia las salas origen (tipo, formato de nombre, categoria...). |
| RoleUtils | Copia los roles "sticky"; los reaction roles dependen de mensajes y no se copian. |
| RolesButtons, UrlButtons, DiscordModals | Van ligados a mensajes concretos: solo se restauran en el mismo servidor; en otro servidor avisa de que hay que recrearlos. |
| DisboardReminder | No copia la hora del proximo bump. |
| YouTube | Las suscripciones son globales del bot: avisa de que hay que volver a suscribir. |

Los canales y roles se re-mapean por nombre tambien dentro de la configuracion por canal.

## Integracion
- Al aplicar un perfil emite `trini_profile_applied`; TriniSecurity activa Watch (nivel `high`) o Watch + Anti-Nuke (`strict`).
- En modo *exacto* crea antes un snapshot con TriniBackups.
- Protocolo de exportacion para otros cogs: `trini_export(guild)` / `trini_import(guild, data, same_guild=...)`.

## Dashboard

Pagina **modules**: estado real de cada modulo por categoria, activar/desactivar y ultimos cambios. Solo admins (o *Gestionar servidor*).

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
