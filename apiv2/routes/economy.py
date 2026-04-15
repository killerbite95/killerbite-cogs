"""
Economy API routes — Red bank (built-in) + ExtendedEconomy cog.

Red bank endpoints work without any extra cog.
ExtendedEconomy endpoints return 503 if the cog is not loaded.
"""

import sys
import logging
from typing import TYPE_CHECKING

import discord
from aiohttp import web
from redbot.core import bank

from ..server import APP_BOT_KEY, json_error

if TYPE_CHECKING:
    from redbot.core.bot import Red

logger = logging.getLogger("red.killerbite95.apiv2.routes.economy")

PREFIX = "/api/v2"

# Valid log-channel event names for ExtendedEconomy
LOG_CHANNEL_FIELDS = {
    "default_log_channel",
    "set_balance",
    "transfer_credits",
    "bank_wipe",
    "prune",
    "set_global",
    "payday_claim",
    "auto_claim",
}


def register_routes(app: web.Application):
    """Register all economy routes."""
    # Red bank
    app.router.add_get(f"{PREFIX}/guilds/{{guild_id}}/economy/currency", handle_currency_get)
    app.router.add_patch(f"{PREFIX}/guilds/{{guild_id}}/economy/currency", handle_currency_patch)
    app.router.add_get(f"{PREFIX}/guilds/{{guild_id}}/economy/balance/{{user_id}}", handle_balance_get)
    app.router.add_patch(f"{PREFIX}/guilds/{{guild_id}}/economy/balance/{{user_id}}", handle_balance_patch)
    app.router.add_post(f"{PREFIX}/guilds/{{guild_id}}/economy/transfer", handle_transfer)
    app.router.add_get(f"{PREFIX}/guilds/{{guild_id}}/economy/leaderboard", handle_leaderboard)
    app.router.add_post(f"{PREFIX}/guilds/{{guild_id}}/economy/prune", handle_prune)
    # ExtendedEconomy
    app.router.add_get(f"{PREFIX}/guilds/{{guild_id}}/economy/costs", handle_costs_list)
    app.router.add_post(f"{PREFIX}/guilds/{{guild_id}}/economy/costs", handle_costs_create)
    app.router.add_patch(f"{PREFIX}/guilds/{{guild_id}}/economy/costs/{{command}}", handle_costs_update)
    app.router.add_delete(f"{PREFIX}/guilds/{{guild_id}}/economy/costs/{{command}}", handle_costs_delete)
    app.router.add_get(f"{PREFIX}/guilds/{{guild_id}}/economy/log-channels", handle_log_channels_get)
    app.router.add_patch(f"{PREFIX}/guilds/{{guild_id}}/economy/log-channels", handle_log_channels_patch)


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


def _get_ex_economy_cog(bot):
    """Return (cog, guild_settings_getter) or (None, error_response)."""
    cog = bot.get_cog("ExtendedEconomy")
    if cog is None:
        return None, json_error(503, "cog_unavailable", "ExtendedEconomy cog is not loaded")
    return cog, None


# ──────────────────────────── Red bank ────────────────────────────


async def handle_currency_get(request: web.Request) -> web.Response:
    """GET /economy/currency — Bank currency name and balance defaults."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild(bot, request.match_info["guild_id"])
    if err:
        return err

    is_global = await bank.is_global()
    currency_name = await bank.get_currency_name(guild)
    default_balance = await bank.get_default_balance(guild)
    max_balance = await bank.get_max_balance(guild)

    return web.json_response({
        "name": currency_name,
        "default_balance": default_balance,
        "max_balance": max_balance,
        "is_global": is_global,
    })


async def handle_currency_patch(request: web.Request) -> web.Response:
    """PATCH /economy/currency — Update currency name or balance defaults."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild(bot, request.match_info["guild_id"])
    if err:
        return err

    try:
        data = await request.json()
    except Exception:
        return json_error(400, "bad_request", "Invalid JSON body")

    updated = {}

    if "name" in data:
        name = str(data["name"]).strip()
        if not name or len(name) > 100:
            return json_error(400, "bad_request", "'name' must be 1–100 characters")
        await bank.set_currency_name(name, guild)
        updated["name"] = name

    if "default_balance" in data:
        try:
            val = int(data["default_balance"])
            if val < 0:
                raise ValueError
        except (ValueError, TypeError):
            return json_error(400, "bad_request", "'default_balance' must be a non-negative integer")
        await bank.set_default_balance(val, guild)
        updated["default_balance"] = val

    if "max_balance" in data:
        try:
            val = int(data["max_balance"])
            if val < 1:
                raise ValueError
        except (ValueError, TypeError):
            return json_error(400, "bad_request", "'max_balance' must be a positive integer")
        await bank.set_max_balance(val, guild)
        updated["max_balance"] = val

    if not updated:
        return json_error(400, "bad_request", "No valid fields to update (name, default_balance, max_balance)")

    return web.json_response({"updated": updated})


