"""
ColaCoins API routes — give, remove, query, and leaderboard.

Requires the ColaCoins cog to be loaded; returns 503 otherwise.
"""

import logging
from typing import TYPE_CHECKING

from aiohttp import web

from ..server import APP_BOT_KEY, json_error

if TYPE_CHECKING:
    from redbot.core.bot import Red

logger = logging.getLogger("red.killerbite95.apiv2.routes.colacoins")

PREFIX = "/api/v2"


def register_routes(app: web.Application):
    """Register all ColaCoins routes."""
    # Static paths first so they don't collide with {user_id}
    app.router.add_get(f"{PREFIX}/guilds/{{guild_id}}/colacoins/leaderboard", handle_leaderboard)
    app.router.add_get(f"{PREFIX}/guilds/{{guild_id}}/colacoins/settings", handle_settings_get)
    # Per-user
    app.router.add_get(f"{PREFIX}/guilds/{{guild_id}}/colacoins/{{user_id}}", handle_balance_get)
    app.router.add_patch(f"{PREFIX}/guilds/{{guild_id}}/colacoins/{{user_id}}", handle_balance_set)
    app.router.add_post(f"{PREFIX}/guilds/{{guild_id}}/colacoins/{{user_id}}/give", handle_give)
    app.router.add_post(f"{PREFIX}/guilds/{{guild_id}}/colacoins/{{user_id}}/remove", handle_remove)


# ──────────────────────────── helpers ────────────────────────────


def _get_guild(bot, guild_id_str: str):
    try:
        gid = int(guild_id_str)
    except ValueError:
        return None, json_error(400, "bad_request", "guild_id must be an integer")
    guild = bot.get_guild(gid)
    if guild is None:
        return None, json_error(404, "not_found", f"Guild {gid} not found")
    return guild, None


def _get_colacoins_cog(bot):
    cog = bot.get_cog("ColaCoins")
    if cog is None:
        return None, json_error(503, "cog_unavailable", "ColaCoins cog is not loaded")
    return cog, None


def _parse_user_id(raw: str):
    try:
        uid = int(raw)
        return uid, None
    except ValueError:
        return None, json_error(400, "bad_request", "user_id must be an integer")


# ──────────────────────────── handlers ────────────────────────────


async def handle_balance_get(request: web.Request) -> web.Response:
    """GET /colacoins/{user_id} — Get a user's ColaCoins balance."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild(bot, request.match_info["guild_id"])
    if err:
        return err
    cog, err = _get_colacoins_cog(bot)
    if err:
        return err
    user_id, err = _parse_user_id(request.match_info["user_id"])
    if err:
        return err

    member = guild.get_member(user_id)
    if member is None:
        return json_error(404, "not_found", f"Member {user_id} not found in guild")

    colacoins = await cog.config.colacoins()
    balance = colacoins.get(str(user_id), 0)
    emoji = await cog.config.emoji() or ""

    return web.json_response({
        "user_id": str(user_id),
        "username": member.display_name,
        "balance": balance,
        "emoji": emoji,
    })


async def handle_balance_set(request: web.Request) -> web.Response:
    """PATCH /colacoins/{user_id} — Set a user's ColaCoins balance directly."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild(bot, request.match_info["guild_id"])
    if err:
        return err
    cog, err = _get_colacoins_cog(bot)
    if err:
        return err
    user_id, err = _parse_user_id(request.match_info["user_id"])
    if err:
        return err

    member = guild.get_member(user_id)
    if member is None:
        return json_error(404, "not_found", f"Member {user_id} not found in guild")

    try:
        data = await request.json()
    except Exception:
        return json_error(400, "bad_request", "Invalid JSON body")

    if "balance" not in data:
        return json_error(400, "bad_request", "Missing 'balance' field")

    try:
        new_balance = int(data["balance"])
        if new_balance < 0:
            raise ValueError
    except (ValueError, TypeError):
        return json_error(400, "bad_request", "'balance' must be a non-negative integer")

    async with cog.config.colacoins() as colacoins:
        colacoins[str(user_id)] = new_balance

    await cog.save_data()

    emoji = await cog.config.emoji() or ""
    return web.json_response({
        "user_id": str(user_id),
        "username": member.display_name,
        "balance": new_balance,
        "emoji": emoji,
    })


