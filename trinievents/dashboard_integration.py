"""
Dashboard integration for TriniEvents.
Pagina de eventos (solo lectura).

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
        name="events",
        description="Eventos programados, en curso y recientes",
        methods=("GET",),
    )
    async def rpc_events_page(self, guild_id: int, **kwargs) -> typing.Dict[str, typing.Any]:
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return _error("Servidor no encontrado.")
        denied = await self._dashboard_denied(guild, kwargs, mod=True)
        if denied:
            return denied
        import datetime

        from .events import STATUS_LABEL
        from .timeparse import get_tz

        tz = get_tz(await self.config.guild(guild).timezone())

        def name_of(user_id) -> str:
            member = guild.get_member(int(user_id))
            return member.display_name if member else str(user_id)

        rows = []
        for ev in (await self.config.guild(guild).events()).values():
            start = datetime.datetime.fromtimestamp(ev.get("start", 0), tz)
            slots = ev.get("slots") or 0
            channel = guild.get_channel(ev.get("channel_id")) if ev.get("channel_id") else None
            rows.append({
                "id": ev["id"],
                "title": ev.get("title", "Evento"),
                "emoji": ev.get("emoji") or "",
                "kind": "ArenCup" if ev.get("arencup") else ev.get("kind", "normal"),
                "start": start.strftime("%d/%m/%Y %H:%M"),
                "start_ts": ev.get("start", 0),
                "status": ev.get("status", "scheduled"),
                "status_label": STATUS_LABEL.get(ev.get("status"), ev.get("status", "")),
                "places": f"{len(ev.get('participants', []))}/{slots}" if slots else str(len(ev.get("participants", []))),
                "waitlist": len(ev.get("waitlist", [])),
                "channel": f"#{channel.name}" if channel else "",
                "participants": ", ".join(name_of(u) for u in ev.get("participants", [])[:30]),
            })
        active = sorted((r for r in rows if r["status"] in ("scheduled", "ongoing")), key=lambda r: r["start_ts"])
        past = sorted((r for r in rows if r["status"] not in ("scheduled", "ongoing")), key=lambda r: -r["start_ts"])[:15]
        settings = await self.config.guild(guild).all()
        default_channel = guild.get_channel(settings["channel"]) if settings["channel"] else None

        source = """
<div class="trini-tp-settings">
  <h3 class="trini-tp-title"><i class="fa fa-calendar"></i> Trini Events</h3>
  <p class="trini-tp-subtitle">
    Zona horaria: <code>{{ timezone }}</code> · Canal por defecto: {{ channel or "ninguno" }} ·
    Recordatorios: {{ reminders }} min antes. Crear y editar eventos: <code>event create</code> en Discord.
  </p>

  {% for section, items, empty in [("Proximos y en curso", active, "No hay eventos programados."), ("Recientes", past, "Sin eventos pasados.")] %}
  <div class="trini-tp-guild-section">
    <div class="trini-tp-guild-header"><h4>{{ section }}</h4><span class="badge bg-gradient-info">{{ items|length }}</span></div>
    {% if items|length > 0 %}
    <div class="table-responsive"><table class="table trini-table trini-tp-table">
      <thead><tr><th>#</th><th>Evento</th><th>Inicio</th><th>Estado</th><th>Plazas</th><th>Espera</th><th>Canal</th></tr></thead>
      <tbody>{% for e in items %}
        <tr>
          <td>{{ e.id }}</td>
          <td>{{ e.emoji }} <strong>{{ e.title }}</strong><br><small class="opacity-7">{{ e.kind }}</small>
            {% if e.participants %}<br><small>{{ e.participants }}</small>{% endif %}</td>
          <td><small>{{ e.start }}</small></td><td>{{ e.status_label }}</td><td>{{ e.places }}</td><td>{{ e.waitlist }}</td><td>{{ e.channel }}</td>
        </tr>
      {% endfor %}</tbody></table></div>
    {% else %}<p class="text-sm opacity-6">{{ empty }}</p>{% endif %}
  </div>
  {% endfor %}
</div>
"""
        return {
            "status": 0,
            "web_content": {
                "source": source,
                "active": active,
                "past": past,
                "timezone": settings["timezone"],
                "channel": f"#{default_channel.name}" if default_channel else "",
                "reminders": ", ".join(str(m) for m in settings["reminders"]),
            },
        }
