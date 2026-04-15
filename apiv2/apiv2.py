"""
APIv2 - REST API server for Red-DiscordBot.
Main cog: starts/stops the aiohttp server and provides management commands.

By Killerbite95
"""

import logging
from datetime import datetime, timezone

import discord
from aiohttp import web
from redbot.core import commands, Config, checks
from redbot.core.bot import Red

from .auth import KeyManager, RateLimiter
from .decorator import API_ROUTE_ATTR
from .server import create_app, APP_BOT_KEY, APP_START_TIME_KEY, json_error
from .webhooks import WebhookManager, SUPPORTED_EVENTS
from .routes.core import register_routes as register_core_routes
from .routes.members import register_routes as register_member_routes
from .routes.moderation import register_routes as register_moderation_routes
from .routes.messaging import register_routes as register_messaging_routes
from .routes.tickets import register_routes as register_ticket_routes
from .routes.suggestions import register_routes as register_suggestion_routes
from .routes.servers import register_routes as register_server_routes
from .routes.webhooks import register_routes as register_webhook_routes
from .routes.docs import register_routes as register_docs_routes
from .routes.economy import register_routes as register_economy_routes
from .routes.warnings_modlog import register_routes as register_warnings_modlog_routes
from .routes.community import register_routes as register_community_routes

logger = logging.getLogger("red.killerbite95.apiv2")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8742


