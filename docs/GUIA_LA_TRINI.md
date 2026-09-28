# Guia de puesta en marcha de La Trini

Tutorial paso a paso para dejar funcionando los modulos de La Trini en un servidor:
**Profiles**, **Security**, **Backups**, **Events** y **AlienHost**.

> Los ejemplos usan el prefijo `!`. Todos los comandos son hibridos: si activas los slash
> (`!slash enablecog <cog>` y `!slash sync`) tambien funcionan con `/`.

Orden recomendado (cada paso se apoya en el anterior):

1. [Instalar los cogs](#1-instalar-los-cogs)
2. [Profiles: elegir que se usa en el servidor](#2-profiles-elegir-que-se-usa-en-el-servidor)
3. [Security: proteger el servidor](#3-security-proteger-el-servidor)
4. [Backups: guardar el estado](#4-backups-guardar-el-estado)
5. [Events: actividades de comunidad](#5-events-actividades-de-comunidad)
6. [AlienHost: servidores de juego desde Discord](#6-alienhost-servidores-de-juego-desde-discord)
7. [Copiar la configuracion a otro servidor](#7-copiar-la-configuracion-a-otro-servidor)
8. [Dashboard web](#8-dashboard-web)
9. [Preguntas frecuentes](#9-preguntas-frecuentes)

---

## 1. Instalar los cogs

Solo el owner del bot. Una vez por bot (no por servidor).

```
!repo update killerbite-cogs
!pipinstall cryptography
!cog install killerbite-cogs triniprofiles trinisecurity trinibackups trinievents alienhost
!load triniprofiles trinisecurity trinibackups trinievents alienhost
```

- `cryptography` solo lo necesita AlienHost (cifra las claves API). Si no lo instalas, AlienHost no carga.
- Comprueba que todo cargo con `!cogs`.

### Permisos que necesita el bot

Dale al rol del bot estos permisos y **colocalo por encima** de los roles que tenga que gestionar
(roles protegidos, roles de staff, roles que restaura un backup...):

| Permiso | Para que |
|---|---|
| View Audit Log | Security atribuye cada accion a su autor. **Sin esto Security no funciona.** |
| Manage Roles | Revertir roles, quarantine, restaurar backups, roles de eventos. |
| Manage Channels | Restaurar canales, canales temporales de eventos. |
| Manage Webhooks | Detectar y borrar webhooks no autorizados. |
| Kick Members | Expulsar bots no autorizados. |
| Manage Server | Listar invitaciones y pausarlas en un lockdown. |
| Manage Messages | Borrar claves API pegadas por error en el chat (AlienHost). |

---

## 2. Profiles: elegir que se usa en el servidor

Profiles decide **que modulos estan activos** en cada servidor. Un perfil es solo un punto de
partida: despues puedes cambiar lo que quieras.

**Paso 1 — Ver el estado real**

```
!trini status
```

Cada modulo sale con su estado real en el servidor:
🟢 funciona · 🔴 desactivado aqui · 🟠 activado pero el cog no esta cargado · ⚫ no cargado.

**Paso 2 — Aplicar un perfil (opcional)**

```
!trini setup
```

Elige el tipo de servidor en el desplegable (Gaming, Esports, Roleplay, Hosting, General,
Todo activado o Personalizado), revisa la previsualizacion y pulsa:

- **Aplicar**: activa los modulos marcados como ✅.
- **Aplicar + recomendados**: ademas activa los ⭐.
- **Aplicar exacto**: ademas **desactiva** todo lo que no este en el perfil (crea antes un backup).

**Paso 3 — Ajustar a mano**

```
!trini modules
```

Elige la categoria y activa/desactiva cada modulo. Tambien por comando:

```
!trini enable events
!trini disable giveaways
```

Si un modulo necesita otro, se activa solo (te pide confirmacion).

**Paso 4 — Guardar tu configuracion como preset (opcional)**

```
!profile save Servidor RP completo
!profile apply Servidor RP completo      # en otro servidor
```

> Un **preset** guarda solo **que modulos** estan activos. Para copiar tambien la configuracion
> de cada cog (canales, roles, paneles de tickets...) usa export/import (seccion 7).

---

## 3. Security: proteger el servidor

**Paso 1 — Canal y rol de alertas**

```
!security config logchannel #seguridad
!security config alertrole @Staff
```

**Paso 2 — Primera auditoria**

```
!security audit
!security health
```

Te da un Health Score de 0 a 100 con cada riesgo explicado (permisos peligrosos en @everyone,
escaladas de privilegios, canales privados expuestos, bots con Administrator, invitaciones
permanentes, 2FA...). Corrige los 🔴 primero. `!security health` te dice que activar para subir la puntuacion.

**Paso 3 — Quien manda (Authority)**

Tener Administrator en Discord no te da autoridad en Trini Security.

```
!security authority add @Socio extra_owner      # solo el Owner del servidor
!security authority add @JefeStaff trusted_admin  # Owner o Extra Owners
!security authority list
```

- **Extra Owner**: configura Security, añade Trusted Admins, sale del lockdown.
- **Trusted Admin**: puede hacer acciones sensibles sin que Anti-Nuke lo frene.

**Paso 4 — Proteger los roles importantes**

```
!security protectedrole add @Administrador
!security protectedrole add @Arbitro Principal
!security protectedrole list
```

Si alguien sin autorizacion asigna un rol protegido, se retira al instante y se avisa.
Para dejar que alguien lo gestione un rato:

```
!security whitelist temp @Administrador @Pepe 1h
```

**Paso 5 — Whitelists**

```
!security whitelist add bots @MiBotDeConfianza
!security whitelist add channels #canal-de-webhooks
!security whitelist list
```

Añade a la whitelist de bots **todos los bots legitimos** antes de activar Anti-Nuke: con
Anti-Nuke activo, un bot que no este en la lista se expulsa automaticamente al entrar.

**Paso 6 — Vigilancia y Anti-Nuke**

```
!security watch enable
!security antinuke enable
!security antinuke status
```

- **Watch** avisa de cambios sensibles (Administrator otorgado, @everyone, webhooks, bots nuevos...).
- **Anti-Nuke** puntua cada accion peligrosa: 30+ alerta, 50+ bloquea y revierte, 70+ **quarantine**
  (retira los roles peligrosos al responsable y los guarda para devolverlos).
- Opcional: rol que se pone a quien entra en quarantine: `!security config quarantinerole @Cuarentena`.

**Paso 7 — Resumen semanal (opcional)**

```
!security digest enable #seguridad
```

### En una emergencia

```
!security lockdown enable      # bots, webhooks, roles protegidos y cambios admin bloqueados
!security timeline 15m         # que ha pasado
!security incident list        # incidentes reconstruidos
!security quarantine list
!security quarantine release @usuario
!security lockdown disable     # solo Owner / Extra Owners
```

---

## 4. Backups: guardar el estado

**Paso 1 — Primer backup**

```
!backup create Estado inicial
```

Guarda roles, categorias, canales, permisos, bots y la configuracion de los cogs compatibles.

**Paso 2 — Backups automaticos**

```
!backup schedule daily 4        # todos los dias a las 04:00 UTC
!backup retention 7 4 6         # guarda 7 diarios, 4 semanales y 6 mensuales
```

**Paso 3 — Comparar**

```
!backup list
!backup diff                    # ultimo backup vs estado actual
!backup compare <id1> <id2>
```

**Paso 4 — Restaurar (si algo sale mal)**

```
!backup restore <id>
```

Muestra una previsualizacion con botones para elegir que restaurar (roles, canales, permisos,
jerarquia, configuracion). **Nunca borra nada**: solo crea lo que falta y corrige lo que cambio.
Antes de restaurar hace un backup automatico por si acaso.

> Restaurar requiere ser Owner, Extra Owner o Trusted Admin en Trini Security.

---

## 5. Events: actividades de comunidad

**Paso 1 — Configuracion basica**

```
!event settings timezone Europe/Madrid
!event settings channel #eventos
!event settings reminders 1440,60,15      # 24h, 1h y 15 min antes (por DM)
!event settings staffrole @Staff true     # true = mencionar al staff en los recordatorios
!event settings show
```

**Paso 2 — Roles y canales temporales (opcional)**

```
!event settings participantrole @Participante   # rol fijo para los inscritos
!event settings autorole true                    # o un rol nuevo por cada evento
!event settings rolelead 60                      # se da 60 min antes
!event settings tempchannels true delete         # categoria + canales por evento; delete o archive al acabar
!event settings checkin 15                       # el check-in se abre 15 min antes
```

**Paso 3 — Crear un evento**

```
!event create
!event create #otro-canal @RolRequerido minecraft
```

Pulsa **Abrir formulario** y rellena nombre, fecha (`02/10/2026 22:00`, `viernes 22:00`,
`mañana 21:30`, `+2h`), plazas, duracion y descripcion. Los usuarios se apuntan con los botones
✅ Participar · ❌ Cancelar plaza · 🔔 Recordarme · ✋ Check-in. Si se llena, entran en lista de
espera y suben solos si alguien cancela.

**Paso 4 — Gestion**

```
!event list
!event participants <id>
!event edit <id>
!event repeat <id> weekly viernes 22:00   # se crea la siguiente edicion al terminar
!event clone <id> sabado 21:00
!event cancel <id> motivo
!event stats
```

**Torneos ArenCup**: `!event arencup` publica un torneo con check-in, inicio, equipos y boton
**Ver torneo** (los brackets siguen en ArenCup).

---

## 6. AlienHost: servidores de juego desde Discord

### Owner del bot (una vez)

```
!alienhost set panels list          # por defecto: https://pelican.alienhost.es
!alienhost admin setkey             # clave de APLICACION (papp_) en formulario privado, opcional
```

### Administradores de cada servidor de Discord

```
!alienhost set logchannel #alienhost-logs        # registro de acciones
!alienhost set adminrole @Staff true             # true = exigir tambien Trusted Admin
```

### Cada usuario

1. En el panel `https://pelican.alienhost.es`: **Perfil → Claves API → Crear**.
   Puedes limitarla a la IP del bot en "IPs permitidas".
2. En Discord:

```
!alienhost link
```

Pulsa **Conectar cuenta** y pega la URL del panel y la clave en el **formulario privado**.
**Nunca pegues la clave en el chat** (si ocurre, el bot la borra y te avisa para revocarla).

3. Uso diario:

```
!ah servers                 # lista + panel con Iniciar/Reiniciar/Detener/Kill, Backups, Alertas
!ah server <nombre>
!ah power <nombre> restart
!ah backups <nombre>
!ah alerts <nombre>         # avisos por DM: offline, RAM, CPU, backup fallido, reinicio
!ah account
!ah unlink
```

La vinculacion es **por usuario**: sirve en cualquier servidor de Discord donde este La Trini.

### Administradores de AlienHost

```
!ah admin servers           # TODOS los servidores del panel (necesita cuenta root admin vinculada)
!ah admin servers france-02 # filtrado
!ah admin nodes             # necesita la clave de aplicacion
!ah admin incidents
!ah admin user email@cliente.com
```

---

## 7. Copiar la configuracion a otro servidor

**En el servidor de origen:**

```
!profile export
```

Te llega un JSON por mensaje privado.

**En el servidor destino:** adjunta el archivo al mensaje:

```
!profile import
```

Veras un resumen antes de confirmar. Que se copia:

| Se copia | No se copia |
|---|---|
| Que modulos estan activos | Tickets abiertos, sugerencias, historiales, estadisticas |
| Configuracion de cada cog compatible | Partidas, votaciones o eventos en curso |
| Canales y roles, re-mapeados **por nombre** | Mensajes ya publicados (paneles, monitores) |
| Autoridad de Security (solo mismo servidor) | Listas negras de otra comunidad |

Cogs con soporte completo (copian solo la configuracion):
TriniProfiles, TriniSecurity, TriniBackups, TriniEvents, AlienHost, TicketsTrini,
GameServerMonitor, Suggestions, Giveaways, Honeypot, TrickOrTreat, MapTrack, RustMapsVote,
AutoPrune, AutoNick y DayCounter.

Otros cogs (de Red o de terceros) se copian **completos tal cual**; el aviso de importacion lo
indica. Para que los canales y roles se re-mapeen bien, crealos en el servidor destino **con el
mismo nombre** antes de importar.

**Despues de importar:**

- **Tickets**: vuelve a publicar cada panel y enlazalo con `!ticketst panelmessage <panel> <mensaje>`.
- **GameServerMonitor**: los mensajes de estado se crean solos en el siguiente refresco.
- **Security**: la autoridad (Extra Owners / Trusted Admins) no se copia entre servidores; vuelve a asignarla.

---

## 8. Dashboard web

Con el cog **Dashboard** (AAA3A) cargado, cada cog aparece en **Terceros** de la web del bot con estas paginas. El Dashboard solo comprueba que estes en el servidor, asi que **cada pagina exige sus propios permisos**:

| Cog | Pagina | Quien puede entrar |
|---|---|---|
| TriniProfiles | modules: estado real de los modulos y activar/desactivar | Admins / *Gestionar servidor* |
| TriniSecurity | status: estado, incidentes, cuarentena y eventos (solo lectura) | Admins |
| TriniBackups | backups: listar, crear y programar | *Administrador* |
| TriniEvents | events: eventos y plazas (solo lectura) | Mods y admins |
| AlienHost | servers: "Mis servidores" con tu cuenta vinculada | Cada usuario, solo sus servidores |
| AlienHost | settings: canal de auditoria y rol admin | Admins |
| TicketsTrini | view_tickets / close_ticket | Staff (mods, *Gestionar servidor* o rol de soporte) |
| TicketsTrini | resumen global y ajustes | Owner del bot |
| GameServerMonitor | servers | Mods y admins |
| Suggestions | suggestions | Mods y admins |
| AutoNick | settings | Admins |
| AutoPrune | bans: ajustes (admins) y pendientes (mods) | Mods y admins |
| DayCounter | counters | Admins |
| Giveaways | giveaways | Mods y admins |
| ColaCoins | colacoins: clasificacion y dar/quitar | Admins |
| TrickOrTreat | settings: ajustes (admins), clasificacion (mods) | Mods y admins |
| RustMapsVote | votes: sesion actual (mods), ajustes (admins) | Mods y admins |
| ListRoles | roles | Mods y admins |
| AdvCheck | check: ficha de un miembro | Mods y admins |
| Honeypot | settings | Dueño del servidor |
| Blackjack / APIv2 | pagina principal | Owner del bot |

Las claves de AlienHost y los tokens de la API **nunca** se muestran ni se piden en la web: las claves de AlienHost se introducen solo en el formulario privado de Discord.

## 9. Preguntas frecuentes

**Todo sale ⚫ en `!trini status` pero funciona.**
Ya no deberia: el estado muestra la realidad de Red. ⚫ significa que el cog no esta cargado en el
bot (`!load <cog>`).

**Desactive un modulo en Profiles y sigue funcionando.**
Mira `!trini status`: si la sincronizacion con Red esta desactivada (`!trini syncred false`),
Profiles solo toma nota. Activala con `!trini syncred true`.

**Security no detecta nada.**
El bot necesita **View Audit Log**. `!security status` te avisa si falta.

**Anti-Nuke ha puesto en quarantine a alguien de confianza.**
`!security quarantine release @usuario` le devuelve sus roles. Para que no vuelva a pasar:
`!security authority add @usuario trusted_admin` o `!security whitelist add users @usuario`.

**Un bot legitimo se expulsa al entrar.**
Añadelo antes a la whitelist: `!security whitelist add bots <ID del bot>`.

**No puedo restaurar un backup.**
Hace falta ser Owner, Extra Owner o Trusted Admin, y que el rol del bot este por encima de los roles a restaurar.

**`!ah admin servers` dice que no soy administrador del panel.**
Tu cuenta vinculada con `!alienhost link` tiene que ser root admin en Pelican.