async def handle_balance_get(request: web.Request) -> web.Response:
    """GET /economy/balance/{user_id} — Get a member's bank balance."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild(bot, request.match_info["guild_id"])
    if err:
        return err

    try:
        user_id = int(request.match_info["user_id"])
    except ValueError:
        return json_error(400, "bad_request", "user_id must be an integer")

    member = guild.get_member(user_id)
    if member is None:
        # Bank can work with User objects too for global bank
        user = bot.get_user(user_id) or discord.Object(id=user_id)
    else:
        user = member

    try:
        balance = await bank.get_balance(user)
    except bank.AccountNotFound:
        return json_error(404, "not_found", f"No bank account found for user {user_id}")

    currency_name = await bank.get_currency_name(guild)

    return web.json_response({
        "user_id": str(user_id),
        "balance": balance,
        "currency": currency_name,
    })


async def handle_balance_patch(request: web.Request) -> web.Response:
    """PATCH /economy/balance/{user_id} — Set a member's balance."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild(bot, request.match_info["guild_id"])
    if err:
        return err

    try:
        user_id = int(request.match_info["user_id"])
    except ValueError:
        return json_error(400, "bad_request", "user_id must be an integer")

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

    member = guild.get_member(user_id)
    if member is None:
        return json_error(404, "not_found", f"Member {user_id} not found in guild")

    max_balance = await bank.get_max_balance(guild)
    if new_balance > max_balance:
        return json_error(400, "bad_request", f"Balance exceeds max allowed ({max_balance})")

    try:
        await bank.set_balance(member, new_balance)
    except bank.BalanceTooHigh as e:
        return json_error(400, "bad_request", str(e))

    currency_name = await bank.get_currency_name(guild)
    return web.json_response({
        "user_id": str(user_id),
        "balance": new_balance,
        "currency": currency_name,
    })


async def handle_transfer(request: web.Request) -> web.Response:
    """POST /economy/transfer — Transfer credits between two members."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild(bot, request.match_info["guild_id"])
    if err:
        return err

    try:
        data = await request.json()
    except Exception:
        return json_error(400, "bad_request", "Invalid JSON body")

    from_id = data.get("from_user_id")
    to_id = data.get("to_user_id")
    amount = data.get("amount")

    if not from_id or not to_id or amount is None:
        return json_error(400, "bad_request", "Required: from_user_id, to_user_id, amount")

    try:
        from_id = int(from_id)
        to_id = int(to_id)
        amount = int(amount)
        if amount <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return json_error(400, "bad_request", "user IDs and amount must be positive integers")

    from_member = guild.get_member(from_id)
    to_member = guild.get_member(to_id)

    if from_member is None:
        return json_error(404, "not_found", f"Member {from_id} not found in guild")
    if to_member is None:
        return json_error(404, "not_found", f"Member {to_id} not found in guild")

    try:
        await bank.transfer_credits(from_member, to_member, amount)
    except bank.AccountNotFound as e:
        return json_error(404, "not_found", str(e))
    except (bank.BalanceTooHigh, ValueError) as e:
        return json_error(400, "bad_request", str(e))

    from_bal = await bank.get_balance(from_member)
    to_bal = await bank.get_balance(to_member)
    currency_name = await bank.get_currency_name(guild)

    return web.json_response({
        "transferred": amount,
        "currency": currency_name,
        "from": {"user_id": str(from_id), "new_balance": from_bal},
        "to": {"user_id": str(to_id), "new_balance": to_bal},
    })


async def handle_leaderboard(request: web.Request) -> web.Response:
    """GET /economy/leaderboard — Top balances in the guild."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild(bot, request.match_info["guild_id"])
    if err:
        return err

    try:
        limit = min(int(request.rel_url.query.get("limit", 10)), 100)
        offset = int(request.rel_url.query.get("offset", 0))
    except ValueError:
        return json_error(400, "bad_request", "limit and offset must be integers")

    currency_name = await bank.get_currency_name(guild)

    # Collect balances for all guild members who have accounts
    entries = []
    for member in guild.members:
        if member.bot:
            continue
        try:
            bal = await bank.get_balance(member)
            entries.append({"user_id": str(member.id), "username": member.display_name, "balance": bal})
        except bank.AccountNotFound:
            continue

    # Sort descending by balance
    entries.sort(key=lambda x: x["balance"], reverse=True)

    total = len(entries)
    page = entries[offset:offset + limit]
    for i, entry in enumerate(page):
        entry["rank"] = offset + i + 1

    return web.json_response({
        "currency": currency_name,
        "total": total,
        "limit": limit,
        "offset": offset,
        "leaderboard": page,
    })


