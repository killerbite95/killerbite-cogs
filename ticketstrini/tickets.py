import asyncio
import datetime
import logging
import typing as t
from time import perf_counter

import discord
from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n

from .abc import CompositeMetaClass
from .commands import TicketCommands
from .common.constants import DEFAULT_GUILD, SCHEMA_VERSION
from .common.functions import Functions
from .common.utils import (
    close_ticket,
    prune_invalid_tickets,
    ticket_owner_hastyped,
    update_active_overview,
    migrate_schema,
    log_audit_action,
    check_auto_close_warnings,
    should_auto_close,
    update_last_message,
    escalate_ticket,
)
from .common.views import CloseView, LogView, PanelView, StaffActionsView

# ----------------- Agregamos la integración del Dashboard -----------------
from .dashboard_integration import DashboardIntegration, dashboard_page

log = logging.getLogger("red.killerbite95.ticketstrini")
_ = Translator("TicketsTrini", __file__)

@cog_i18n(_)
class TicketsTrini(TicketCommands, Functions, DashboardIntegration, commands.Cog, metaclass=CompositeMetaClass):
    """
    Sistema de tickets de soporte multi-panel con botones (Trini Edition)
    """
    __author__ = "[Killerbite95](https://github.com/killerbite95/killerbite-cogs)"
    __version__ = "4.0.0"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        info = f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}\n"
        return info

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""
        return

    def __init__(self, bot: Red):
        self.bot: Red = bot
        self.config = Config.get_conf(self, 117117, force_registration=True)
        self.config.register_guild(**DEFAULT_GUILD)

        # Cache
        self.valid = []  # Valid ticket channels
        self.views = []  # Saved views to end on reload
        self.view_cache: t.Dict[int, t.List[discord.ui.View]] = {}  # Saved views to end on reload
        self.initializing = False
        
        # Track message timestamps for smart auto-close
        self.last_activity: t.Dict[str, datetime.datetime] = {}  # channel_id -> last message time

        self.auto_close.start()
        self.escalation_check.start()

    async def cog_load(self) -> None:
        asyncio.create_task(self._startup())

    async def cog_unload(self) -> None:
        self.auto_close.cancel()
        self.escalation_check.cancel()
        for view in self.views:
            view.stop()

    async def _startup(self) -> None:
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(6)
        await self.initialize()

    async def initialize(self, target_guild: discord.Guild | None = None) -> None:
        if target_guild:
            data = await self.config.guild(target_guild).all()
            return await self._init_guild(target_guild, data)

        t1 = perf_counter()
        conf = await self.config.all_guilds()
        for gid, data in conf.items():
            if not data:
                continue
            guild = self.bot.get_guild(gid)
            if not guild:
                continue
            try:
                await self._init_guild(guild, data)
            except Exception as e:
                log.error(f"Failed to initialize tickets for {guild.name}", exc_info=e)

        td = (perf_counter() - t1) * 1000
        log.info(f"Tickets initialized in {round(td, 1)}ms")

    async def _init_guild(self, guild: discord.Guild, data: dict) -> None:
        # Stop and clear guild views from cache
        views = self.view_cache.setdefault(guild.id, [])
        for view in views:
            view.stop()
        self.view_cache[guild.id].clear()

        # Schema migration check
        current_version = data.get("schema_version", 1)
        if current_version < SCHEMA_VERSION:
            log.info(f"Migrating schema for {guild.name} from v{current_version} to v{SCHEMA_VERSION}")
            data = await migrate_schema(guild, data, self.config)
            await self.config.guild(guild).schema_version.set(SCHEMA_VERSION)

        pruned = await prune_invalid_tickets(guild, data, self.config)
        if pruned:
            data = await self.config.guild(guild).all()

        # Refresh overview panel
        new_id = await update_active_overview(guild, data)
        if new_id:
            await self.config.guild(guild).overview_msg.set(new_id)

        # v1.14.0 Migration, new support role schema
        cleaned = []
        for i in data["support_roles"]:
            if isinstance(i, int):
                cleaned.append([i, False])
        if cleaned:
            await self.config.guild(guild).support_roles.set(cleaned)

        # Refresh buttons for all panels
        migrations = False
        all_panels = data["panels"]
        prefetched = []
        to_deploy = {}  # Message ID keys for multi-button support
        for panel_name, panel in all_panels.items():
            category_id = panel["category_id"]
            channel_id = panel["channel_id"]
            message_id = panel["message_id"]
            if any([not category_id, not channel_id, not message_id]):
                # Panel does not have all channels set
                continue

            category = guild.get_channel(category_id)
            channel_obj = guild.get_channel(channel_id)
            if isinstance(channel_obj, discord.ForumChannel) or isinstance(channel_obj, discord.CategoryChannel):
                log.error(f"Invalid channel type for panel {panel_name} in {guild.name}")
                continue
            if any([not category, not channel_obj]):
                if not category:
                    log.error(f"Invalid category for panel {panel_name} in {guild.name}")
                if not channel_obj:
                    log.error(f"Invalid channel for panel {panel_name} in {guild.name}")
                continue

            if message_id not in prefetched:
                try:
                    await channel_obj.fetch_message(message_id)
                    prefetched.append(message_id)
                except discord.NotFound:
                    continue
                except discord.Forbidden:
                    log.error(f"I can no longer see the {panel_name} panel's channel in {guild.name}")
                    continue

            # v1.3.10 schema update (Modals)
            if "modals" not in panel:
                panel["modals"] = {}
                migrations = True
            # Schema update (Sub support roles)
            if "roles" not in panel:
                panel["roles"] = []
                migrations = True
            # v1.14.0 Schema update (Mentionable support roles + alt channel)
            cleaned = []
            for i in panel["roles"]:
                if isinstance(i, int):
                    cleaned.append([i, False])
            if cleaned:
                panel["roles"] = cleaned
                migrations = True
            if "alt_channel" not in panel:
                panel["alt_channel"] = 0
                migrations = True
            # v1.15.0 schema update (Button priority and rows)
            if "row" not in panel or "priority" not in panel:
                panel["row"] = None
                panel["priority"] = 1
                migrations = True
            # v2.4.0 schema update (Disable panels)
            if "disabled" not in panel:
                panel["disabled"] = False
                migrations = True

            panel["name"] = panel_name
            key = f"{channel_id}-{message_id}"
            if key in to_deploy:
                to_deploy[key].append(panel)
            else:
                to_deploy[key] = [panel]

        if not to_deploy:
            return

        # Update config for any migrations
        if migrations:
            await self.config.guild(guild).panels.set(all_panels)

        try:
            for panels in to_deploy.values():
                sorted_panels = sorted(panels, key=lambda x: x["priority"])
                panelview = PanelView(self.bot, guild, self.config, sorted_panels)
                # Panels can change so we want to edit every time
                await panelview.start()
                self.view_cache[guild.id].append(panelview)
        except discord.NotFound:
            log.warning(f"Failed to refresh panels in {guild.name}")

        # Refresh view for logs of opened tickets (v1.8.18 update)
        for uid, opened_tickets in data["opened"].items():
            member = guild.get_member(int(uid))
            if not member:
                continue
            for ticket_channel_id, ticket_info in opened_tickets.items():
                ticket_channel = guild.get_channel_or_thread(int(ticket_channel_id))
                if not ticket_channel:
                    continue

                # v2.0.0 stores message id for close button to re-init views on reload
                if message_id := ticket_info.get("message_id"):
                    view = CloseView(self.bot, self.config, int(uid), ticket_channel)
                    self.bot.add_view(view, message_id=message_id)
                    self.view_cache[guild.id].append(view)

                if not ticket_info["logmsg"]:
                    continue

                panel_name = ticket_info["panel"]
                if panel_name not in all_panels:
                    continue
                panel = all_panels[panel_name]
                if not panel["log_channel"]:
                    continue
                log_channel = guild.get_channel(int(panel["log_channel"]))
                if not log_channel:
                    log.warning(f"Log channel no longer exits for {member.name}'s ticket in {guild.name}")
                    continue

                max_claims = ticket_info.get("max_claims", 0)
                logview = LogView(guild, ticket_channel, max_claims)
                self.bot.add_view(logview, message_id=ticket_info["logmsg"])
                self.view_cache[guild.id].append(logview)

    @tasks.loop(minutes=20)
    async def auto_close(self):
        """Smart auto-close that differentiates user vs staff inactivity"""
        actasks = []
        conf = await self.config.all_guilds()
        for gid, gconf in conf.items():
            if not gconf:
                continue
            guild = self.bot.get_guild(gid)
            if not guild:
                continue
            
            # Check both legacy inactive and new auto_close settings
            inactive = gconf.get("inactive", 0)
            auto_close_user_hours = gconf.get("auto_close_user_hours", 0)
            auto_close_staff_hours = gconf.get("auto_close_staff_hours", 0)
            auto_close_warning_hours = gconf.get("auto_close_warning_hours", 0)
            
            # Skip if no auto-close configured
            if not inactive and not auto_close_user_hours and not auto_close_staff_hours:
                continue
            
            opened = gconf.get("opened", {})
            if not opened:
                continue
            
            for uid, tickets in opened.items():
                member = guild.get_member(int(uid))
                if not member:
                    continue
                
                for channel_id, ticket in tickets.items():
                    channel = guild.get_channel_or_thread(int(channel_id))
                    if not channel:
                        continue
                    
                    # Legacy behavior: check has_response flag
                    has_response = ticket.get("has_response")
                    if has_response and channel_id not in self.valid:
                        self.valid.append(channel_id)
                        continue
                    if channel_id in self.valid:
                        continue
                    
                    now = datetime.datetime.now().astimezone()
                    
                    # Get status and timestamps for smart auto-close
                    status = ticket.get("status", "open")
                    last_user_msg = ticket.get("last_user_message")
                    last_staff_msg = ticket.get("last_staff_message")
                    close_warnings = ticket.get("close_warnings_sent", 0)
                    
                    # Smart auto-close based on who needs to respond
                    should_close = False
                    close_reason = None
                    time_since_user = None
                    time_since_staff = None
                    
                    if last_user_msg:
                        last_user_dt = datetime.datetime.fromisoformat(last_user_msg)
                        time_since_user = (now - last_user_dt).total_seconds() / 3600
                    
                    if last_staff_msg:
                        last_staff_dt = datetime.datetime.fromisoformat(last_staff_msg)
                        time_since_staff = (now - last_staff_dt).total_seconds() / 3600
                    
                    # Check if we should send warning or close
                    if status == "awaiting_user" and auto_close_user_hours > 0:
                        if time_since_staff and time_since_staff >= auto_close_user_hours:
                            should_close = True
                            close_reason = _("(Auto-Close) User did not respond for {} hours").format(
                                auto_close_user_hours
                            )
                        elif auto_close_warning_hours > 0 and time_since_staff:
                            warning_threshold = auto_close_user_hours - auto_close_warning_hours
                            if time_since_staff >= warning_threshold and close_warnings == 0:
                                # Send warning
                                warning = _(
                                    "⚠️ {mention}\nThis ticket will be **automatically closed** in "
                                    "approximately **{hours} hours** if you do not respond."
                                ).format(mention=member.mention, hours=auto_close_warning_hours)
                                try:
                                    await channel.send(warning)
                                    # Update warnings sent
                                    async with self.config.guild(guild).opened() as op:
                                        if uid in op and channel_id in op[uid]:
                                            op[uid][channel_id]["close_warnings_sent"] = 1
                                except discord.HTTPException:
                                    pass
                                continue
                    
                    elif status == "awaiting_staff" and auto_close_staff_hours > 0:
                        if time_since_user and time_since_user >= auto_close_staff_hours:
                            should_close = True
                            close_reason = _("(Auto-Close) No staff response for {} hours").format(
                                auto_close_staff_hours
                            )
                    
                    # Legacy behavior fallback
                    if not should_close and inactive > 0:
                        opened_on = datetime.datetime.fromisoformat(ticket["opened"])
                        hastyped = await ticket_owner_hastyped(channel, member)
                        if hastyped and channel_id not in self.valid:
                            self.valid.append(channel_id)
                            continue
                        td = (now - opened_on).total_seconds() / 3600
                        next_td = td + 0.33
                        
                        if td < inactive <= next_td:
                            warning = _(
                                "If you do not respond to this ticket "
                                "within the next 20 minutes it will be closed automatically."
                            )
                            await channel.send(f"{member.mention}\n{warning}")
                            continue
                        elif td < inactive:
                            continue
                        
                        should_close = True
                        time_word = "hours" if inactive != 1 else "hour"
                        close_reason = _("(Auto-Close) Opened ticket with no response for ") + f"{inactive} {time_word}"
                    
                    if should_close and close_reason:
                        try:
                            await close_ticket(
                                self.bot,
                                member,
                                guild,
                                channel,
                                gconf,
                                close_reason,
                                self.bot.user.name,
                                self.config,
                            )
                            log.info(f"Ticket opened by {member.name} has been auto-closed: {close_reason}")
                        except Exception as e:
                            log.error(f"Failed to auto-close ticket for {member} in {guild.name}\nException: {e}")

        if actasks:
            await asyncio.gather(*actasks)

    @auto_close.before_loop
    async def before_auto_close(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(300)

    @tasks.loop(minutes=15)
    async def escalation_check(self):
        """Check tickets that need escalation based on time without response"""
        conf = await self.config.all_guilds()
        for gid, gconf in conf.items():
            if not gconf:
                continue
            guild = self.bot.get_guild(gid)
            if not guild:
                continue
            
            escalation_minutes = gconf.get("escalation_minutes", 0)
            escalation_channel_id = gconf.get("escalation_channel", 0)
            escalation_role_id = gconf.get("escalation_role", 0)
            
            if not escalation_minutes or (not escalation_channel_id and not escalation_role_id):
                continue
            
            escalation_channel = guild.get_channel(escalation_channel_id) if escalation_channel_id else None
            escalation_role = guild.get_role(escalation_role_id) if escalation_role_id else None
            
            opened = gconf.get("opened", {})
            now = datetime.datetime.now().astimezone()
            
            for uid, tickets in opened.items():
                for channel_id, ticket in tickets.items():
                    # Skip already escalated tickets
                    if ticket.get("escalated"):
                        continue
                    
                    # Skip claimed tickets (they're being handled)
                    if ticket.get("claimed_by"):
                        continue
                    
                    status = ticket.get("status", "open")
                    if status != "open" and status != "awaiting_staff":
                        continue
                    
                    # Check time since last user message
                    last_user_msg = ticket.get("last_user_message")
                    if not last_user_msg:
                        # Use opened time
                        last_user_msg = ticket.get("opened")
                    
                    if not last_user_msg:
                        continue
                    
                    last_user_dt = datetime.datetime.fromisoformat(last_user_msg)
                    minutes_elapsed = (now - last_user_dt).total_seconds() / 60
                    
                    if minutes_elapsed >= escalation_minutes:
                        channel = guild.get_channel_or_thread(int(channel_id))
                        if not channel:
                            continue
                        
                        # Escalate the ticket
                        await escalate_ticket(
                            guild=guild,
                            channel=channel,
                            config=self.config,
                            conf=gconf,
                            escalation_channel=escalation_channel,
                            escalation_role=escalation_role,
                        )
                        log.info(f"Escalated ticket {channel_id} in {guild.name} after {minutes_elapsed:.0f} minutes")

    @escalation_check.before_loop
    async def before_escalation_check(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(600)  # Wait 10 minutes after startup

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Track messages in ticket channels for smart auto-close"""
        if message.author.bot:
            return
        if not message.guild:
            return
        
        # Check if this is a ticket channel
        conf = await self.config.guild(message.guild).all()
        opened = conf.get("opened", {})
        
        channel_id = str(message.channel.id)
        ticket_owner_id = None
        ticket_data = None
        
        for uid, tickets in opened.items():
            if channel_id in tickets:
                ticket_owner_id = uid
                ticket_data = tickets[channel_id]
                break
        
        if not ticket_owner_id or not ticket_data:
            return
        
        # Determine if message is from user or staff
        is_owner = str(message.author.id) == ticket_owner_id
        
        # Get support roles
        support_roles = [i[0] for i in conf.get("support_roles", [])]
        panel_name = ticket_data.get("panel")
        if panel_name and panel_name in conf.get("panels", {}):
            panel_roles = conf["panels"][panel_name].get("roles", [])
            support_roles.extend([i[0] for i in panel_roles])
        
        user_roles = [r.id for r in message.author.roles]
        is_staff = any(rid in support_roles for rid in user_roles)
        
        # Update last message timestamps
        await update_last_message(
            guild=message.guild,
            channel_id=channel_id,
            owner_id=ticket_owner_id,
            is_staff=is_staff,
            config=self.config,
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if not member:
            return
        guild = member.guild
        if not guild:
            return
        conf = await self.config.guild(guild).all()
        opened = conf["opened"]
        if str(member.id) not in opened:
            return
        tickets = opened[str(member.id)]
        if not tickets:
            return

        for cid in tickets:
            chan = guild.get_channel_or_thread(int(cid))
            if not chan:
                continue
            try:
                await close_ticket(
                    bot=self.bot,
                    member=member,
                    guild=guild,
                    channel=chan,
                    conf=conf,
                    reason=_("User left guild(Auto-Close)"),
                    closedby=self.bot.user.name,
                    config=self.config,
                )
            except Exception as e:
                log.error(f"Failed to auto-close ticket for {member} leaving {member.guild}\nException: {e}")

    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread):
        if not thread:
            return
        guild = thread.guild
        conf = await self.config.guild(guild).all()
        pruned = await prune_invalid_tickets(guild, conf, self.config)
        if pruned:
            log.info("Pruned old ticket threads")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        if not channel:
            return
        guild = channel.guild
        conf = await self.config.guild(guild).all()
        pruned = await prune_invalid_tickets(guild, conf, self.config)
        if pruned:
            log.info("Pruned old ticket channels")

    # -------------------- Dashboard Integration --------------------
    @dashboard_page(name="view_tickets", description="Ver tickets activos")
    async def rpc_view_tickets(self, guild_id: int, **kwargs) -> t.Dict[str, t.Any]:
        """
        Página del Dashboard para ver los tickets activos.
        Se espera que se pase 'guild_id' (int) en los kwargs.
        """
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {"status": 1, "error": "Guild no encontrada."}
        conf = await self.config.guild(guild).all()
        opened = conf.get("opened", {})
        html_content = """
        <!-- Bootstrap CSS -->
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css"
              integrity="sha384-ENjdO4Dr2bkBIFxQG+8exIg2knQW4PuAtf3y5PxC5bl80k4CL8nAeZp3rNZZ8VC3"
              crossorigin="anonymous">
        <div class="container mt-4">
          <h1 class="mb-4">Tickets Activos</h1>
          <table class="table table-bordered table-striped">
            <thead class="table-dark">
              <tr>
                <th scope="col">Usuario</th>
                <th scope="col">ID del Canal</th>
                <th scope="col">Panel</th>
                <th scope="col">Abierto</th>
              </tr>
            </thead>
            <tbody>
        """
        if not opened:
            html_content += "<tr><td colspan='4'>No hay tickets activos</td></tr>"
        else:
            for uid, tickets in opened.items():
                member = guild.get_member(int(uid))
                member_name = member.display_name if member else "Desconocido"
                for cid, ticket in tickets.items():
                    opened_at = ticket.get("opened", "N/A")
                    panel = ticket.get("panel", "N/A")
                    html_content += f"""
                      <tr>
                        <td>{member_name}</td>
                        <td>{cid}</td>
                        <td>{panel}</td>
                        <td>{opened_at}</td>
                      </tr>
                    """
        html_content += """
            </tbody>
          </table>
        </div>
        """
        return {"status": 0, "web_content": {"source": html_content}}

    @dashboard_page(name="close_ticket", description="Cerrar un ticket", methods=("GET", "POST"))
    async def rpc_close_ticket(self, guild_id: int, **kwargs) -> t.Dict[str, t.Any]:
        """
        Página del Dashboard para cerrar un ticket.
        Se espera que se pase 'guild_id' (int) en los kwargs.
        """
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {"status": 1, "error": "Guild no encontrada."}
        import wtforms
        class CloseTicketForm(kwargs["Form"]):
            channel_id = wtforms.IntegerField("ID del canal del ticket", validators=[wtforms.validators.InputRequired()])
            submit = wtforms.SubmitField("Cerrar Ticket")
        form = CloseTicketForm()
        if form.validate_on_submit():
            cid = form.channel_id.data
            channel = guild.get_channel(cid)
            if not channel:
                return {"status": 1, "error": "Canal no encontrado."}
            conf = await self.config.guild(guild).all()
            ticket_owner = None
            for uid, tickets in conf.get("opened", {}).items():
                if str(cid) in tickets:
                    ticket_owner = guild.get_member(int(uid))
                    break
            if not ticket_owner:
                return {"status": 1, "error": "Ticket no encontrado en la configuración."}
            await close_ticket(
                bot=self.bot,
                member=ticket_owner,
                guild=guild,
                channel=channel,
                conf=conf,
                reason="Cerrado desde el Dashboard",
                closedby="Dashboard",
                config=self.config,
            )
            return {"status": 0, "notifications": [{"message": "Ticket cerrado con éxito.", "category": "success"}], "redirect_url": kwargs["request_url"]}
        source = "{{ form|safe }}"
        return {"status": 0, "web_content": {"source": source, "form": form}}
