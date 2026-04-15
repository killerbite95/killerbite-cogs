"""
Dashboard integration for PruneBans.
Provides per-guild web interface for monitoring bans and prune status.
"""
import typing
import html as html_mod
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
        description="Seguimiento de baneos y prune",
        methods=("GET",),
    )
    async def rpc_bans_page(self, guild_id: int, **kwargs) -> typing.Dict[str, typing.Any]:
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {"status": 0, "web_content": {"source": '<div class="trini-tp-empty"><i class="fa fa-exclamation-triangle fa-3x"></i><p>Servidor no encontrado.</p></div>'}}

        try:
            data = await self.config.guild(guild).all()
        except Exception:
            return {"status": 0, "web_content": {"source": '<div class="trini-tp-empty"><i class="fa fa-exclamation-triangle fa-3x"></i><p>Error al cargar datos.</p></div>'}}

        ban_track = data.get("ban_track", {})
        log_ch_id = data.get("log_channel")
        ban_log_ch_id = data.get("ban_log_channel")
        now = datetime.datetime.utcnow()

        log_ch_name = ""
        if log_ch_id:
            ch = guild.get_channel(log_ch_id)
            log_ch_name = f"#{ch.name}" if ch else f"ID: {log_ch_id}"

        ban_log_ch_name = ""
        if ban_log_ch_id:
            ch = guild.get_channel(ban_log_ch_id)
            ban_log_ch_name = f"#{ch.name}" if ch else f"ID: {ban_log_ch_id}"

        bans_list = []
        ready_count = 0
        for uid_str, binfo in ban_track.items():
            if not isinstance(binfo, dict):
                continue
            try:
                user_id = int(uid_str)
                user = self.bot.get_user(user_id)
                user_name = html_mod.escape(str(user)) if user else f"ID: {user_id}"

                ban_date_str = str(binfo.get("ban_date", ""))
                unban_date_str = str(binfo.get("unban_date", ""))
                balance = binfo.get("balance", "Desconocido")

                remaining_text = "?"
                is_ready = False
                status_class = "warning"
                try:
                    unban_dt = datetime.datetime.fromisoformat(unban_date_str)
                    remaining = unban_dt - now
                    if remaining.total_seconds() <= 0:
                        remaining_text = "Listo para prune"
                        is_ready = True
                        status_class = "danger"
                        ready_count += 1
                    else:
                        days = remaining.days
                        hours = remaining.seconds // 3600
                        mins = (remaining.seconds % 3600) // 60
                        remaining_text = f"{days}d {hours}h {mins}m"
                        if days <= 1:
                            status_class = "warning"
                        else:
                            status_class = "info"
                except (ValueError, TypeError):
                    pass

                bans_list.append({
                    "user_id": user_id,
                    "user_name": user_name,
                    "ban_date": ban_date_str[:10],
                    "unban_date": unban_date_str[:10],
                    "balance": str(balance),
                    "remaining": remaining_text,
                    "is_ready": is_ready,
                    "status_class": status_class,
                })
            except (ValueError, TypeError):
                continue

        bans_list.sort(key=lambda b: (not b["is_ready"], b["ban_date"]))

        source = """
<div class="trini-tp-settings">
  <h3 class="trini-tp-title"><i class="fa fa-gavel"></i> AutoPrune - Seguimiento de Baneos</h3>
  <p class="trini-tp-subtitle">
    {{ total_bans }} baneo{{ "s" if total_bans != 1 else "" }}
    {% if ready_count > 0 %}
      &bull; <span class="text-danger">{{ ready_count }} listo{{ "s" if ready_count != 1 else "" }} para prune</span>
    {% endif %}
  </p>

  <div class="row mt-2 mb-2">
    {% if log_channel %}
    <div class="col-auto"><small class="text-muted"><i class="fa fa-hashtag"></i> Log prune: {{ log_channel }}</small></div>
    {% endif %}
    {% if ban_log_channel %}
    <div class="col-auto"><small class="text-muted"><i class="fa fa-hashtag"></i> Log baneos: {{ ban_log_channel }}</small></div>
    {% endif %}
  </div>

  {% if bans|length > 0 %}
  <div class="table-responsive">
    <table class="table trini-table trini-tp-table">
      <thead>
        <tr>
          <th>Usuario</th>
          <th>Fecha baneo</th>
          <th>Fecha prune</th>
          <th>Créditos</th>
          <th>Tiempo restante</th>
        </tr>
      </thead>
      <tbody>
        {% for ban in bans %}
        <tr>
          <td>{{ ban.user_name }}</td>
          <td><small>{{ ban.ban_date }}</small></td>
          <td><small>{{ ban.unban_date }}</small></td>
          <td><strong>{{ ban.balance }}</strong></td>
          <td>
            {% if ban.is_ready %}
              <span class="badge bg-gradient-danger"><i class="fa fa-exclamation-triangle me-1"></i>{{ ban.remaining }}</span>
            {% else %}
              <span class="badge bg-gradient-{{ ban.status_class }}"><i class="fa fa-clock-o me-1"></i>{{ ban.remaining }}</span>
            {% endif %}
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% else %}
  <div class="trini-tp-empty">
    <i class="fa fa-gavel fa-3x"></i>
    <p>No hay baneos en seguimiento en este servidor.</p>
  </div>
  {% endif %}
</div>
"""

        return {
            "status": 0,
            "web_content": {
                "source": source,
                "bans": bans_list,
                "total_bans": len(bans_list),
                "ready_count": ready_count,
                "log_channel": log_ch_name,
                "ban_log_channel": ban_log_ch_name,
            },
        }
