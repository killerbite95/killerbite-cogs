"""
Dashboard integration for ScrimsLoL.
Pagina de equipos (solo lectura).

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


def _error(message: str) -> typing.Dict[str, typing.Any]:
    return {"status": 0, "web_content": {"source": '<div class="trini-tp-empty"><i class="fa fa-exclamation-triangle fa-3x"></i><p>{{ message }}</p></div>', "message": message}}


class DashboardIntegration:
    bot: Red
    config: typing.Any

    async def _dashboard_denied(self, guild, kwargs, *, mod: bool = False, strict: bool = False):
        """Devuelve la respuesta 403 o ``None`` si el usuario puede pasar."""
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
        name="teams",
        description="Equipos de scrims, capitanes y roster",
        methods=("GET",),
    )
    async def rpc_teams_page(self, guild_id: int, **kwargs) -> typing.Dict[str, typing.Any]:
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return _error("Servidor no encontrado.")
        denied = await self._dashboard_denied(guild, kwargs, mod=True)
        if denied:
            return denied

        def name_of(user_id) -> str:
            member = guild.get_member(int(user_id))
            return member.display_name if member else str(user_id)

        teams = await self.config.guild(guild).teams()
        rows = []
        for team in sorted(teams.values(), key=lambda item: str(item.get("name", "")).casefold()):
            members = team.get("members", {})
            rows.append({
                "id": team.get("id"),
                "name": team.get("name", ""),
                "tag": team.get("tag") or "",
                "captain": name_of(team.get("captain_id", 0)),
                "count": len(members),
                "players": ", ".join(name_of(uid) for uid, role in members.items() if role == "player"),
                "subs": ", ".join(name_of(uid) for uid, role in members.items() if role == "sub"),
            })

        source = """
<div class="trini-tp-settings">
  <h3 class="trini-tp-title"><i class="fa fa-users"></i> Scrims LoL · Equipos</h3>
  <p class="trini-tp-subtitle">
    {{ teams|length }} equipos registrados. Crear y editar equipos: <code>team create</code> en Discord.
  </p>
  {% if teams|length > 0 %}
  <div class="table-responsive"><table class="table trini-table trini-tp-table">
    <thead><tr><th>#</th><th>Equipo</th><th>Capitan</th><th>Miembros</th><th>Titulares</th><th>Suplentes</th></tr></thead>
    <tbody>{% for t in teams %}
      <tr>
        <td>{{ t.id }}</td>
        <td><strong>{{ t.name }}</strong>{% if t.tag %} <small class="opacity-7">[{{ t.tag }}]</small>{% endif %}</td>
        <td>{{ t.captain }}</td>
        <td>{{ t.count }}</td>
        <td>{{ t.players or "—" }}</td>
        <td>{{ t.subs or "—" }}</td>
      </tr>
    {% endfor %}</tbody></table></div>
  {% else %}<p class="text-sm opacity-6">Todavia no hay equipos.</p>{% endif %}
</div>
"""
        return {"status": 0, "web_content": {"source": source, "teams": rows}}
