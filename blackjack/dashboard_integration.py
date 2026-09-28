"""
Dashboard integration for Blackjack.
Emojis de la baraja (solo owner, global).

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
        description="Blackjack: emojis de las cartas (global)",
        methods=("GET", "POST"),
        is_owner=True,
    )
    async def rpc_cards_page(self, **kwargs) -> typing.Dict[str, typing.Any]:
        user = kwargs.get("user")
        if user is None or user.id not in self.bot.owner_ids:
            return {"status": 1, "message": "Forbidden access.", "error_code": 403,
                    "error_message": "Solo el owner del bot puede cambiar la baraja."}
        notifications = []
        if kwargs.get("method") == "POST":
            ranks = dict(self.card_config["ranks"])
            suits = dict(self.card_config["suits"])
            for key in ranks:
                value = _form_value(kwargs, f"rank_{key}")
                if value:
                    ranks[key] = value[:64]
            for index, key in enumerate(list(suits)):
                value = _form_value(kwargs, f"suit_{index}")
                if value:
                    suits[key] = value[:64]
            self.card_config["ranks"], self.card_config["suits"] = ranks, suits
            await self.config.ranks.set(ranks)
            await self.config.suits.set(suits)
            notifications.append({"message": "Baraja guardada.", "category": "success"})
        ranks = [{"key": k, "value": v} for k, v in self.card_config["ranks"].items()]
        suits = [{"index": i, "key": k, "value": v} for i, (k, v) in enumerate(self.card_config["suits"].items())]
        source = """
<div class="trini-tp-settings">
  <h3 class="trini-tp-title"><i class="fa fa-diamond"></i> Blackjack · Baraja</h3>
  <p class="trini-tp-subtitle">Texto o emoji (por ejemplo <code>&lt;:as:123&gt;</code>) que se muestra para cada carta. Es global.</p>
  <form method="POST" class="mt-3">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <div class="row">
      {% for r in ranks %}<div class="col-lg-1 col-md-2 col-3 mb-3"><label class="form-label text-xs mb-1">{{ r.key }}</label>
        <input type="text" class="form-control form-control-sm" name="rank_{{ r.key }}" value="{{ r.value }}" maxlength="64"></div>{% endfor %}
    </div>
    <div class="row">
      {% for s in suits %}<div class="col-lg-2 col-md-3 col-6 mb-3"><label class="form-label text-xs mb-1">{{ s.key }}</label>
        <input type="text" class="form-control form-control-sm" name="suit_{{ s.index }}" value="{{ s.value }}" maxlength="64"></div>{% endfor %}
    </div>
    <button type="submit" class="btn btn-xs bg-gradient-info mb-0"><i class="fa fa-save me-1"></i> Guardar</button>
  </form>
</div>
"""
        result = {"status": 0, "web_content": {"source": source, "ranks": ranks, "suits": suits}}
        if notifications:
            result["notifications"] = notifications
        return result
