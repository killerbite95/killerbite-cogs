# La Trini - Roadmap de módulos propios

## Objetivo

Este documento recoge una propuesta funcional para evolucionar La Trini desde un bot basado en Red-DiscordBot con muchos cogs hacia una herramienta propia de administracion, seguridad, comunidad e infraestructura.

Los módulos principales planteados son:

- Trini Security
- Trini Backups
- Trini Events
- AlienHost Integration
- Configuracion por perfiles

La idea no es duplicar cogs que La Trini ya tiene cubiertos, sino crear capas superiores que conecten seguridad, auditoria, automatizacion, configuracion y servicios externos.

## Principios de diseño

- Evitar duplicar sistemas ya existentes como tickets, sugerencias, captcha, automod, giveaways, voice rooms o logging generico.
- Priorizar funciones diferenciales: auditoria, reconstruccion de incidentes, backups comparables, perfiles de configuracion e integracion real con AlienHost.
- Separar claramente moderacion, seguridad estructural e infraestructura.
- Guardar logs claros de cambios sensibles y configuracion.
- No dar poder destructivo automatico sin previsualizacion, confirmacion y trazabilidad.
- Pensar los módulos como piezas conectadas, no como cogs aislados.

## Roadmap recomendado

### Primera fase

1. Configuracion por perfiles
2. Trini Security
3. Trini Backups

Esta fase crea la base: que cada servidor tenga un perfil, que Security entienda riesgos y que Backups pueda registrar estados y comparar cambios.

### Segunda fase

1. Trini Events
2. Mejoras de comunidad
3. Integracion con ArenCup para eventos/logistica

Esta fase mejora la actividad de comunidad sin sustituir brackets ni torneos completos.

### Tercera fase

1. AlienHost Integration
2. API intermedia de AlienHost
3. Alertas, acciones seguras y vista de servicios

Esta fase requiere mas cuidado porque conecta Discord con infraestructura real.

---

# 1. Trini Security

## Enfoque

Trini Security no debe ser otro automod, otro captcha, otro reports ni otro logger generico. La Trini ya tiene muchas de esas piezas cubiertas.

Su funcion deberia ser una capa defensiva encima del servidor:

- auditar permisos;
- detectar configuraciones peligrosas;
- proteger roles sensibles;
- vigilar cambios administrativos;
- detectar acciones tipo nuke;
- reconstruir incidentes;
- generar health score;
- registrar cambios internos de configuracion.

## Modulos internos

```text
Trini Security

├── Security Audit
│   ├── Guild
│   ├── Role
│   ├── User
│   ├── Channel
│   ├── Bot
│   ├── Webhook
│   └── Invites
│
├── Authority
│   ├── Owner
│   ├── Extra Owners
│   └── Trusted Admins
│
├── Security Watch
│
├── Anti-Nuke
│   ├── thresholds
│   ├── risk score
│   └── quarantine
│
├── Protected Roles
│
├── Whitelists
│   ├── Users
│   ├── Roles
│   ├── Bots
│   ├── Webhooks
│   └── Channels
│
├── Emergency Lockdown
│
├── Security Timeline
│
├── Incident Reconstruction
│
├── Health Score
│
├── Weekly Digest
│
├── Security Settings Audit
│
└── Advanced
    ├── Threat Media Detection
    └── Local Message Analysis
```

## Security Audit

Comando principal:

```text
/security audit
```

Debe revisar:

- permisos peligrosos en `@everyone`;
- roles con `Administrator`;
- roles con `Manage Guild`, `Manage Roles`, `Manage Channels`, `Manage Webhooks`, `Ban Members` o `Kick Members`;
- bots con permisos excesivos;
- roles mal posicionados en la jerarquia;
- canales privados con overwrites inconsistentes;
- categorias privadas con canales que no heredan permisos;
- webhooks existentes;
- invitaciones permanentes;
- roles que pueden mencionar `@everyone`;
- permisos de aplicaciones/bots;
- usuarios que acumulan varios roles administrativos;
- posibles escaladas de privilegios.