class APIv2(commands.Cog):
    """
    REST API server embedded in the bot for external integrations.

    Exposes authenticated HTTP endpoints to control the bot from
    websites, scripts, and automations.
    """

    __author__ = "Killerbite95"
    __version__ = "2.0.0"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=7283910462, force_registration=True)
        self.config.register_global(
            host=DEFAULT_HOST,
            port=DEFAULT_PORT,
            api_keys={},
            webhooks={},
        )

        self.key_manager = KeyManager(self.config)
        self.rate_limiter = RateLimiter(default_max=200, window_seconds=60)
        self.webhook_manager = WebhookManager(self.config)

        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._external_routes: dict[str, list[dict]] = {}

    async def cog_load(self):
        await self.key_manager.load_cache()
        await self._load_key_rate_limits()
        await self.webhook_manager.initialize()
        self._scan_all_cogs()
        await self._start_server()

    async def cog_unload(self):
        await self._stop_server()
        await self.webhook_manager.close()

    async def _load_key_rate_limits(self):
        """Sync per-key rate limits from config to the RateLimiter."""
        keys = await self.key_manager.list_keys()
        for k in keys:
            if k.get("rate_limit") is not None:
                self.rate_limiter.set_key_limit(k["name"], k["rate_limit"])

    # ==================== SERVER LIFECYCLE ====================

    async def _start_server(self):
        """Build the aiohttp app and start listening."""
        host = await self.config.host()
        port = await self.config.port()

        self._app = create_app(self.bot, self.key_manager, self.rate_limiter, self.webhook_manager)
        register_core_routes(self._app)
        register_member_routes(self._app)
        register_moderation_routes(self._app)
        register_messaging_routes(self._app)
        register_ticket_routes(self._app)
        register_suggestion_routes(self._app)
        register_server_routes(self._app)
        register_webhook_routes(self._app)
        register_economy_routes(self._app)
        register_warnings_modlog_routes(self._app)
        register_community_routes(self._app)

        # Register external cog routes (@api_route)
        for cog_name, routes in self._external_routes.items():
            for route_info in routes:
                handler = self._make_external_handler(cog_name, route_info["method_name"])
                handler.__doc__ = route_info["meta"].get("summary") or ""
                self._app.router.add_route(
                    route_info["http_method"],
                    route_info["path"],
                    handler,
                )

        # Docs routes last so they can see all registered routes
        register_docs_routes(self._app)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        try:
            self._site = web.TCPSite(self._runner, host, port)
            await self._site.start()
            logger.info(f"APIv2 server started on {host}:{port}")
        except OSError as e:
            logger.error(f"Failed to start APIv2 server on {host}:{port}: {e}")
            await self._runner.cleanup()
            self._runner = None
            self._app = None
            self._site = None

    async def _stop_server(self):
        """Gracefully stop the server."""
        if self._runner:
            await self._runner.cleanup()
            logger.info("APIv2 server stopped")
        self._runner = None
        self._app = None
        self._site = None

    def _is_running(self) -> bool:
        return self._site is not None

    # ==================== EXTERNAL ROUTE DISCOVERY ====================

    def _scan_cog_routes(self, cog: commands.Cog) -> list[dict]:
        """Scan a cog for @api_route decorated methods."""
        routes = []
        cog_name = type(cog).__name__
        for attr_name in dir(cog):
            try:
                method = getattr(cog, attr_name)
            except Exception:
                continue
            meta_list = getattr(method, API_ROUTE_ATTR, None)
            if not isinstance(meta_list, list) or not meta_list:
                continue
            for meta in meta_list:
                routes.append({
                    "cog_name": cog_name,
                    "method_name": attr_name,
                    "http_method": meta["method"],
                    "path": meta["path"],
                    "meta": meta,
                })
        return routes

    def _scan_all_cogs(self):
        """Scan all loaded cogs for @api_route decorated methods."""
        self._external_routes.clear()
        for cog_name, cog in self.bot.cogs.items():
            if cog is self:
                continue
            routes = self._scan_cog_routes(cog)
            if routes:
                self._external_routes[cog_name] = routes
                logger.info(f"Discovered {len(routes)} API route(s) in {cog_name}")

    def _make_external_handler(self, cog_name: str, method_name: str):
        """Create a handler that dispatches to a cog method at request time."""
        async def handler(request: web.Request) -> web.Response:
            bot = request.app[APP_BOT_KEY]
            cog = bot.get_cog(cog_name)
            if cog is None:
                return json_error(503, "cog_unavailable", f"Cog {cog_name} is not loaded")
            func = getattr(cog, method_name, None)
            if func is None:
                return json_error(503, "cog_unavailable", f"Handler not available on {cog_name}")
            return await func(request)

        return handler

    # ==================== COG LISTENERS ====================

    @commands.Cog.listener()
    async def on_cog_add(self, cog: commands.Cog):
        """Detect external cogs with @api_route and restart server if needed."""
        if cog is self:
            return
        routes = self._scan_cog_routes(cog)
        if routes:
            cog_name = type(cog).__name__
            self._external_routes[cog_name] = routes
            logger.info(f"Cog {cog_name} has {len(routes)} API routes, restarting server...")
            await self._stop_server()
            await self._start_server()

    @commands.Cog.listener()
    async def on_cog_remove(self, cog: commands.Cog):
        """Remove routes from unloaded cogs and restart server if needed."""
        if cog is self:
            return
        cog_name = type(cog).__name__
        if cog_name in self._external_routes:
            del self._external_routes[cog_name]
            logger.info(f"Cog {cog_name} unloaded, removing its API routes...")
            await self._stop_server()
            await self._start_server()

    # ==================== WEBHOOK EVENT LISTENERS ====================

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self.webhook_manager.dispatch("member_join", {
            "guild_id": str(member.guild.id),
            "guild_name": member.guild.name,
            "user": {
                "id": str(member.id),
                "username": member.name,
                "display_name": member.display_name,
                "avatar_url": str(member.display_avatar.url),
                "bot": member.bot,
            },
            "joined_at": member.joined_at.isoformat() if member.joined_at else None,
        }, guild_id=member.guild.id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await self.webhook_manager.dispatch("member_remove", {
            "guild_id": str(member.guild.id),
            "guild_name": member.guild.name,
            "user": {
                "id": str(member.id),
                "username": member.name,
                "display_name": member.display_name,
            },
        }, guild_id=member.guild.id)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        await self.webhook_manager.dispatch("member_ban", {
            "guild_id": str(guild.id),
            "guild_name": guild.name,
            "user": {
                "id": str(user.id),
                "username": user.name,
            },
        }, guild_id=guild.id)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        await self.webhook_manager.dispatch("member_unban", {
            "guild_id": str(guild.id),
            "guild_name": guild.name,
            "user": {
                "id": str(user.id),
                "username": user.name,
            },
        }, guild_id=guild.id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        await self.webhook_manager.dispatch("message", {
            "guild_id": str(message.guild.id),
            "channel_id": str(message.channel.id),
            "channel_name": getattr(message.channel, "name", str(message.channel.id)),
            "message_id": str(message.id),
            "author": {
                "id": str(message.author.id),
                "username": message.author.name,
                "display_name": message.author.display_name,
            },
            "content": message.content[:2000],
            "created_at": message.created_at.isoformat(),
        }, guild_id=message.guild.id)

    # ==================== COMMANDS ====================

    @commands.group(name="apiv2")
    @checks.is_owner()
    async def apiv2_group(self, ctx: commands.Context):
        """Manage the APIv2 REST server."""

    # ---- Status ----

    @apiv2_group.command(name="status")
    async def cmd_status(self, ctx: commands.Context):
        """Show the API server status."""
        host = await self.config.host()
        port = await self.config.port()

        if not self._is_running():
            embed = discord.Embed(
                title="APIv2 Status",
                description="🔴 **Server is stopped**",
                color=discord.Color.red(),
            )
            embed.add_field(name="Configured", value=f"`{host}:{port}`", inline=True)
            await ctx.send(embed=embed)
            return

        import time
        uptime_s = time.monotonic() - self._app[APP_START_TIME_KEY]
        hours, rem = divmod(int(uptime_s), 3600)
        mins, secs = divmod(rem, 60)

        keys = await self.key_manager.list_keys()
        active_keys = sum(1 for k in keys if k["active"])

        embed = discord.Embed(
            title="APIv2 Status",
            description="🟢 **Server is running**",
            color=discord.Color.green(),
        )
        embed.add_field(name="Listening", value=f"`{host}:{port}`", inline=True)
        embed.add_field(name="Uptime", value=f"{hours}h {mins}m {secs}s", inline=True)
        embed.add_field(name="API Keys", value=f"{active_keys} active", inline=True)
        await ctx.send(embed=embed)

    # ---- Restart ----

    @apiv2_group.command(name="restart")
    async def cmd_restart(self, ctx: commands.Context):
        """Restart the API server."""
        await self._stop_server()
        await self._start_server()
        if self._is_running():
            await ctx.send("✅ APIv2 server restarted.")
        else:
            await ctx.send("❌ Failed to restart. Check logs.")

    # ---- Key management ----

    @apiv2_group.group(name="key")
    async def key_group(self, ctx: commands.Context):
        """Manage API keys."""

    @key_group.command(name="create")
    async def cmd_key_create(self, ctx: commands.Context, name: str):
        """Create a new API key. The key will be sent via DM."""
        # Validate name: alphanumeric, dashes, underscores only
        if not all(c.isalnum() or c in "-_" for c in name) or not name:
            await ctx.send("❌ Key name must contain only letters, numbers, dashes or underscores.")
            return

        token = await self.key_manager.create_key(name)
        if token is None:
            await ctx.send(f"❌ A key named `{name}` already exists.")
            return

        # Send token via DM
        try:
            embed = discord.Embed(
                title="🔑 New API Key Created",
                description=(
                    f"**Name:** `{name}`\n"
                    f"**Token:** ||`{token}`||\n\n"
                    "Use in header: `Authorization: Bearer <token>`\n\n"
                    "⚠️ **Save this token now. You can view it again with** "
                    "`[p]apiv2 key show`**, but keep it secret.**"
                ),
                color=discord.Color.green(),
            )
            await ctx.author.send(embed=embed)
            await ctx.send(f"✅ Key `{name}` created. Check your DMs for the token.")
        except discord.Forbidden:
            # Can't DM — show in channel with spoiler
            await ctx.send(
                f"✅ Key `{name}` created.\n"
                f"Token: ||`{token}`||\n"
                "⚠️ **Delete this message after saving the token!**"
            )

    @key_group.command(name="revoke")
    async def cmd_key_revoke(self, ctx: commands.Context, name: str):
        """Revoke an API key (immediate effect)."""
        success = await self.key_manager.revoke_key(name)
        if success:
            await ctx.send(f"✅ Key `{name}` revoked. It can no longer be used.")
        else:
            await ctx.send(f"❌ Key `{name}` not found.")

    @key_group.command(name="list")
    async def cmd_key_list(self, ctx: commands.Context):
        """List all API keys."""
        keys = await self.key_manager.list_keys()
        if not keys:
            await ctx.send("No API keys configured. Create one with `[p]apiv2 key create <name>`.")
            return

        lines = []
        for k in keys:
            status = "🟢" if k["active"] else "🔴"
            created = k["created_at"][:10] if k["created_at"] else "?"
            last = k["last_used"][:16].replace("T", " ") if k.get("last_used") else "never"
            rl = f" — rate: {k['rate_limit']}/min" if k.get("rate_limit") else ""
            lines.append(f"{status} **{k['name']}** — created: {created} — last used: {last}{rl}")

        embed = discord.Embed(
            title="API Keys",
            description="\n".join(lines),
            color=discord.Color.blue(),
        )
        await ctx.send(embed=embed)

    @key_group.command(name="show")
    async def cmd_key_show(self, ctx: commands.Context, name: str):
        """Show the token for a key (sent via DM)."""
        token = await self.key_manager.get_key_token(name)
        if token is None:
            await ctx.send(f"❌ Key `{name}` not found.")
            return

        try:
            embed = discord.Embed(
                title=f"🔑 API Key: {name}",
                description=f"**Token:** ||`{token}`||",
                color=discord.Color.blue(),
            )
            await ctx.author.send(embed=embed)
            await ctx.send(f"✅ Token for `{name}` sent to your DMs.")
        except discord.Forbidden:
            await ctx.send("❌ I can't send you a DM. Please enable DMs from server members.")

    @key_group.command(name="ratelimit")
    async def cmd_key_ratelimit(self, ctx: commands.Context, name: str, limit: int = None):
        """Set a custom rate limit for a key (requests/min).

        Use 0 or omit to reset to the global default (200/min).
        """
        if limit is not None and limit <= 0:
            limit = None

        success = await self.key_manager.set_rate_limit(name, limit)
        if not success:
            await ctx.send(f"❌ Key `{name}` not found.")
            return

        self.rate_limiter.set_key_limit(name, limit)

        if limit is None:
            await ctx.send(f"✅ Key `{name}` rate limit reset to global default (200/min).")
        else:
            await ctx.send(f"✅ Key `{name}` rate limit set to **{limit}** requests/min.")

    # ---- Webhooks ----

    @apiv2_group.group(name="webhook")
    async def webhook_group(self, ctx: commands.Context):
        """Manage outgoing webhooks."""

    @webhook_group.command(name="create")
    async def cmd_webhook_create(self, ctx: commands.Context, name: str, url: str, *events: str):
        """Create an outgoing webhook.

        Events: member_join, member_remove, member_ban, member_unban, message
        """
        if not url.startswith(("https://", "http://")):
            await ctx.send("❌ URL must start with `http://` or `https://`.")
            return

        if not events:
            await ctx.send(
                "❌ Specify at least one event.\n"
                f"Supported: {', '.join(sorted(SUPPORTED_EVENTS))}"
            )
            return

        invalid = set(events) - SUPPORTED_EVENTS
        if invalid:
            await ctx.send(
                f"❌ Invalid events: {', '.join(sorted(invalid))}\n"
                f"Supported: {', '.join(sorted(SUPPORTED_EVENTS))}"
            )
            return

        secret = await self.webhook_manager.create(name, url, list(events))
        if secret is None:
            await ctx.send(f"❌ Webhook `{name}` already exists.")
            return

        try:
            embed = discord.Embed(
                title="🔗 Webhook Created",
                description=(
                    f"**Name:** `{name}`\n"
                    f"**URL:** `{url}`\n"
                    f"**Events:** {', '.join(events)}\n"
                    f"**Secret:** ||`{secret}`||\n\n"
                    "Use the secret to verify HMAC-SHA256 signatures.\n"
                    "Header: `X-APIv2-Signature: sha256=<hex>`"
                ),
                color=discord.Color.green(),
            )
            await ctx.author.send(embed=embed)
            await ctx.send(f"✅ Webhook `{name}` created. Signing secret sent to your DMs.")
        except discord.Forbidden:
            await ctx.send(
                f"✅ Webhook `{name}` created.\n"
                f"Secret: ||`{secret}`||\n"
                "⚠️ Save the secret and delete this message!"
            )

    @webhook_group.command(name="delete")
    async def cmd_webhook_delete(self, ctx: commands.Context, name: str):
        """Delete an outgoing webhook."""
        success = await self.webhook_manager.delete(name)
        if success:
            await ctx.send(f"✅ Webhook `{name}` deleted.")
        else:
            await ctx.send(f"❌ Webhook `{name}` not found.")

    @webhook_group.command(name="list")
    async def cmd_webhook_list(self, ctx: commands.Context):
        """List all outgoing webhooks."""
        webhooks = await self.webhook_manager.list_webhooks()
        if not webhooks:
            await ctx.send("No webhooks configured. Create one with `[p]apiv2 webhook create`.")
            return

        lines = []
        for wh in webhooks:
            status = "🟢" if wh["active"] else "🔴"
            evts = ", ".join(wh["events"])
            guild = f" (guild: {wh['guild_id']})" if wh.get("guild_id") else ""
            lines.append(f"{status} **{wh['name']}** → `{wh['url']}`\n   Events: {evts}{guild}")

        embed = discord.Embed(
            title="Outgoing Webhooks",
            description="\n".join(lines),
            color=discord.Color.blue(),
        )
        await ctx.send(embed=embed)

    @webhook_group.command(name="test")
    async def cmd_webhook_test(self, ctx: commands.Context, name: str):
        """Send a test ping to a webhook."""
        result = await self.webhook_manager.test(name)
        if result is None:
            await ctx.send(f"❌ Webhook `{name}` not found.")
        elif isinstance(result, int):
            if result < 400:
                await ctx.send(f"✅ Test ping to `{name}` — response: **{result}**")
            else:
                await ctx.send(f"⚠️ Test ping to `{name}` — error response: **{result}**")
        else:
            await ctx.send(f"❌ Test ping to `{name}` failed: {result}")

    # ---- Settings ----

    @apiv2_group.group(name="set")
    async def set_group(self, ctx: commands.Context):
        """Configure API server settings."""

    @set_group.command(name="port")
    async def cmd_set_port(self, ctx: commands.Context, port: int):
        """Change the API server port. Requires restart."""
        if not 1024 <= port <= 65535:
            await ctx.send("❌ Port must be between 1024 and 65535.")
            return
        await self.config.port.set(port)
        await ctx.send(f"✅ Port set to `{port}`. Run `[p]apiv2 restart` to apply.")

    @set_group.command(name="host")
    async def cmd_set_host(self, ctx: commands.Context, host: str):
        """Change the API server bind address. Requires restart."""
        await self.config.host.set(host)
        await ctx.send(f"✅ Host set to `{host}`. Run `[p]apiv2 restart` to apply.")
