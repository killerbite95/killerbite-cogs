"""
Members and roles API routes.
"""

import logging
from typing import TYPE_CHECKING

from aiohttp import web

from ..server import APP_BOT_KEY, json_error

if TYPE_CHECKING:
    from redbot.core.bot import Red

logger = logging.getLogger("red.killerbite95.apiv2.routes.members")

PREFIX = "/api/v2"


def register_routes(app: web.Application):
    """Register all member and role routes."""
    # Members
    app.router.add_get(f"{PREFIX}/guilds/{{guild_id}}/members", handle_members_list)
    app.router.add_get(f"{PREFIX}/guilds/{{guild_id}}/members/{{user_id}}", handle_member_detail)
    app.router.add_patch(f"{PREFIX}/guilds/{{guild_id}}/members/{{user_id}}", handle_member_patch)

    # Roles
    app.router.add_get(f"{PREFIX}/guilds/{{guild_id}}/roles", handle_roles_list)
    app.router.add_put(
        f"{PREFIX}/guilds/{{guild_id}}/members/{{user_id}}/roles/{{role_id}}",
        handle_role_add,
    )
    app.router.add_delete(
        f"{PREFIX}/guilds/{{guild_id}}/members/{{user_id}}/roles/{{role_id}}",
        handle_role_remove,
    )
    app.router.add_post(
        f"{PREFIX}/guilds/{{guild_id}}/members/{{user_id}}/roles",
        handle_roles_bulk,
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


def _serialize_member(member) -> dict:
    """Serialize a discord.Member to a JSON-safe dict."""
    return {
        "id": str(member.id),
        "username": member.name,
        "display_name": member.display_name,
        "avatar_url": str(member.display_avatar.url) if member.display_avatar else None,
        "roles": [
            {"id": str(r.id), "name": r.name, "color": r.color.value, "position": r.position}
            for r in member.roles
            if not r.is_default()
        ],
        "joined_at": member.joined_at.isoformat() if member.joined_at else None,
        "is_bot": member.bot,
        "nick": member.nick,
        "premium_since": member.premium_since.isoformat() if member.premium_since else None,
        "status": str(member.status),
    }


# ==================== MEMBERS ====================

async def handle_members_list(request: web.Request) -> web.Response:
    """GET /api/v2/guilds/{guild_id}/members?limit=100&after=0"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild_or_error(bot, request.match_info["guild_id"])
    if err:
        return err

    try:
        limit = min(int(request.query.get("limit", "100")), 1000)
        after = int(request.query.get("after", "0"))
    except ValueError:
        return json_error(400, "bad_request", "limit and after must be integers")

    members = sorted(guild.members, key=lambda m: m.id)
    if after > 0:
        members = [m for m in members if m.id > after]
    members = members[:limit]

    return web.json_response({
        "members": [_serialize_member(m) for m in members],
        "count": len(members),
        "total": guild.member_count,
    })


async def handle_member_detail(request: web.Request) -> web.Response:
    """GET /api/v2/guilds/{guild_id}/members/{user_id}"""
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

    return web.json_response(_serialize_member(member))


async def handle_member_patch(request: web.Request) -> web.Response:
    """PATCH /api/v2/guilds/{guild_id}/members/{user_id} — Change nickname."""
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
        body = await request.json()
    except Exception:
        return json_error(400, "bad_request", "Invalid JSON body")

    nickname = body.get("nickname")
    if nickname is not None and not isinstance(nickname, str):
        return json_error(422, "validation_error", "nickname must be a string or null")

    try:
        await member.edit(nick=nickname)
    except Exception as e:
        return json_error(403, "forbidden", f"Cannot change nickname: {e}")

    return web.json_response({"ok": True, "nickname": nickname})


# ==================== ROLES ====================

async def handle_roles_list(request: web.Request) -> web.Response:
    """GET /api/v2/guilds/{guild_id}/roles"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild_or_error(bot, request.match_info["guild_id"])
    if err:
        return err

    roles = []
    for role in guild.roles:
        roles.append({
            "id": str(role.id),
            "name": role.name,
            "color": role.color.value,
            "position": role.position,
            "mentionable": role.mentionable,
            "managed": role.managed,
            "is_default": role.is_default(),
            "member_count": len(role.members),
        })

    return web.json_response(roles)


async def handle_role_add(request: web.Request) -> web.Response:
    """PUT /api/v2/guilds/{guild_id}/members/{user_id}/roles/{role_id}"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild_or_error(bot, request.match_info["guild_id"])
    if err:
        return err

    try:
        user_id = int(request.match_info["user_id"])
        role_id = int(request.match_info["role_id"])
    except ValueError:
        return json_error(400, "bad_request", "user_id and role_id must be integers")

    member = guild.get_member(user_id)
    if member is None:
        return json_error(404, "not_found", f"Member {user_id} not found in guild")

    role = guild.get_role(role_id)
    if role is None:
        return json_error(404, "not_found", f"Role {role_id} not found in guild")

    if role in member.roles:
        return web.json_response({"ok": True, "action": "already_has_role"})

    try:
        await member.add_roles(role, reason="APIv2")
    except Exception as e:
        return json_error(403, "forbidden", f"Cannot add role: {e}")

    return web.json_response({"ok": True, "action": "role_added"})


async def handle_role_remove(request: web.Request) -> web.Response:
    """DELETE /api/v2/guilds/{guild_id}/members/{user_id}/roles/{role_id}"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild_or_error(bot, request.match_info["guild_id"])
    if err:
        return err

    try:
        user_id = int(request.match_info["user_id"])
        role_id = int(request.match_info["role_id"])
    except ValueError:
        return json_error(400, "bad_request", "user_id and role_id must be integers")

    member = guild.get_member(user_id)
    if member is None:
        return json_error(404, "not_found", f"Member {user_id} not found in guild")

    role = guild.get_role(role_id)
    if role is None:
        return json_error(404, "not_found", f"Role {role_id} not found in guild")

    if role not in member.roles:
        return web.json_response({"ok": True, "action": "does_not_have_role"})

    try:
        await member.remove_roles(role, reason="APIv2")
    except Exception as e:
        return json_error(403, "forbidden", f"Cannot remove role: {e}")

    return web.json_response({"ok": True, "action": "role_removed"})


async def handle_roles_bulk(request: web.Request) -> web.Response:
    """POST /api/v2/guilds/{guild_id}/members/{user_id}/roles — Bulk set roles."""
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
        body = await request.json()
    except Exception:
        return json_error(400, "bad_request", "Invalid JSON body")

    role_ids = body.get("role_ids")
    if not isinstance(role_ids, list):
        return json_error(422, "validation_error", "role_ids must be a list of role ID integers")

    roles_to_set = []
    for rid in role_ids:
        try:
            rid_int = int(rid)
        except (ValueError, TypeError):
            return json_error(422, "validation_error", f"Invalid role_id: {rid}")
        role = guild.get_role(rid_int)
        if role is None:
            return json_error(404, "not_found", f"Role {rid_int} not found in guild")
        if role.managed or role.is_default():
            continue  # Skip managed/default roles silently
        roles_to_set.append(role)

    # Keep managed and default roles the member already has
    keep_roles = [r for r in member.roles if r.managed or r.is_default()]
    final_roles = list(set(keep_roles + roles_to_set))

    try:
        await member.edit(roles=final_roles, reason="APIv2 bulk role set")
    except Exception as e:
        return json_error(403, "forbidden", f"Cannot set roles: {e}")

    return web.json_response({
        "ok": True,
        "roles_set": [str(r.id) for r in roles_to_set],
    })
