import typing
import datetime
from redbot.core import commands, Config
from redbot.core.bot import Red
import discord


def dashboard_page(*args, **kwargs):
    """
    Decorador para marcar métodos como páginas del Dashboard.
    Al aplicarlo se almacenan los parámetros en __dashboard_decorator_params__.
    """
    def decorator(func: typing.Callable):
        func.__dashboard_decorator_params__ = (args, kwargs)
        return func
    return decorator


class DashboardIntegration:
    bot: Red
    config: Config

    @commands.Cog.listener()
    async def on_dashboard_cog_add(self, dashboard_cog: commands.Cog) -> None:
        dashboard_cog.rpc.third_parties_handler.add_third_party(self)

    # ── Main page: Overview with stats ──────────────────────────────
    @dashboard_page(
        name=None,
        description="Panel de control de TicketsTrini — estadísticas y resumen",
        methods=("GET",),
    )
    async def dashboard_main(self, **kwargs) -> typing.Dict[str, typing.Any]:
        # Gather stats from all guilds the bot is in
        all_guilds = await self.config.all_guilds()
        total_open = 0
        total_opened_all = 0
        total_closed_all = 0
        total_panels = 0
        total_blacklisted = 0
        guilds_using = 0

        for gid, data in all_guilds.items():
            if not data:
                continue
            opened = data.get("opened", {})
            panels = data.get("panels", {})
            stats = data.get("stats", {})
            blacklist = data.get("blacklist", [])
            bl_advanced = data.get("blacklist_advanced", {})

            guild_open = sum(len(channels) for channels in opened.values())
            if guild_open > 0 or panels:
                guilds_using += 1
            total_open += guild_open
            total_opened_all += stats.get("total_opened", 0)
            total_closed_all += stats.get("total_closed", 0)
            total_panels += len(panels)
            total_blacklisted += len(blacklist) + len(bl_advanced)

        avg_claim = 0
        avg_close = 0
        guilds_with_stats = 0
        for gid, data in all_guilds.items():
            s = data.get("stats", {})
            if s.get("avg_claim_time", 0) > 0:
                avg_claim += s["avg_claim_time"]
                guilds_with_stats += 1
            if s.get("avg_close_time", 0) > 0:
                avg_close += s["avg_close_time"]
        if guilds_with_stats > 0:
            avg_claim = round(avg_claim / guilds_with_stats, 1)
            avg_close = round(avg_close / guilds_with_stats, 1)

        source = """
<div class="trini-tp-overview">
  <h3 class="trini-tp-title"><i class="fa fa-ticket"></i> TicketsTrini — Panel de Control</h3>
  <p class="trini-tp-subtitle">v{{ version }} por {{ author }}</p>

  <div class="row mt-4">
    <div class="col-lg-3 col-md-6 col-sm-6 mb-4">
      <div class="trini-tp-stat-card">
        <div class="trini-tp-stat-icon bg-gradient-success"><i class="fa fa-folder-open"></i></div>
        <div class="trini-tp-stat-body">
          <p class="trini-tp-stat-label">Tickets Abiertos</p>
          <h4 class="trini-tp-stat-value">{{ total_open }}</h4>
        </div>
      </div>
    </div>
    <div class="col-lg-3 col-md-6 col-sm-6 mb-4">
      <div class="trini-tp-stat-card">
        <div class="trini-tp-stat-icon bg-gradient-info"><i class="fa fa-check-circle"></i></div>
        <div class="trini-tp-stat-body">
          <p class="trini-tp-stat-label">Total Cerrados</p>
          <h4 class="trini-tp-stat-value">{{ total_closed }}</h4>
        </div>
      </div>
    </div>
    <div class="col-lg-3 col-md-6 col-sm-6 mb-4">
      <div class="trini-tp-stat-card">
        <div class="trini-tp-stat-icon bg-gradient-warning"><i class="fa fa-cubes"></i></div>
        <div class="trini-tp-stat-body">
          <p class="trini-tp-stat-label">Paneles Activos</p>
          <h4 class="trini-tp-stat-value">{{ total_panels }}</h4>
        </div>
      </div>
    </div>
    <div class="col-lg-3 col-md-6 col-sm-6 mb-4">
      <div class="trini-tp-stat-card">
        <div class="trini-tp-stat-icon bg-gradient-primary"><i class="fa fa-server"></i></div>
        <div class="trini-tp-stat-body">
          <p class="trini-tp-stat-label">Servidores</p>
          <h4 class="trini-tp-stat-value">{{ guilds_using }}</h4>
        </div>
      </div>
    </div>
  </div>

  <div class="row mt-2">
    <div class="col-lg-3 col-md-6 col-sm-6 mb-4">
      <div class="trini-tp-stat-card">
        <div class="trini-tp-stat-icon bg-gradient-dark"><i class="fa fa-bar-chart"></i></div>
        <div class="trini-tp-stat-body">
          <p class="trini-tp-stat-label">Total Abiertos</p>
          <h4 class="trini-tp-stat-value">{{ total_opened }}</h4>
        </div>
      </div>
    </div>
    <div class="col-lg-3 col-md-6 col-sm-6 mb-4">
      <div class="trini-tp-stat-card">
        <div class="trini-tp-stat-icon bg-gradient-danger"><i class="fa fa-ban"></i></div>
        <div class="trini-tp-stat-body">
          <p class="trini-tp-stat-label">Blacklisted</p>
          <h4 class="trini-tp-stat-value">{{ total_blacklisted }}</h4>
        </div>
      </div>
    </div>
    <div class="col-lg-3 col-md-6 col-sm-6 mb-4">
      <div class="trini-tp-stat-card">
        <div class="trini-tp-stat-icon bg-gradient-secondary"><i class="fa fa-clock-o"></i></div>
        <div class="trini-tp-stat-body">
          <p class="trini-tp-stat-label">Avg Claim (min)</p>
          <h4 class="trini-tp-stat-value">{{ avg_claim }}</h4>
        </div>
      </div>
    </div>
    <div class="col-lg-3 col-md-6 col-sm-6 mb-4">
      <div class="trini-tp-stat-card">
        <div class="trini-tp-stat-icon bg-gradient-secondary"><i class="fa fa-hourglass-end"></i></div>
        <div class="trini-tp-stat-body">
          <p class="trini-tp-stat-label">Avg Cierre (min)</p>
          <h4 class="trini-tp-stat-value">{{ avg_close }}</h4>
        </div>
      </div>
    </div>
  </div>

  <div class="row mt-2">
    <div class="col-12">
      <div class="trini-tp-info-card">
        <h5><i class="fa fa-info-circle"></i> Páginas disponibles</h5>
        <ul class="trini-tp-page-list">
          <li><a href="{{ url }}tickets"><i class="fa fa-list"></i> Tickets Activos</a> — Ver todos los tickets abiertos por servidor</li>
          <li><a href="{{ url }}settings"><i class="fa fa-cog"></i> Configuración</a> — Ver paneles y ajustes por servidor</li>
        </ul>
      </div>
    </div>
  </div>
</div>
"""
        base_url = kwargs.get("request_url", "").split("?")[0]
        if not base_url.endswith("/"):
            base_url += "/"

        return {
            "status": 0,
            "web_content": {
                "source": source,
                "version": self.__version__,
                "author": "Killerbite95",
                "total_open": total_open,
                "total_closed": total_closed_all,
                "total_opened": total_opened_all,
                "total_panels": total_panels,
                "guilds_using": guilds_using,
                "total_blacklisted": total_blacklisted,
                "avg_claim": avg_claim,
                "avg_close": avg_close,
                "url": base_url,
            },
        }

    # ── Tickets page: Active tickets per guild ──────────────────────
    @dashboard_page(
        name="tickets",
        description="Ver todos los tickets activos por servidor",
        methods=("GET",),
    )
    async def dashboard_tickets(self, **kwargs) -> typing.Dict[str, typing.Any]:
        all_guilds = await self.config.all_guilds()
        guilds_data = []

        for gid, data in all_guilds.items():
            opened = data.get("opened", {})
            if not opened:
                continue
            guild = self.bot.get_guild(gid)
            guild_name = guild.name if guild else f"ID: {gid}"
            guild_icon = str(guild.icon.url) if guild and guild.icon else ""

            tickets = []
            for uid_str, channels in opened.items():
                for ch_id_str, tdata in channels.items():
                    user = None
                    try:
                        user = self.bot.get_user(int(uid_str))
                    except (ValueError, TypeError):
                        pass
                    user_name = str(user) if user else f"ID: {uid_str}"
                    user_avatar = str(user.display_avatar.url) if user else ""

                    status = tdata.get("status", "open")
                    panel = tdata.get("panel", "—")
                    opened_at = tdata.get("opened", "")
                    claimed_by_id = tdata.get("claimed_by")
                    claimed_name = ""
                    if claimed_by_id:
                        claimer = self.bot.get_user(int(claimed_by_id)) if claimed_by_id else None
                        claimed_name = str(claimer) if claimer else f"ID: {claimed_by_id}"
                    escalated = tdata.get("escalated", False)
                    notes_count = len(tdata.get("notes", []))

                    # Format opened_at
                    opened_display = ""
                    if opened_at:
                        try:
                            dt = datetime.datetime.fromisoformat(str(opened_at))
                            opened_display = dt.strftime("%d/%m/%Y %H:%M")
                        except (ValueError, TypeError):
                            opened_display = str(opened_at)[:16]

                    status_class = {
                        "open": "success",
                        "claimed": "info",
                        "awaiting_user": "warning",
                        "awaiting_staff": "danger",
                    }.get(status, "secondary")

                    status_label = {
                        "open": "Abierto",
                        "claimed": "Reclamado",
                        "awaiting_user": "Esperando usuario",
                        "awaiting_staff": "Esperando staff",
                    }.get(status, status)

                    tickets.append({
                        "user_name": user_name,
                        "user_avatar": user_avatar,
                        "channel_id": ch_id_str,
                        "panel": panel,
                        "status": status,
                        "status_class": status_class,
                        "status_label": status_label,
                        "opened_at": opened_display,
                        "claimed_by": claimed_name,
                        "escalated": escalated,
                        "notes_count": notes_count,
                    })

            if tickets:
                guilds_data.append({
                    "name": guild_name,
                    "icon": guild_icon,
                    "id": gid,
                    "tickets": tickets,
                    "count": len(tickets),
                })

        source = """
<div class="trini-tp-tickets">
  <h3 class="trini-tp-title"><i class="fa fa-list"></i> Tickets Activos</h3>

  {% if guilds|length == 0 %}
    <div class="trini-tp-empty">
      <i class="fa fa-check-circle fa-3x"></i>
      <p>No hay tickets abiertos actualmente.</p>
    </div>
  {% else %}
    <p class="trini-tp-subtitle">{{ total_tickets }} ticket{{ "s" if total_tickets != 1 else "" }} en {{ guilds|length }} servidor{{ "es" if guilds|length != 1 else "" }}</p>

    {% for guild in guilds %}
    <div class="trini-tp-guild-section">
      <div class="trini-tp-guild-header">
        {% if guild.icon %}<img src="{{ guild.icon }}" class="trini-tp-guild-icon" />{% endif %}
        <h4>{{ guild.name }}</h4>
        <span class="badge bg-gradient-primary">{{ guild.count }}</span>
      </div>

      <div class="table-responsive">
        <table class="table trini-table trini-tp-table">
          <thead>
            <tr>
              <th>Usuario</th>
              <th>Panel</th>
              <th>Estado</th>
              <th>Abierto</th>
              <th>Reclamado por</th>
              <th>Info</th>
            </tr>
          </thead>
          <tbody>
            {% for t in guild.tickets %}
            <tr>
              <td>
                {% if t.user_avatar %}<img src="{{ t.user_avatar }}" class="trini-tp-user-avatar" />{% endif %}
                {{ t.user_name }}
              </td>
              <td><code>{{ t.panel }}</code></td>
              <td><span class="badge bg-gradient-{{ t.status_class }}">{{ t.status_label }}</span></td>
              <td>{{ t.opened_at }}</td>
              <td>{{ t.claimed_by if t.claimed_by else "—" }}</td>
              <td>
                {% if t.escalated %}<span class="badge bg-gradient-danger" title="Escalado"><i class="fa fa-exclamation-triangle"></i></span>{% endif %}
                {% if t.notes_count > 0 %}<span class="badge bg-gradient-info" title="{{ t.notes_count }} nota(s)"><i class="fa fa-sticky-note"></i> {{ t.notes_count }}</span>{% endif %}
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
        total_tickets = sum(g["count"] for g in guilds_data)

        return {
            "status": 0,
            "web_content": {
                "source": source,
                "guilds": guilds_data,
                "total_tickets": total_tickets,
            },
        }

    # ── Settings page: Panels and config per guild ──────────────────
    @dashboard_page(
        name="settings",
        description="Ver configuración de paneles y ajustes por servidor",
        methods=("GET",),
        is_owner=True,
    )
    async def dashboard_settings(self, **kwargs) -> typing.Dict[str, typing.Any]:
        all_guilds = await self.config.all_guilds()
        guilds_data = []

        for gid, data in all_guilds.items():
            panels = data.get("panels", {})
            if not panels:
                continue
            guild = self.bot.get_guild(gid)
            guild_name = guild.name if guild else f"ID: {gid}"

            support_roles = data.get("support_roles", [])
            role_names = []
            if guild:
                for rid in support_roles:
                    role = guild.get_role(rid)
                    role_names.append(role.name if role else f"ID: {rid}")

            panels_list = []
            for pname, pdata in panels.items():
                cat_id = pdata.get("category_id", 0)
                cat_name = ""
                if guild and cat_id:
                    cat = guild.get_channel(cat_id)
                    cat_name = cat.name if cat else f"ID: {cat_id}"

                log_ch = pdata.get("log_channel", 0)
                log_name = ""
                if guild and log_ch:
                    lch = guild.get_channel(log_ch)
                    log_name = f"#{lch.name}" if lch else f"ID: {log_ch}"

                panels_list.append({
                    "name": pname,
                    "disabled": pdata.get("disabled", False),
                    "threads": pdata.get("threads", False),
                    "button_text": pdata.get("button_text", "Open a Ticket"),
                    "button_color": pdata.get("button_color", "blue"),
                    "category": cat_name,
                    "log_channel": log_name,
                    "max_claims": pdata.get("max_claims", 0),
                    "ticket_num": pdata.get("ticket_num", 1),
                    "has_modal": bool(pdata.get("modal", {})),
                    "cooldown": pdata.get("cooldown", 0),
                    "schedule": pdata.get("schedule"),
                })

            settings_info = {
                "max_tickets": data.get("max_tickets", 1),
                "dm": data.get("dm", False),
                "transcript": data.get("transcript", False),
                "user_can_close": data.get("user_can_close", True),
                "user_can_rename": data.get("user_can_rename", False),
                "auto_close_user": data.get("auto_close_user_hours", 0),
                "auto_close_staff": data.get("auto_close_staff_hours", 0),
                "escalation_minutes": data.get("escalation_minutes", 0),
                "ticket_cooldown": data.get("ticket_cooldown", 0),
                "global_rate_limit": data.get("global_rate_limit", 0),
            }

            guilds_data.append({
                "name": guild_name,
                "id": gid,
                "panels": panels_list,
                "panel_count": len(panels_list),
                "support_roles": role_names,
                "settings": settings_info,
            })

        source = """
