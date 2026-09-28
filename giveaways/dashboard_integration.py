"""
Dashboard integration for Giveaways.
Pagina de sorteos activos e historial (mods).

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
        name="giveaways",
        description="Sorteos activos e historial",
        methods=("GET",),
    )
    async def rpc_giveaways_page(self, guild_id: int, **kwargs) -> typing.Dict[str, typing.Any]:
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return _error("Servidor no encontrado.")
        denied = await self._dashboard_denied(guild, kwargs, mod=True)
        if denied:
            return denied
        import datetime

        def fmt(dt) -> str:
            if isinstance(dt, (int, float)):
                dt = datetime.datetime.fromtimestamp(dt, datetime.timezone.utc)
            return dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "?"

        def channel_name(channel_id) -> str:
            channel = guild.get_channel(channel_id) if channel_id else None
            return f"#{channel.name}" if channel else str(channel_id or "")

        def member_name(user_id) -> str:
            member = guild.get_member(int(user_id))
            return str(member) if member else str(user_id)

        active = []
        for giveaway in self.giveaways.values():
            if giveaway.guildid != guild.id:
                continue
            active.append({
                "prize": giveaway.prize or "",
                "channel": channel_name(giveaway.channelid),
                "ends": fmt(giveaway.endtime),
                "entrants": len(set(giveaway.entrants)),
                "winners": giveaway.kwargs.get("winners", 1) or 1,
                "sort": giveaway.endtime.timestamp() if giveaway.endtime else 0,
            })
        active.sort(key=lambda g: g["sort"])
        history = [
            {"prize": h.get("prize") or "", "ended": fmt(h.get("ended_at", 0)), "channel": channel_name(h.get("channel_id")),
             "entrants": h.get("entrant_count", 0), "winners": ", ".join(member_name(w) for w in h.get("winners", [])) or "—"}
            for h in reversed((await self.config.guild(guild).history())[-25:])
        ]
        source = """
<div class="trini-tp-settings">
  <h3 class="trini-tp-title"><i class="fa fa-gift"></i> Sorteos</h3>
  <p class="trini-tp-subtitle">Crear sorteos: <code>giveaway create</code> en Discord.</p>
  <div class="trini-tp-guild-section">
    <div class="trini-tp-guild-header"><h4>Activos</h4><span class="badge bg-gradient-success">{{ active|length }}</span></div>
    {% if active|length > 0 %}
    <div class="table-responsive"><table class="table trini-table trini-tp-table">
      <thead><tr><th>Premio</th><th>Canal</th><th>Termina</th><th>Participantes</th><th>Ganadores</th></tr></thead>
      <tbody>{% for g in active %}<tr><td><strong>{{ g.prize }}</strong></td><td>{{ g.channel }}</td><td><small>{{ g.ends }}</small></td><td>{{ g.entrants }}</td><td>{{ g.winners }}</td></tr>{% endfor %}</tbody>
    </table></div>
    {% else %}<p class="text-sm opacity-6">No hay sorteos activos.</p>{% endif %}
  </div>
  <div class="trini-tp-guild-section">
    <div class="trini-tp-guild-header"><h4>Historial</h4></div>
    {% if history|length > 0 %}
    <div class="table-responsive"><table class="table trini-table trini-tp-table">
      <thead><tr><th>Premio</th><th>Termino</th><th>Canal</th><th>Participantes</th><th>Ganadores</th></tr></thead>
      <tbody>{% for h in history %}<tr><td>{{ h.prize }}</td><td><small>{{ h.ended }}</small></td><td>{{ h.channel }}</td><td>{{ h.entrants }}</td><td>{{ h.winners }}</td></tr>{% endfor %}</tbody>
    </table></div>
    {% else %}<p class="text-sm opacity-6">Sin sorteos terminados.</p>{% endif %}
  </div>
</div>
"""
        return {"status": 0, "web_content": {"source": source, "active": active, "history": history}}
