"""
Dashboard integration for PruneBans.
Provides per-guild web interface for monitoring bans and prune status.
"""
import typing
import datetime
from redbot.core import commands
from redbot.core.bot import Red


def dashboard_page(*args, **kwargs):
    def decorator(func: typing.Callable):
        func.__dashboard_decorator_params__ = (args, kwargs)
        return func
    return decorator


class DashboardIntegration:
    bot: Red
    config: typing.Any

    async def _dashboard_denied(self, guild, kwargs, *, mod: bool = False):
        """El Dashboard solo comprueba que el usuario este en el servidor:
        cada pagina debe exigir sus propios permisos. Devuelve la respuesta
        de error o ``None`` si puede pasar."""
        user = kwargs.get("user")
        user_id = getattr(user, "id", kwargs.get("user_id"))
        if user_id is not None and user_id in self.bot.owner_ids:
            return None
        member = guild.get_member(user_id) if (guild is not None and user_id is not None) else None
        allowed = False
        if member is not None:
            perms = member.guild_permissions
            if perms.administrator or perms.manage_guild or await self.bot.is_admin(member):
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

    @commands.Cog.listener()
    async def on_dashboard_cog_add(self, dashboard_cog: commands.Cog) -> None:
        dashboard_cog.rpc.third_parties_handler.add_third_party(self)

    async def cog_load(self) -> None:
        dashboard_cog = self.bot.get_cog("Dashboard")
        if dashboard_cog and hasattr(dashboard_cog, "rpc"):
            try:
                dashboard_cog.rpc.third_parties_handler.add_third_party(self)
            except Exception:
                pass

    @dashboard_page(
        name="bans",
        description="Limpieza automatica de creditos de baneados",
        methods=("GET", "POST"),
    )
    async def rpc_bans_page(self, guild_id: int, **kwargs) -> typing.Dict[str, typing.Any]:
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {"status": 0, "web_content": {"source": '<div class="trini-tp-empty"><i class="fa fa-exclamation-triangle fa-3x"></i><p>Servidor no encontrado.</p></div>'}}
        denied = await self._dashboard_denied(guild, kwargs, mod=True)
        if denied:
            return denied

        notifications = []
        can_edit = await self._dashboard_denied(guild, kwargs) is None
        if kwargs.get("method") == "POST":
            if not can_edit:
                notifications.append({"message": "Solo los administradores pueden cambiar la configuracion.", "category": "danger"})
            else:
                form = kwargs.get("data", {}).get("form", {})

                def _fv(key, default=""):
                    value = form.get(key, [default])
                    return value[0] if isinstance(value, list) else str(value)

                try:
                    group = self.config.guild(guild)
                    await group.enabled.set(_fv("enabled") == "on")
                    days = max(0, min(365, int(_fv("delay_days", "7") or 7)))
                    await group.delay_days.set(days)
                    channel_id = _fv("log_channel")
                    channel = guild.get_channel(int(channel_id)) if channel_id.isdigit() else None
                    await group.log_channel.set(channel.id if channel else None)
                    notifications.append({"message": "Configuracion guardada.", "category": "success"})
                except (ValueError, TypeError) as e:
                    notifications.append({"message": f"Error: {e}", "category": "danger"})

        data = await self.config.guild(guild).all()
        now = datetime.datetime.now(datetime.timezone.utc)
        bans_list = []
        for uid_str, binfo in data.get("ban_track", {}).items():
            if not isinstance(binfo, dict):
                continue
            user = self.bot.get_user(int(uid_str)) if uid_str.isdigit() else None
            remaining_text, status_class = "?", "info"
            try:
                due = datetime.datetime.fromisoformat(str(binfo.get("unban_date", "")))
                if due.tzinfo is None:
                    due = due.replace(tzinfo=datetime.timezone.utc)
                remaining = due - now
                if remaining.total_seconds() <= 0:
                    remaining_text, status_class = "En la proxima revision", "danger"
                else:
                    remaining_text = f"{remaining.days}d {remaining.seconds // 3600}h"
                    status_class = "warning" if remaining.days < 1 else "info"
            except (ValueError, TypeError):
                pass
            bans_list.append({
                "user_name": str(user) if user else f"ID: {uid_str}",
                "ban_date": str(binfo.get("ban_date", ""))[:10],
                "prune_date": str(binfo.get("unban_date", ""))[:10],
                "balance": str(binfo.get("balance", "?")),
                "remaining": remaining_text,
                "status_class": status_class,
            })
        bans_list.sort(key=lambda b: b["prune_date"])
        channels = [
            {"id": ch.id, "name": f"#{ch.name}", "selected": ch.id == data.get("log_channel")}
            for ch in sorted(guild.text_channels, key=lambda c: c.position)
        ]

        source = """
<div class="trini-tp-settings">
  <h3 class="trini-tp-title"><i class="fa fa-gavel"></i> AutoPrune</h3>
  <p class="trini-tp-subtitle">Borra los creditos de quien siga baneado pasados unos dias. Los baneos los registra el modlog.</p>

  <div class="trini-tp-guild-section">
    <div class="trini-tp-guild-header">
      <h4><i class="fa fa-cog me-1"></i> Configuracion</h4>
      {% if enabled %}<span class="badge bg-gradient-success">Activado</span>{% else %}<span class="badge bg-gradient-secondary">Desactivado</span>{% endif %}
    </div>
    {% if can_edit %}
    <form method="POST" class="mt-3">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
      <div class="row align-items-end">
        <div class="col-lg-2 col-md-3 mb-3">
          <div class="form-check form-switch">
            <input class="form-check-input" type="checkbox" name="enabled" id="ap-enabled" {{ "checked" if enabled }}>
            <label class="form-check-label" for="ap-enabled">Activado</label>
          </div>
        </div>
        <div class="col-lg-2 col-md-3 mb-3">
          <label class="form-label text-xs mb-1">Dias de espera</label>
          <input type="number" class="form-control form-control-sm" name="delay_days" value="{{ delay_days }}" min="0" max="365">
        </div>
        <div class="col-lg-4 col-md-6 mb-3">
          <label class="form-label text-xs mb-1">Canal de logs</label>
          <select class="form-select form-select-sm" name="log_channel">
            <option value="">-- Ninguno --</option>
            {% for ch in channels %}<option value="{{ ch.id }}" {{ "selected" if ch.selected }}>{{ ch.name }}</option>{% endfor %}
          </select>
        </div>
        <div class="col-lg-2 col-12 mb-3">
          <button type="submit" class="btn btn-xs bg-gradient-info mb-0 w-100"><i class="fa fa-save me-1"></i> Guardar</button>
        </div>
      </div>
    </form>
    {% else %}
    <p class="text-sm opacity-6 mt-2">Espera: {{ delay_days }} dias. Solo los administradores pueden cambiar la configuracion.</p>
    {% endif %}
  </div>

  <div class="trini-tp-guild-section">
    <div class="trini-tp-guild-header">
      <h4><i class="fa fa-clock-o me-1"></i> En seguimiento</h4>
      <span class="badge bg-gradient-info">{{ bans|length }}</span>
    </div>
    {% if bans|length > 0 %}
    <div class="table-responsive">
      <table class="table trini-table trini-tp-table">
        <thead><tr><th>Usuario</th><th>Baneado</th><th>Limpieza</th><th>Creditos</th><th>Falta</th></tr></thead>
        <tbody>
          {% for ban in bans %}
          <tr>
            <td>{{ ban.user_name }}</td>
            <td><small>{{ ban.ban_date }}</small></td>
            <td><small>{{ ban.prune_date }}</small></td>
            <td><strong>{{ ban.balance }}</strong></td>
            <td><span class="badge bg-gradient-{{ ban.status_class }}">{{ ban.remaining }}</span></td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% else %}
    <div class="trini-tp-empty"><i class="fa fa-gavel fa-3x"></i><p>No hay baneos en seguimiento.</p></div>
    {% endif %}
  </div>
</div>
"""
        result = {
            "status": 0,
            "web_content": {
                "source": source,
                "bans": bans_list,
                "enabled": data.get("enabled", False),
                "delay_days": data.get("delay_days", 7),
                "channels": channels,
                "can_edit": can_edit,
            },
        }
        if notifications:
            result["notifications"] = notifications
        return result
