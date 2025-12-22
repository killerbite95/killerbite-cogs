# SimpleSuggestions v2.0.0

Sistema de sugerencias completo para Discord con botones interactivos, votaciones persistentes, múltiples estados y panel de control web.

## ✨ Novedades en v2.0.0

- **🔘 Botones interactivos**: Vota, edita y gestiona sugerencias con botones
- **♻️ Views persistentes**: Los botones funcionan incluso tras reiniciar el bot
- **🔒 Contador atómico**: Sin duplicados de ID aunque haya spam simultáneo
- **📊 9 estados diferentes**: Pendiente, En revisión, Planeado, En progreso, Aprobado, Implementado, Rechazado, Duplicado, No se hará
- **📜 Historial de cambios**: Auditoría completa de cada sugerencia
- **🔔 Notificaciones**: DM al autor cuando cambia el estado
- **🛠️ Comandos de mantenimiento**: resync, repost, purge
- **⚡ Comandos híbridos**: Funcionan con prefix y slash commands
- **🌐 Dashboard mejorado**: Filtros, paginación y gestión web

---

## 📋 Características

- **Canal de sugerencias dedicado**: Las sugerencias se envían a un canal específico
- **Sistema de votación**: Botones 👍/👎 o reacciones (configurable)
- **Numeración automática**: Cada sugerencia recibe un ID único incremental
- **Gestión de estados**: Múltiples estados con indicadores visuales de color
- **Hilos de discusión**: Opción para crear hilos automáticos por sugerencia
- **Edición de sugerencias**: Los usuarios pueden editar sus propias sugerencias pendientes
- **Integración con Dashboard**: Panel web completo para gestionar sugerencias

---

## 📥 Instalación

```
[p]repo add killerbite-cogs https://github.com/killerbite95/killerbite-cogs
[p]cog install killerbite-cogs suggestions
[p]load suggestions
```

---

## ⚙️ Configuración Inicial

### Configuración rápida
```
[p]suggestset channel #sugerencias
```

### Ver toda la configuración
```
[p]suggestset settings
```

---

## 📝 Comandos

### Comandos para Usuarios

| Comando | Descripción |
|---------|-------------|
| `[p]suggest <texto>` | Envía una nueva sugerencia |
| `/suggest` | Envía sugerencia con modal interactivo |
| `[p]editsuggest <ref> <nuevo_texto>` | Edita una sugerencia propia |
| `[p]mysuggestions` | Ver tus propias sugerencias |
| `[p]suggestioninfo <ref>` | Ver información detallada |

### Comandos de Staff

| Comando | Descripción |
|---------|-------------|
| `[p]approve <ref> [motivo]` | Aprueba una sugerencia |
| `[p]deny <ref> [motivo]` | Rechaza una sugerencia |
| `[p]setstatus <ref> <estado> [motivo]` | Cambia el estado |
| `[p]suggestions [estado]` | Lista sugerencias (con filtro opcional) |
| `[p]suggestionhistory <ref>` | Ver historial de cambios |

### Comandos de Administración

| Comando | Descripción |
|---------|-------------|
| `[p]suggestadmin resync` | Sincroniza mensajes eliminados |
| `[p]suggestadmin repost <ref>` | Re-publica una sugerencia |
| `[p]suggestadmin purge deleted` | Elimina registros huérfanos |

### Configuración (`[p]suggestset`)

| Subcomando | Descripción |
|------------|-------------|
| `channel <#canal>` | Canal de sugerencias |
| `logchannel [#canal]` | Canal de logs |
| `notifychannel [#canal]` | Canal alternativo para notificaciones |
| `staffrole [@rol]` | Rol de staff |
| `buttons` | Alternar botones/reacciones |
| `threads` | Activar/desactivar hilos |
| `autoarchive` | Archivar hilos al cerrar |
| `notify` | Notificar al autor por DM |
| `settings` | Ver configuración actual |

---

## 🔍 Referencias a Sugerencias

Puedes referenciar sugerencias de varias formas:

| Formato | Ejemplo |
|---------|---------|
| ID de sugerencia | `#123` |
| ID de mensaje | `1234567890123456789` |
| URL del mensaje | `https://discord.com/channels/...` |

**Ejemplos:**
```
[p]approve #123 Buena idea!
[p]deny 1234567890 No es viable
[p]setstatus #45 planned Lo haremos en enero
```

---

## 🎨 Estados de Sugerencias