async def handle_prune(request: web.Request) -> web.Response:
    """POST /economy/prune — Remove bank accounts for users no longer in guild."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild(bot, request.match_info["guild_id"])
    if err:
        return err

    try:
        data = await request.json()
    except Exception:
        return json_error(400, "bad_request", "Invalid JSON body")

    if not data.get("confirm"):
        return json_error(400, "bad_request", "Send { \"confirm\": true } to confirm bank prune")

    pruned = await bank.bank_prune(bot, guild)
    return web.json_response({"pruned_accounts": pruned})


# ──────────────────────────── ExtendedEconomy ────────────────────────────


async def handle_costs_list(request: web.Request) -> web.Response:
    """GET /economy/costs — List all command costs (ExtendedEconomy)."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild(bot, request.match_info["guild_id"])
    if err:
        return err

    cog, err = _get_ex_economy_cog(bot)
    if err:
        return err

    guild_conf = cog.db.get_conf(guild)
    costs = []
    for cmd_name, cc in guild_conf.command_costs.items():
        costs.append({
            "command": cmd_name,
            "cost": cc.cost,
            "duration": cc.duration,
            "level": cc.level,
            "prompt": cc.prompt,
            "modifier": cc.modifier,
            "value": cc.value,
        })

    # Also include global costs (apply to all guilds)
    global_costs = []
    for cmd_name, cc in cog.db.command_costs.items():
        global_costs.append({
            "command": cmd_name,
            "cost": cc.cost,
            "duration": cc.duration,
            "level": cc.level,
            "prompt": cc.prompt,
            "modifier": cc.modifier,
            "value": cc.value,
        })

    return web.json_response({
        "guild_costs": costs,
        "global_costs": global_costs,
    })


async def handle_costs_create(request: web.Request) -> web.Response:
    """POST /economy/costs — Create or replace a command cost (ExtendedEconomy)."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild(bot, request.match_info["guild_id"])
    if err:
        return err

    cog, err = _get_ex_economy_cog(bot)
    if err:
        return err

    try:
        data = await request.json()
    except Exception:
        return json_error(400, "bad_request", "Invalid JSON body")

    cmd_name = data.get("command")
    if not cmd_name:
        return json_error(400, "bad_request", "Missing 'command'")

    valid_levels = {"admin", "mod", "all", "user", "global"}
    valid_prompts = {"text", "reaction", "button", "silent", "notify"}
    valid_modifiers = {"static", "percent", "exponential", "linear"}

    try:
        cost = int(data.get("cost", 0))
        duration = int(data.get("duration", 3600))
        level = data.get("level", "all")
        prompt = data.get("prompt", "silent")
        modifier = data.get("modifier", "static")
        value = float(data.get("value", 0.0))
    except (ValueError, TypeError):
        return json_error(400, "bad_request", "Invalid field types")

    if level not in valid_levels:
        return json_error(400, "bad_request", f"'level' must be one of: {', '.join(sorted(valid_levels))}")
    if prompt not in valid_prompts:
        return json_error(400, "bad_request", f"'prompt' must be one of: {', '.join(sorted(valid_prompts))}")
    if modifier not in valid_modifiers:
        return json_error(400, "bad_request", f"'modifier' must be one of: {', '.join(sorted(valid_modifiers))}")

    # Resolve the CommandCost class from the cog's module
    cog_pkg = type(cog).__module__.rsplit(".", 1)[0]
    models_mod = sys.modules.get(f"{cog_pkg}.common.models")
    if models_mod is None:
        return json_error(503, "cog_unavailable", "ExtendedEconomy models module not available")

    CommandCost = models_mod.CommandCost
    cc = CommandCost(cost=cost, duration=duration, level=level, prompt=prompt, modifier=modifier, value=value)

    guild_conf = cog.db.get_conf(guild)
    guild_conf.command_costs[cmd_name] = cc
    await cog.save()

    return web.json_response({
        "command": cmd_name,
        "cost": cc.cost,
        "duration": cc.duration,
        "level": cc.level,
        "prompt": cc.prompt,
        "modifier": cc.modifier,
        "value": cc.value,
    }, status=201)


async def handle_costs_update(request: web.Request) -> web.Response:
    """PATCH /economy/costs/{command} — Update fields of an existing command cost."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild(bot, request.match_info["guild_id"])
    if err:
        return err

    cog, err = _get_ex_economy_cog(bot)
    if err:
        return err

    cmd_name = request.match_info["command"]
    guild_conf = cog.db.get_conf(guild)

    if cmd_name not in guild_conf.command_costs:
        return json_error(404, "not_found", f"No cost configured for command '{cmd_name}'")

    try:
        data = await request.json()
    except Exception:
        return json_error(400, "bad_request", "Invalid JSON body")

    cc = guild_conf.command_costs[cmd_name]

    valid_levels = {"admin", "mod", "all", "user", "global"}
    valid_prompts = {"text", "reaction", "button", "silent", "notify"}
    valid_modifiers = {"static", "percent", "exponential", "linear"}

    if "cost" in data:
        cc.cost = int(data["cost"])
    if "duration" in data:
        cc.duration = int(data["duration"])
    if "level" in data:
        if data["level"] not in valid_levels:
            return json_error(400, "bad_request", f"'level' must be one of: {', '.join(sorted(valid_levels))}")
        cc.level = data["level"]
    if "prompt" in data:
        if data["prompt"] not in valid_prompts:
            return json_error(400, "bad_request", f"'prompt' must be one of: {', '.join(sorted(valid_prompts))}")
        cc.prompt = data["prompt"]
    if "modifier" in data:
        if data["modifier"] not in valid_modifiers:
            return json_error(400, "bad_request", f"'modifier' must be one of: {', '.join(sorted(valid_modifiers))}")
        cc.modifier = data["modifier"]
    if "value" in data:
        cc.value = float(data["value"])

    await cog.save()

    return web.json_response({
        "command": cmd_name,
        "cost": cc.cost,
        "duration": cc.duration,
        "level": cc.level,
        "prompt": cc.prompt,
        "modifier": cc.modifier,
        "value": cc.value,
    })