<div class="trini-tp-settings">
  <h3 class="trini-tp-title"><i class="fa fa-cog"></i> Configuración de TicketsTrini</h3>

  {% if guilds|length == 0 %}
    <div class="trini-tp-empty">
      <i class="fa fa-cog fa-3x"></i>
      <p>No hay servidores con paneles configurados.</p>
    </div>
  {% else %}
    {% for guild in guilds %}
    <div class="trini-tp-guild-section">
      <div class="trini-tp-guild-header">
        <h4>{{ guild.name }}</h4>
        <span class="badge bg-gradient-primary">{{ guild.panel_count }} panel{{ "es" if guild.panel_count != 1 else "" }}</span>
      </div>

      <!-- Settings summary -->
      <div class="trini-tp-settings-grid">
        <div class="trini-tp-setting-item">
          <span class="trini-tp-setting-label">Max tickets/usuario</span>
          <span class="trini-tp-setting-value">{{ guild.settings.max_tickets }}</span>
        </div>
        <div class="trini-tp-setting-item">
          <span class="trini-tp-setting-label">DM al cerrar</span>
          <span class="trini-tp-setting-value">{{ "Sí" if guild.settings.dm else "No" }}</span>
        </div>
        <div class="trini-tp-setting-item">
          <span class="trini-tp-setting-label">Transcripts</span>
          <span class="trini-tp-setting-value">{{ "Sí" if guild.settings.transcript else "No" }}</span>
        </div>
        <div class="trini-tp-setting-item">
          <span class="trini-tp-setting-label">Auto-close (usuario)</span>
          <span class="trini-tp-setting-value">{{ guild.settings.auto_close_user }}h</span>
        </div>
        <div class="trini-tp-setting-item">
          <span class="trini-tp-setting-label">Auto-close (staff)</span>
          <span class="trini-tp-setting-value">{{ guild.settings.auto_close_staff }}h</span>
        </div>
        <div class="trini-tp-setting-item">
          <span class="trini-tp-setting-label">Escalación</span>
          <span class="trini-tp-setting-value">{{ guild.settings.escalation_minutes }}min</span>
        </div>
        <div class="trini-tp-setting-item">
          <span class="trini-tp-setting-label">Cooldown</span>
          <span class="trini-tp-setting-value">{{ guild.settings.ticket_cooldown }}s</span>
        </div>
        <div class="trini-tp-setting-item">
          <span class="trini-tp-setting-label">Rate limit</span>
          <span class="trini-tp-setting-value">{{ guild.settings.global_rate_limit }}/h</span>
        </div>
      </div>

      {% if guild.support_roles %}
      <p class="mt-3"><strong>Roles de soporte:</strong> {{ guild.support_roles|join(", ") }}</p>
      {% endif %}

      <!-- Panels table -->
      <div class="table-responsive mt-3">
        <table class="table trini-table trini-tp-table">
          <thead>
            <tr>
              <th>Panel</th>
              <th>Estado</th>
              <th>Tipo</th>
              <th>Botón</th>
              <th>Categoría</th>
              <th>Log</th>
              <th>Claims</th>
              <th>#</th>
              <th>Modal</th>
            </tr>
          </thead>
          <tbody>
            {% for p in guild.panels %}
            <tr>
              <td><strong>{{ p.name }}</strong></td>
              <td>
                {% if p.disabled %}
                  <span class="badge bg-gradient-danger">Desactivado</span>
                {% else %}
                  <span class="badge bg-gradient-success">Activo</span>
                {% endif %}
              </td>
              <td>{{ "Thread" if p.threads else "Canal" }}</td>
              <td><code>{{ p.button_text }}</code> <span class="badge" style="background: {{ p.button_color }};">{{ p.button_color }}</span></td>
              <td>{{ p.category if p.category else "—" }}</td>
              <td>{{ p.log_channel if p.log_channel else "—" }}</td>
              <td>{{ p.max_claims if p.max_claims > 0 else "∞" }}</td>
              <td>{{ p.ticket_num }}</td>
              <td>{{ "Sí" if p.has_modal else "No" }}</td>
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