| Estado | Emoji | Color | Descripción |
|--------|-------|-------|-------------|
| Pendiente | 🔵 | Azul | Nueva sin revisar |
| En revisión | 🟡 | Oro | Siendo evaluada |
| Planeado | 🟣 | Púrpura | Aprobada para futuro |
| En progreso | 🟠 | Naranja | En desarrollo |
| Aprobado | 🟢 | Verde | Aceptada |
| Implementado | ✅ | Verde oscuro | Ya implementada |
| Rechazado | 🔴 | Rojo | Denegada |
| Duplicado | 🔄 | Gris | Ya existe otra igual |
| No se hará | ⛔ | Gris oscuro | Descartada |

---

## 🔘 Botones Interactivos

Cada sugerencia incluye botones:

**Fila 1 - Usuarios:**
- 👍 **Upvote** - Votar a favor (toggle)
- 👎 **Downvote** - Votar en contra (toggle)
- 📊 **Ver votos** - Estadísticas detalladas
- ✏️ **Editar** - Solo autor, solo si pendiente

**Fila 2 - Staff:**
- ✅ **Aprobar** - Cambiar a aprobado
- ❌ **Rechazar** - Cambiar a rechazado
- 📋 **Cambiar estado** - Menú de estados

### Sistema de votos
- Los votos se **persisten** en la base de datos
- Un usuario solo puede votar **una vez** (up o down)
- Pulsar el mismo botón **retira** el voto (toggle)
- Pulsar el botón contrario **cambia** el voto

---

## 🌐 Dashboard Web

Si tienes **Red-Dashboard** instalado:

### Página principal (`/suggestions`)
- Lista paginada de sugerencias
- Filtro por estado
- Búsqueda por contenido
- Estadísticas

### Gestión individual (`/manage_suggestion`)
- Ver detalles completos
- Cambiar estado con motivo
- Ver historial de cambios

---

## 🔔 Notificaciones

Cuando cambia el estado de una sugerencia:

1. Se intenta enviar **DM al autor**
2. Si los DMs están cerrados, se envía al **canal de notificaciones** (si está configurado)

El embed incluye:
- Contenido de la sugerencia
- Estado anterior → nuevo
- Motivo (si se proporcionó)
- Quién realizó el cambio

---

## 🛠️ Mantenimiento

### Sincronizar mensajes eliminados
```
[p]suggestadmin resync
```
Verifica qué mensajes existen y marca como eliminadas las sugerencias huérfanas.

### Re-publicar una sugerencia
```
[p]suggestadmin repost #123
```
Crea un nuevo mensaje para una sugerencia eliminada, manteniendo su ID original.

### Limpiar registros
```
[p]suggestadmin purge deleted
```
Elimina permanentemente los registros marcados como eliminados.

---

## 💡 Configuración Recomendada

### Servidor pequeño
```
[p]suggestset channel #sugerencias
```

### Servidor mediano
```
[p]suggestset channel #sugerencias
[p]suggestset threads
```

### Servidor grande
```
[p]suggestset channel #sugerencias
[p]suggestset threads
[p]suggestset autoarchive
[p]suggestset staffrole @Moderadores
[p]suggestset notifychannel #notificaciones
```

---

## 🔄 Migración desde v1.x

La migración es **automática**:
- Los datos se convierten al nuevo formato al usar cualquier comando
- Las sugerencias existentes mantienen sus IDs
- Los estados antiguos se mapean a los nuevos

---

## ❓ FAQ

### ¿Los botones funcionan tras reiniciar el bot?
Sí, gracias al sistema de **persistent views**.

### ¿Qué pasa si varios usuarios votan a la vez?
El sistema usa **locks** para evitar race conditions.

### ¿Puedo usar reacciones en lugar de botones?
Sí: `[p]suggestset buttons` para alternar.

### ¿Puedo tener varios canales de sugerencias?
No, actualmente solo uno por servidor.

---

## 📊 Almacenamiento

Por cada sugerencia se guarda:
- ID de sugerencia (numérico incremental)
- ID del mensaje
- Contenido
- ID del autor
- Estado actual
- Fecha de creación
- ID del hilo (si existe)
- Lista de votos positivos
- Lista de votos negativos
- Motivo del último cambio
- Historial completo de cambios
- Flag de eliminado

---

## 🔗 Enlaces

- **Repositorio**: [killerbite-cogs](https://github.com/killerbite95/killerbite-cogs)
- **Autor**: Killerbite95

---

## 📜 Changelog

### v2.0.0
- Refactor completo del código en módulos
- Sistema de botones interactivos
- Persistent views
- Contador atómico con locks
- Sistema de votos con persistencia
- 9 estados de sugerencias
- Historial de cambios con auditoría
- Notificaciones al autor
- Comandos de mantenimiento
- Dashboard mejorado con filtros y paginación
- Comandos híbridos (prefix + slash)
- Migración automática desde v1.x

### v1.0.0
- Sistema básico de sugerencias
- Comandos approve/deny
- Soporte para hilos
- Integración con Dashboard
