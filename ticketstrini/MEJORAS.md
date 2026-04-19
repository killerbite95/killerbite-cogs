# TicketsTrini — Plan de Mejoras

## Prioridad Alta

### A1. Extraer helper de permisos de staff (DRY)

**Archivos:** `commands/base.py`, `common/views.py`  
**Problema:** El mismo bloque de ~12 líneas para verificar si un usuario es staff se repite ~10 veces (add, remove, rename, note, notes, quickreply, claim, transfer, CloseView, StaffActionsView):

```python
panel_roles = conf["panels"][panel_name]["roles"]
user_roles = [r.id for r in ctx.author.roles]
support_roles = [i[0] for i in conf["support_roles"]]
support_roles.extend([i[0] for i in panel_roles])
is_staff = any(i in support_roles for i in user_roles)
if not is_staff and ctx.author.id != ctx.guild.owner_id:
    if not await is_admin_or_superior(self.bot, ctx.author): ...
```

**Solución:** Extraer a `is_ticket_staff(bot, user, guild, conf, panel_name) -> bool` en `common/utils.py`. Llamar desde todos los sitios. Elimina ~200 líneas duplicadas.

---

### A2. Unificar lógica de creación de tickets (DRY)

**Archivos:** `common/views.py` (`SupportButton._open_ticket`, ~400 líneas), `common/functions.py` (`create_ticket_for_user`, ~270 líneas)  
**Problema:** Ambas funciones replican la misma lógica: crear canal/hilo, configurar permisos, construir embed de bienvenida, enviar mensajes, logging, update de overview. Si se cambia algo en una, hay que replicarlo en la otra.  
**Solución:** Extraer a `_create_ticket_internal(guild, user, panel_name, conf, config, modal_answers=None)` en `common/utils.py`. Llamar desde ambos sitios.

---

### B. Loggers con nombre incorrecto (vestigio del fork VRT)

**Archivos afectados:**

| Archivo | Logger actual | Logger correcto |
|---------|--------------|-----------------|
| `commands/base.py:26` | `red.vrt.tickets.base` | `red.killerbite95.tickets.base` |
| `commands/admin.py:40` | `red.vrt.admincommands` | `red.killerbite95.tickets.admin` |
| `common/functions.py:16` | `red.vrt.tickets.functions` | `red.killerbite95.tickets.functions` |

**Nota:** `common/utils.py` ya usa `red.killerbite95.tickets.utils` correctamente.

---

### C. Eliminar dependencia `numpy`

**Archivos:** `common/views.py:665-666`, `common/functions.py:315-316`  
**Problema:** Se usa numpy **solo** para encontrar el valor más cercano en un array de 4 elementos:

```python
arr = np.asarray([60, 1440, 4320, 10080])
index = (np.abs(arr - archive)).argmin()
auto_archive_duration = int(arr[index])
```

**Solución:** Reemplazar con Python puro:

```python
auto_archive_duration = min([60, 1440, 4320, 10080], key=lambda x: abs(x - archive))
```

Eliminar `import numpy as np` de ambos archivos y de `info.json` si está listado.

---

### D. Slash commands en admin.py — describe, autocomplete y choices

**Archivo:** `commands/admin.py`  
**Problema:** 0 decoradores `@app_commands.describe` y 0 funciones de autocomplete. Los usuarios deben escribir nombres de panel de memoria.  
**Solución:**

1. **Autocomplete para `panel_name`:** Crear función que lea los panels del config y sugiera los que coincidan con lo que el usuario escribe. Aplicar a todos los comandos que reciben panel_name (category, channel, panelmessage, buttontext, buttoncolor, buttonemoji, usethreads, addmessage, ticketname, etc.).
2. **Autocomplete para `template_name`:** Para comandos de quickreply (remove, addadvanced).
3. **`@app_commands.choices` para `buttoncolor`:** Dropdown con `red`, `blue`, `green`, `grey`.
4. **`@app_commands.describe`:** Añadir descripciones a todos los parámetros de comandos híbridos.

---

### E. Guard contra panel borrado con tickets abiertos

**Archivos:** `commands/base.py`, `common/utils.py`, `common/views.py`  
**Problema:** Múltiples sitios hacen `conf["panels"][panel_name]` sin verificar que el panel siga existiendo. Si un admin borra un panel mientras hay tickets abiertos → `KeyError` → crash.  
**Solución:** Cambiar accesos directos por:

```python
panel = conf["panels"].get(panel_name)
if not panel:
    log.warning(f"Panel '{panel_name}' not found for ticket in channel {channel.id}")
    return  # o mensaje al usuario
```

---

### F. Feature incompleta: `can_reopen_ticket` es un stub

**Archivos:** `common/utils.py:1773-1793`, `commands/admin.py:2124`  
**Problema:** La función existe, el config `reopen_hours` existe, el comando admin para configurarlo existe... pero `can_reopen_ticket()` siempre retorna `False` y nunca se invoca desde ningún lado.  
**Solución:** Decidir entre:

