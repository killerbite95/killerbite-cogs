"""
Dashboard integration for AlienHost.
Pagina personal "Mis servidores" (con la cuenta vinculada por modal) y ajustes del servidor.

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
        name="servers",
        description="Mis servidores de AlienHost: estado y encendido",
        methods=("GET", "POST"),
    )
    async def rpc_my_servers(self, user_id: int, **kwargs) -> typing.Dict[str, typing.Any]:
        """Pagina personal: usa la cuenta que el usuario vinculo en Discord (por modal).

        La clave nunca se pide ni se muestra aqui."""
        user = kwargs.get("user") or self.bot.get_user(user_id)
        if user is None:
            return _error("Usuario no encontrado.")
        from .api import PelicanError

        notifications = []
        linked = bool((await self.config.user(user).api_key()))
        if kwargs.get("method") == "POST" and linked:
            signal = _form_value(kwargs, "signal")
            uuid = _form_value(kwargs, "uuid")
            try:
                own = {s["uuid"]: s for s in await self._servers(user)}
            except PelicanError as exc:
                own = {}
                notifications.append({"message": exc.friendly, "category": "danger"})
            # Solo servidores de su propia cuenta y senales conocidas.
            if uuid in own and signal in ("start", "restart", "stop"):
                server = own[uuid]
                text = await self.do_power(user, None, uuid, server.get("name", server.get("identifier", uuid)), signal)
                ok = text.startswith("✅")
                notifications.append({"message": text.replace("**", ""), "category": "success" if ok else "warning"})

        rows, error = [], ""
        if linked:
            try:
                servers = await self._servers(user, fresh=kwargs.get("method") == "POST")
                states = await self.fetch_states(user, [s["uuid"] for s in servers[:50]])
                state_label = {"running": ("Online", "success"), "starting": ("Arrancando", "info"),
                               "stopping": ("Parando", "warning"), "offline": ("Offline", "secondary")}
                for s in servers[:50]:
                    label, css = state_label.get(states.get(s["uuid"]) or "", ("Desconocido", "secondary"))
                    limits = s.get("limits") or {}
                    rows.append({
                        "uuid": s["uuid"],
                        "name": s.get("name", s.get("identifier", "")),
                        "identifier": s.get("identifier", ""),
                        "node": s.get("node", ""),
                        "memory": f"{(limits.get('memory') or 0) / 1024:.1f} GB" if limits.get("memory") else "∞",
                        "state": label,
                        "css": css,
                        "running": states.get(s["uuid"]) == "running",
                    })
            except PelicanError as exc:
                error = exc.friendly
        account = await self.config.user(user).account()

        source = """
<div class="trini-tp-settings">
  <h3 class="trini-tp-title"><i class="fa fa-server"></i> Mis servidores · AlienHost</h3>
  {% if not linked %}
  <div class="trini-tp-empty"><i class="fa fa-link fa-3x"></i>
    <p>No tienes cuenta vinculada. En Discord usa <code>{{ prefix }}alienhost link</code>: la clave se pide en un formulario privado y nunca se escribe en el chat ni aqui.</p></div>
  {% else %}
  <p class="trini-tp-subtitle">Cuenta: <strong>{{ account.get("username", "?") }}</strong> · Las acciones cuentan para el limite de acciones por hora.</p>
  {% if error %}<p class="text-danger">{{ error }}</p>{% endif %}
  {% if rows|length > 0 %}
  <div class="table-responsive"><table class="table trini-table trini-tp-table">
    <thead><tr><th>Servidor</th><th>Nodo</th><th>RAM</th><th>Estado</th><th>Acciones</th></tr></thead>
    <tbody>{% for s in rows %}
      <tr>
        <td><strong>{{ s.name }}</strong><br><small><code>{{ s.identifier }}</code></small></td>
        <td>{{ s.node }}</td><td>{{ s.memory }}</td>
        <td><span class="badge bg-gradient-{{ s.css }}">{{ s.state }}</span></td>
        <td>
          {% for signal, label, css, confirm in [("start", "Iniciar", "success", ""), ("restart", "Reiniciar", "warning", "¿Reiniciar este servidor?"), ("stop", "Detener", "danger", "¿Detener este servidor?")] %}
          {% if (signal == "start" and not s.running) or (signal != "start" and s.running) %}
          <form method="POST" style="display:inline">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <input type="hidden" name="uuid" value="{{ s.uuid }}">
            <input type="hidden" name="signal" value="{{ signal }}">
            <button type="submit" class="btn btn-xs bg-gradient-{{ css }} mb-0" {% if confirm %}onclick="return confirm('{{ confirm }}')"{% endif %}>{{ label }}</button>
          </form>
          {% endif %}
          {% endfor %}
        </td>
      </tr>
    {% endfor %}</tbody></table></div>
  {% elif not error %}<p class="text-sm opacity-6">Tu cuenta no tiene servidores.</p>{% endif %}
  {% endif %}
