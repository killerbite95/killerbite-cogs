"""
Dashboard integration for APIv2.
Estado de la API, claves (sin tokens) y webhooks (solo owner).

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
        name=None,
        description="API v2: estado del servidor, claves y webhooks",
        methods=("GET",),
        is_owner=True,
    )
    async def rpc_api_page(self, **kwargs) -> typing.Dict[str, typing.Any]:
        user = kwargs.get("user")
        if user is None or user.id not in self.bot.owner_ids:
            return {"status": 1, "message": "Forbidden access.", "error_code": 403,
                    "error_message": "Solo el owner del bot puede ver la API."}
        import datetime

        def fmt(value) -> str:
            if not value:
                return "nunca"
            try:
                if isinstance(value, (int, float)):
                    value = datetime.datetime.fromtimestamp(value, datetime.timezone.utc)
                elif isinstance(value, str):
                    value = datetime.datetime.fromisoformat(value)
                return value.strftime("%Y-%m-%d %H:%M")
            except (TypeError, ValueError, OSError):
                return str(value)

        keys = [
            {"name": k["name"], "active": k["active"], "created": fmt(k.get("created_at")),
             "last_used": fmt(k.get("last_used")), "limit": k.get("rate_limit") or "por defecto"}
            for k in await self.key_manager.list_keys()
        ]
        webhooks = []
        for hook in await self.webhook_manager.list_webhooks():
            webhooks.append({"name": hook.get("name", ""), "events": ", ".join(hook.get("events", [])),
                             "active": hook.get("active", True)})
        source = """
<div class="trini-tp-settings">
  <h3 class="trini-tp-title"><i class="fa fa-plug"></i> API v2</h3>
  <p class="trini-tp-subtitle">Servidor: <code>{{ host }}:{{ port }}</code> · {{ "en marcha" if running else "parado" }}.
    Los tokens no se muestran nunca: crealos o revocalos desde Discord.</p>
  <div class="trini-tp-guild-section">
    <div class="trini-tp-guild-header"><h4>Claves</h4><span class="badge bg-gradient-info">{{ keys|length }}</span></div>
    {% if keys|length > 0 %}
    <div class="table-responsive"><table class="table trini-table trini-tp-table">
      <thead><tr><th>Nombre</th><th>Estado</th><th>Creada</th><th>Ultimo uso</th><th>Limite/min</th></tr></thead>
      <tbody>{% for k in keys %}<tr><td><strong>{{ k.name }}</strong></td>
        <td>{% if k.active %}<span class="badge bg-gradient-success">activa</span>{% else %}<span class="badge bg-gradient-secondary">revocada</span>{% endif %}</td>
        <td><small>{{ k.created }}</small></td><td><small>{{ k.last_used }}</small></td><td>{{ k.limit }}</td></tr>{% endfor %}</tbody>
    </table></div>
    {% else %}<p class="text-sm opacity-6">No hay claves.</p>{% endif %}
  </div>
  <div class="trini-tp-guild-section">
    <div class="trini-tp-guild-header"><h4>Webhooks</h4><span class="badge bg-gradient-info">{{ webhooks|length }}</span></div>
    {% if webhooks|length > 0 %}
    <div class="table-responsive"><table class="table trini-table trini-tp-table">
      <thead><tr><th>Nombre</th><th>Eventos</th><th>Estado</th></tr></thead>
      <tbody>{% for w in webhooks %}<tr><td>{{ w.name }}</td><td><small>{{ w.events }}</small></td><td>{{ "activo" if w.active else "pausado" }}</td></tr>{% endfor %}</tbody>
    </table></div>
    {% else %}<p class="text-sm opacity-6">No hay webhooks.</p>{% endif %}
  </div>
</div>
"""
        return {"status": 0, "web_content": {
            "source": source, "keys": keys, "webhooks": webhooks,
            "host": await self.config.host(), "port": await self.config.port(), "running": self._site is not None}}