async def handle_give(request: web.Request) -> web.Response:
    """POST /colacoins/{user_id}/give — Give ColaCoins to a user."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild(bot, request.match_info["guild_id"])
    if err:
        return err
    cog, err = _get_colacoins_cog(bot)
    if err:
        return err
    user_id, err = _parse_user_id(request.match_info["user_id"])
    if err:
        return err

    member = guild.get_member(user_id)
    if member is None:
        return json_error(404, "not_found", f"Member {user_id} not found in guild")

    try:
        data = await request.json()
    except Exception:
        return json_error(400, "bad_request", "Invalid JSON body")

    amount = data.get("amount")
    if amount is None:
        return json_error(400, "bad_request", "Missing 'amount' field")

    try:
        amount = int(amount)
        if amount <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return json_error(400, "bad_request", "'amount' must be a positive integer")

    async with cog.config.colacoins() as colacoins:
        current = colacoins.get(str(user_id), 0)
        colacoins[str(user_id)] = current + amount
        new_balance = colacoins[str(user_id)]

    await cog.save_data()

    emoji = await cog.config.emoji() or ""
    return web.json_response({
        "user_id": str(user_id),
        "username": member.display_name,
        "given": amount,
        "balance": new_balance,
        "emoji": emoji,
    })


async def handle_remove(request: web.Request) -> web.Response:
    """POST /colacoins/{user_id}/remove — Remove ColaCoins from a user."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild(bot, request.match_info["guild_id"])
    if err:
        return err
    cog, err = _get_colacoins_cog(bot)
    if err:
        return err
    user_id, err = _parse_user_id(request.match_info["user_id"])
    if err:
        return err

    member = guild.get_member(user_id)
    if member is None:
        return json_error(404, "not_found", f"Member {user_id} not found in guild")

    try:
        data = await request.json()
    except Exception:
        return json_error(400, "bad_request", "Invalid JSON body")

    amount = data.get("amount")
    if amount is None:
        return json_error(400, "bad_request", "Missing 'amount' field")

    try:
        amount = int(amount)
        if amount <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return json_error(400, "bad_request", "'amount' must be a positive integer")

    async with cog.config.colacoins() as colacoins:
        current = colacoins.get(str(user_id), 0)
        if current < amount:
            emoji = await cog.config.emoji() or ""
            return json_error(
                400,
                "insufficient_balance",
                f"User has {current} ColaCoins, cannot remove {amount}",
            )
        colacoins[str(user_id)] = current - amount
        new_balance = colacoins[str(user_id)]

    await cog.save_data()

    emoji = await cog.config.emoji() or ""
    return web.json_response({
        "user_id": str(user_id),
        "username": member.display_name,
        "removed": amount,
        "balance": new_balance,
        "emoji": emoji,
    })


async def handle_leaderboard(request: web.Request) -> web.Response:
    """GET /colacoins/leaderboard — Top ColaCoins holders in the guild."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild(bot, request.match_info["guild_id"])
    if err:
        return err
    cog, err = _get_colacoins_cog(bot)
    if err:
        return err

    try:
        limit = min(int(request.rel_url.query.get("limit", 10)), 100)
        offset = int(request.rel_url.query.get("offset", 0))
    except ValueError:
        return json_error(400, "bad_request", "limit and offset must be integers")

    colacoins = await cog.config.colacoins()
    emoji = await cog.config.emoji() or ""

    # Build entries only for members present in this guild with balance > 0
    entries = []
    for uid_str, amount in colacoins.items():
        if amount <= 0:
            continue
        try:
            member = guild.get_member(int(uid_str))
        except ValueError:
            continue
        if member is None:
            continue
        entries.append({
            "user_id": uid_str,
            "username": member.display_name,
            "balance": amount,
        })

    entries.sort(key=lambda x: x["balance"], reverse=True)

    total = len(entries)
    page = entries[offset:offset + limit]
    for i, entry in enumerate(page):
        entry["rank"] = offset + i + 1

    return web.json_response({
        "emoji": emoji,
        "total": total,
        "limit": limit,
        "offset": offset,
        "leaderboard": page,
    })


async def handle_settings_get(request: web.Request) -> web.Response:
    """GET /colacoins/settings — Current ColaCoins emoji/config."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild(bot, request.match_info["guild_id"])
    if err:
        return err
    cog, err = _get_colacoins_cog(bot)
    if err:
        return err

    emoji = await cog.config.emoji() or ""
    colacoins = await cog.config.colacoins()
    total_users = sum(1 for v in colacoins.values() if v > 0)
    total_coins = sum(v for v in colacoins.values() if v > 0)

    return web.json_response({
        "emoji": emoji,
        "total_users_with_coins": total_users,
        "total_coins_in_circulation": total_coins,
    })