async def handle_costs_delete(request: web.Request) -> web.Response:
    """DELETE /economy/costs/{command} — Remove a command cost."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild(bot, request.match_info["guild_id"])
    if err:
        return err

    cog, err = _get_ex_economy_cog(bot)
    if err:
        return err

    cmd_name = request.match_info["command"]
    guild_conf = cog.db.get_conf(guild)

    if cmd_name not in guild_conf.command_costs:
        return json_error(404, "not_found", f"No cost configured for command '{cmd_name}'")

    del guild_conf.command_costs[cmd_name]
    await cog.save()

    return web.json_response({"deleted": cmd_name})


async def handle_log_channels_get(request: web.Request) -> web.Response:
    """GET /economy/log-channels — Get bank event log channel mapping."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild(bot, request.match_info["guild_id"])
    if err:
        return err

    cog, err = _get_ex_economy_cog(bot)
    if err:
        return err

    guild_conf = cog.db.get_conf(guild)
    logs = guild_conf.logs

    def ch_str(val: int) -> str | None:
        return str(val) if val else None

    return web.json_response({
        "default_log_channel": ch_str(logs.default_log_channel),
        "set_balance": ch_str(logs.set_balance),
        "transfer_credits": ch_str(logs.transfer_credits),
        "bank_wipe": ch_str(logs.bank_wipe),
        "prune": ch_str(logs.prune),
        "set_global": ch_str(logs.set_global),
        "payday_claim": ch_str(logs.payday_claim),
        "auto_claim": ch_str(logs.auto_claim),
    })


async def handle_log_channels_patch(request: web.Request) -> web.Response:
    """PATCH /economy/log-channels — Update bank event log channels."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild(bot, request.match_info["guild_id"])
    if err:
        return err

    cog, err = _get_ex_economy_cog(bot)
    if err:
        return err

    try:
        data = await request.json()
    except Exception:
        return json_error(400, "bad_request", "Invalid JSON body")

    invalid_keys = set(data.keys()) - LOG_CHANNEL_FIELDS
    if invalid_keys:
        return json_error(400, "bad_request", f"Unknown fields: {', '.join(sorted(invalid_keys))}. Valid: {', '.join(sorted(LOG_CHANNEL_FIELDS))}")

    guild_conf = cog.db.get_conf(guild)
    logs = guild_conf.logs
    updated = {}

    for field in LOG_CHANNEL_FIELDS:
        if field not in data:
            continue
        val = data[field]
        if val is None:
            setattr(logs, field, 0)
            updated[field] = None
        else:
            try:
                ch_id = int(val)
            except (ValueError, TypeError):
                return json_error(400, "bad_request", f"'{field}' must be a channel ID integer or null")
            channel = guild.get_channel(ch_id)
            if channel is None:
                return json_error(404, "not_found", f"Channel {ch_id} not found in guild")
            setattr(logs, field, ch_id)
            updated[field] = str(ch_id)

    await cog.save()
    return web.json_response({"updated": updated})
