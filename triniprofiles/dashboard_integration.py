"""
Dashboard integration for TriniProfiles.
Pagina de modulos: estado real y activar/desactivar.

El Dashboard (AAA3A) solo comprueba que el usuario este en el servidor:
cada pagina exige sus propios permisos con ``_dashboard_denied``.
"""
import typing

from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator

_ = Translator("TriniProfiles", __file__)


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
        name="modules",
        description="Modulos de La Trini: estado real y activar/desactivar",
        methods=("GET", "POST"),
    )
    async def rpc_modules_page(self, guild_id: int, **kwargs) -> typing.Dict[str, typing.Any]:
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return _error("Servidor no encontrado.")
        denied = await self._dashboard_denied(guild, kwargs)
        if denied:
            return denied
        from .profiles import STATE_ICON, STATE_LEGEND  # import diferido (evita import circular)
        from .registry import MODULES, PROFILES

        notifications = []
        if kwargs.get("method") == "POST":
            key = _form_value(kwargs, "module")
            enabled = _form_value(kwargs, "enabled") == "1"
            ok, text = await self.set_module(guild, key, enabled, actor=kwargs.get("user"))
            # El mensaje viene en markdown de Discord: se deja en texto plano.
            plain = text.replace("**", "").replace("`", "")
            notifications.append({"message": plain, "category": "success" if ok else "danger"})

        data = await self.config.guild(guild).all()
        states = await self.effective_states(guild, data["modules"])
        categories: typing.Dict[str, typing.List[typing.Dict[str, typing.Any]]] = {}
        for info in sorted(MODULES.values(), key=lambda m: (m.category, m.name)):
            state = states.get(info.key, "missing")
            categories.setdefault(_(info.category), []).append({
                "key": info.key,
                "name": _(info.name),
                "emoji": info.emoji,
                "description": _(info.description),
                "icon": STATE_ICON.get(state, "⚫"),
                "wanted": info.core or bool(data["modules"].get(info.key)),
                "core": info.core,
                "loaded": state in ("on", "off"),
                "hint": (info.install_hint() or "") if state in ("missing", "missing_on") else "",
            })
        profile = PROFILES.get(data["profile"]) if data["profile"] else None
        history = [
            {"ts": h.get("ts", 0), "action": h.get("action", ""), "detail": h.get("detail", ""),
             "actor": str(guild.get_member(h["actor"]) or h["actor"]) if h.get("actor") else "sistema"}
            for h in reversed(data["history"][-15:])
        ]
        on_count = sum(1 for s in states.values() if s == "on")

        source = """
<div class="trini-tp-settings">
  <h3 class="trini-tp-title"><i class="fa fa-sliders"></i> La Trini · Modulos</h3>
  <p class="trini-tp-subtitle">
    Perfil: <strong>{{ profile or "ninguno" }}</strong> · Seguridad: <code>{{ security_level }}</code> ·
    {{ on_count }} modulos funcionando · Sincronizacion con Red: {{ "si" if sync_red else "no" }}
  </p>
  <p class="text-sm opacity-7">{{ legend }}</p>

  {% for category, modules in categories.items() %}
  <div class="trini-tp-guild-section">
    <div class="trini-tp-guild-header"><h4>{{ category }}</h4><span class="badge bg-gradient-info">{{ modules|length }}</span></div>
    <div class="table-responsive">
      <table class="table trini-table trini-tp-table">
        <thead><tr><th></th><th>Modulo</th><th>Descripcion</th><th></th></tr></thead>
        <tbody>
          {% for m in modules %}
          <tr>
            <td>{{ m.icon }}</td>
            <td>{{ m.emoji }} <strong>{{ m.name }}</strong><br><small><code>{{ m.key }}</code></small></td>
            <td><small>{{ m.description }}</small>{% if m.hint %}<br><small class="text-warning">{{ m.hint }}</small>{% endif %}</td>
            <td>
              {% if m.core %}
                <span class="badge bg-gradient-secondary">base</span>
              {% else %}
              <form method="POST" style="display:inline">
                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                <input type="hidden" name="module" value="{{ m.key }}">
                {% if m.wanted %}
                <input type="hidden" name="enabled" value="0">
                <button type="submit" class="btn btn-xs bg-gradient-danger mb-0">Desactivar</button>
                {% else %}
                <input type="hidden" name="enabled" value="1">
                <button type="submit" class="btn btn-xs bg-gradient-success mb-0">Activar</button>
                {% endif %}
              </form>
              {% endif %}
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
  {% endfor %}

  <div class="trini-tp-guild-section">
    <div class="trini-tp-guild-header"><h4><i class="fa fa-history me-1"></i> Ultimos cambios</h4></div>
    {% if history|length > 0 %}
    <ul class="text-sm">
      {% for h in history %}<li><code>{{ h.action }}</code> {{ h.detail }} · {{ h.actor }}</li>{% endfor %}
    </ul>
    {% else %}<p class="text-sm opacity-6">Sin cambios registrados.</p>{% endif %}
  </div>
</div>
"""
        result = {
            "status": 0,
            "web_content": {
                "source": source,
                "categories": categories,
                "profile": _(profile.name) if profile else (data["profile"] or ""),
                "security_level": data["security_level"],
                "sync_red": data["sync_red"],
                "on_count": on_count,
                "legend": _(STATE_LEGEND),
                "history": history,
            },
        }
        if notifications:
            result["notifications"] = notifications
        return result