Ejemplo:

```text
🔐 Security Audit

Servidor: ArenCup
Health Score: 82 / 100

🔴 Riesgos criticos: 2
🟠 Advertencias: 5
🔵 Observaciones: 8

🔴 @everyone puede crear invitaciones en #general

🔴 Rol Moderador
Tiene Manage Roles y puede modificar:
- Tournament Staff
- Caster
- Arbitro

🟠 Bot XYZ tiene Administrator
Actualmente solo parece necesitar:
- Manage Messages
- Manage Roles

🟢 No se detectaron webhooks desconocidos
```

Auditorias especificas:

```text
/security user @usuario
/security role @Staff
/security channel #staff
/security bot @bot
/security webhooks
/security invites
```

Una funcion clave es mostrar el origen real de cada permiso:

```text
/security user @Killerbite
```

Ejemplo:

```text
Permisos efectivos

Administrator       ✅
Manage Guild        ✅
Manage Roles        ✅
Manage Channels     ✅
Ban Members         ✅
Kick Members        ✅
Manage Webhooks     ✅

Origen:
Administrator       Terra Owner
Manage Roles        Host Manager
Manage Webhooks     Host Manager
```

## Authority

Discord puede permitir a alguien hacer acciones sensibles porque tiene `Administrator`, pero Trini Security necesita su propio modelo de confianza.

Jerarquia interna:

```text
Server Owner
   ↓
Extra Owners
   ↓
Trusted Admins
   ↓
Regular Administrators
   ↓
Moderators
```

Comandos:

```text
/security authority add @usuario extra_owner
/security authority add @usuario trusted_admin
/security authority remove @usuario
/security authority list
```

Reglas:

```text
Server Owner
→ puede hacer todo

Extra Owner
→ puede configurar Security
→ puede añadir Trusted Admins
→ no puede quitar al Owner

Trusted Admin
→ inmune a ciertas protecciones
→ puede realizar acciones sensibles autorizadas
→ no puede modificar owners

Administrador normal
→ Discord puede permitirle hacer cosas
→ Security puede bloquear o reaccionar si cruza limites
```

Esto permite que La Trini responda a casos como:

```text
Tienes Administrator en Discord, pero no eres Trusted Admin en Trini Security.
Accion bloqueada o marcada como sensible.
```

## Protected Roles

Modulo para proteger roles criticos:

- Owner;
- Administracion;
- Staff Manager;
- Bots;
- Tournament Manager;
- Arbitro Principal;
- Host Manager;
- roles de pool o roles internos sensibles.

Comandos:

```text
/security protected-role add @Administrador
/security protected-role remove @Administrador
/security protected-role list
/security protected-role config @Administrador
```

Configuracion ejemplo:

```text
Rol protegido: Administrador

Allowed:
- extra_owner
- trusted_admin

self_assign: false
bots: false
temporary_whitelist: true
```

Si un usuario no autorizado intenta asignarlo:

```text
🚨 Protected Role violation

@Moderador intento asignar:
@Administrador

A:
@Usuario

Accion:
Asignacion revertida.

Motivo:
El usuario no esta autorizado para gestionar este rol.
```

Whitelist temporal:

```text
/security whitelist role @Administrador user @Pepe duration:1h
```

## Anti-Nuke

Anti-Nuke debe detectar patrones peligrosos por acciones y ventanas temporales.

Ejemplo de thresholds:

```text
Channel Delete
5 / minuto
10 / hora

Role Delete
3 / minuto
8 / hora

Ban Members
10 / minuto
30 / hora

Kick Members
10 / minuto
30 / hora

Webhook Create
3 / minuto

Dangerous Permission Change
1 evento critico
```

Sistema de puntuacion:

```text
Eliminar canal          20 puntos
Eliminar rol            25 puntos
Añadir Administrator    50 puntos
Cambiar @everyone       40 puntos
Crear webhook           10 puntos
Ban                     5 puntos
Kick                    3 puntos
```

Respuesta escalonada:

