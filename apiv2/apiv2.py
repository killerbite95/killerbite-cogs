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
from .server import create_app, APP_START_TIME_KEY
from .routes.core import register_routes as register_core_routes
from .routes.members import register_routes as register_member_routes
from .routes.moderation import register_routes as register_moderation_routes
from .routes.messaging import register_routes as register_messaging_routes
from .routes.tickets import register_routes as register_ticket_routes
from .routes.suggestions import register_routes as register_suggestion_routes
from .routes.servers import register_routes as register_server_routes

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
    __version__ = "1.0.0"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=7283910462, force_registration=True)
        self.config.register_global(
            host=DEFAULT_HOST,
            port=DEFAULT_PORT,
            api_keys={},
        )

        self.key_manager = KeyManager(self.config)
        self.rate_limiter = RateLimiter(max_requests=200, window_seconds=60)

        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

    async def cog_load(self):
        await self.key_manager.load_cache()
        await self._start_server()

    async def cog_unload(self):
        await self._stop_server()

    # ==================== SERVER LIFECYCLE ====================

    async def _start_server(self):
        """Build the aiohttp app and start listening."""
        host = await self.config.host()
        port = await self.config.port()

        self._app = create_app(self.bot, self.key_manager, self.rate_limiter)
        register_core_routes(self._app)
        register_member_routes(self._app)
        register_moderation_routes(self._app)
        register_messaging_routes(self._app)
        register_ticket_routes(self._app)
        register_suggestion_routes(self._app)
        register_server_routes(self._app)

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
            lines.append(f"{status} **{k['name']}** — created: {created} — last used: {last}")

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
