"""
Dashboard integration for AdvCheck.
Ficha de un miembro (mods).

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
        name="check",
        description="Ficha de un miembro: roles, fechas, permisos y sanciones",
        methods=("GET", "POST"),
    )
    async def rpc_check_page(self, guild_id: int, **kwargs) -> typing.Dict[str, typing.Any]:
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return _error("Servidor no encontrado.")
        denied = await self._dashboard_denied(guild, kwargs, mod=True)
        if denied:
            return denied
        query = _form_value(kwargs, "member") if kwargs.get("method") == "POST" else ""
        member = None
        if query:
            if query.isdigit():
                member = guild.get_member(int(query))
            else:
                lowered = query.lower()
                member = next((m for m in guild.members if m.name.lower() == lowered or m.display_name.lower() == lowered), None)
        info = None
        if member is not None:
            ban_info = None
            prune = self.bot.get_cog("PruneBans")
            if prune is not None:
                ban_info = (await prune.config.guild(guild).ban_track()).get(str(member.id))
            info = {
                "name": str(member),
                "display": member.display_name,
                "id": member.id,
                "avatar": member.display_avatar.url,
                "created": member.created_at.strftime("%Y-%m-%d"),
                "joined": member.joined_at.strftime("%Y-%m-%d") if member.joined_at else "?",
                "roles": [r.name for r in reversed(member.roles) if not r.is_default()],
                "perms": [p.replace("_", " ") for p, v in member.guild_permissions if v],
                "bot": member.bot,
                "timeout": member.timed_out_until.strftime("%Y-%m-%d %H:%M UTC") if member.is_timed_out() else "",
                "ban": ban_info,
            }
        source = """
<div class="trini-tp-settings">
  <h3 class="trini-tp-title"><i class="fa fa-id-card"></i> Ficha de miembro</h3>
  <form method="POST" class="mt-3">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <div class="row align-items-end">
      <div class="col-lg-5 col-md-8 mb-3"><label class="form-label text-xs mb-1">ID o nombre exacto</label>
        <input type="text" class="form-control form-control-sm" name="member" value="{{ query }}" maxlength="100" required></div>
      <div class="col-lg-2 col-md-4 mb-3"><button type="submit" class="btn btn-xs bg-gradient-info mb-0 w-100"><i class="fa fa-search me-1"></i> Buscar</button></div>
    </div>
  </form>
  {% if query and not info %}<p class="text-warning">No se encontro a nadie con "{{ query }}" en este servidor.</p>{% endif %}
  {% if info %}
  <div class="trini-tp-guild-section">
    <div class="trini-tp-guild-header">
      <img src="{{ info.avatar }}" alt="" style="width:40px;height:40px;border-radius:50%" class="me-2">
      <h4>{{ info.display }} <small class="opacity-7">{{ info.name }} · <code>{{ info.id }}</code></small></h4>
      {% if info.bot %}<span class="badge bg-gradient-secondary">bot</span>{% endif %}
      {% if info.timeout %}<span class="badge bg-gradient-warning">aislado hasta {{ info.timeout }}</span>{% endif %}
    </div>
    <div class="row text-sm mt-2">
      <div class="col-md-6 mb-2">Cuenta creada: <strong>{{ info.created }}</strong></div>
      <div class="col-md-6 mb-2">Entro al servidor: <strong>{{ info.joined }}</strong></div>
      <div class="col-12 mb-2">Roles ({{ info.roles|length }}): {{ info.roles|join(", ") or "ninguno" }}</div>
      <div class="col-12 mb-2">Permisos: <small>{{ info.perms|join(", ") or "ninguno" }}</small></div>
      {% if info.ban %}<div class="col-12 mb-2 text-danger">Baneado · creditos en seguimiento: {{ info.ban.get("balance", "?") }} · limpieza: {{ info.ban.get("unban_date", "?")[:10] }}</div>{% endif %}
    </div>
  </div>
  {% endif %}
</div>
"""
        return {"status": 0, "web_content": {"source": source, "query": query, "info": info}}
