"""
Dashboard integration for TriniBackups.
Pagina de backups: listar, crear y programar (restaurar sigue en Discord).

El Dashboard (AAA3A) solo comprueba que el usuario este en el servidor:
cada pagina exige sus propios permisos con ``_dashboard_denied``.
"""
import typing

from redbot.core import commands
from redbot.core.bot import Red


def dashboard_page(*args, **kwargs):
    def decorator(func: typing.Callable):
        func.__dashboard_decorator_params__ = (args, kwargs)
        return func
    return decorator


def _form_value(kwargs: typing.Dict[str, typing.Any], key: str, default: str = "") -> str:
    form = kwargs.get("data", {}).get("form", {})
    value = form.get(key, [default])
    return (value[0] if isinstance(value, list) else str(value)).strip()


def _error(message: str) -> typing.Dict[str, typing.Any]:
    return {"status": 0, "web_content": {"source": '<div class="trini-tp-empty"><i class="fa fa-exclamation-triangle fa-3x"></i><p>{{ message }}</p></div>', "message": message}}


class DashboardIntegration:
    bot: Red
    config: typing.Any

    async def _dashboard_denied(self, guild, kwargs, *, mod: bool = False, strict: bool = False):
        """Devuelve la respuesta 403 o ``None`` si el usuario puede pasar.

        Pasa el owner del bot, los admins de Red o con Administrador, los que
        tienen Gestionar servidor (salvo con ``strict=True``) y, con
        ``mod=True``, tambien los mods de Red."""
        user = kwargs.get("user")
        user_id = getattr(user, "id", kwargs.get("user_id"))
        if user_id is not None and user_id in self.bot.owner_ids:
            return None
        member = guild.get_member(user_id) if (guild is not None and user_id is not None) else None
        allowed = False
        if member is not None:
            perms = member.guild_permissions
            if perms.administrator or await self.bot.is_admin(member):
                allowed = True
            elif perms.manage_guild and not strict:
                allowed = True
            elif mod and await self.bot.is_mod(member):
                allowed = True
        if allowed:
            return None
        return {
            "status": 1,
            "message": "Forbidden access.",
            "error_code": 403,
            "error_message": "No tienes permisos para acceder a esta pagina.",
        }

    def _dashboard_register(self) -> None:
        dashboard_cog = self.bot.get_cog("Dashboard")
        if dashboard_cog is not None and hasattr(dashboard_cog, "rpc"):
            try:
                dashboard_cog.rpc.third_parties_handler.add_third_party(self)
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_dashboard_cog_add(self, dashboard_cog: commands.Cog) -> None:
        dashboard_cog.rpc.third_parties_handler.add_third_party(self)

    async def cog_load(self) -> None:
        self._dashboard_register()

    @dashboard_page(
        name="backups",
        description="Backups del servidor: listar, crear y programar",
        methods=("GET", "POST"),
    )
    async def rpc_backups_page(self, guild_id: int, **kwargs) -> typing.Dict[str, typing.Any]:
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return _error("Servidor no encontrado.")
        # Igual que los comandos (cog_check): hace falta Administrador.
        denied = await self._dashboard_denied(guild, kwargs, strict=True)
        if denied:
            return denied
        import datetime

        notifications = []
        if kwargs.get("method") == "POST":
            action = _form_value(kwargs, "action")
            if action == "create":
                name = _form_value(kwargs, "name")[:80] or None
                meta = await self.create_snapshot(guild, name=name, kind="manual", author=kwargs.get("user"))
                notifications.append({"message": f"Backup {meta['id']} creado.", "category": "success"})
            elif action == "schedule":
                mode = _form_value(kwargs, "mode")
                try:
                    hour = max(0, min(23, int(_form_value(kwargs, "hour", "3") or 3)))
                except ValueError:
                    hour = 3
                if mode in ("off", "daily", "weekly"):
                    async with self.config.guild(guild).schedule() as schedule:
                        schedule["mode"] = mode
                        schedule["hour"] = hour
                    notifications.append({"message": "Programacion guardada.", "category": "success"})

        def fmt(ts) -> str:
            return datetime.datetime.fromtimestamp(float(ts), datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        kind_label = {"manual": "manual", "auto": "automatico", "security": "seguridad", "pre-restore": "pre-restore"}
        snaps = sorted((await self.config.guild(guild).snapshots()).values(), key=lambda m: -m["created_at"])
        rows = []
        for m in snaps:
            author = guild.get_member(m["author"]) if m.get("author") else None
            counts = m.get("counts", {})
            rows.append({
                "id": m["id"],
                "name": m.get("name") or "",
                "kind": kind_label.get(m.get("kind"), m.get("kind", "")),
                "created": fmt(m["created_at"]),
                "author": str(author) if author else ("sistema" if not m.get("author") else str(m["author"])),
                "roles": counts.get("roles", 0),
                "channels": counts.get("channels", 0),
                "size": f"{m.get('size', 0) / 1024:.1f} KB",
            })
        schedule = await self.config.guild(guild).schedule()
        retention = await self.config.guild(guild).retention()

        source = """
<div class="trini-tp-settings">
  <h3 class="trini-tp-title"><i class="fa fa-archive"></i> Trini Backups</h3>
  <p class="trini-tp-subtitle">Restaurar y borrar backups se hace desde Discord (<code>backup restore</code>), con previsualizacion y confirmacion.</p>

  <div class="trini-tp-guild-section">
    <div class="trini-tp-guild-header"><h4><i class="fa fa-plus me-1"></i> Crear backup</h4></div>
    <form method="POST" class="mt-3">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
      <input type="hidden" name="action" value="create">
      <div class="row align-items-end">
        <div class="col-lg-6 col-md-8 mb-3"><label class="form-label text-xs mb-1">Nombre (opcional)</label>
          <input type="text" class="form-control form-control-sm" name="name" maxlength="80" placeholder="Antes del torneo"></div>
        <div class="col-lg-2 col-md-4 mb-3"><button type="submit" class="btn btn-xs bg-gradient-success mb-0 w-100"><i class="fa fa-save me-1"></i> Crear</button></div>
      </div>
    </form>
  </div>

  <div class="trini-tp-guild-section">
    <div class="trini-tp-guild-header"><h4><i class="fa fa-clock-o me-1"></i> Programacion</h4>
      <small class="text-muted ms-2">Retencion: {{ retention.daily }} diarios · {{ retention.weekly }} semanales · {{ retention.monthly }} mensuales</small></div>
    <form method="POST" class="mt-3">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
      <input type="hidden" name="action" value="schedule">
      <div class="row align-items-end">
        <div class="col-lg-3 col-md-4 mb-3"><label class="form-label text-xs mb-1">Frecuencia</label>
          <select class="form-select form-select-sm" name="mode">
            {% for value, label in [("off", "Desactivado"), ("daily", "Diario"), ("weekly", "Semanal")] %}
            <option value="{{ value }}" {{ "selected" if schedule.mode == value }}>{{ label }}</option>{% endfor %}
          </select></div>
        <div class="col-lg-2 col-md-4 mb-3"><label class="form-label text-xs mb-1">Hora (UTC)</label>
          <input type="number" class="form-control form-control-sm" name="hour" value="{{ schedule.hour }}" min="0" max="23"></div>
        <div class="col-lg-2 col-md-4 mb-3"><button type="submit" class="btn btn-xs bg-gradient-info mb-0 w-100"><i class="fa fa-save me-1"></i> Guardar</button></div>
      </div>
    </form>
  </div>

  <div class="trini-tp-guild-section">
    <div class="trini-tp-guild-header"><h4><i class="fa fa-list me-1"></i> Backups</h4><span class="badge bg-gradient-info">{{ rows|length }}</span></div>
    {% if rows|length > 0 %}
    <div class="table-responsive"><table class="table trini-table trini-tp-table">
      <thead><tr><th>ID</th><th>Nombre</th><th>Tipo</th><th>Fecha</th><th>Autor</th><th>Roles</th><th>Canales</th><th>Tamaño</th></tr></thead>
      <tbody>{% for r in rows %}
        <tr><td><code>{{ r.id }}</code></td><td>{{ r.name }}</td><td>{{ r.kind }}</td><td><small>{{ r.created }}</small></td>
        <td>{{ r.author }}</td><td>{{ r.roles }}</td><td>{{ r.channels }}</td><td><small>{{ r.size }}</small></td></tr>
      {% endfor %}</tbody></table></div>
    {% else %}<div class="trini-tp-empty"><i class="fa fa-archive fa-3x"></i><p>No hay backups.</p></div>{% endif %}
  </div>
</div>
"""
        result = {"status": 0, "web_content": {"source": source, "rows": rows, "schedule": schedule, "retention": retention}}
        if notifications:
            result["notifications"] = notifications
        return result
