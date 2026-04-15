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

    async def cog_load(self) -> None:
        dashboard_cog = self.bot.get_cog("Dashboard")
        if dashboard_cog and hasattr(dashboard_cog, "rpc"):
            try:
                dashboard_cog.rpc.third_parties_handler.add_third_party(self)
            except Exception:
                pass

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


    # ── Settings page: Configurable panels and guild settings ───────
    @dashboard_page(
        name="settings",
        description="Ver y editar configuración de paneles y ajustes por servidor",
        methods=("GET", "POST"),
        is_owner=True,
    )
    async def dashboard_settings(self, **kwargs) -> typing.Dict[str, typing.Any]:
        method = kwargs.get("method", "GET")
        notifications = []

        def _fv(form, key, default=""):
            v = form.get(key, [default])
            return v[0] if isinstance(v, list) else str(v)

        # ── Handle POST ─────────────────────────────────────────────
        if method == "POST":
            form = kwargs.get("data", {}).get("form", {})
            action = _fv(form, "action")
            try:
                guild_id = int(_fv(form, "guild_id", "0"))
                guild = self.bot.get_guild(guild_id)
            except (ValueError, TypeError):
                guild = None

            if not guild:
                notifications.append({"message": "Servidor no encontrado.", "category": "danger"})

            elif action == "update_guild":
                try:
                    async with self.config.guild(guild).all() as gdata:
                        for key in [
                            "dm", "transcript", "detailed_transcript",
                            "user_can_close", "user_can_rename", "user_can_manage",
                            "auto_add", "thread_close",
                        ]:
                            gdata[key] = f"field_{key}" in form
                        for key, mn, mx, dv in [
                            ("max_tickets", 1, 50, 1),
                            ("inactive", 0, 720, 0),
                            ("ticket_cooldown", 0, 86400, 0),
                            ("global_rate_limit", 0, 1000, 0),
                            ("min_account_age", 0, 365, 0),
                            ("min_server_age", 0, 365, 0),
                            ("auto_close_user_hours", 0, 720, 0),
                            ("auto_close_staff_hours", 0, 720, 0),
                            ("max_claims_per_staff", 0, 100, 0),
                            ("escalation_minutes", 0, 10080, 0),
                        ]:
                            try:
                                val = int(_fv(form, f"field_{key}", str(dv)))
                                gdata[key] = max(mn, min(mx, val))
                            except (ValueError, TypeError):
                                pass
                    notifications.append({"message": f"Configuración de {guild.name} guardada.", "category": "success"})
                except Exception as e:
                    notifications.append({"message": f"Error al guardar: {e}", "category": "danger"})

            elif action == "toggle_panel":
                panel_name = _fv(form, "panel_name")
                try:
                    async with self.config.guild(guild).panels() as panels:
                        if panel_name in panels:
                            panels[panel_name]["disabled"] = not panels[panel_name].get("disabled", False)
                            state = "desactivado" if panels[panel_name]["disabled"] else "activado"
                            notifications.append({"message": f"Panel '{panel_name}' {state}.", "category": "success"})
                except Exception as e:
                    notifications.append({"message": f"Error: {e}", "category": "danger"})

            elif action == "update_panel":
                panel_name = _fv(form, "panel_name")
                try:
                    async with self.config.guild(guild).panels() as panels:
                        if panel_name in panels:
                            btn_text = _fv(form, "field_button_text")
                            if btn_text:
                                panels[panel_name]["button_text"] = btn_text[:80]
                            btn_color = _fv(form, "field_button_color", "blue")
                            if btn_color in ("blue", "green", "red", "grey"):
                                panels[panel_name]["button_color"] = btn_color
                            try:
                                mc = int(_fv(form, "field_max_claims", "0"))
                                panels[panel_name]["max_claims"] = max(0, min(100, mc))
                            except (ValueError, TypeError):
                                pass
                            panels[panel_name]["close_reason"] = "field_close_reason" in form
                            panels[panel_name]["threads"] = "field_threads" in form
                            notifications.append({"message": f"Panel '{panel_name}' actualizado.", "category": "success"})
                except Exception as e:
                    notifications.append({"message": f"Error: {e}", "category": "danger"})

            elif action == "create_panel":
                raw_name = _fv(form, "panel_name").strip().lower()
                panel_name = raw_name.replace(" ", "_")
                if not panel_name or not panel_name.replace("_", "").isalnum():
                    notifications.append({"message": "Nombre inválido. Usa solo letras, números y guiones bajos.", "category": "danger"})
                elif len(panel_name) > 40:
                    notifications.append({"message": "El nombre del panel no puede superar 40 caracteres.", "category": "danger"})
                else:
                    try:
                        async with self.config.guild(guild).panels() as panels:
                            if panel_name in panels:
                                notifications.append({"message": f"Ya existe un panel con el nombre '{panel_name}'.", "category": "warning"})
                            else:
                                btn_text = _fv(form, "field_button_text", "Abrir Ticket")[:80] or "Abrir Ticket"
                                btn_color = _fv(form, "field_button_color", "blue")
                                if btn_color not in ("blue", "green", "red", "grey"):
                                    btn_color = "blue"
                                try:
                                    cat_id = int(_fv(form, "field_category_id", "0"))
                                except (ValueError, TypeError):
                                    cat_id = 0
                                try:
                                    log_id = int(_fv(form, "field_log_channel", "0"))
                                except (ValueError, TypeError):
                                    log_id = 0
                                try:
                                    mc = int(_fv(form, "field_max_claims", "0"))
                                    mc = max(0, min(100, mc))
                                except (ValueError, TypeError):
                                    mc = 0
                                new_panel = {
                                    "category_id": cat_id,
                                    "channel_id": 0,
                                    "message_id": 0,
                                    "disabled": False,
                                    "alt_channel": 0,
                                    "required_roles": [],
                                    "close_reason": "field_close_reason" in form,
                                    "button_text": btn_text,
                                    "button_color": btn_color,
                                    "button_emoji": None,
                                    "priority": len(panels) + 1,
                                    "row": None,
                                    "ticket_messages": [],
                                    "ticket_name": None,
                                    "log_channel": log_id,
                                    "modal": {},
                                    "modal_title": "",
                                    "threads": "field_threads" in form,
                                    "roles": [],
                                    "max_claims": mc,
                                    "ticket_num": 1,
                                    "cooldown": 0,
                                    "rate_limit": 0,
                                    "max_open": 0,
                                    "schedule": None,
                                    "welcome_sections": None,
                                    "fallback_mode": "none",
                                }
                                panels[panel_name] = new_panel
                                notifications.append({
                                    "message": f"Panel '{panel_name}' creado exitosamente. Usa [p]tickets panel post {panel_name} en Discord para publicarlo.",
                                    "category": "success",
                                })
                    except Exception as e:
                        notifications.append({"message": f"Error al crear panel: {e}", "category": "danger"})

            elif action == "delete_panel":
                panel_name = _fv(form, "panel_name")
                if not panel_name:
                    notifications.append({"message": "Panel no encontrado.", "category": "danger"})
                else:
                    try:
                        async with self.config.guild(guild).panels() as panels:
                            if panel_name in panels:
                                del panels[panel_name]
                                notifications.append({"message": f"Panel '{panel_name}' eliminado.", "category": "success"})
                            else:
                                notifications.append({"message": f"Panel '{panel_name}' no existe.", "category": "warning"})
                    except Exception as e:
                        notifications.append({"message": f"Error: {e}", "category": "danger"})

        # ── Load all guilds ─────────────────────────────────────────
        try:
            all_guilds = await self.config.all_guilds()
        except Exception:
            return {
                "status": 0,
                "web_content": {
                    "source": '<div class="trini-tp-empty"><i class="fa fa-exclamation-triangle fa-3x"></i><p>Error al cargar configuración.</p></div>',
                },
            }

        guilds_data = []
        seen_gids = set()
        for gid, data in all_guilds.items():
            try:
                seen_gids.add(gid)
                panels = data.get("panels", {})
                guild = self.bot.get_guild(gid)
                guild_name = guild.name if guild else f"ID: {gid}"
                editable = guild is not None

                # Parse support_roles — handle [[id, bool], ...] format
                support_roles_raw = data.get("support_roles", [])
                role_names = []
                for role_entry in support_roles_raw:
                    if isinstance(role_entry, (list, tuple)):
                        rid = role_entry[0] if role_entry else 0
                    else:
                        rid = role_entry
                    try:
                        rid = int(rid)
                    except (ValueError, TypeError):
                        continue
                    if guild:
                        role = guild.get_role(rid)
                        role_names.append(role.name if role else f"ID: {rid}")
                    else:
                        role_names.append(f"ID: {rid}")

                panels_list = []
                for pname, pdata in panels.items():
                    if not isinstance(pdata, dict):
                        continue
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
                        "name": str(pname),
                        "disabled": bool(pdata.get("disabled", False)),
                        "threads": bool(pdata.get("threads", False)),
                        "button_text": str(pdata.get("button_text", "Open a Ticket")),
                        "button_color": str(pdata.get("button_color", "blue")),
                        "button_emoji": str(pdata.get("button_emoji", "") or ""),
                        "category": str(cat_name),
                        "log_channel": str(log_name),
                        "max_claims": int(pdata.get("max_claims", 0) or 0),
                        "ticket_num": int(pdata.get("ticket_num", 1) or 1),
                        "has_modal": bool(pdata.get("modal", {})),
                        "close_reason": bool(pdata.get("close_reason", True)),
                    })

                # Collect categories and text channels for dropdowns
                categories = []
                text_channels = []
                if guild:
                    for cat in guild.categories:
                        categories.append({"id": cat.id, "name": cat.name})
                    for ch in guild.text_channels:
                        text_channels.append({"id": ch.id, "name": f"#{ch.name}"})

                settings_info = {
                    "max_tickets": int(data.get("max_tickets", 1) or 1),
                    "dm": bool(data.get("dm", False)),
                    "transcript": bool(data.get("transcript", False)),
                    "detailed_transcript": bool(data.get("detailed_transcript", False)),
                    "user_can_close": bool(data.get("user_can_close", True)),
                    "user_can_rename": bool(data.get("user_can_rename", False)),
                    "user_can_manage": bool(data.get("user_can_manage", False)),
                    "auto_add": bool(data.get("auto_add", False)),
                    "thread_close": bool(data.get("thread_close", True)),
                    "inactive": int(data.get("inactive", 0) or 0),
                    "auto_close_user": int(data.get("auto_close_user_hours", 0) or 0),
                    "auto_close_staff": int(data.get("auto_close_staff_hours", 0) or 0),
                    "escalation_minutes": int(data.get("escalation_minutes", 0) or 0),
                    "ticket_cooldown": int(data.get("ticket_cooldown", 0) or 0),
                    "global_rate_limit": int(data.get("global_rate_limit", 0) or 0),
                    "min_account_age": int(data.get("min_account_age", 0) or 0),
                    "min_server_age": int(data.get("min_server_age", 0) or 0),
                    "max_claims_per_staff": int(data.get("max_claims_per_staff", 0) or 0),
                }

                guilds_data.append({
                    "name": guild_name,
                    "id": gid,
                    "editable": editable,
                    "panels": panels_list,
                    "panel_count": len(panels_list),
                    "support_roles": role_names,
                    "settings": settings_info,
                    "categories": categories,
                    "text_channels": text_channels,
                })
            except Exception:
                continue

        # Also show bot guilds not yet in config (so panels can be created)
        for guild in self.bot.guilds:
            if guild.id not in seen_gids:
                categories = [{"id": c.id, "name": c.name} for c in guild.categories]
                text_channels = [{"id": c.id, "name": f"#{c.name}"} for c in guild.text_channels]
                guilds_data.append({
                    "name": guild.name,
                    "id": guild.id,
                    "editable": True,
                    "panels": [],
                    "panel_count": 0,
                    "support_roles": [],
                    "settings": {
                        "max_tickets": 1, "dm": False, "transcript": False,
                        "detailed_transcript": False, "user_can_close": True,
                        "user_can_rename": False, "user_can_manage": False,
                        "auto_add": False, "thread_close": True, "inactive": 0,
                        "auto_close_user": 0, "auto_close_staff": 0,
                        "escalation_minutes": 0, "ticket_cooldown": 0,
                        "global_rate_limit": 0, "min_account_age": 0,
                        "min_server_age": 0, "max_claims_per_staff": 0,
                    },
                    "categories": categories,
                    "text_channels": text_channels,
                })

        guilds_data.sort(key=lambda g: (not g["editable"], g["name"].lower()))

        source = """
<div class="trini-tp-settings">
  <h3 class="trini-tp-title"><i class="fa fa-cog"></i> Configuración de TicketsTrini</h3>
  <p class="trini-tp-subtitle">{{ guilds|length }} servidor{{ "es" if guilds|length != 1 else "" }} disponible{{ "s" if guilds|length != 1 else "" }}</p>

  {% if guilds|length == 0 %}
    <div class="trini-tp-empty">
      <i class="fa fa-cog fa-3x"></i>
      <p>No hay servidores disponibles.</p>
    </div>
  {% else %}
    {% for guild in guilds %}
    <div class="trini-tp-guild-section">
      <div class="trini-tp-guild-header">
        <h4>{{ guild.name }}</h4>
        <span class="badge bg-gradient-primary">{{ guild.panel_count }} panel{{ "es" if guild.panel_count != 1 else "" }}</span>
      </div>

      {% if guild.editable %}
      {# ═══ FORM: Editable guild settings ═══ #}
      <form method="POST" class="mt-3">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <input type="hidden" name="action" value="update_guild">
        <input type="hidden" name="guild_id" value="{{ guild.id }}">

        <h6 class="text-uppercase text-xs font-weight-bolder opacity-6 mb-3">
          <i class="fa fa-toggle-on me-1"></i> Ajustes Generales
        </h6>
        <div class="row">
          <div class="col-lg-3 col-md-4 col-6 mb-2">
            <div class="form-check form-switch">
              <input class="form-check-input" type="checkbox" name="field_dm" id="dm_{{ guild.id }}" {% if guild.settings.dm %}checked{% endif %}>
              <label class="form-check-label" for="dm_{{ guild.id }}">DM al cerrar</label>
            </div>
          </div>
          <div class="col-lg-3 col-md-4 col-6 mb-2">
            <div class="form-check form-switch">
              <input class="form-check-input" type="checkbox" name="field_transcript" id="tr_{{ guild.id }}" {% if guild.settings.transcript %}checked{% endif %}>
              <label class="form-check-label" for="tr_{{ guild.id }}">Transcripts</label>
            </div>
          </div>
          <div class="col-lg-3 col-md-4 col-6 mb-2">
            <div class="form-check form-switch">
              <input class="form-check-input" type="checkbox" name="field_detailed_transcript" id="dt_{{ guild.id }}" {% if guild.settings.detailed_transcript %}checked{% endif %}>
              <label class="form-check-label" for="dt_{{ guild.id }}">Transcript HTML</label>
            </div>
          </div>
          <div class="col-lg-3 col-md-4 col-6 mb-2">
            <div class="form-check form-switch">
              <input class="form-check-input" type="checkbox" name="field_user_can_close" id="ucc_{{ guild.id }}" {% if guild.settings.user_can_close %}checked{% endif %}>
              <label class="form-check-label" for="ucc_{{ guild.id }}">User puede cerrar</label>
            </div>
          </div>
          <div class="col-lg-3 col-md-4 col-6 mb-2">
            <div class="form-check form-switch">
              <input class="form-check-input" type="checkbox" name="field_user_can_rename" id="ucr_{{ guild.id }}" {% if guild.settings.user_can_rename %}checked{% endif %}>
              <label class="form-check-label" for="ucr_{{ guild.id }}">User puede renombrar</label>
            </div>
          </div>
          <div class="col-lg-3 col-md-4 col-6 mb-2">
            <div class="form-check form-switch">
              <input class="form-check-input" type="checkbox" name="field_user_can_manage" id="ucm_{{ guild.id }}" {% if guild.settings.user_can_manage %}checked{% endif %}>
              <label class="form-check-label" for="ucm_{{ guild.id }}">User puede gestionar</label>
            </div>
          </div>
          <div class="col-lg-3 col-md-4 col-6 mb-2">
            <div class="form-check form-switch">
              <input class="form-check-input" type="checkbox" name="field_auto_add" id="aa_{{ guild.id }}" {% if guild.settings.auto_add %}checked{% endif %}>
              <label class="form-check-label" for="aa_{{ guild.id }}">Auto-add roles</label>
            </div>
          </div>
          <div class="col-lg-3 col-md-4 col-6 mb-2">
            <div class="form-check form-switch">
              <input class="form-check-input" type="checkbox" name="field_thread_close" id="tc_{{ guild.id }}" {% if guild.settings.thread_close %}checked{% endif %}>
              <label class="form-check-label" for="tc_{{ guild.id }}">Cerrar threads</label>
            </div>
          </div>
        </div>

        <h6 class="text-uppercase text-xs font-weight-bolder opacity-6 mt-3 mb-3">
          <i class="fa fa-sliders me-1"></i> Valores
        </h6>
        <div class="row">
          <div class="col-lg-3 col-md-4 col-6 mb-3">
            <label class="form-label text-xs mb-1">Max tickets/usuario</label>
            <input type="number" class="form-control form-control-sm" name="field_max_tickets" value="{{ guild.settings.max_tickets }}" min="1" max="50">
          </div>
          <div class="col-lg-3 col-md-4 col-6 mb-3">
            <label class="form-label text-xs mb-1">Inactividad (horas)</label>
            <input type="number" class="form-control form-control-sm" name="field_inactive" value="{{ guild.settings.inactive }}" min="0" max="720">
          </div>
          <div class="col-lg-3 col-md-4 col-6 mb-3">
            <label class="form-label text-xs mb-1">Cooldown (segundos)</label>
            <input type="number" class="form-control form-control-sm" name="field_ticket_cooldown" value="{{ guild.settings.ticket_cooldown }}" min="0" max="86400">
          </div>
          <div class="col-lg-3 col-md-4 col-6 mb-3">
            <label class="form-label text-xs mb-1">Rate limit (/hora)</label>
            <input type="number" class="form-control form-control-sm" name="field_global_rate_limit" value="{{ guild.settings.global_rate_limit }}" min="0" max="1000">
          </div>
          <div class="col-lg-3 col-md-4 col-6 mb-3">
            <label class="form-label text-xs mb-1">Edad cuenta (días)</label>
            <input type="number" class="form-control form-control-sm" name="field_min_account_age" value="{{ guild.settings.min_account_age }}" min="0" max="365">
          </div>
          <div class="col-lg-3 col-md-4 col-6 mb-3">
            <label class="form-label text-xs mb-1">Edad server (días)</label>
            <input type="number" class="form-control form-control-sm" name="field_min_server_age" value="{{ guild.settings.min_server_age }}" min="0" max="365">
          </div>
          <div class="col-lg-3 col-md-4 col-6 mb-3">
            <label class="form-label text-xs mb-1">Auto-close user (h)</label>
            <input type="number" class="form-control form-control-sm" name="field_auto_close_user_hours" value="{{ guild.settings.auto_close_user }}" min="0" max="720">
          </div>
          <div class="col-lg-3 col-md-4 col-6 mb-3">
            <label class="form-label text-xs mb-1">Auto-close staff (h)</label>
            <input type="number" class="form-control form-control-sm" name="field_auto_close_staff_hours" value="{{ guild.settings.auto_close_staff }}" min="0" max="720">
          </div>
          <div class="col-lg-3 col-md-4 col-6 mb-3">
            <label class="form-label text-xs mb-1">Max claims/staff</label>
            <input type="number" class="form-control form-control-sm" name="field_max_claims_per_staff" value="{{ guild.settings.max_claims_per_staff }}" min="0" max="100">
          </div>
          <div class="col-lg-3 col-md-4 col-6 mb-3">
            <label class="form-label text-xs mb-1">Escalación (min)</label>
            <input type="number" class="form-control form-control-sm" name="field_escalation_minutes" value="{{ guild.settings.escalation_minutes }}" min="0" max="10080">
          </div>
        </div>

        <button type="submit" class="btn btn-sm bg-gradient-success mb-0">
          <i class="fa fa-save me-1"></i> Guardar Cambios
        </button>
      </form>

      {% else %}
      {# ═══ Read-only settings ═══ #}
      <div class="trini-tp-settings-grid">
        <div class="trini-tp-setting-item"><span class="trini-tp-setting-label">Max tickets</span><span class="trini-tp-setting-value">{{ guild.settings.max_tickets }}</span></div>
        <div class="trini-tp-setting-item"><span class="trini-tp-setting-label">DM al cerrar</span><span class="trini-tp-setting-value">{{ "Sí" if guild.settings.dm else "No" }}</span></div>
        <div class="trini-tp-setting-item"><span class="trini-tp-setting-label">Transcripts</span><span class="trini-tp-setting-value">{{ "Sí" if guild.settings.transcript else "No" }}</span></div>
        <div class="trini-tp-setting-item"><span class="trini-tp-setting-label">Inactividad</span><span class="trini-tp-setting-value">{{ guild.settings.inactive }}h</span></div>
      </div>
      {% endif %}

      {% if guild.support_roles %}
      <div class="mt-3">
        <span class="text-uppercase text-xs font-weight-bolder opacity-6"><i class="fa fa-shield me-1"></i> Roles de soporte:</span>
        {{ guild.support_roles|join(", ") }}
      </div>
      {% endif %}

      {# ═══ PANELS TABLE ═══ #}
      {% if guild.panels|length > 0 %}
      <h6 class="text-uppercase text-xs font-weight-bolder opacity-6 mt-4 mb-2">
        <i class="fa fa-th-large me-1"></i> Paneles
      </h6>
      <div class="table-responsive">
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
              {% if guild.editable %}<th>Acciones</th>{% endif %}
            </tr>
          </thead>
          <tbody>
            {% for p in guild.panels %}
            <tr>
              <td><strong>{{ p.name }}</strong></td>
              <td>
                {% if guild.editable %}
                <form method="POST" style="display:inline;margin:0">
                  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                  <input type="hidden" name="action" value="toggle_panel">
                  <input type="hidden" name="guild_id" value="{{ guild.id }}">
                  <input type="hidden" name="panel_name" value="{{ p.name }}">
                  <button type="submit" class="btn btn-xs mb-0 {{ 'bg-gradient-danger' if p.disabled else 'bg-gradient-success' }}">
                    {{ "Off" if p.disabled else "On" }}
                  </button>
                </form>
                {% else %}
                <span class="badge {{ 'bg-gradient-danger' if p.disabled else 'bg-gradient-success' }}">{{ "Off" if p.disabled else "On" }}</span>
                {% endif %}
              </td>
              <td>{{ "Thread" if p.threads else "Canal" }}</td>
              <td>{% if p.button_emoji %}{{ p.button_emoji }} {% endif %}<code>{{ p.button_text }}</code> <span class="badge" style="background:{{ p.button_color }}">{{ p.button_color }}</span></td>
              <td>{{ p.category if p.category else "—" }}</td>
              <td>{{ p.log_channel if p.log_channel else "—" }}</td>
              <td>{{ p.max_claims if p.max_claims > 0 else "∞" }}</td>
              <td>{{ p.ticket_num }}</td>
              {% if guild.editable %}
              <td>
                <a href="javascript:void(0)" onclick="toggleEdit('{{ guild.id }}','{{ loop.index }}')" class="text-info text-xs font-weight-bold me-2" title="Editar"><i class="fa fa-pencil"></i></a>
                <a href="javascript:void(0)" onclick="confirmDelete('{{ guild.id }}','{{ p.name }}')" class="text-danger text-xs font-weight-bold" title="Eliminar"><i class="fa fa-trash"></i></a>
              </td>
              {% endif %}
            </tr>
            {% if guild.editable %}
            <tr id="edit_{{ guild.id }}_{{ loop.index }}" style="display:none">
              <td colspan="10" style="background:rgba(94,114,228,0.04)">
                <form method="POST" class="row align-items-end py-2 px-1">
                  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                  <input type="hidden" name="action" value="update_panel">
                  <input type="hidden" name="guild_id" value="{{ guild.id }}">
                  <input type="hidden" name="panel_name" value="{{ p.name }}">
                  <div class="col-lg-3 col-md-4 col-6 mb-2">
                    <label class="form-label text-xs mb-1">Texto botón</label>
                    <input type="text" class="form-control form-control-sm" name="field_button_text" value="{{ p.button_text }}" maxlength="80">
                  </div>
                  <div class="col-lg-2 col-md-3 col-6 mb-2">
                    <label class="form-label text-xs mb-1">Color</label>
                    <select class="form-select form-select-sm" name="field_button_color">
                      <option value="blue" {{ "selected" if p.button_color == "blue" }}>Azul</option>
                      <option value="green" {{ "selected" if p.button_color == "green" }}>Verde</option>
                      <option value="red" {{ "selected" if p.button_color == "red" }}>Rojo</option>
                      <option value="grey" {{ "selected" if p.button_color == "grey" }}>Gris</option>
                    </select>
                  </div>
                  <div class="col-lg-2 col-md-2 col-4 mb-2">
                    <label class="form-label text-xs mb-1">Max Claims</label>
                    <input type="number" class="form-control form-control-sm" name="field_max_claims" value="{{ p.max_claims }}" min="0" max="100">
                  </div>
                  <div class="col-lg-2 col-4 mb-2">
                    <div class="form-check form-switch mt-4">
                      <input class="form-check-input" type="checkbox" name="field_close_reason" {% if p.close_reason %}checked{% endif %}>
                      <label class="form-check-label text-xs">Razón cierre</label>
                    </div>
                  </div>
                  <div class="col-lg-1 col-4 mb-2">
                    <div class="form-check form-switch mt-4">
                      <input class="form-check-input" type="checkbox" name="field_threads" {% if p.threads %}checked{% endif %}>
                      <label class="form-check-label text-xs">Threads</label>
                    </div>
                  </div>
                  <div class="col-lg-2 col-12 mb-2">
                    <button type="submit" class="btn btn-xs bg-gradient-info mb-0 w-100 mt-2">
                      <i class="fa fa-save me-1"></i> Guardar
                    </button>
                  </div>
                </form>
              </td>
            </tr>
            {% endif %}
            {% endfor %}
          </tbody>
        </table>
      </div>
      {% elif not guild.editable %}
      <p class="text-sm opacity-6 mt-3">No hay paneles configurados.</p>
      {% endif %}

      {# ═══ CREATE NEW PANEL ═══ #}
      {% if guild.editable %}
      <div class="mt-4">
        <a href="javascript:void(0)" onclick="toggleCreate('{{ guild.id }}')" class="btn btn-sm bg-gradient-primary mb-0">
          <i class="fa fa-plus me-1"></i> Crear Nuevo Panel
        </a>
      </div>
      <div id="create_{{ guild.id }}" style="display:none" class="mt-3 p-3" style="border-radius:0.5rem;background:rgba(94,114,228,0.04)">
        <h6 class="text-uppercase text-xs font-weight-bolder opacity-6 mb-3">
          <i class="fa fa-plus-circle me-1"></i> Nuevo Panel
        </h6>
        <form method="POST">
          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
          <input type="hidden" name="action" value="create_panel">
          <input type="hidden" name="guild_id" value="{{ guild.id }}">
          <div class="row">
            <div class="col-lg-3 col-md-4 col-6 mb-3">
              <label class="form-label text-xs mb-1">Nombre del panel <span class="text-danger">*</span></label>
              <input type="text" class="form-control form-control-sm" name="panel_name" placeholder="ej: soporte" required maxlength="40" pattern="[a-zA-Z0-9_ ]+">
              <small class="text-muted text-xxs">Solo letras, números y guiones bajos</small>
            </div>
            <div class="col-lg-3 col-md-4 col-6 mb-3">
              <label class="form-label text-xs mb-1">Texto del botón</label>
              <input type="text" class="form-control form-control-sm" name="field_button_text" value="Abrir Ticket" maxlength="80">
            </div>
            <div class="col-lg-2 col-md-4 col-6 mb-3">
              <label class="form-label text-xs mb-1">Color</label>
              <select class="form-select form-select-sm" name="field_button_color">
                <option value="blue" selected>Azul</option>
                <option value="green">Verde</option>
                <option value="red">Rojo</option>
                <option value="grey">Gris</option>
              </select>
            </div>
            <div class="col-lg-4 col-md-6 col-6 mb-3">
              <label class="form-label text-xs mb-1">Categoría (donde abrir tickets)</label>
              <select class="form-select form-select-sm" name="field_category_id">
                <option value="0">— Sin asignar —</option>
                {% for cat in guild.categories %}
                <option value="{{ cat.id }}">{{ cat.name }}</option>
                {% endfor %}
              </select>
            </div>
            <div class="col-lg-3 col-md-4 col-6 mb-3">
              <label class="form-label text-xs mb-1">Canal de log</label>
              <select class="form-select form-select-sm" name="field_log_channel">
                <option value="0">— Ninguno —</option>
                {% for ch in guild.text_channels %}
                <option value="{{ ch.id }}">{{ ch.name }}</option>
                {% endfor %}
              </select>
            </div>
            <div class="col-lg-2 col-md-3 col-4 mb-3">
              <label class="form-label text-xs mb-1">Max Claims</label>
              <input type="number" class="form-control form-control-sm" name="field_max_claims" value="0" min="0" max="100">
              <small class="text-muted text-xxs">0 = ilimitado</small>
            </div>
            <div class="col-lg-2 col-4 mb-3">
              <div class="form-check form-switch mt-4">
                <input class="form-check-input" type="checkbox" name="field_threads">
                <label class="form-check-label text-xs">Usar threads</label>
              </div>
            </div>
            <div class="col-lg-2 col-4 mb-3">
              <div class="form-check form-switch mt-4">
                <input class="form-check-input" type="checkbox" name="field_close_reason" checked>
                <label class="form-check-label text-xs">Razón cierre</label>
              </div>
            </div>
          </div>
          <button type="submit" class="btn btn-sm bg-gradient-success mb-0">
            <i class="fa fa-plus me-1"></i> Crear Panel
          </button>
          <a href="javascript:void(0)" onclick="toggleCreate('{{ guild.id }}')" class="btn btn-sm btn-outline-secondary mb-0 ms-2">Cancelar</a>
        </form>
      </div>
      {% endif %}

    </div>
    {% endfor %}
  {% endif %}
</div>
<script>
function toggleEdit(g, i) {
  var r = document.getElementById('edit_' + g + '_' + i);
  if (r) r.style.display = r.style.display === 'none' ? 'table-row' : 'none';
}
function toggleCreate(g) {
  var r = document.getElementById('create_' + g);
  if (r) r.style.display = r.style.display === 'none' ? 'block' : 'none';
}
function confirmDelete(gid, pname) {
  if (confirm('¿Estás seguro de eliminar el panel "' + pname + '"? Esta acción no se puede deshacer.')) {
    var f = document.createElement('form');
    f.method = 'POST';
    f.innerHTML = '<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">' +
      '<input type="hidden" name="action" value="delete_panel">' +
      '<input type="hidden" name="guild_id" value="' + gid + '">' +
      '<input type="hidden" name="panel_name" value="' + pname + '">';
    document.body.appendChild(f);
    f.submit();
  }
}
</script>
"""

        result = {
            "status": 0,
            "web_content": {
                "source": source,
                "guilds": guilds_data,
            },
        }
        if notifications:
            result["notifications"] = notifications
        return result