```text
0 - 29
Log

30 - 49
Alertar staff

50 - 69
Bloquear nuevas acciones sensibles

70+
Quarantine
```

Quarantine puede:

- retirar temporalmente roles peligrosos;
- guardar que roles tenia el usuario;
- bloquear acciones sensibles;
- alertar a Owner, Extra Owners y Trusted Admins;
- generar un incidente.

## Emergency Lockdown

Comando:

```text
/security lockdown
```

Modo emergencia:

```text
🔐 SECURITY LOCKDOWN

• Nuevos bots: bloqueados
• Webhooks nuevos: bloqueados
• Protected Roles: bloqueados
• Cambios administrativos: restringidos
• Invitaciones: opcionalmente desactivadas
• Security Watch: maximo nivel
```

Solo deberian poder salir del lockdown:

- Server Owner;
- Extra Owners.

Comando:

```text
/security lockdown disable
```

## Whitelists

No debe existir una unica whitelist generica. Debe haber whitelists por tipo:

```text
/security whitelist bot
/security whitelist webhook
/security whitelist role
/security whitelist user
/security whitelist channel
/security whitelist invite
```

Ejemplo de bot no autorizado:

```text
🚨 Bot no autorizado

Añadido:
SomeRandomBot

Añadido por:
@Usuario

Accion:
Bot expulsado automaticamente.
```

## Security Watch

Comando:

```text
/security watch enable
```

Debe vigilar:

- `Administrator` otorgado;
- permisos de `@everyone`;
- nuevos webhooks;
- nuevos bots;
- creacion de roles administrativos;
- cambios en categorias privadas;
- cambios importantes en jerarquia;
- invitaciones permanentes;
- modificaciones de roles protegidos;
- cambios de configuracion de Security.

Ejemplo:

```text
🚨 Cambio critico

Rol:
Moderador

Ejecutado por:
@AdminX

CAMBIOS

Manage Roles
❌ → ✅

Administrator
❌ → ✅

RIESGO

Este rol ahora puede modificar:
• Support
• Event Staff
• Tournament Staff

Security Score:
-18
```

## Security Timeline

Comando:

```text
/security timeline 15m
```

Ejemplo:

```text
17:42:01
@AdminX crea rol "test"

17:42:08
@AdminX añade Administrator

17:42:12
@AdminX crea webhook en #general

17:42:19
@AdminX elimina #staff

17:42:22
@AdminX elimina #logs

17:42:25
Trini Security activa quarantine
```

Esto sirve para investigar ataques sin leer cientos de lineas de audit log.

## Incident Reconstruction

Cuando Security detecta un nuke o patron critico, debe agrupar eventos relacionados.

Comando:

```text
/security incident 184
```

Ejemplo:

```text
INCIDENT #184

Inicio:
17:42:01

Fin:
17:42:25

Responsable principal:
@AdminX

Eventos relacionados:
14

Canales eliminados:
2

Roles modificados:
3

Usuarios baneados:
7

Webhooks creados:
1

Backup previo:
16:00

[Comparar]
[Generar informe]
```

## Health Score

No debe ser solo un numero decorativo. Debe explicar sus penalizaciones y mejoras.

Ejemplo:

```text
Security Health
82 / 100

-10
3 bots tienen Administrator

-5
@everyone puede crear invites

-3
4 roles tienen Manage Webhooks

+5
Protected Roles activo

+5
Anti-Nuke activo
```

## Weekly Security Digest

Resumen semanal:

```text
🔐 Security Digest

Periodo:
21 - 27 septiembre

Cambios administrativos: 14
Cambios criticos: 2
Roles modificados: 7
Bots añadidos: 1
Webhooks creados: 0

Anti-Nuke:
0 activaciones

Protected Roles:
2 intentos bloqueados

Security Health:
86 → 91

Principales mejoras:
• Se elimino Administrator de BotX
• Se corrigieron permisos de #staff
```

## Security Settings Audit

Debe registrar cambios internos del propio cog:

