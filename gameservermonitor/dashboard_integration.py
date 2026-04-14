"""
Dashboard Integration para GameServerMonitor.
Proporciona integración con Red-Dashboard.
By Killerbite95
"""

import typing
import html as html_mod

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
    query_service: typing.Any

    @commands.Cog.listener()
    async def on_dashboard_cog_add(self, dashboard_cog: commands.Cog) -> None:
        dashboard_cog.rpc.third_parties_handler.add_third_party(self)

    @dashboard_page(
        name="servers",
        description="Estado de servidores de juegos",
        methods=("GET",),
        is_owner=True,
    )
    async def rpc_servers_page(self, **kwargs) -> typing.Dict[str, typing.Any]:
        try:
            all_guilds = await self.config.all_guilds()
        except Exception:
            return {"status": 0, "web_content": {"source": '<div class="trini-tp-empty"><i class="fa fa-exclamation-triangle fa-3x"></i><p>Error al cargar datos.</p></div>'}}

        guilds_data = []
        for gid, data in all_guilds.items():
            try:
                servers_raw = data.get("servers", {})
                if not servers_raw:
                    continue
                guild = self.bot.get_guild(gid)
                guild_name = guild.name if guild else f"ID: {gid}"
                tz = data.get("timezone", "UTC")
                refresh = data.get("refresh_time", 60)
                public_ip = data.get("public_ip")

                servers_list = []
                online_count = 0
                total_players = 0

                for key, sdata in servers_raw.items():
                    if not isinstance(sdata, dict):
                        continue
                    game = str(sdata.get("game", "unknown"))
                    name = html_mod.escape(str(sdata.get("name", key)))
                    domain = html_mod.escape(str(sdata.get("domain", ""))) if sdata.get("domain") else ""

                    # Display IP
                    display_ip = key
                    if public_ip and ":" in key:
                        ip_part, port_part = key.split(":", 1)
                        if ip_part.startswith(("10.", "192.168.", "172.")):
                            display_ip = f"{public_ip}:{port_part}"

                    last_status = str(sdata.get("last_status", "unknown")).lower()
                    is_online = last_status in ("online", "maintenance")
                    if is_online:
                        online_count += 1

                    players = int(sdata.get("current_players", 0) or 0)
                    max_players = int(sdata.get("max_players", 0) or 0)
                    total_players += players

                    map_name = html_mod.escape(str(sdata.get("current_map", "-") or "-"))

                    total_q = int(sdata.get("total_queries", 0) or 0)
                    success_q = int(sdata.get("successful_queries", 0) or 0)
                    success_pct = round(success_q / total_q * 100) if total_q > 0 else 0

                    status_class = "success" if is_online else "danger"
                    status_icon = "check-circle" if is_online else "times-circle"
                    if last_status == "maintenance":
                        status_class = "warning"
                        status_icon = "lock"

                    servers_list.append({
                        "key": html_mod.escape(key),
                        "display_ip": html_mod.escape(display_ip),
                        "name": name,
                        "domain": domain,
                        "game": html_mod.escape(game.upper()),
                        "status": last_status,
                        "status_class": status_class,
                        "status_icon": status_icon,
                        "players": players,
                        "max_players": max_players,
                        "map": map_name,
                        "success_pct": success_pct,
                    })

                guilds_data.append({
                    "name": html_mod.escape(guild_name),
                    "id": gid,
                    "timezone": html_mod.escape(tz),
                    "refresh": refresh,
                    "total": len(servers_list),
                    "online": online_count,
                    "total_players": total_players,
                    "servers": servers_list,
                })
            except Exception:
                continue

        guilds_data.sort(key=lambda g: g["name"].lower())

        source = """
<div class="trini-tp-settings">
  <h3 class="trini-tp-title"><i class="fa fa-gamepad"></i> Monitor de Servidores</h3>
  <p class="trini-tp-subtitle">Estado en tiempo real de los servidores de juegos</p>

  {% if guilds|length == 0 %}
    <div class="trini-tp-empty">
      <i class="fa fa-gamepad fa-3x"></i>
      <p>No hay servidores configurados.</p>
    </div>
  {% else %}
    {% for guild in guilds %}
    <div class="trini-tp-guild-section">
      <div class="trini-tp-guild-header">
        <h4>{{ guild.name }}</h4>
        <span class="badge bg-gradient-success">{{ guild.online }}/{{ guild.total }} online</span>
        <span class="badge bg-gradient-info ms-1">{{ guild.total_players }} jugadores</span>
        <span class="badge bg-gradient-secondary ms-1">{{ guild.timezone }} &bull; {{ guild.refresh }}s</span>
      </div>

      <div class="table-responsive mt-3">
        <table class="table trini-table trini-tp-table">
          <thead>
            <tr>
              <th>Estado</th>
              <th>Servidor</th>
              <th>Juego</th>
              <th>IP</th>
              <th>Mapa</th>
              <th>Jugadores</th>
              <th>Salud</th>
            </tr>
          </thead>
          <tbody>
            {% for s in guild.servers %}
            <tr>
              <td>
                <i class="fa fa-{{ s.status_icon }} text-{{ s.status_class }}"></i>
              </td>
              <td>
                <strong>{{ s.name }}</strong>
                {% if s.domain %}<br><small class="text-muted">{{ s.domain }}</small>{% endif %}
              </td>
              <td><span class="badge bg-gradient-dark">{{ s.game }}</span></td>
              <td><code>{{ s.display_ip }}</code></td>
              <td>{{ s.map }}</td>
              <td>
                {% if s.max_players > 0 %}
                  <div class="d-flex align-items-center">
                    <span class="me-2">{{ s.players }}/{{ s.max_players }}</span>
                    <div class="progress" style="width:60px;height:6px">
                      {% set pct = (s.players / s.max_players * 100)|int if s.max_players > 0 else 0 %}
                      <div class="progress-bar bg-gradient-{{ 'success' if pct < 70 else ('warning' if pct < 90 else 'danger') }}" style="width:{{ pct }}%"></div>
                    </div>
                  </div>
                {% else %}
                  {{ s.players }}
                {% endif %}
              </td>
              <td>
                <div class="d-flex align-items-center">
                  <span class="me-2 text-xs">{{ s.success_pct }}%</span>
                  <div class="progress" style="width:50px;height:6px">
                    <div class="progress-bar bg-gradient-{{ 'success' if s.success_pct >= 80 else ('warning' if s.success_pct >= 50 else 'danger') }}" style="width:{{ s.success_pct }}%"></div>
                  </div>
                </div>
              </td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
    {% endfor %}
  {% endif %}
</div>
"""

        return {
            "status": 0,
            "web_content": {
                "source": source,
                "guilds": guilds_data,
            },
        }
