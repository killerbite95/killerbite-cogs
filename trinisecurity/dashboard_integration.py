"""
Dashboard integration for TriniSecurity.
Pagina de estado (solo lectura): modulos, incidentes, cuarentena y eventos.

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
        name="status",
        description="Estado de Trini Security, incidentes y eventos recientes",
        methods=("GET",),
    )
    async def rpc_security_status(self, guild_id: int, **kwargs) -> typing.Dict[str, typing.Any]:
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return _error("Servidor no encontrado.")
        denied = await self._dashboard_denied(guild, kwargs)
        if denied:
            return denied
        import datetime

        def when(ts) -> str:
            try:
                return datetime.datetime.fromtimestamp(float(ts), datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            except (TypeError, ValueError, OSError):
                return "?"

        def who(user_id) -> str:
            if not user_id:
                return "sistema"
            member = guild.get_member(int(user_id))
            return str(member) if member else str(user_id)

        data = await self.config.guild(guild).all()
        antinuke = self._merged_antinuke(data["antinuke"])
        log_channel = guild.get_channel(data["log_channel"]) if data["log_channel"] else None
        incidents = sorted(data["incidents"].values(), key=lambda i: -i["id"])
        status = {
            "log_channel": f"#{log_channel.name}" if log_channel else "",
            "lockdown": bool(data["lockdown"].get("active")),
            "watch": bool(data["watch"].get("enabled")),
            "watch_level": data["watch"].get("level", "normal"),
            "antinuke": bool(antinuke.get("enabled")),
            "protected_roles": len(data["protected_roles"]),
            "extra_owners": len(data["authority"].get("extra_owners", [])),
            "trusted_admins": len(data["authority"].get("trusted_admins", [])),
            "quarantined": len(data["quarantined"]),
            "open_incidents": sum(1 for i in incidents if not i.get("closed")),
            "health": data.get("last_health"),
            "audit_log": guild.me.guild_permissions.view_audit_log,
        }
        incident_rows = [
            {"id": i["id"], "when": when(i.get("start")), "actor": who(i.get("actor")), "level": i.get("level", ""),
             "events": len(i.get("events", [])), "closed": bool(i.get("closed"))}
            for i in incidents[:20]
        ]
        event_rows = [
            {"when": when(e.get("ts")), "type": e.get("type", ""), "actor": who(e.get("actor")),
             "target": e.get("target_name", ""), "detail": e.get("detail", ""), "severity": e.get("severity", "info")}
            for e in reversed(data["events"][-30:])
        ]
        quarantine_rows = [
            {"user": who(uid), "when": when(q.get("at")), "reason": q.get("reason", ""), "roles": len(q.get("roles", []))}
            for uid, q in data["quarantined"].items()
        ]
        severity_class = {"critical": "danger", "warning": "warning", "info": "info"}

        source = """
<div class="trini-tp-settings">
  <h3 class="trini-tp-title"><i class="fa fa-shield"></i> Trini Security</h3>
  <p class="trini-tp-subtitle">Solo lectura: las acciones (lockdown, cuarentena, whitelists...) se hacen desde Discord con <code>security</code>.</p>

  <div class="trini-tp-guild-section">
    <div class="trini-tp-guild-header"><h4><i class="fa fa-heartbeat me-1"></i> Estado</h4>
      {% if s.lockdown %}<span class="badge bg-gradient-danger">LOCKDOWN ACTIVO</span>{% endif %}
      {% if s.health is not none %}<span class="badge bg-gradient-info ms-1">Health {{ s.health }}/100</span>{% endif %}
    </div>
    <div class="row mt-2 text-sm">
      <div class="col-md-4 mb-2">Canal de alertas: <strong>{{ s.log_channel or "sin configurar" }}</strong></div>
      <div class="col-md-4 mb-2">Security Watch: <strong>{{ "activo (" ~ s.watch_level ~ ")" if s.watch else "desactivado" }}</strong></div>
      <div class="col-md-4 mb-2">Anti-Nuke: <strong>{{ "activo" if s.antinuke else "desactivado" }}</strong></div>
      <div class="col-md-4 mb-2">Protected Roles: <strong>{{ s.protected_roles }}</strong></div>
      <div class="col-md-4 mb-2">Authority: <strong>{{ s.extra_owners }}</strong> Extra Owners · <strong>{{ s.trusted_admins }}</strong> Trusted Admins</div>
      <div class="col-md-4 mb-2">En cuarentena: <strong>{{ s.quarantined }}</strong> · Incidentes abiertos: <strong>{{ s.open_incidents }}</strong></div>
    </div>
    {% if not s.audit_log %}<p class="text-warning text-sm">⚠️ El bot no tiene "Ver registro de auditoria": no puede atribuir acciones.</p>{% endif %}
  </div>

  <div class="trini-tp-guild-section">
    <div class="trini-tp-guild-header"><h4><i class="fa fa-folder-open me-1"></i> Incidentes</h4></div>
    {% if incidents|length > 0 %}
    <div class="table-responsive"><table class="table trini-table trini-tp-table">
      <thead><tr><th>#</th><th>Inicio</th><th>Autor</th><th>Nivel</th><th>Eventos</th><th>Estado</th></tr></thead>
      <tbody>{% for i in incidents %}
        <tr><td>{{ i.id }}</td><td><small>{{ i.when }}</small></td><td>{{ i.actor }}</td><td>{{ i.level }}</td><td>{{ i.events }}</td>
        <td>{% if i.closed %}<span class="badge bg-gradient-secondary">cerrado</span>{% else %}<span class="badge bg-gradient-danger">abierto</span>{% endif %}</td></tr>
      {% endfor %}</tbody></table></div>
    {% else %}<p class="text-sm opacity-6">No hay incidentes registrados.</p>{% endif %}
  </div>

  {% if quarantine|length > 0 %}
  <div class="trini-tp-guild-section">
    <div class="trini-tp-guild-header"><h4><i class="fa fa-lock me-1"></i> Cuarentena</h4></div>
    <div class="table-responsive"><table class="table trini-table trini-tp-table">
      <thead><tr><th>Usuario</th><th>Desde</th><th>Roles retirados</th><th>Motivo</th></tr></thead>
      <tbody>{% for q in quarantine %}<tr><td>{{ q.user }}</td><td><small>{{ q.when }}</small></td><td>{{ q.roles }}</td><td><small>{{ q.reason }}</small></td></tr>{% endfor %}</tbody>
    </table></div>
  </div>
  {% endif %}

  <div class="trini-tp-guild-section">
    <div class="trini-tp-guild-header"><h4><i class="fa fa-list me-1"></i> Ultimos eventos</h4></div>
    {% if events|length > 0 %}
    <div class="table-responsive"><table class="table trini-table trini-tp-table">
      <thead><tr><th>Fecha</th><th>Tipo</th><th>Autor</th><th>Objetivo</th><th>Detalle</th></tr></thead>
      <tbody>{% for e in events %}
        <tr><td><small>{{ e.when }}</small></td><td><span class="badge bg-gradient-{{ severity_class.get(e.severity, 'info') }}">{{ e.type }}</span></td>
        <td>{{ e.actor }}</td><td>{{ e.target }}</td><td><small>{{ e.detail }}</small></td></tr>
      {% endfor %}</tbody></table></div>
    {% else %}<p class="text-sm opacity-6">Sin eventos.</p>{% endif %}
  </div>
</div>
"""
        return {
            "status": 0,
            "web_content": {
                "source": source,
                "s": status,
                "incidents": incident_rows,
                "events": event_rows,
                "quarantine": quarantine_rows,
                "severity_class": severity_class,
            },
        }