- quien activo o desactivo modulos;
- quien cambio thresholds;
- quien añadio o elimino whitelists;
- quien asigno Trusted Admins;
- quien modifico Protected Roles;
- quien activo Lockdown;
- quien desactivo Lockdown.

Comando:

```text
/security settings-log
```

## Advanced: Threat Media Detection

Modulo opcional basado en perceptual hashing para detectar imagenes similares a amenazas conocidas:

- scams de Nitro;
- crypto scam;
- MrBeast scam;
- QR de token grabber;
- imagenes de phishing recurrentes.

Acciones posibles:

```text
Delete
Alert
Timeout
Log
```

Debe ser fase posterior, no nucleo inicial.

## Advanced: Local Message Analysis

Modulo opcional con modelo local para puntuar mensajes:

- scam likelihood;
- phishing;
- toxicidad;
- amenazas;
- spam generado;
- manipulacion social sospechosa.

Ejemplo:

```text
Scam > 0.90
→ borrar + alertar

Toxicity > 0.95
→ avisar staff
```

No deberia aplicar bans graves por si solo.

---

# 2. Trini Backups

## Enfoque

Trini Backups no debe prometer una restauracion perfecta de Discord, porque Discord no permite restaurar absolutamente todo de forma transparente.

Debe plantearse como un sistema de:

- snapshots estructurales;
- comparacion de cambios;
- auditoria historica;
- restauracion segura y parcial;
- integracion con Security.

## Snapshot

Comando:

```text
/backup create
```

Debe guardar:

```text
Servidor

Roles
├─ nombre
├─ ID
├─ color
├─ posicion
├─ permisos
└─ mentionable

Categorias

Canales
├─ tipo
├─ posicion
├─ topic
├─ NSFW
├─ slowmode
└─ overwrites

Foros
Canales de voz
Permisos

Configuracion La Trini
├─ modulos activos
├─ canales configurados
├─ roles configurados
├─ mensajes persistentes
└─ ajustes de cada cog compatible
```

Snapshot con nombre:

```text
/backup create name:"Antes del torneo"
```

## Diff

La funcion mas valiosa no es restaurar, sino comparar.

Comando:

```text
/backup diff
```

Ejemplo:

```text
📦 Diferencias desde
Backup: 25/09/2026 03:00

ROLES

Moderador
+ Manage Roles
+ Manage Threads

Administrador
- Manage Webhooks

CANALES

+ #torneo-valorant
- #pruebas

#staff
View Channel:
@everyone ❌ → ✅

BOTS

+ TournamentBot
```

## Backups automaticos

Comando:

```text
/backup schedule daily
```

Politica de retencion:

```text
Ultimos 7 diarios
Ultimos 4 semanales
Ultimos 6 mensuales
```

Comandos:

```text
/backup list
/backup inspect
/backup compare
/backup delete
```

## Restauracion segura

Separar dos modos.

### Safe Restore

Restauracion no destructiva:

- roles desaparecidos;
- canales eliminados;
- categorias eliminadas;
- overwrites;
- topics;
- slowmode;
- configuracion de La Trini.

### Restore avanzado

Comando:

```text
/backup restore
```

Debe mostrar previsualizacion:

```text
Se realizaran:

+ Crear 2 roles
+ Crear 3 canales
~ Modificar 14 permisos
~ Reordenar 7 roles
~ Modificar 5 canales

No se eliminara ningun elemento actual.

[Continuar]
[Cancelar]
```

No debe eliminar cosas automaticamente sin confirmacion explicita.

## Integracion con Security

Antes de cambios criticos, Security puede forzar un snapshot:

```text
Backup automatico:
pre-security-fix-2026-09-27
```

Cuando Security detecta un cambio sensible:

```text
🚨 Cambio critico detectado.

Se ha modificado @everyone.

[Comparar con backup]
```

En un incidente:

```text
Backup previo:
16:00

[Comparar estado anterior]
[Generar informe]
```

---

# 3. Trini Events

## Enfoque

