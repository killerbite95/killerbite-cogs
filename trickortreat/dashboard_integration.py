"""
Dashboard integration for TrickOrTreat.
Ajustes (admins), evento y clasificacion (mods).

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
        name="settings",
        description="Truco o trato: ajustes, evento y clasificacion",
        methods=("GET", "POST"),
    )
    async def rpc_tot_page(self, guild_id: int, **kwargs) -> typing.Dict[str, typing.Any]:
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
                form = kwargs.get("data", {}).get("form", {})
                raw_channels = form.getlist("channels") if hasattr(form, "getlist") else form.get("channels", [])
                channel_ids = [int(c) for c in raw_channels if str(c).isdigit() and guild.get_channel(int(c))]
                group = self.config.guild(guild)
                toggle = _form_value(kwargs, "toggle") == "on"
                await group.toggle.set(toggle)
                await group.channel.set(channel_ids)
                for key, low, high in (("cooldown", 0, 86400), ("pickup_cooldown", 0, 86400), ("steal_cooldown", 0, 86400), ("shield_hours", 0, 168)):
                    try:
                        await group.set_raw(key, value=max(low, min(high, int(_form_value(kwargs, key)))))
                    except (ValueError, TypeError):
                        pass
                # Caches del listener: deben reflejar los cambios al momento.
                self._toggle_cache[guild.id] = toggle
                self._channel_cache[guild.id] = channel_ids
                notifications.append({"message": "Ajustes guardados.", "category": "success"})
        conf = await self.config.guild(guild).all()
        channels = [{"id": c.id, "name": f"#{c.name}", "selected": c.id in conf["channel"]}
                    for c in sorted(guild.text_channels, key=lambda c: c.position)]
        users = await self.config.all_users()
        board = []
        for uid, data in sorted(users.items(), key=lambda kv: -kv[1].get("candies", 0)):
            member = guild.get_member(uid)
            if member is None or not data.get("candies"):
                continue
            board.append({"pos": len(board) + 1, "name": member.display_name, "candies": data.get("candies", 0),
                          "eaten": data.get("eaten", 0), "stolen": data.get("stolen", 0), "streak": data.get("best_streak", 0)})
            if len(board) >= 25:
                break
        source = """
<div class="trini-tp-settings">
  <h3 class="trini-tp-title"><i class="fa fa-magic"></i> Truco o trato</h3>
  <p class="trini-tp-subtitle">
    Juego: <strong>{{ "activo" if conf.toggle else "desactivado" }}</strong>
    {% if conf.event_active %} · Evento <strong>{{ conf.event_type }}</strong>: {{ conf.event_progress }}/{{ conf.event_goal }}{% endif %}
  </p>
  {% if can_edit %}
  <div class="trini-tp-guild-section">
    <div class="trini-tp-guild-header"><h4><i class="fa fa-cog me-1"></i> Ajustes</h4></div>
    <form method="POST" class="mt-3">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
      <div class="row align-items-end">
        <div class="col-lg-2 col-md-4 mb-3"><div class="form-check form-switch">
          <input class="form-check-input" type="checkbox" name="toggle" id="tot-toggle" {{ "checked" if conf.toggle }}>
          <label class="form-check-label" for="tot-toggle">Juego activo</label></div></div>
        <div class="col-lg-4 col-md-8 mb-3"><label class="form-label text-xs mb-1">Canales (Ctrl+clic para varios)</label>
          <select class="form-select form-select-sm" name="channels" multiple size="5">
            {% for c in channels %}<option value="{{ c.id }}" {{ "selected" if c.selected }}>{{ c.name }}</option>{% endfor %}</select></div>
        {% for key, label in [("cooldown", "Cooldown truco o trato (s)"), ("pickup_cooldown", "Cooldown recoger (s)"), ("steal_cooldown", "Cooldown robar (s)"), ("shield_hours", "Escudo (horas)")] %}
        <div class="col-lg-2 col-md-4 mb-3"><label class="form-label text-xs mb-1">{{ label }}</label>
          <input type="number" class="form-control form-control-sm" name="{{ key }}" value="{{ conf[key] }}" min="0"></div>
        {% endfor %}
        <div class="col-lg-2 col-md-4 mb-3"><button type="submit" class="btn btn-xs bg-gradient-info mb-0 w-100"><i class="fa fa-save me-1"></i> Guardar</button></div>
      </div>
    </form>
  </div>
  {% endif %}
  <div class="trini-tp-guild-section">
    <div class="trini-tp-guild-header"><h4><i class="fa fa-trophy me-1"></i> Clasificacion</h4></div>
    {% if board|length > 0 %}
    <div class="table-responsive"><table class="table trini-table trini-tp-table">
      <thead><tr><th>#</th><th>Usuario</th><th>Caramelos</th><th>Comidos</th><th>Robados</th><th>Mejor racha</th></tr></thead>
      <tbody>{% for r in board %}<tr><td>{{ r.pos }}</td><td>{{ r.name }}</td><td><strong>{{ r.candies }}</strong></td><td>{{ r.eaten }}</td><td>{{ r.stolen }}</td><td>{{ r.streak }}</td></tr>{% endfor %}</tbody>
    </table></div>
    {% else %}<p class="text-sm opacity-6">Nadie tiene caramelos todavia.</p>{% endif %}
  </div>
</div>
"""
        result = {"status": 0, "web_content": {"source": source, "conf": conf, "channels": channels, "board": board, "can_edit": can_edit}}
        if notifications:
            result["notifications"] = notifications
        return result