- **Implementar:** Guardar timestamp de cierre en config, añadir botón "Reopen" en el DM de cierre al usuario, verificar ventana de tiempo.
- **Eliminar:** Borrar la función stub, el setting del config y el comando admin.

---

## Prioridad Media

### G. Race condition en `close_ticket`

**Archivo:** `common/utils.py` (función `close_ticket`)  
**Problema:** Se ejecuta `del opened[uid][cid]` al inicio de la operación. Si falla a mitad (error en transcript, error al borrar canal, etc.), los datos del ticket se pierden irrecuperablemente.  
**Solución:** Mover el `del` al final de la operación dentro de un `try/finally`, o copiar datos a una variable temporal y solo borrar al completar exitosamente.

---

### H. Cache de config con TTL para `on_message`

**Archivo:** `tickets.py` (listener `on_message`)  
**Problema:** Aunque el filtro rápido con `ticket_channel_ids` evita cargar config en canales no-ticket, cuando SÍ es un canal de ticket se ejecuta `await self.config.guild(guild).all()` en cada mensaje. En servidores ocupados esto es costoso.  
**Solución:** Implementar cache con TTL de ~60s:

```python
self._config_cache: Dict[int, Tuple[dict, float]] = {}

async def _get_cached_config(self, guild):
    now = time.time()
    if guild.id in self._config_cache:
        data, ts = self._config_cache[guild.id]
        if now - ts < 60:
            return data
    data = await self.config.guild(guild).all()
    self._config_cache[guild.id] = (data, now)
    return data
```

Invalidar en operaciones que modifiquen config (admin commands).

---

### I. Strings HTML del dashboard sin i18n

**Archivo:** `tickets.py` (método `rpc_view_tickets`)  
**Problema:** Headers HTML hardcodeados en español: `<th>Usuario</th>`, `<th>ID del Canal</th>`, etc.  
**Solución:** Envolver en `_()` o mover a un sistema de templates.

---

### J. `TICKET_STATUSES` sin i18n

**Archivo:** `common/constants.py`  
**Problema:** Valores hardcodeados en inglés:

```python
TICKET_STATUSES = {
    "open": "🟢 Open",
    "claimed": "🔵 Claimed",
    ...
}
```

**Solución:** Envolver valores en `_()`: `"open": _("🟢 Open")`.

---

### K. Respuestas ephemeral inconsistentes

**Archivos:** `commands/base.py`, `common/views.py`, `commands/admin.py`  
**Problema:** Algunos errores son ephemeral, otros públicos. Sin criterio claro.  
**Solución:** Establecer regla:

- **Ephemeral:** Errores de permisos, confirmaciones de acciones individuales, info sensible.
- **Público:** Notificaciones de staff, cambios de estado del ticket, mensajes para el usuario del ticket.

---

### L. Comandos largos sin `defer()`

**Archivos:** `commands/admin.py` (repairviews, preflight, cleanup, export, import, stats)  
**Problema:** Operaciones que tardan >3 segundos no llaman `defer()` → Discord muestra "Application did not respond".  
**Solución:** Añadir `await ctx.defer()` al inicio de comandos pesados.

---

## Prioridad Baja

### M. Lógica de `auto_archive_duration` duplicada

**Archivos:** `common/views.py:665-668`, `common/functions.py:315-318`  
**Problema:** Las mismas 4 líneas de cálculo copiadas.  
**Solución:** Extraer a helper `get_auto_archive_duration(inactive_minutes: int) -> int` en `common/utils.py`. (Se resuelve junto con el punto C de numpy.)

---

### N. `ctx.tick()` como única confirmación

**Archivos:** `commands/base.py` (rename, claim, unclaim)  
**Problema:** Un checkmark como confirmación no da contexto al usuario.  
**Solución:** Reemplazar con embed breve que incluya qué se hizo (ej: "✅ Ticket renombrado a **nuevo-nombre**").

---

### O. TimeParser unidades sin i18n

**Archivo:** `common/models.py` (`TimeParser.format_duration`)  
**Problema:** Retorna strings como `"1h"`, `"30m"`, `"2d"` con letras hardcodeadas.  
**Solución:** Envolver en `_()` o usar formato localizable.

---

### P. Contexto faltante para traductores

**Archivos:** Múltiples  
**Problema:** Strings ambiguos como `_("Claimed")` no tienen contexto — ¿es un verbo en pasado o un estado?  
**Solución:** Añadir comentarios `# Translators:` encima de strings ambiguos, o usar `pgettext("ticket_status", "Claimed")`.

---

## Resumen

| Prioridad | Items | Impacto |
|-----------|-------|---------|
| **Alta** | A1, A2, B, C, D, E, F | ~450 líneas duplicadas eliminadas, quita numpy, autocomplete en slash, previene crashes |
| **Media** | G, H, I, J, K, L | Robustez, rendimiento, i18n, UX de slash commands |
| **Baja** | M, N, O, P | Polish general, mejor experiencia de traducción |
