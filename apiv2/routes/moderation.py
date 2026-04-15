"""
Moderation API routes — kick, ban, unban, timeout.
"""

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

import discord
from aiohttp import web

from ..server import APP_BOT_KEY, json_error

if TYPE_CHECKING:
    from redbot.core.bot import Red

logger = logging.getLogger("red.killerbite95.apiv2.routes.moderation")

PREFIX = "/api/v2"


def register_routes(app: web.Application):
    """Register all moderation routes."""
    app.router.add_post(
        f"{PREFIX}/guilds/{{guild_id}}/members/{{user_id}}/kick", handle_kick
    )
    app.router.add_post(
        f"{PREFIX}/guilds/{{guild_id}}/members/{{user_id}}/ban", handle_ban
    )
    app.router.add_delete(
        f"{PREFIX}/guilds/{{guild_id}}/bans/{{user_id}}", handle_unban
    )
    app.router.add_post(
        f"{PREFIX}/guilds/{{guild_id}}/members/{{user_id}}/timeout", handle_timeout_add
    )
    app.router.add_delete(
        f"{PREFIX}/guilds/{{guild_id}}/members/{{user_id}}/timeout", handle_timeout_remove
    )


# ==================== HELPERS ====================

def _get_guild_or_error(bot: "Red", guild_id_str: str):
    """Parse guild_id and return (guild, None) or (None, error_response)."""
    try:
        guild_id = int(guild_id_str)
    except ValueError:
        return None, json_error(400, "bad_request", "guild_id must be an integer")
    guild = bot.get_guild(guild_id)
    if guild is None:
        return None, json_error(404, "not_found", f"Guild {guild_id} not found")
    return guild, None


async def _read_body(request: web.Request) -> dict:
    """Read JSON body or return empty dict for bodyless requests."""
    try:
        return await request.json()
    except Exception:
        return {}


# ==================== MODERATION ====================

async def handle_kick(request: web.Request) -> web.Response:
    """POST /api/v2/guilds/{guild_id}/members/{user_id}/kick"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild_or_error(bot, request.match_info["guild_id"])
    if err:
        return err

    try:
        user_id = int(request.match_info["user_id"])
    except ValueError:
        return json_error(400, "bad_request", "user_id must be an integer")

    member = guild.get_member(user_id)
    if member is None:
        return json_error(404, "not_found", f"Member {user_id} not found in guild")

    body = await _read_body(request)
    reason = body.get("reason", "APIv2 kick")

    try:
        await guild.kick(member, reason=reason)
    except discord.Forbidden:
        return json_error(403, "forbidden", "Bot lacks permission to kick this member")
    except Exception as e:
        return json_error(500, "internal_error", f"Kick failed: {e}")

    return web.json_response({"ok": True, "action": "kicked", "user_id": str(user_id)})


async def handle_ban(request: web.Request) -> web.Response:
    """POST /api/v2/guilds/{guild_id}/members/{user_id}/ban"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild_or_error(bot, request.match_info["guild_id"])
    if err:
        return err

    try:
        user_id = int(request.match_info["user_id"])
    except ValueError:
        return json_error(400, "bad_request", "user_id must be an integer")

    body = await _read_body(request)
    reason = body.get("reason", "APIv2 ban")
    delete_days = body.get("delete_message_days", 0)

    if not isinstance(delete_days, int) or not (0 <= delete_days <= 7):
        return json_error(422, "validation_error", "delete_message_days must be 0-7")

    try:
        await guild.ban(
            discord.Object(id=user_id),
            reason=reason,
            delete_message_days=delete_days,
        )
    except discord.NotFound:
        return json_error(404, "not_found", f"User {user_id} not found")
    except discord.Forbidden:
        return json_error(403, "forbidden", "Bot lacks permission to ban this user")
    except Exception as e:
        return json_error(500, "internal_error", f"Ban failed: {e}")

    return web.json_response({"ok": True, "action": "banned", "user_id": str(user_id)})


async def handle_unban(request: web.Request) -> web.Response:
    """DELETE /api/v2/guilds/{guild_id}/bans/{user_id}"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild_or_error(bot, request.match_info["guild_id"])
    if err:
        return err

    try:
        user_id = int(request.match_info["user_id"])
    except ValueError:
        return json_error(400, "bad_request", "user_id must be an integer")

    try:
        await guild.unban(discord.Object(id=user_id), reason="APIv2 unban")
    except discord.NotFound:
        return json_error(404, "not_found", f"User {user_id} is not banned")
    except discord.Forbidden:
        return json_error(403, "forbidden", "Bot lacks permission to unban")
    except Exception as e:
        return json_error(500, "internal_error", f"Unban failed: {e}")

    return web.json_response({"ok": True, "action": "unbanned", "user_id": str(user_id)})


async def handle_timeout_add(request: web.Request) -> web.Response:
    """POST /api/v2/guilds/{guild_id}/members/{user_id}/timeout"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild_or_error(bot, request.match_info["guild_id"])
    if err:
        return err

    try:
        user_id = int(request.match_info["user_id"])
    except ValueError:
        return json_error(400, "bad_request", "user_id must be an integer")

    member = guild.get_member(user_id)
    if member is None:
        return json_error(404, "not_found", f"Member {user_id} not found in guild")

    body = await _read_body(request)
    duration_seconds = body.get("duration_seconds")
    reason = body.get("reason", "APIv2 timeout")

    if duration_seconds is None or not isinstance(duration_seconds, (int, float)):
        return json_error(422, "validation_error", "duration_seconds is required (integer)")

    # Discord max timeout is 28 days
    max_seconds = 28 * 24 * 3600
    if duration_seconds < 1 or duration_seconds > max_seconds:
        return json_error(422, "validation_error", f"duration_seconds must be 1-{max_seconds}")

    try:
        await member.timeout(timedelta(seconds=int(duration_seconds)), reason=reason)
    except discord.Forbidden:
        return json_error(403, "forbidden", "Bot lacks permission to timeout this member")
    except Exception as e:
        return json_error(500, "internal_error", f"Timeout failed: {e}")

    return web.json_response({
        "ok": True,
        "action": "timeout_applied",
        "user_id": str(user_id),
        "duration_seconds": int(duration_seconds),
    })


async def handle_timeout_remove(request: web.Request) -> web.Response:
    """DELETE /api/v2/guilds/{guild_id}/members/{user_id}/timeout"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild_or_error(bot, request.match_info["guild_id"])
    if err:
        return err

    try:
        user_id = int(request.match_info["user_id"])
    except ValueError:
        return json_error(400, "bad_request", "user_id must be an integer")

    member = guild.get_member(user_id)
    if member is None:
        return json_error(404, "not_found", f"Member {user_id} not found in guild")

    try:
        await member.timeout(None, reason="APIv2 timeout removed")
    except discord.Forbidden:
        return json_error(403, "forbidden", "Bot lacks permission to remove timeout")
    except Exception as e:
        return json_error(500, "internal_error", f"Remove timeout failed: {e}")

    return web.json_response({"ok": True, "action": "timeout_removed", "user_id": str(user_id)})
