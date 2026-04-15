"""
Core API routes: /health, /info, /guilds
"""

import time
import logging
from typing import TYPE_CHECKING

from aiohttp import web

from ..server import APP_BOT_KEY, APP_START_TIME_KEY, json_error

if TYPE_CHECKING:
    from redbot.core.bot import Red

logger = logging.getLogger("red.killerbite95.apiv2.routes.core")

PREFIX = "/api/v2"


def register_routes(app: web.Application):
    """Register all core routes."""
    app.router.add_get(f"{PREFIX}/health", handle_health)
    app.router.add_get(f"{PREFIX}/info", handle_info)
    app.router.add_get(f"{PREFIX}/guilds", handle_guilds)
    app.router.add_get(f"{PREFIX}/guilds/{{guild_id}}", handle_guild_detail)


async def handle_health(request: web.Request) -> web.Response:
    """GET /api/v2/health — Public health check (no auth required)."""
    bot: "Red" = request.app[APP_BOT_KEY]
    start_time: float = request.app[APP_START_TIME_KEY]
    uptime = time.monotonic() - start_time

    latency_ms = round(bot.latency * 1000, 1) if bot.latency else None

    return web.json_response({
        "status": "ok",
        "bot": bot.user.name if bot.user else "unknown",
        "guilds": len(bot.guilds),
        "latency_ms": latency_ms,
        "uptime_s": round(uptime),
    })


async def handle_info(request: web.Request) -> web.Response:
    """GET /api/v2/info — Bot metadata and loaded cogs."""
    bot: "Red" = request.app[APP_BOT_KEY]

    cogs_loaded = sorted(bot.cogs.keys())

    return web.json_response({
        "bot_id": str(bot.user.id) if bot.user else None,
        "name": bot.user.name if bot.user else "unknown",
        "discriminator": bot.user.discriminator if bot.user else None,
        "avatar_url": str(bot.user.display_avatar.url) if bot.user else None,
        "red_version": None,  # Populated below
        "python_version": None,  # Populated below
        "cogs_loaded": cogs_loaded,
        "guild_count": len(bot.guilds),
    })


async def handle_guilds(request: web.Request) -> web.Response:
    """GET /api/v2/guilds — List all guilds the bot is in."""
    bot: "Red" = request.app[APP_BOT_KEY]

    guilds = []
    for guild in bot.guilds:
        guilds.append({
            "id": str(guild.id),
            "name": guild.name,
            "icon_url": str(guild.icon.url) if guild.icon else None,
            "member_count": guild.member_count,
            "owner_id": str(guild.owner_id),
        })

    return web.json_response(guilds)


async def handle_guild_detail(request: web.Request) -> web.Response:
    """GET /api/v2/guilds/{guild_id} — Detailed guild info."""
    bot: "Red" = request.app[APP_BOT_KEY]

    try:
        guild_id = int(request.match_info["guild_id"])
    except ValueError:
        return json_error(400, "bad_request", "guild_id must be an integer")

    guild = bot.get_guild(guild_id)
    if guild is None:
        return json_error(404, "not_found", f"Guild {guild_id} not found or bot is not a member")

    channels = []
    for ch in guild.channels:
        if hasattr(ch, "category_id"):
            channels.append({
                "id": str(ch.id),
                "name": ch.name,
                "type": str(ch.type),
                "category_id": str(ch.category_id) if ch.category_id else None,
                "position": ch.position,
            })

    roles = []
    for role in guild.roles:
        roles.append({
            "id": str(role.id),
            "name": role.name,
            "color": role.color.value,
            "position": role.position,
            "mentionable": role.mentionable,
            "managed": role.managed,
            "member_count": len(role.members),
        })

    return web.json_response({
        "id": str(guild.id),
        "name": guild.name,
        "icon_url": str(guild.icon.url) if guild.icon else None,
        "banner_url": str(guild.banner.url) if guild.banner else None,
        "member_count": guild.member_count,
        "owner_id": str(guild.owner_id),
        "created_at": guild.created_at.isoformat(),
        "channels": channels,
        "roles": roles,
    })
