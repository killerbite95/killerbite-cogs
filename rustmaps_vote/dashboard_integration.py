"""
Dashboard integration for RustMapsVote.
Sesion de votacion actual (mods) y ajustes (admins).

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
        name="votes",
        description="Votacion de mapas de Rust: sesion actual y ajustes",
        methods=("GET", "POST"),
    )
    async def rpc_votes_page(self, guild_id: int, **kwargs) -> typing.Dict[str, typing.Any]:
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return _error("Servidor no encontrado.")
        denied = await self._dashboard_denied(guild, kwargs, mod=True)
        if denied:
            return denied
        can_edit = await self._dashboard_denied(guild, kwargs) is None
        notifications = []
        if kwargs.get("method") == "POST":
            if not can_edit:
                notifications.append({"message": "Solo los administradores pueden cambiar los ajustes.", "category": "danger"})
            else:
                channel_id = _form_value(kwargs, "vote_channel_id")
                channel = guild.get_channel(int(channel_id)) if channel_id.isdigit() else None
                await self.config.guild(guild).vote_channel_id.set(channel.id if channel else None)
                try:
                    await self.config.guild(guild).max_votes_per_user.set(max(1, min(10, int(_form_value(kwargs, "max_votes", "1")))))
                except ValueError:
                    pass
                notifications.append({"message": "Ajustes guardados.", "category": "success"})
        conf = await self.config.guild(guild).all()
        session = conf["vote_session_data"] or {}
        votes = session.get("votes", {})
        counts: typing.Dict[str, int] = {}
        for chosen in votes.values():
            for map_id in chosen:
                counts[map_id] = counts.get(map_id, 0) + 1
        maps = sorted(
            ({"id": m.get("map_id", ""), "size": m.get("size", 0), "seed": m.get("seed", 0), "url": m.get("url") or "",
              "type": m.get("map_type") or "", "votes": counts.get(m.get("map_id", ""), 0)} for m in session.get("maps", [])),
            key=lambda m: -m["votes"],
        )
        channels = [{"id": c.id, "name": f"#{c.name}", "selected": c.id == conf["vote_channel_id"]}
                    for c in sorted(guild.text_channels, key=lambda c: c.position)]
        source = """
<div class="trini-tp-settings">
  <h3 class="trini-tp-title"><i class="fa fa-map"></i> RustMaps · Votacion</h3>
  <p class="trini-tp-subtitle">Sesion: <strong>{{ "abierta" if active else "cerrada" }}</strong> · {{ voters }} votantes · sesiones totales: {{ counter }}</p>
  {% if maps|length > 0 %}
  <div class="trini-tp-guild-section">
    <div class="trini-tp-guild-header"><h4>Mapas de la {{ "sesion actual" if active else "ultima sesion" }}</h4></div>
    <div class="table-responsive"><table class="table trini-table trini-tp-table">
      <thead><tr><th>Mapa</th><th>Tamaño</th><th>Seed</th><th>Tipo</th><th>Votos</th></tr></thead>
      <tbody>{% for m in maps %}<tr>
        <td>{% if m.url.startswith("https://") %}<a href="{{ m.url }}" target="_blank" rel="noopener">{{ m.id }}</a>{% else %}{{ m.id }}{% endif %}</td>
        <td>{{ m.size }}</td><td>{{ m.seed }}</td><td>{{ m.type }}</td><td><strong>{{ m.votes }}</strong></td></tr>{% endfor %}</tbody>
    </table></div>
  </div>
  {% endif %}
  {% if can_edit %}
  <div class="trini-tp-guild-section">
    <div class="trini-tp-guild-header"><h4><i class="fa fa-cog me-1"></i> Ajustes</h4></div>
    <form method="POST" class="mt-3">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
      <div class="row align-items-end">
        <div class="col-lg-4 col-md-6 mb-3"><label class="form-label text-xs mb-1">Canal de votacion</label>
          <select class="form-select form-select-sm" name="vote_channel_id"><option value="">-- Ninguno --</option>
            {% for c in channels %}<option value="{{ c.id }}" {{ "selected" if c.selected }}>{{ c.name }}</option>{% endfor %}</select></div>
        <div class="col-lg-2 col-md-3 mb-3"><label class="form-label text-xs mb-1">Votos por usuario</label>
          <input type="number" class="form-control form-control-sm" name="max_votes" value="{{ max_votes }}" min="1" max="10"></div>
        <div class="col-lg-2 col-md-3 mb-3"><button type="submit" class="btn btn-xs bg-gradient-info mb-0 w-100"><i class="fa fa-save me-1"></i> Guardar</button></div>
      </div>
    </form>
  </div>
  {% endif %}
</div>
"""
        result = {"status": 0, "web_content": {
            "source": source, "active": conf["vote_session_active"], "voters": len(votes), "counter": conf["session_counter"],
            "maps": maps, "channels": channels, "max_votes": conf["max_votes_per_user"], "can_edit": can_edit}}
        if notifications:
            result["notifications"] = notifications
        return result
