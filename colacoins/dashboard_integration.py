"""
Dashboard integration for ColaCoins.
Clasificacion y dar/quitar ColaCoins (admins).

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
        name="colacoins",
        description="Clasificacion de ColaCoins y ajustes de saldo",
        methods=("GET", "POST"),
    )
    async def rpc_colacoins_page(self, guild_id: int, **kwargs) -> typing.Dict[str, typing.Any]:
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return _error("Servidor no encontrado.")
        # Los saldos son globales (compartidos entre servidores), como los comandos: solo admins.
        denied = await self._dashboard_denied(guild, kwargs)
        if denied:
            return denied
        notifications = []
        if kwargs.get("method") == "POST":
            raw_user = _form_value(kwargs, "user_id")
            action = _form_value(kwargs, "action")
            try:
                amount = int(_form_value(kwargs, "amount", "0"))
            except ValueError:
                amount = 0
            member = guild.get_member(int(raw_user)) if raw_user.isdigit() else None
            if member is None:
                notifications.append({"message": "Ese usuario no esta en este servidor.", "category": "danger"})
            elif amount <= 0:
                notifications.append({"message": "La cantidad debe ser positiva.", "category": "danger"})
            else:
                async with self.config.colacoins() as colacoins:
                    current = colacoins.get(str(member.id), 0)
                    if action == "remove" and current < amount:
                        notifications.append({"message": f"{member} solo tiene {current}.", "category": "danger"})
                    else:
                        colacoins[str(member.id)] = current + (amount if action == "give" else -amount)
                        notifications.append({"message": f"{member}: {colacoins[str(member.id)]} ColaCoins.", "category": "success"})
                await self.save_data()
                user = kwargs.get("user")
                self.logger.info(f"Dashboard: {user} {action} {amount} ColaCoins a {member}.")
        colacoins = await self.config.colacoins()
        emoji = await self.config.emoji() or ""
        rows = []
        for uid, amount in sorted(colacoins.items(), key=lambda kv: -kv[1]):
            member = guild.get_member(int(uid)) if str(uid).isdigit() else None
            if member is None or amount <= 0:
                continue
            rows.append({"pos": len(rows) + 1, "name": member.display_name, "id": member.id, "amount": amount})
            if len(rows) >= 100:
                break
        source = """
<div class="trini-tp-settings">
  <h3 class="trini-tp-title"><i class="fa fa-trophy"></i> ColaCoins {{ emoji }}</h3>
  <p class="trini-tp-subtitle">Los saldos son globales: son los mismos en todos los servidores del bot.</p>
  <div class="trini-tp-guild-section">
    <div class="trini-tp-guild-header"><h4>Dar o quitar</h4></div>
    <form method="POST" class="mt-3">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
      <div class="row align-items-end">
        <div class="col-lg-4 col-md-6 mb-3"><label class="form-label text-xs mb-1">ID del usuario</label>
          <input type="text" class="form-control form-control-sm" name="user_id" pattern="[0-9]+" required></div>
        <div class="col-lg-2 col-md-3 mb-3"><label class="form-label text-xs mb-1">Cantidad</label>
          <input type="number" class="form-control form-control-sm" name="amount" min="1" required></div>
        <div class="col-lg-2 col-md-3 mb-3"><label class="form-label text-xs mb-1">Accion</label>
          <select class="form-select form-select-sm" name="action"><option value="give">Dar</option><option value="remove">Quitar</option></select></div>
        <div class="col-lg-2 col-md-4 mb-3"><button type="submit" class="btn btn-xs bg-gradient-info mb-0 w-100">Aplicar</button></div>
      </div>
    </form>
  </div>
  <div class="trini-tp-guild-section">
    <div class="trini-tp-guild-header"><h4>Clasificacion de este servidor</h4><span class="badge bg-gradient-info">{{ rows|length }}</span></div>
    {% if rows|length > 0 %}
    <div class="table-responsive"><table class="table trini-table trini-tp-table">
      <thead><tr><th>#</th><th>Usuario</th><th>ID</th><th>ColaCoins</th></tr></thead>
      <tbody>{% for r in rows %}<tr><td>{{ r.pos }}</td><td>{{ r.name }}</td><td><small><code>{{ r.id }}</code></small></td><td><strong>{{ r.amount }}</strong></td></tr>{% endfor %}</tbody>
    </table></div>
    {% else %}<p class="text-sm opacity-6">Nadie tiene ColaCoins en este servidor.</p>{% endif %}
  </div>
</div>
"""
        result = {"status": 0, "web_content": {"source": source, "rows": rows, "emoji": emoji}}
        if notifications:
            result["notifications"] = notifications
        return result