Trini Events no debe ser solo un clon de los eventos de Discord. Debe ser un gestor de actividades, inscripciones, recordatorios, reservas y logistica.

## Crear evento

Comando:

```text
/event create
```

Modal:

```text
Nombre
Noche de Minecraft

Fecha
02/10/2026 22:00

Plazas
20

Descripcion
...

Rol requerido
@Miembro
```

Publicacion:

```text
🎮 Noche de Minecraft

📅 Viernes 2 de octubre
🕙 22:00
👥 14 / 20 participantes

Jugaremos survival durante aproximadamente 2 horas.

[✅ Participar]
[❌ Cancelar plaza]
[🔔 Recordarme]
```

## Participantes y reservas

Si se llena:

```text
20 / 20

Lista de espera:
3
```

Si alguien cancela:

```text
@Usuario2 ha pasado automaticamente de reserva a participante.
```

## Recordatorios

Avisos configurables:

```text
24 horas antes
1 hora antes
15 minutos antes
```

Solo deben recibirlos:

- inscritos;
- usuarios que pulsaron Recordarme;
- staff si se configura.

## Roles temporales

Una hora antes:

```text
Asignar @Participante Evento
```

Al acabar:

```text
Eliminar @Participante Evento
```

## Canales temporales

Opcion para crear automaticamente:

```text
📁 Evento - Minecraft
├─ #informacion
├─ #chat
└─ 🔊 Evento
```

Y eliminarlos o archivarlos al finalizar.

## Eventos recurrentes

Comando:

```text
/event repeat weekly friday 22:00
```

Comando para repetir uno anterior:

```text
/event clone
```

## Integracion con ArenCup

Trini Events puede publicar y recordar eventos de ArenCup, pero no debe gestionar brackets.

Ejemplo:

```text
🏆 ArenCup Friday Cup #14

Check-in: 18:30
Inicio: 19:00

16 equipos

[Ver torneo]
[Recordarme]
```

ArenCup sigue siendo la fuente principal de torneos. Trini Events gestiona la capa social y logistica en Discord.

## Estadisticas

Comando:

```text
/event stats
```

Metricas:

- asistencia historica;
- cancelaciones;
- no-shows;
- eventos con mayor participacion;
- usuarios mas activos;
- tasa de asistencia por tipo de evento.

---

# 4. AlienHost Integration

> **Decision de implementacion:** el cog `alienhost` usa directamente la Client API de Pelican con la clave `pacc_` de cada usuario (pedida en un modal y guardada cifrada, solo hacia paneles permitidos). La API intermedia descrita abajo queda como evolucion futura.

## Enfoque

GameServerMonitor monitoriza servidores publicos.

AlienHost Integration debe permitir que clientes de AlienHost interactuen con sus propios servicios desde Discord, de forma segura y limitada.

## Vinculacion de cuenta

Comando:

```text
/alienhost link
```

Flujo:

```text
Vincula tu cuenta de Discord con AlienHost.

[Conectar cuenta]
```

El usuario inicia sesion en AlienHost y el backend genera asociacion:

```text
discord_user_id
alienhost_user_id
```

Nunca se deben introducir usuarios, contraseñas ni API keys dentro de Discord.

## Servidores

Comando:

```text
/alienhost servers
```

Ejemplo:

```text
🖥 Minecraft Survival

Estado       🟢 Online
Nodo         France-02
CPU          34 %
RAM          4.8 / 8 GB
Disco        13 / 40 GB

Jugadores    18 / 50
Uptime       2d 14h

[Reiniciar]
[Backups]
[Detalles]
```

## Acciones permitidas

Segun permisos:

```text
Start
Stop
Restart
Kill
```

Evitar inicialmente una consola completa por Discord.

Si se añade en el futuro:

```text
/alienhost command
```

Debe tener:

- permisos estrictos;
- logs;
- rate limiting;
- lista de comandos bloqueados;
- confirmacion en acciones peligrosas.

## Backups

Comando:

```text
/alienhost backups
```

Ejemplo:

