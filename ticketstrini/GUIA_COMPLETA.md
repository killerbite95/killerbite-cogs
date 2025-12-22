# 🎫 Guía Completa del Sistema de TicketsTrini

<div align="center">

![Version](https://img.shields.io/badge/Version-3.0.0-blue)
![Discord](https://img.shields.io/badge/Platform-Discord-5865F2)
![Red-DiscordBot](https://img.shields.io/badge/Red--DiscordBot-Cog-red)

**Sistema de tickets de soporte multi-panel para Red-DiscordBot (Trini Edition)**

</div>

---

## 📑 Tabla de Contenidos

1. [Introducción](#-introducción)
2. [Características Principales](#-características-principales)
3. [Requisitos Previos](#-requisitos-previos)
4. [Instalación](#-instalación)
5. [Configuración Inicial (Setup Básico)](#-configuración-inicial-setup-básico)
6. [Crear tu Primer Panel de Tickets](#-crear-tu-primer-panel-de-tickets)
7. [Personalización de Botones](#-personalización-de-botones)
8. [Sistema de Roles](#-sistema-de-roles)
9. [Configuración de Modales](#-configuración-de-modales-formularios)
10. [Mensajes de Ticket](#-mensajes-de-ticket)
11. [Sistema de Logs y Transcripts](#-sistema-de-logs-y-transcripts)
12. [Configuración Avanzada](#-configuración-avanzada)
13. [Paneles Multi-Botón](#-paneles-multi-botón)
14. [Comandos de Usuario](#-comandos-de-usuario)
15. [Gestión de Tickets](#-gestión-de-tickets)
16. [Solución de Problemas](#-solución-de-problemas)
17. [Referencia Completa de Comandos](#-referencia-completa-de-comandos)

---

## 📖 Introducción

**Tickets-Trini** es un sistema completo de soporte por tickets diseñado para servidores de Discord que utilizan Red-DiscordBot. Permite crear múltiples paneles de tickets con botones interactivos, formularios modales, transcripciones automáticas y mucho más.

### ¿Qué es un Panel de Tickets?

Un panel de tickets es un mensaje con botones que los usuarios pueden presionar para abrir un nuevo ticket de soporte. Cada panel puede tener su propia configuración, categoría, roles de soporte y personalización.

### ¿Canales o Hilos?

El sistema soporta dos modos de operación:
- **Canales**: Crea un canal de texto privado para cada ticket
- **Hilos (Threads)**: Crea un hilo privado para cada ticket (más ligero y organizado)

---

## ✨ Características Principales

| Característica | Descripción |
|----------------|-------------|
| 🎛️ **Multi-Panel** | Crea múltiples paneles con diferentes configuraciones |
| 🧵 **Hilos o Canales** | Elige entre crear hilos privados o canales de texto |
| 📝 **Modales/Formularios** | Solicita información al usuario antes de abrir el ticket |
| 📊 **Transcripciones** | Guarda automáticamente el historial de conversaciones |
| 🔔 **Notificaciones** | Menciones y DMs configurables |
| 🎨 **Personalización Total** | Colores, emojis, textos y nombres personalizables |
| 👥 **Sistema de Roles** | Roles de soporte globales y por panel |
| ⏰ **Auto-cierre** | Cierra tickets inactivos automáticamente |
| 📋 **Overview en Vivo** | Panel que muestra todos los tickets activos |
| 🚫 **Blacklist** | Bloquea usuarios o roles de abrir tickets |

---

## 📋 Requisitos Previos

Antes de comenzar, asegúrate de que tu bot tenga los siguientes permisos:

### Permisos Esenciales
- ✅ `Manage Channels` (Gestionar Canales)
- ✅ `Manage Roles` (Gestionar Roles/Permisos)
- ✅ `View Channel` (Ver Canales)
- ✅ `Send Messages` (Enviar Mensajes)
- ✅ `Read Message History` (Leer Historial de Mensajes)
- ✅ `Embed Links` (Insertar Enlaces)
- ✅ `Attach Files` (Adjuntar Archivos)
- ✅ `Create Private Threads` (Si usas hilos)
- ✅ `Send Messages in Threads` (Si usas hilos)

### Estructura de Servidor Recomendada

```
📁 Tu Servidor
├── 📁 TICKETS (Categoría)
│   └── Aquí se crearán los tickets
├── 💬 #soporte (Canal de texto)
│   └── Aquí irá el panel de botones
└── 📝 #logs-tickets (Canal de texto)
    └── Registro de tickets abiertos/cerrados
```

---

## 💾 Instalación

### Paso 1: Cargar el COG

```
[p]load ticketstrini
```

> **Nota**: Reemplaza `[p]` con el prefijo de tu bot (ej: `!`, `.`, `?`, etc.)

### Paso 2: Verificar la instalación

```
[p]tickets view
```

Si ves la configuración del sistema de tickets, ¡la instalación fue exitosa!

---

## 🚀 Configuración Inicial (Setup Básico)

### Vista Rápida con el Comando de Ayuda

Antes de empezar, puedes ver la guía integrada:

```
[p]tickets setuphelp
```

### Paso 1: Preparar la Estructura del Servidor

1. **Crea una categoría** para los tickets:
   - Nombre sugerido: `🎫 TICKETS` o `SOPORTE`
   
2. **Crea un canal** donde estará el panel:
   - Nombre sugerido: `#abrir-ticket` o `#soporte`
   
3. **Crea un canal de logs** (opcional pero recomendado):
   - Nombre sugerido: `#logs-tickets`

### Paso 2: Configurar Roles de Soporte

Los roles de soporte pueden ver y responder todos los tickets.

```
[p]tickets supportrole @Staff
```

**Con mención automática** (el rol será mencionado cuando se abra un ticket):
```
[p]tickets supportrole @Staff true
```

> **Tip**: Puedes añadir múltiples roles de soporte repitiendo el comando.

### Paso 3: Configurar Opciones Globales

#### Máximo de Tickets por Usuario
```
[p]tickets maxtickets 2
```
*El usuario podrá tener máximo 2 tickets abiertos a la vez.*

#### Activar DMs al Cerrar Tickets
```
[p]tickets dm
```
*Toggle: El usuario recibirá un DM cuando su ticket sea cerrado.*

#### Activar Transcripciones
```
[p]tickets transcript
```
*Toggle: Guarda una transcripción cuando se cierra un ticket.*

#### Transcripciones Interactivas (HTML)
```
[p]tickets interactivetranscript
```
*Toggle: Las transcripciones serán archivos HTML visuales.*

---

## 🎫 Crear tu Primer Panel de Tickets

### Ejemplo Completo: Panel de Soporte General

Vamos a crear un panel llamado `soporte` paso a paso.

#### Paso 1: Crear el Panel
```
[p]tickets addpanel soporte
```
✅ *Respuesta: "soporte Panel Saved - Your panel has been added and will need to be configured."*

#### Paso 2: Asignar la Categoría
```
[p]tickets category soporte #🎫-TICKETS
```
*O con ID:*
```
[p]tickets category soporte 123456789012345678
```
✅ *Respuesta: "New tickets will now be opened under that category!"*

#### Paso 3: Asignar el Canal del Panel
```
[p]tickets channel soporte #abrir-ticket
```
✅ *Respuesta: Confirmación con ✅*

#### Paso 4: Crear el Mensaje del Panel

Primero, crea un embed bonito usando el comando integrado:

```
[p]tickets embed #FF5733 #abrir-ticket "🎫 Centro de Soporte" "¡Bienvenido al centro de soporte!\n\n**¿Necesitas ayuda?**\nHaz clic en el botón de abajo para abrir un ticket.\n\n📋 **Antes de abrir un ticket:**\n• Revisa las FAQ\n• Describe tu problema claramente\n• Sé paciente, te responderemos pronto"
```

**Desglose del comando:**
- `#FF5733` = Color del embed (hexadecimal)
- `#abrir-ticket` = Canal donde se enviará
- Primer texto entre comillas = Título
- Segundo texto entre comillas = Descripción (usa `\n` para saltos de línea)

#### Paso 5: Vincular el Panel al Mensaje

Obtén el ID del mensaje que acabas de crear (clic derecho > Copiar ID del mensaje) y ejecuta el comando **en el mismo canal donde está el mensaje**:

```
[p]tickets panelmessage soporte 123456789012345678
```

¡Listo! El botón debería aparecer en el mensaje.

---

## 🎨 Personalización de Botones

### Cambiar el Texto del Botón
```
[p]tickets buttontext soporte "📩 Abrir Ticket"
```

### Cambiar el Color del Botón

Colores disponibles: `red`, `blue`, `green`, `grey`

```
[p]tickets buttoncolor soporte blue
```

**Ejemplos visuales:**

| Color | Resultado |
|-------|-----------|
| `blue` | 🔵 Azul (Blurple Discord) |
| `green` | 🟢 Verde |
| `red` | 🔴 Rojo |
| `grey` | ⚪ Gris |

### Añadir Emoji al Botón
```
[p]tickets buttonemoji soporte 🎫
```

*También funciona con emojis personalizados del servidor.*

### Ejemplo de Botón Personalizado Completo
```
[p]tickets buttontext soporte "Necesito Ayuda"
[p]tickets buttoncolor soporte green
[p]tickets buttonemoji soporte 🆘
```

**Resultado**: Un botón verde con el emoji 🆘 y el texto "Necesito Ayuda"

---

## 👥 Sistema de Roles

### Roles de Soporte Globales

Los roles globales pueden ver **todos** los tickets de **todos** los paneles.

```
[p]tickets supportrole @Moderadores
[p]tickets supportrole @Soporte true
```

*El segundo rol será mencionado cuando se abra un ticket.*

### Roles de Panel Específicos

Roles que solo pueden ver tickets de un panel específico.

```
[p]tickets panelrole soporte @SoporteGeneral true
```

**Ejemplo práctico:**
```
# Panel de soporte técnico - solo el equipo técnico puede ver
[p]tickets addpanel tecnico
[p]tickets panelrole tecnico @EquipoTecnico true

# Panel de ventas - solo el equipo de ventas puede ver
[p]tickets addpanel ventas
[p]tickets panelrole ventas @EquipoVentas true
```

### Roles Requeridos para Abrir Ticket

Limita quién puede abrir tickets en un panel específico.

```
[p]tickets openrole soporte @Miembros
```

*Solo usuarios con el rol @Miembros podrán abrir tickets en el panel "soporte".*

### Blacklist (Lista Negra)

Bloquea usuarios o roles de abrir tickets.

```
[p]tickets blacklist @UsuarioProblematico
[p]tickets blacklist @RolBloqueado
```

---

## 📝 Configuración de Modales (Formularios)

Los modales son formularios que aparecen cuando el usuario hace clic para abrir un ticket. Puedes usar hasta **5 campos** por panel.

### Crear un Campo de Modal

```
[p]tickets addmodal soporte asunto
```

El bot te guiará con preguntas interactivas:

1. **Label (Etiqueta)**: El título visible del campo
2. **Style (Estilo)**: `short` (una línea) o `long` (múltiples líneas)
3. **Placeholder**: Texto de ejemplo que aparece en gris
4. **Default**: Valor predeterminado (opcional)
5. **Required**: ¿Es obligatorio?
6. **Min/Max Length**: Longitud mínima y máxima

### Ejemplo Completo de Modal

Vamos a crear un formulario de soporte con 3 campos:

```
# Campo 1: Asunto
[p]tickets addmodal soporte asunto
# Cuando te pregunte:
# - Label: "¿Cuál es tu problema?"
# - Style: short
# - Placeholder: Sí → "Ej: No puedo acceder a mi cuenta"
# - Default: No
# - Required: Sí
# - Min Length: Sí → 10
# - Max Length: Sí → 100

# Campo 2: Descripción
[p]tickets addmodal soporte descripcion
# - Label: "Describe tu problema en detalle"
# - Style: long
# - Placeholder: Sí → "Incluye toda la información relevante..."
# - Default: No
# - Required: Sí
# - Min Length: Sí → 20
# - Max Length: Sí → 1000

# Campo 3: Intentos Previos
[p]tickets addmodal soporte intentos
# - Label: "¿Qué has intentado para solucionar?"
# - Style: long
# - Placeholder: Sí → "Ej: Reinicié el equipo, limpié caché..."
# - Default: No
# - Required: No
```

### Personalizar el Título del Modal
```
[p]tickets modaltitle soporte "📋 Formulario de Soporte"
```

### Ver los Modales Configurados
```
[p]tickets viewmodal soporte
```

*Te permite ver y eliminar campos individuales.*

### Eliminar un Campo de Modal

Simplemente ejecuta el mismo comando de crear con el mismo nombre:
```
[p]tickets addmodal soporte asunto
```
*Si el campo ya existe, será eliminado.*

---

## 💬 Mensajes de Ticket

Los mensajes de ticket son embeds que se envían automáticamente cuando se abre un nuevo ticket.

### Crear un Mensaje de Bienvenida

```
[p]tickets addmessage soporte
```

El bot te preguntará:
1. **¿Título?** → Ej: "🎫 Ticket de Soporte"
2. **Descripción** → El mensaje principal
3. **¿Footer?** → Texto pequeño al final

### Variables Disponibles

Puedes usar estas variables en tus mensajes:

| Variable | Resultado |
|----------|-----------|
| `{username}` | Nombre de usuario de Discord |
| `{mention}` | Mención del usuario (@usuario) |
| `{id}` | ID numérico del usuario |

### Ejemplo de Mensaje

```
[p]tickets addmessage soporte
```

- **Título**: "🎫 Ticket #{num}"
- **Descripción**: 
```
¡Hola {mention}! 👋

Gracias por contactarnos. Un miembro del equipo te atenderá pronto.

**Mientras esperas:**
• Describe tu problema con detalle
• Adjunta capturas de pantalla si es necesario
• Sé paciente, respondemos en orden de llegada

**Tu ID de usuario:** `{id}`
```
- **Footer**: "Ticket creado • El equipo de soporte"

### Ver/Eliminar Mensajes
```
[p]tickets viewmessages soporte
```

---

## 📊 Sistema de Logs y Transcripts

### Configurar Canal de Logs

```
[p]tickets logchannel soporte #logs-tickets
```

El canal de logs mostrará:
- 🟢 Tickets abiertos (quién, cuándo, qué panel)
- 🔴 Tickets cerrados (quién lo cerró, razón)
- 📎 Transcripciones adjuntas (si están activadas)

### Activar Transcripciones

**Transcripciones simples (texto plano):**
```
[p]tickets transcript
```

**Transcripciones interactivas (HTML visual):**
```
[p]tickets interactivetranscript
```

### Recuperar Link de Transcripción

Si necesitas obtener el link de una transcripción antigua:
```
[p]tickets getlink <ID_del_mensaje_de_log>
```

---

## ⚙️ Configuración Avanzada

### Usar Hilos en Lugar de Canales

```
[p]tickets usethreads soporte
```

**Ventajas de los hilos:**
- ✅ Más ligero para el servidor
- ✅ No llena la categoría de canales
- ✅ Mejor organización

**Requisitos para hilos:**
- El bot necesita `Create Private Threads` y `Send Messages in Threads`

### Auto-Cierre por Inactividad

Cierra tickets automáticamente si no hay actividad:

```
[p]tickets noresponse 24
```
*Cierra tickets sin respuesta del usuario después de 24 horas.*

```
[p]tickets noresponse 0
```
*Desactiva el auto-cierre.*

### Formato del Nombre del Canal/Hilo

Personaliza cómo se nombran los tickets:

```
[p]tickets ticketname soporte ticket-{num}-{user}
```

**Variables disponibles:**

| Variable | Resultado | Ejemplo |
|----------|-----------|---------|
| `{num}` | Número de ticket | 42 |
| `{user}` | Nombre de usuario | john |
| `{displayname}` | Nombre mostrado | John Doe |
| `{id}` | ID del usuario | 123456789 |
| `{shortdate}` | Fecha corta | 12-25 |
| `{longdate}` | Fecha larga | 12-25-2024 |
| `{time}` | Hora | 03-45-PM |

**Ejemplos:**
```
[p]tickets ticketname soporte ticket-{num}
# Resultado: ticket-1, ticket-2, ticket-3...

[p]tickets ticketname soporte {user}-{shortdate}
# Resultado: john-12-25, maria-12-26...

[p]tickets ticketname soporte soporte-{num}-{displayname}
# Resultado: soporte-1-John Doe, soporte-2-Maria...
```

### Permitir que Usuarios Renombren su Ticket

```
[p]tickets selfrename
```

### Permitir que Usuarios Cierren su Ticket

```
[p]tickets selfclose
```

### Permitir que Usuarios Añadan Otros Usuarios

```
[p]tickets selfmanage
```

### Modal de Razón al Cerrar

Solicita una razón cuando alguien cierra el ticket:

```
[p]tickets closemodal soporte
```

### Canal/Categoría Alternativa

Abre tickets en un lugar diferente al configurado:

```
# Para paneles de canales (necesita una categoría)
[p]tickets altchannel soporte #CategoríaAlternativa

# Para paneles de hilos (necesita un canal de texto)
[p]tickets altchannel soporte #canal-alternativo
```

### Auto-añadir Roles a Hilos

Añade automáticamente los roles de soporte a los hilos:

```
[p]tickets autoadd
```

> ⚠️ **Nota**: Añadir usuarios a hilos los menciona, por eso está desactivado por defecto.

### Suspender el Sistema de Tickets

Desactiva temporalmente la apertura de tickets:

```
[p]tickets suspend "El sistema de soporte está en mantenimiento. Vuelve mañana."
```

**Reactivar:**
```
[p]tickets suspend
```

---

## 🎛️ Paneles Multi-Botón

Puedes tener **múltiples paneles** en el **mismo mensaje**, creando un sistema con varios botones.

### Ejemplo: Panel con 3 Tipos de Soporte

```
# Paso 1: Crear el embed base
[p]tickets embed #2B2D31 #soporte "🎯 Centro de Soporte" "Selecciona el tipo de ayuda que necesitas:\n\n🛠️ **Soporte Técnico** - Problemas con el bot o servidor\n💰 **Ventas** - Preguntas sobre compras\n📋 **General** - Otras consultas"

# Paso 2: Crear los tres paneles
[p]tickets addpanel tecnico
[p]tickets addpanel ventas  
[p]tickets addpanel general

# Paso 3: Configurar cada panel con la MISMA categoría y canal
[p]tickets category tecnico #TICKETS
[p]tickets category ventas #TICKETS
[p]tickets category general #TICKETS

[p]tickets channel tecnico #soporte
[p]tickets channel ventas #soporte
[p]tickets channel general #soporte

# Paso 4: Vincular todos al MISMO mensaje
[p]tickets panelmessage tecnico 123456789012345678
[p]tickets panelmessage ventas 123456789012345678
[p]tickets panelmessage general 123456789012345678

# Paso 5: Personalizar cada botón
[p]tickets buttontext tecnico "🛠️ Soporte Técnico"
[p]tickets buttoncolor tecnico blue
[p]tickets panelrole tecnico @EquipoTecnico true

[p]tickets buttontext ventas "💰 Ventas"
[p]tickets buttoncolor ventas green
[p]tickets panelrole ventas @EquipoVentas true

[p]tickets buttontext general "📋 General"
[p]tickets buttoncolor general grey
```

### Controlar el Orden de los Botones

```
[p]tickets priority tecnico 1
[p]tickets priority ventas 2
[p]tickets priority general 3
```

*Los botones se ordenan de menor a mayor prioridad.*

### Organizar Botones en Filas

Discord permite hasta 5 botones por fila (0-4 = 5 filas posibles):

```
[p]tickets row tecnico 0
[p]tickets row ventas 0
[p]tickets row general 1
```

*tecnico y ventas estarán en la primera fila, general en la segunda.*

---

## 👤 Comandos de Usuario

Estos comandos pueden ser usados por los usuarios dentro de sus tickets:

### Añadir Usuario al Ticket
```
[p]add @Usuario
/add @Usuario
```

### Renombrar el Ticket
```
[p]renameticket nuevo-nombre
/renameticket nuevo-nombre
```
*Requiere que `selfrename` esté activado.*

### Cerrar el Ticket
```
[p]close
[p]close Problema resuelto, gracias!
[p]close 1h
[p]close 30m Cerrando en 30 minutos si no hay respuesta
/close
```

**Formatos de tiempo aceptados:**
- `1h` = 1 hora
- `30m` = 30 minutos
- `2d` = 2 días

---

## 📋 Gestión de Tickets

### Overview de Tickets Activos

Configura un canal que muestre todos los tickets activos en tiempo real:

```
[p]tickets overview #tickets-activos
```

**Mostrar menciones de canal:**
```
[p]tickets overviewmention
```

### Abrir Ticket para Otro Usuario (Moderadores)

```
[p]openfor @Usuario soporte
/openfor @Usuario soporte
```

### Limpieza de Tickets Inválidos

Elimina tickets de la configuración que ya no existen:

```
[p]tickets cleanup
```

### Ver Configuración Actual

```
[p]tickets view
```

### Ver Paneles Configurados

```
[p]tickets panels
```

### Activar/Desactivar un Panel

```
[p]tickets toggle soporte
```
*El botón seguirá visible pero estará desactivado.*

---

## 🔧 Solución de Problemas

### El botón no aparece en el mensaje

1. Verifica que el panel tenga categoría, canal y mensaje configurados
2. Ejecuta `[p]tickets panels` para ver si todo está correcto
3. El bot debe haber enviado el mensaje (no puede añadir botones a mensajes de otros)

### Error de permisos al crear tickets

Verifica que el bot tenga en la categoría de tickets:
- `Manage Channels`
- `Manage Roles`
- `View Channel`
- `Send Messages`

### Los hilos no se crean

Verifica que el bot tenga:
- `Create Private Threads`
- `Send Messages in Threads`

### Las transcripciones no se guardan

1. Verifica que `[p]tickets transcript` esté activado
2. El bot necesita `Attach Files` en el canal de logs

### El panel dejó de funcionar después de reiniciar

El bot reinicializa automáticamente los paneles. Si no funciona:
```
[p]reload tickets
```

### Limpiar tickets huérfanos
```
[p]tickets cleanup
```

---

## 📚 Referencia Completa de Comandos

### Comandos de Administración (`[p]tickets` o `[p]tset`)

| Comando | Descripción |
|---------|-------------|
| `setuphelp` | Muestra la guía de configuración |
| `view` | Ver configuración actual |
| `panels` | Ver/Eliminar paneles configurados |
| `addpanel <nombre>` | Crear nuevo panel |
| `category <panel> <categoría>` | Asignar categoría |
| `channel <panel> <canal>` | Asignar canal del panel |
| `panelmessage <panel> <mensaje_id>` | Vincular mensaje |
| `embed <color> <canal> <título> <descripción>` | Crear embed |
| `buttontext <panel> <texto>` | Texto del botón |
| `buttoncolor <panel> <color>` | Color del botón |
| `buttonemoji <panel> <emoji>` | Emoji del botón |
| `toggle <panel>` | Activar/Desactivar panel |
| `priority <panel> <número>` | Orden del botón |
| `row <panel> <0-4>` | Fila del botón |
| `usethreads <panel>` | Toggle hilos/canales |
| `ticketname <panel> <formato>` | Formato del nombre |
| `logchannel <panel> <canal>` | Canal de logs |
| `addmessage <panel>` | Añadir mensaje de ticket |
| `viewmessages <panel>` | Ver/Eliminar mensajes |
| `addmodal <panel> <nombre_campo>` | Añadir campo de modal |
| `viewmodal <panel>` | Ver/Eliminar modales |
| `modaltitle <panel> <título>` | Título del modal |
| `closemodal <panel>` | Toggle modal de cierre |
| `supportrole <rol> [mention]` | Rol de soporte global |
| `panelrole <panel> <rol> [mention]` | Rol de soporte del panel |
| `openrole <panel> <rol>` | Rol requerido para abrir |
| `blacklist <usuario_o_rol>` | Añadir/Quitar de blacklist |
| `maxtickets <cantidad>` | Máx tickets por usuario |
| `maxclaims <panel> <cantidad>` | Máx staff por ticket |
| `dm` | Toggle DMs al cerrar |
| `transcript` | Toggle transcripciones |
| `interactivetranscript` | Toggle HTML transcripts |
| `selfclose` | Toggle usuarios cierran |
| `selfrename` | Toggle usuarios renombran |
| `selfmanage` | Toggle usuarios añaden otros |
| `noresponse <horas>` | Auto-cierre por inactividad |
| `autoadd` | Auto-añadir roles a hilos |
| `threadclose` | Toggle archivar vs eliminar |
| `overview [canal]` | Panel de overview |
| `overviewmention` | Toggle menciones en overview |
| `altchannel <panel> <canal>` | Canal alternativo |
| `suspend [mensaje]` | Suspender sistema |
| `cleanup` | Limpiar tickets inválidos |
| `getlink <mensaje>` | Obtener link de transcript |
| `updatemessage <origen> <destino>` | Actualizar mensaje |

### Comandos de Usuario

| Comando | Descripción |
|---------|-------------|
| `[p]add <usuario>` | Añadir usuario al ticket |
| `[p]renameticket <nombre>` | Renombrar ticket |
| `[p]close [razón]` | Cerrar ticket |
| `[p]openfor <usuario> <panel>` | Abrir ticket para otro (MOD) |

---

## 🎉 ¡Listo!

¡Felicidades! Ahora tienes un sistema completo de tickets configurado en tu servidor. 

### Resumen de lo que puedes hacer:

- ✅ Múltiples paneles con diferentes propósitos
- ✅ Formularios personalizados antes de abrir tickets
- ✅ Logs y transcripciones automáticas
- ✅ Roles de soporte globales y por panel
- ✅ Control total sobre quién puede abrir tickets
- ✅ Personalización visual completa
- ✅ Soporte tanto para canales como hilos

### ¿Necesitas ayuda?

- Revisa `[p]tickets setuphelp` para la guía rápida
- Usa `[p]tickets view` para ver tu configuración actual
- Usa `[p]tickets panels` para revisar tus paneles

---

<div align="center">

**Desarrollado con ❤️ para la comunidad de Red-DiscordBot**

*Versión 2.9.12 | Autor: [vertyco](https://github.com/vertyco/vrt-cogs)*

</div>
