"""
Dashboard integration for EquiposRoles.
Read-only page with the registered teams and the latest requests.
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
        name="equipos_roles",
        description="Solicitudes de rol de equipo y equipos registrados",
        methods=("GET",),
    )
    async def rpc_equipos_page(self, guild_id: int, **kwargs) -> typing.Dict[str, typing.Any]:
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
        requests = await self.config.guild(guild).requests()

        team_rows = []
        for team in sorted(teams.values(), key=lambda item: str(item.get("name", "")).casefold()):
            role = guild.get_role(int(team.get("role_id", 0)))
            channel = guild.get_channel(int(team.get("channel_id", 0)))
            pending = sum(
                1
                for request in requests.values()
                if request.get("team_id") == team.get("id") and request.get("status") == "pending"
            )
            team_rows.append({
                "id": team.get("id"),
                "name": team.get("name", ""),
                "role": role.name if role is not None else "—",
                "channel": f"#{channel.name}" if channel is not None else "—",
                "pending": pending,
            })

        request_rows = []
        ordered = sorted(
            requests.values(),
            key=lambda item: int(item.get("created_at", 0)),
            reverse=True,
        )
        for request in ordered[:50]:
            team = teams.get(str(request.get("team_id")))
            request_rows.append({
                "id": request.get("id"),
                "player": name_of(request.get("user_id", 0)),
                "team": team.get("name", "—") if team else "—",
                "status": request.get("status", "pending"),
                "created": f"<t:{int(request.get('created_at', 0))}:R>",
                "resolved_by": name_of(request.get("resolved_by")) if request.get("resolved_by") else "—",
            })

        source = """
<div class="trini-tp-settings">
  <h3 class="trini-tp-title"><i class="fa fa-ticket"></i> EquiposRoles · Solicitudes</h3>
  <p class="trini-tp-subtitle">
    {{ teams|length }} equipos registrados. Alta de equipos: <code>teamroles add</code> en Discord.
  </p>
  {% if teams|length > 0 %}
  <div class="table-responsive"><table class="table trini-table trini-tp-table">
    <thead><tr><th>#</th><th>Equipo</th><th>Rol</th><th>Canal</th><th>Pendientes</th></tr></thead>
    <tbody>{% for t in teams %}
      <tr>
        <td>{{ t.id }}</td>
        <td><strong>{{ t.name }}</strong></td>
        <td>{{ t.role }}</td>
        <td>{{ t.channel }}</td>
        <td>{{ t.pending }}</td>
      </tr>
    {% endfor %}</tbody></table></div>
  {% else %}<p class="text-sm opacity-6">Todavía no hay equipos.</p>{% endif %}

  <h3 class="trini-tp-title" style="margin-top:1.5rem"><i class="fa fa-list"></i> Ultimas solicitudes</h3>
  {% if requests|length > 0 %}
  <div class="table-responsive"><table class="table trini-table trini-tp-table">
    <thead><tr><th>#</th><th>Jugador</th><th>Equipo</th><th>Estado</th><th>Creada</th><th>Resuelta por</th></tr></thead>
    <tbody>{% for r in requests %}
      <tr>
        <td>{{ r.id }}</td>
        <td>{{ r.player }}</td>
        <td>{{ r.team }}</td>
        <td>{{ r.status }}</td>
        <td>{{ r.created }}</td>
        <td>{{ r.resolved_by }}</td>
      </tr>
    {% endfor %}</tbody></table></div>
  {% else %}<p class="text-sm opacity-6">Todavía no hay solicitudes.</p>{% endif %}
</div>
"""
        return {"status": 0, "web_content": {"source": source, "teams": team_rows, "requests": request_rows}}
