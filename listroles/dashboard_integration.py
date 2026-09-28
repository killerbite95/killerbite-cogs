"""
Dashboard integration for ListRoles.
Roles con ID y miembros (mods).

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
        name="roles",
        description="Roles del servidor con su ID y numero de miembros",
        methods=("GET",),
    )
    async def rpc_roles_page(self, guild_id: int, **kwargs) -> typing.Dict[str, typing.Any]:
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return _error("Servidor no encontrado.")
        denied = await self._dashboard_denied(guild, kwargs, mod=True)
        if denied:
            return denied
        rows = [
            {"name": role.name, "id": role.id, "members": len(role.members), "color": f"#{role.color.value:06x}",
             "managed": role.managed, "admin": role.permissions.administrator}
            for role in reversed(guild.roles)
        ]
        source = """
<div class="trini-tp-settings">
  <h3 class="trini-tp-title"><i class="fa fa-tags"></i> Roles</h3>
  <p class="trini-tp-subtitle">{{ rows|length }} roles, de mayor a menor en la jerarquia.</p>
  <div class="table-responsive"><table class="table trini-table trini-tp-table">
    <thead><tr><th>Rol</th><th>ID</th><th>Miembros</th><th></th></tr></thead>
    <tbody>{% for r in rows %}<tr>
      <td><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{{ r.color }}"></span> {{ r.name }}</td>
      <td><code>{{ r.id }}</code></td><td>{{ r.members }}</td>
      <td>{% if r.admin %}<span class="badge bg-gradient-danger">admin</span>{% endif %}{% if r.managed %}<span class="badge bg-gradient-secondary">integracion</span>{% endif %}</td>
    </tr>{% endfor %}</tbody>
  </table></div>
</div>
"""
        return {"status": 0, "web_content": {"source": source, "rows": rows}}