```text
Ultimos backups

✅ 27/09 04:00    4.7 GB
✅ 26/09 04:00    4.6 GB
❌ 25/09 04:00    Fallido
```

Posible accion:

```text
[Crear backup]
```

No descargar backups directamente desde Discord.

## Alertas

Comando:

```text
/alienhost alerts
```

Ejemplo:

```text
Servidor offline       ✅
RAM > 90 %             ✅
CPU > 95 % 10 min      ❌
Backup fallido         ✅
Servidor reiniciado    ✅
```

Alerta:

```text
⚠️ AlienHost

Minecraft Survival

RAM superior al 90 % durante 10 minutos.

7.6 / 8 GB
```

## Administracion interna de AlienHost

Solo para administradores:

```text
/alienhost admin nodes
```

Ejemplo:

```text
France-01     🟢
France-02     🟢
France-03     🟠

FR-03
CPU: 93 %
RAM: 86 %
Servers: 43
```

Otros comandos:

```text
/alienhost admin incidents
/alienhost admin server <id>
/alienhost admin user
```

## Arquitectura recomendada

Evitar:

```text
Discord Bot → Pelican directamente
```

Preferir:

```text
La Trini
     │
     ▼
AlienHost API
     │
     ├── autenticacion
     ├── autorizacion
     ├── rate limits
     ├── auditoria
     │
     ▼
Pelican
```

Ventajas:

- Discord no guarda credenciales sensibles de infraestructura;
- AlienHost decide que operaciones acepta;
- se centraliza autorizacion y auditoria;
- se puede limitar por cliente, servidor y accion;
- se evita exponer Pelican directamente al bot.

---

# 5. Configuracion por perfiles

## Enfoque

Con muchos cogs y comandos, el problema no es solo tener funciones, sino activar las adecuadas para cada tipo de servidor.

Los perfiles deben funcionar como plantillas iniciales, no como estados rigidos permanentes.

## Setup inicial

Comando:

```text
/trini setup
```

Pregunta:

```text
¿Como se utiliza este Discord?

🎮 Comunidad Gaming
🏆 Esports / Torneos
🎭 Roleplay
🖥 Hosting / Soporte
🌐 Comunidad General
⚙️ Personalizado
```

## Perfil Gaming

Activa o recomienda:

```text
GameServerMonitor    ✅
AutoRoom             ✅
Giveaways            ✅
Streams              ✅
YouTube              ✅
Welcome              ✅
RolesButtons         ✅
Audio                ✅

Economy              opcional
Tickets              opcional
Security             recomendado
Backups              recomendado
```

## Perfil ArenCup / Esports

```text
Moderation
TicketsTrini
Reports
Events
RolesButtons
Welcome
Captcha
Security
Backups
ArenCup
```

## Perfil AlienHost

```text
TicketsTrini
AlienHost
GameServerMonitor
Security
Backups
Reports
Welcome
Incidents
Status
Forms
```

## Perfil Roleplay

```text
Moderation
Warnings
Reports
Tickets
AutoRoom
Welcome
Captcha
RolesButtons
Security
Backups
Applications
Forms
```

## Personalizacion posterior

Comando:

```text
/trini modules
```

Desde ahi se pueden activar o desactivar modulos.

Un perfil solo prepara la base. El servidor puede cambiar cualquier modulo despues.

## Dependencias

Ejemplo:

```text
AlienHost Integration
    └─ necesita APIv2
```

Si se activa AlienHost:

```text
AlienHost requiere APIv2.

APIv2 se activara automaticamente.

[Continuar]
```

Si se intenta apagar APIv2:

```text
No se puede desactivar.

Dependencias activas:
• AlienHost Integration
```

## Presets personalizados

Guardar preset:

```text
/profile save "Servidor RP completo"
```

Aplicar preset:

```text
/profile apply "Servidor RP completo"
```

Esto es util para administrar varios Discord parecidos.

## Exportar configuracion

Comando:

```text
/profile export
```

Debe guardar:

