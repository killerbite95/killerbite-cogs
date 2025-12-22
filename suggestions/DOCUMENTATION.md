# SimpleSuggestions

Sistema de sugerencias para Discord con soporte para hilos, votaciones y panel de control web.

## 📋 Características

- **Canal de sugerencias dedicado**: Las sugerencias se envían a un canal específico
- **Sistema de votación**: Reacciones automáticas 👍/👎 en cada sugerencia
- **Numeración automática**: Cada sugerencia recibe un ID único incremental
- **Gestión de estados**: Aprobar o rechazar sugerencias con indicadores visuales
- **Hilos de discusión**: Opción para crear hilos automáticos por sugerencia
- **Edición de sugerencias**: Los usuarios pueden editar sus propias sugerencias pendientes
- **Integración con Dashboard**: Panel web para gestionar sugerencias

---

## 📥 Instalación

```
[p]repo add killerbite-cogs https://github.com/killerbite95/killerbite-cogs
[p]cog install killerbite-cogs suggestions
[p]load suggestions
```

---

## ⚙️ Configuración Inicial

### 1. Establecer el canal de sugerencias (Requerido)
```
[p]setsuggestionchannel #canal-sugerencias
```

### 2. Establecer el canal de logs (Opcional)
```
[p]setlogchannel #logs-sugerencias
```

### 3. Activar hilos para sugerencias (Opcional)
```
[p]togglesuggestionthreads
```

### 4. Activar archivado automático de hilos (Opcional)
```
[p]togglethreadarchive
```

---

## 📝 Comandos

### Comandos para Usuarios

| Comando | Descripción |
|---------|-------------|
| `[p]suggest <texto>` | Envía una nueva sugerencia |
| `[p]editsuggest <message_id> <nuevo_texto>` | Edita una sugerencia propia (solo si está pendiente) |

### Comandos de Administración

| Comando | Descripción | Permisos |
|---------|-------------|----------|
| `[p]setsuggestionchannel <canal>` | Establece el canal de sugerencias | Admin |
| `[p]setlogchannel <canal>` | Establece el canal de logs | Admin |
| `[p]approve <message_id>` | Aprueba una sugerencia | Admin |
| `[p]deny <message_id>` | Rechaza una sugerencia | Admin |
| `[p]togglesuggestionthreads` | Activa/desactiva hilos automáticos | Admin |
| `[p]togglethreadarchive` | Activa/desactiva archivado de hilos | Admin |

---

## 🎨 Estados de Sugerencias

| Estado | Color | Descripción |
|--------|-------|-------------|
| **Pendiente** | 🔵 Azul | Sugerencia nueva sin revisar |
| **Aprobado** | 🟢 Verde | Sugerencia aceptada |
| **Rechazado** | 🔴 Rojo | Sugerencia denegada |

---

## 📖 Ejemplos de Uso

### Enviar una sugerencia
```
[p]suggest Añadir un canal de música para escuchar juntos
```

**Resultado:**
- Se crea un embed azul con el título "Sugerencia #1"
- Se añaden reacciones 👍 y 👎 automáticamente
- Si los hilos están activados, se crea un hilo de discusión

### Aprobar una sugerencia
```
[p]approve 1234567890123456789
```

**Resultado:**
- El embed cambia a color verde
- Se añade el footer "Aprobado"
- Si está configurado, el hilo se archiva y bloquea

### Rechazar una sugerencia
```
[p]deny 1234567890123456789
```

**Resultado:**
- El embed cambia a color rojo
- Se añade el footer "Rechazado"
- Si está configurado, el hilo se archiva y bloquea

### Editar una sugerencia
```
[p]editsuggest 1234567890123456789 Nuevo texto de mi sugerencia
```

> ⚠️ Solo puedes editar tus propias sugerencias que estén en estado "Pendiente"

---

## 🌐 Integración con Dashboard

Si tienes el cog **Red-Dashboard** instalado, puedes gestionar las sugerencias desde el panel web:

### Páginas disponibles:

| Página | Descripción |
|--------|-------------|
| **Ver sugerencias** | Tabla con todas las sugerencias del servidor |
| **Aprobar sugerencia** | Formulario para aprobar por ID de mensaje |
| **Rechazar sugerencia** | Formulario para rechazar por ID de mensaje |

La tabla de sugerencias muestra:
- ID del mensaje
- Número de sugerencia
- Contenido
- Autor
- Estado actual

---

## 💡 Configuración Recomendada

### Para servidores pequeños/medianos:
```
[p]setsuggestionchannel #sugerencias
```

### Para servidores grandes:
```
[p]setsuggestionchannel #sugerencias
[p]togglesuggestionthreads
[p]togglethreadarchive
```

Los hilos permiten discusiones organizadas sin llenar el canal principal.

---

## ❓ Preguntas Frecuentes

### ¿Dónde encuentro el ID del mensaje?
1. Activa el **Modo Desarrollador** en Discord (Ajustes > Avanzado)
2. Haz clic derecho en el mensaje de la sugerencia
3. Selecciona "Copiar ID del mensaje"

### ¿Puedo cambiar el canal de sugerencias después?
Sí, simplemente usa `[p]setsuggestionchannel #nuevo-canal`. Las sugerencias anteriores permanecerán en el canal antiguo.

### ¿Qué pasa si elimino un mensaje de sugerencia?
La sugerencia seguirá registrada en la base de datos pero no podrá ser gestionada (aprobar/rechazar).

### ¿Los usuarios pueden eliminar sus sugerencias?
No directamente. Un administrador debe eliminar el mensaje manualmente si es necesario.

---

## 📊 Almacenamiento de Datos

Este cog almacena por servidor:
- ID del canal de sugerencias
- ID del canal de logs
- Configuración de hilos
- Contador de sugerencias
- Registro de sugerencias (ID mensaje, contenido, autor, estado)

---

## 🔗 Enlaces

- **Repositorio**: [killerbite-cogs](https://github.com/killerbite95/killerbite-cogs)
- **Autor**: Killerbite95
- **Soporte**: Abre un issue en GitHub

---

## 📜 Changelog

### v1.0.0
- Sistema básico de sugerencias
- Comandos approve/deny
- Soporte para hilos
- Integración con Dashboard