</div>
"""
        result = {"status": 0, "web_content": {
            "source": source, "linked": linked, "rows": rows, "error": error,
            "account": account or {}, "prefix": self.p,
        }}
        if notifications:
            result["notifications"] = notifications
        return result

    @dashboard_page(
        name="settings",
        description="Ajustes de AlienHost en este servidor",
        methods=("GET", "POST"),
    )
    async def rpc_guild_settings(self, guild_id: int, **kwargs) -> typing.Dict[str, typing.Any]:
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return _error("Servidor no encontrado.")
        denied = await self._dashboard_denied(guild, kwargs)
        if denied:
            return denied
        notifications = []
        if kwargs.get("method") == "POST":
            channel_id = _form_value(kwargs, "log_channel")
            role_id = _form_value(kwargs, "admin_role")
            channel = guild.get_channel(int(channel_id)) if channel_id.isdigit() else None
            role = guild.get_role(int(role_id)) if role_id.isdigit() else None
            group = self.config.guild(guild)
            await group.log_channel.set(channel.id if channel else None)
            await group.admin_role.set(role.id if role else None)
            await group.require_trusted.set(_form_value(kwargs, "require_trusted") == "on")
            self.bot.dispatch("trini_settings_change", guild, "AlienHost", kwargs.get("user"), "dashboard", f"log={channel} role={role}")
            notifications.append({"message": "Configuracion guardada.", "category": "success"})
        conf = await self.config.guild(guild).all()
        channels = [{"id": c.id, "name": f"#{c.name}", "selected": c.id == conf["log_channel"]}
                    for c in sorted(guild.text_channels, key=lambda c: c.position)]
        roles = [{"id": r.id, "name": r.name, "selected": r.id == conf["admin_role"]}
                 for r in reversed(guild.roles) if not r.is_default() and not r.managed]
        source = """
<div class="trini-tp-settings">
  <h3 class="trini-tp-title"><i class="fa fa-cog"></i> AlienHost · Ajustes del servidor</h3>
  <p class="trini-tp-subtitle">Las claves API solo se introducen en Discord, en un formulario privado (<code>alienhost link</code>).</p>
  <form method="POST" class="mt-3">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <div class="row align-items-end">
      <div class="col-lg-4 col-md-6 mb-3"><label class="form-label text-xs mb-1">Canal de auditoria</label>
        <select class="form-select form-select-sm" name="log_channel"><option value="">-- Ninguno --</option>
          {% for c in channels %}<option value="{{ c.id }}" {{ "selected" if c.selected }}>{{ c.name }}</option>{% endfor %}</select></div>
      <div class="col-lg-4 col-md-6 mb-3"><label class="form-label text-xs mb-1">Rol de administracion</label>
        <select class="form-select form-select-sm" name="admin_role"><option value="">-- Ninguno --</option>
          {% for r in roles %}<option value="{{ r.id }}" {{ "selected" if r.selected }}>{{ r.name }}</option>{% endfor %}</select></div>
      <div class="col-lg-2 col-md-6 mb-3"><div class="form-check form-switch">
        <input class="form-check-input" type="checkbox" name="require_trusted" id="ah-trusted" {{ "checked" if require_trusted }}>
        <label class="form-check-label" for="ah-trusted">Exigir Trusted Admin</label></div></div>
      <div class="col-lg-2 col-md-6 mb-3"><button type="submit" class="btn btn-xs bg-gradient-info mb-0 w-100"><i class="fa fa-save me-1"></i> Guardar</button></div>
    </div>
  </form>
</div>
"""
        result = {"status": 0, "web_content": {"source": source, "channels": channels, "roles": roles, "require_trusted": conf["require_trusted"]}}
        if notifications:
            result["notifications"] = notifications
        return result