```text
Cogs activos
Configuracion
Canales asociados
Roles asociados
Permisos Trini
Dependencias
```

Importar:

```text
/profile import
```

Esto permite montar servidores nuevos mucho mas rapido.

---

# Conexion entre modulos

```text
                    LA TRINI
                       │
         ┌─────────────┼─────────────┐
         │             │             │
     SECURITY       BACKUPS        EVENTS
         │             │             │
         └──────┬──────┘             │
                │                    │
             PROFILES                │
                │                    │
                └──────────┬─────────┘
                           │
                     INTEGRATIONS
                           │
                       AlienHost
```

## Flujo ideal

1. Profiles prepara el servidor segun su uso.
2. Security audita si la configuracion es segura.
3. Backups guarda el estado y permite comparar cambios.
4. Events gestiona la actividad de comunidad.
5. AlienHost conecta Discord con servicios reales mediante una API segura.

## Integraciones clave

### Security + Backups

- Security detecta cambio critico.
- Backups permite comparar con estado anterior.
- Incident Reconstruction enlaza con el backup previo.
- Restore puede recuperar roles/canales/permisos de forma controlada.

### Profiles + Security

- Cada perfil puede recomendar una configuracion de seguridad distinta.
- Perfil AlienHost requiere Security alto.
- Perfil ArenCup requiere proteccion de roles de staff, arbitros y organizadores.

### Events + ArenCup

- Events publica torneos y recordatorios.
- ArenCup mantiene brackets, resultados y check-in.
- Discord queda como capa social y logistica.

### AlienHost + Security

- Acciones sensibles de AlienHost pueden requerir usuario vinculado y permiso interno.
- Security puede auditar quien tiene acceso a comandos de infraestructura.
- Backups puede guardar configuracion de integracion.

---

# Prioridad tecnica sugerida

## MVP 1: Profiles

- `/trini setup`
- perfiles predefinidos;
- activacion/desactivacion de modulos;
- dependencias basicas;
- presets guardables.

## MVP 2: Security Audit + Authority

- `/security audit`
- `/security user`
- `/security role`
- modelo Owner / Extra Owner / Trusted Admin;
- settings audit.

## MVP 3: Protected Roles + Security Watch

- roles protegidos;
- alertas de cambios sensibles;
- whitelists;
- logs claros.

## MVP 4: Backups + Diff

- snapshot;
- diff;
- backups programados;
- comparacion con cambios de Security.

## MVP 5: Anti-Nuke + Incident Reconstruction

- thresholds;
- risk score;
- quarantine;
- timeline;
- incident reports.

## MVP 6: Events

- crear eventos;
- inscripciones;
- reservas;
- recordatorios;
- roles temporales;
- estadisticas.

## MVP 7: AlienHost Integration

- link de cuenta;
- listado de servidores;
- start/stop/restart;
- backups;
- alertas;
- API intermedia.

---

# Funciones que no conviene duplicar ahora

No priorizar:

- otro sistema de tickets;
- otro sistema de sugerencias;
- otro automod generico;
- otro reaction roles;
- otro sistema de giveaways;
- otro voice room;
- otro logger generico;
- otro captcha;
- otro bot musical.

La Trini ya esta cubierta en esas areas. El valor diferencial esta en seguridad estructural, auditoria, backups comparables, perfiles inteligentes, eventos gestionados e integracion con AlienHost.

---

# Resumen final

La evolucion mas interesante de La Trini seria convertirla en una capa de administracion completa:

- Profiles decide que necesita cada servidor.
- Security protege y audita.
- Backups conserva estados y permite comparar.
- Events mueve la comunidad.
- AlienHost conecta Discord con infraestructura real.

El nucleo mas potente a corto plazo seria:

```text
Profiles
→ Security Audit
→ Protected Roles
→ Backups Diff
→ Anti-Nuke / Incident Reconstruction
```

Con eso La Trini dejaria de sentirse como una coleccion enorme de cogs y empezaria a funcionar como una plataforma propia para administrar comunidades, torneos y servicios.
