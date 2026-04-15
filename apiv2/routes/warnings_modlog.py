"""
Phase 7 — Warnings (Red Mod) + Security cog + ExtendedModLog cog

Warnings endpoints: read/write the Mod cog's per-member warnings config.
Modlog cases: use redbot.core.modlog (built-in, no extra cog needed).
Security endpoints: use the Security cog's config and helper methods.
ExtendedModLog endpoints: read/write the ExtendedModLog cog's guild config.
"""

import sys
import uuid
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord
from aiohttp import web
from redbot.core import modlog

from ..server import APP_BOT_KEY, json_error

if TYPE_CHECKING:
    from redbot.core.bot import Red

logger = logging.getLogger("red.killerbite95.apiv2.routes.warnings_modlog")

PREFIX = "/api/v2"

# All valid ExtendedModLog event keys (from settings.py inv_settings)
MODLOG_EVENT_KEYS = frozenset({
    "message_edit", "message_delete", "user_change", "role_change",
    "role_create", "role_delete", "voice_change", "user_join", "user_left",
    "channel_change", "channel_create", "channel_delete", "thread_change",
    "thread_create", "thread_delete", "guild_change", "emoji_change",
    "stickers_change", "commands_used", "invite_created", "invite_deleted",
})

# Valid whitelist type values (from security/constants.py WHITELIST_TYPES)
VALID_WHITELIST_TYPES = frozenset({
    "auto_mod_spam", "auto_mod_advertising", "auto_mod_mentions",
    "auto_mod_everyone_here_mentions", "logging_message_log", "reports",
    "quarantine", "anti_nuke_filter_kick_ban", "anti_nuke_filter_role_creation",
    "anti_nuke_filter_role_deletion", "anti_nuke_filter_channel_creation",
    "anti_nuke_filter_channel_deletion", "anti_nuke_filter_webhook_creation",
    "anti_nuke_filter_webhook_deletion", "anti_nuke_filter_emoji_creation",
    "anti_nuke_filter_emoji_deletion", "protected_roles", "lockdown",
})


# ──────────────────────────── route registration ─────────────────────────────


def register_routes(app: web.Application):
    """Register all Phase 7 routes."""
    g = "{guild_id}"
    u = "{user_id}"
    # Red Mod — warnings per member
    app.router.add_get(f"{PREFIX}/guilds/{g}/warnings/{u}", handle_warnings_list)
    app.router.add_post(f"{PREFIX}/guilds/{g}/warnings/{u}", handle_warnings_add)
    app.router.add_delete(f"{PREFIX}/guilds/{g}/warnings/{u}/{{warning_id}}", handle_warning_delete)
    app.router.add_delete(f"{PREFIX}/guilds/{g}/warnings/{u}", handle_warnings_clear)
    # Red modlog cases
    app.router.add_get(f"{PREFIX}/guilds/{g}/cases", handle_cases_list)
    app.router.add_get(f"{PREFIX}/guilds/{g}/cases/{{case_number}}", handle_case_get)
    # Security cog
    app.router.add_get(f"{PREFIX}/guilds/{g}/security/settings", handle_security_settings_get)
    app.router.add_patch(f"{PREFIX}/guilds/{g}/security/settings", handle_security_settings_patch)
    app.router.add_get(f"{PREFIX}/guilds/{g}/security/modules", handle_security_modules_list)
    app.router.add_patch(f"{PREFIX}/guilds/{g}/security/modules/{{module}}", handle_security_module_patch)
    app.router.add_get(f"{PREFIX}/guilds/{g}/security/quarantined", handle_quarantined_list)
    app.router.add_post(f"{PREFIX}/guilds/{g}/security/quarantine/{u}", handle_quarantine_add)
    app.router.add_delete(f"{PREFIX}/guilds/{g}/security/quarantine/{u}", handle_quarantine_remove)
    app.router.add_get(f"{PREFIX}/guilds/{g}/security/whitelist/{{object_type}}/{{object_id}}", handle_whitelist_get)
    app.router.add_patch(f"{PREFIX}/guilds/{g}/security/whitelist/{{object_type}}/{{object_id}}", handle_whitelist_patch)
    # ExtendedModLog cog
    app.router.add_get(f"{PREFIX}/guilds/{g}/modlog/settings", handle_extmodlog_settings_get)
    app.router.add_patch(f"{PREFIX}/guilds/{g}/modlog/settings", handle_extmodlog_settings_patch)
    app.router.add_get(f"{PREFIX}/guilds/{g}/modlog/ignored-channels", handle_ignored_channels_get)
    app.router.add_post(f"{PREFIX}/guilds/{g}/modlog/ignored-channels", handle_ignored_channels_add)
    app.router.add_delete(f"{PREFIX}/guilds/{g}/modlog/ignored-channels/{{channel_id}}", handle_ignored_channels_remove)


# ──────────────────────────── shared helpers ─────────────────────────────────


def _get_guild(bot: "Red", guild_id_str: str):
    try:
        gid = int(guild_id_str)
    except ValueError:
        return None
    return bot.get_guild(gid)


def _case_to_dict(case) -> dict:
    """Serialize a Red modlog Case object to a plain dict."""
    def _uid(obj):
        return str(obj.id) if obj else None

    created_at = None
    if case.created_at:
        try:
            created_at = datetime.fromtimestamp(case.created_at, tz=timezone.utc).isoformat()
        except Exception:
            created_at = str(case.created_at)

    return {
        "case_number": case.case_number,
        "action_type": case.action_type,
        "user_id": _uid(case.user),
        "moderator_id": _uid(case.moderator),
        "reason": case.reason,
        "created_at": created_at,
        "amended_by": _uid(case.amended_by),
        "amended_reason": getattr(case, "amended_reason", None),
    }


# ──────────────────────────── Warnings (Red Mod) ─────────────────────────────


async def handle_warnings_list(request: web.Request) -> web.Response:
    """GET /guilds/{guild_id}/warnings/{user_id} — list member warnings."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    mod_cog = bot.get_cog("Mod")
    if mod_cog is None:
        return json_error("cog_unavailable", "Mod cog is not loaded", 503)

    try:
        user_id = int(request.match_info["user_id"])
    except ValueError:
        return json_error("bad_request", "Invalid user_id", 400)

    member = guild.get_member(user_id)
    if member is None:
        # Try fetching from cache-less user object for config access
        user = bot.get_user(user_id)
        if user is None:
            try:
                user = await bot.fetch_user(user_id)
            except discord.NotFound:
                return json_error("not_found", f"User {user_id} not found", 404)
        # Use member_from_ids to access config without needing guild membership
        raw_warnings = await mod_cog.config.member_from_ids(guild.id, user_id).warnings()
    else:
        raw_warnings = await mod_cog.config.member(member).warnings()

    warnings = [
        {
            "id": w.get("id", str(i)),
            "reason": w.get("description", ""),
            "moderator_id": str(w["mod"]) if w.get("mod") else None,
            "created_at": None,  # Red Mod does not store per-warning timestamps
            "weight": w.get("weight", 1),
        }
        for i, w in enumerate(raw_warnings)
    ]
    return web.json_response(warnings)


async def handle_warnings_add(request: web.Request) -> web.Response:
    """POST /guilds/{guild_id}/warnings/{user_id} — add a warning."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    mod_cog = bot.get_cog("Mod")
    if mod_cog is None:
        return json_error("cog_unavailable", "Mod cog is not loaded", 503)

    try:
        user_id = int(request.match_info["user_id"])
    except ValueError:
        return json_error("bad_request", "Invalid user_id", 400)

    try:
        body = await request.json()
    except Exception:
        return json_error("bad_request", "Invalid JSON body", 400)

    reason = body.get("reason", "")
    if not reason:
        return json_error("bad_request", "reason is required", 400)

    raw_mod_id = body.get("moderator_id")
    mod_id = int(raw_mod_id) if raw_mod_id else None
    weight = int(body.get("weight", 1))

    warning_id = str(uuid.uuid4())

    warning_entry = {
        "id": warning_id,
        "description": reason,
        "mod": mod_id,
        "weight": weight,
    }

    # Append to the member's warnings list
    async with mod_cog.config.member_from_ids(guild.id, user_id).warnings() as warnings:
        warnings.append(warning_entry)

    # Optionally create a modlog case (best-effort)
    try:
        member = guild.get_member(user_id)
        target = member
        if target is None:
            target = bot.get_user(user_id) or await bot.fetch_user(user_id)
        moderator = guild.get_member(mod_id) if mod_id else None
        await modlog.create_case(
            bot=bot,
            guild=guild,
            created_at=datetime.now(timezone.utc),
            action_type="warning",
            user=target,
            moderator=moderator,
            reason=reason,
        )
    except Exception as e:
        logger.debug(f"Could not create modlog case for warning: {e}")

    return web.json_response(
        {
            "id": warning_id,
            "reason": reason,
            "moderator_id": str(mod_id) if mod_id else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "weight": weight,
        },
        status=201,
    )


async def handle_warning_delete(request: web.Request) -> web.Response:
    """DELETE /guilds/{guild_id}/warnings/{user_id}/{warning_id} — remove one warning."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    mod_cog = bot.get_cog("Mod")
    if mod_cog is None:
        return json_error("cog_unavailable", "Mod cog is not loaded", 503)

    try:
        user_id = int(request.match_info["user_id"])
    except ValueError:
        return json_error("bad_request", "Invalid user_id", 400)

    warning_id = request.match_info["warning_id"]

    async with mod_cog.config.member_from_ids(guild.id, user_id).warnings() as warnings:
        original_len = len(warnings)
        # Try matching by "id" field first, then by numeric index
        filtered = [w for w in warnings if w.get("id") != warning_id]
        if len(filtered) == original_len:
            # Try matching by numeric index as string
            try:
                idx = int(warning_id)
                if 0 <= idx < original_len:
                    filtered = warnings[:idx] + warnings[idx + 1:]
                else:
                    return json_error("not_found", f"Warning '{warning_id}' not found", 404)
            except ValueError:
                return json_error("not_found", f"Warning '{warning_id}' not found", 404)
        warnings[:] = filtered

    return web.json_response({"deleted": warning_id})


async def handle_warnings_clear(request: web.Request) -> web.Response:
    """DELETE /guilds/{guild_id}/warnings/{user_id} — clear all warnings."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    mod_cog = bot.get_cog("Mod")
    if mod_cog is None:
        return json_error("cog_unavailable", "Mod cog is not loaded", 503)

    try:
        body = await request.json()
    except Exception:
        body = {}
    if not body.get("confirm"):
        return json_error("bad_request", "Set confirm: true to clear all warnings", 400)

    try:
        user_id = int(request.match_info["user_id"])
    except ValueError:
        return json_error("bad_request", "Invalid user_id", 400)

    await mod_cog.config.member_from_ids(guild.id, user_id).warnings.set([])
    return web.json_response({"cleared": True})


# ──────────────────────────── Modlog Cases ───────────────────────────────────


async def handle_cases_list(request: web.Request) -> web.Response:
    """GET /guilds/{guild_id}/cases?type=ban&limit=20&offset=0 — list modlog cases."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    action_type = request.rel_url.query.get("type")
    try:
        limit = max(1, min(100, int(request.rel_url.query.get("limit", 20))))
        offset = max(0, int(request.rel_url.query.get("offset", 0)))
    except ValueError:
        return json_error("bad_request", "Invalid limit or offset", 400)

    try:
        all_cases = await modlog.get_all_cases(guild, bot)
    except Exception as e:
        logger.error(f"Failed to get modlog cases: {e}")
        return json_error("internal_error", "Failed to retrieve cases", 500)

    if action_type:
        all_cases = [c for c in all_cases if c.action_type == action_type]

    # Sort by case_number descending (newest first)
    all_cases.sort(key=lambda c: c.case_number, reverse=True)

    total = len(all_cases)
    page = all_cases[offset: offset + limit]

    return web.json_response({
        "total": total,
        "limit": limit,
        "offset": offset,
        "cases": [_case_to_dict(c) for c in page],
    })


async def handle_case_get(request: web.Request) -> web.Response:
    """GET /guilds/{guild_id}/cases/{case_number} — get a single modlog case."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    try:
        case_number = int(request.match_info["case_number"])
    except ValueError:
        return json_error("bad_request", "case_number must be an integer", 400)

    try:
        case = await modlog.get_case(case_number, guild, bot)
    except Exception:
        return json_error("not_found", f"Case #{case_number} not found", 404)

    return web.json_response(_case_to_dict(case))


# ──────────────────────────── Security cog ───────────────────────────────────


def _get_security_cog(bot: "Red"):
    return bot.get_cog("Security")


async def handle_security_settings_get(request: web.Request) -> web.Response:
    """GET /guilds/{guild_id}/security/settings"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = _get_security_cog(bot)
    if cog is None:
        return json_error("cog_unavailable", "Security cog is not loaded", 503)

    gc = await cog.config.guild(guild).all()
    return web.json_response({
        "quarantine_role": str(gc["quarantine_role"]) if gc.get("quarantine_role") else None,
        "modlog_channel": str(gc["modlog_channel"]) if gc.get("modlog_channel") else None,
        "modlog_ping_role": str(gc["modlog_ping_role"]) if gc.get("modlog_ping_role") else None,
    })


async def handle_security_settings_patch(request: web.Request) -> web.Response:
    """PATCH /guilds/{guild_id}/security/settings"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = _get_security_cog(bot)
    if cog is None:
        return json_error("cog_unavailable", "Security cog is not loaded", 503)

    try:
        body = await request.json()
    except Exception:
        return json_error("bad_request", "Invalid JSON body", 400)

    allowed = {"quarantine_role", "modlog_channel", "modlog_ping_role"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        return json_error("bad_request", f"No valid fields. Allowed: {sorted(allowed)}", 400)

    for field, value in updates.items():
        if value is None:
            await cog.config.guild(guild).set_raw(field, value=None)
        else:
            try:
                int_val = int(value)
            except (ValueError, TypeError):
                return json_error("bad_request", f"'{field}' must be a snowflake ID or null", 400)
            await cog.config.guild(guild).set_raw(field, value=int_val)

    gc = await cog.config.guild(guild).all()
    return web.json_response({
        "quarantine_role": str(gc["quarantine_role"]) if gc.get("quarantine_role") else None,
        "modlog_channel": str(gc["modlog_channel"]) if gc.get("modlog_channel") else None,
        "modlog_ping_role": str(gc["modlog_ping_role"]) if gc.get("modlog_ping_role") else None,
    })


async def handle_security_modules_list(request: web.Request) -> web.Response:
    """GET /guilds/{guild_id}/security/modules"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = _get_security_cog(bot)
    if cog is None:
        return json_error("cog_unavailable", "Security cog is not loaded", 503)

    # Import MODULES list from the security cog's package via sys.modules
    cog_pkg = type(cog).__module__.rsplit(".", 1)[0]
    modules_mod = sys.modules.get(f"{cog_pkg}.modules")
    MODULES = getattr(modules_mod, "MODULES", []) if modules_mod else []

    modules_conf = await cog.config.guild(guild).modules.all()

    result = []
    for module_cls in MODULES:
        key = module_cls.key_name()
        conf = modules_conf.get(key, module_cls.default_config.copy() if hasattr(module_cls, "default_config") else {})
        result.append({
            "key": key,
            "name": getattr(module_cls, "name", key),
            "emoji": getattr(module_cls, "emoji", ""),
            "description": getattr(module_cls, "description", ""),
            "enabled": conf.get("enabled", False),
            "config": conf,
        })
    return web.json_response(result)


async def handle_security_module_patch(request: web.Request) -> web.Response:
    """PATCH /guilds/{guild_id}/security/modules/{module}"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = _get_security_cog(bot)
    if cog is None:
        return json_error("cog_unavailable", "Security cog is not loaded", 503)

    module_key = request.match_info["module"]

    # Verify module exists
    cog_pkg = type(cog).__module__.rsplit(".", 1)[0]
    modules_mod = sys.modules.get(f"{cog_pkg}.modules")
    MODULES = getattr(modules_mod, "MODULES", []) if modules_mod else []
    valid_keys = {m.key_name() for m in MODULES}
    if module_key not in valid_keys:
        return json_error("not_found", f"Module '{module_key}' not found. Valid: {sorted(valid_keys)}", 404)

    try:
        body = await request.json()
    except Exception:
        return json_error("bad_request", "Invalid JSON body", 400)

    current = await cog.config.guild(guild).modules.get_raw(module_key, default={})
    if "enabled" in body:
        current["enabled"] = bool(body["enabled"])
    if "config" in body and isinstance(body["config"], dict):
        for k, v in body["config"].items():
            current[k] = v

    await cog.config.guild(guild).modules.set_raw(module_key, value=current)

    return web.json_response({"key": module_key, "config": current})


async def handle_quarantined_list(request: web.Request) -> web.Response:
    """GET /guilds/{guild_id}/security/quarantined — list quarantined members."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = _get_security_cog(bot)
    if cog is None:
        return json_error("cog_unavailable", "Security cog is not loaded", 503)

    all_member_conf = await cog.config.all_members(guild)
    result = []
    for member_id_int, conf in all_member_conf.items():
        if not conf.get("quarantined", False):
            continue
        result.append({
            "user_id": str(member_id_int),
            "roles_before_quarantine": [str(r) for r in conf.get("roles_before_quarantine", [])],
        })
    return web.json_response(result)


async def handle_quarantine_add(request: web.Request) -> web.Response:
    """POST /guilds/{guild_id}/security/quarantine/{user_id} — quarantine a member."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = _get_security_cog(bot)
    if cog is None:
        return json_error("cog_unavailable", "Security cog is not loaded", 503)

    try:
        user_id = int(request.match_info["user_id"])
    except ValueError:
        return json_error("bad_request", "Invalid user_id", 400)

    member = guild.get_member(user_id)
    if member is None:
        return json_error("not_found", f"Member {user_id} not found in guild", 404)

    try:
        body = await request.json()
    except Exception:
        body = {}

    reason = body.get("reason") or "Quarantined via API"

    try:
        await cog.quarantine_member(member=member, reason=reason)
    except RuntimeError as e:
        return json_error("bad_request", str(e), 400)
    except discord.HTTPException as e:
        return json_error("internal_error", f"Discord error: {e}", 500)

    return web.json_response({
        "quarantined": True,
        "user_id": str(user_id),
        "reason": reason,
    }, status=201)


async def handle_quarantine_remove(request: web.Request) -> web.Response:
    """DELETE /guilds/{guild_id}/security/quarantine/{user_id} — unquarantine a member."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = _get_security_cog(bot)
    if cog is None:
        return json_error("cog_unavailable", "Security cog is not loaded", 503)

    try:
        user_id = int(request.match_info["user_id"])
    except ValueError:
        return json_error("bad_request", "Invalid user_id", 400)

    member = guild.get_member(user_id)
    if member is None:
        return json_error("not_found", f"Member {user_id} not found in guild", 404)

    try:
        body = await request.json()
    except Exception:
        body = {}

    reason = body.get("reason") or "Unquarantined via API"

    try:
        await cog.unquarantine_member(member=member, reason=reason)
    except RuntimeError as e:
        return json_error("bad_request", str(e), 400)
    except discord.HTTPException as e:
        return json_error("internal_error", f"Discord error: {e}", 500)

    return web.json_response({
        "quarantined": False,
        "user_id": str(user_id),
    })


async def handle_whitelist_get(request: web.Request) -> web.Response:
    """GET /guilds/{guild_id}/security/whitelist/{object_type}/{object_id}

    object_type: member | role | channel
    """
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = _get_security_cog(bot)
    if cog is None:
        return json_error("cog_unavailable", "Security cog is not loaded", 503)

    object_type = request.match_info["object_type"]
    object_id_str = request.match_info["object_id"]

    if object_type not in ("member", "role", "channel"):
        return json_error("bad_request", "object_type must be member, role, or channel", 400)

    try:
        object_id = int(object_id_str)
    except ValueError:
        return json_error("bad_request", "Invalid object_id", 400)

    whitelist = await _get_whitelist(cog, guild, object_type, object_id)
    return web.json_response({"object_type": object_type, "object_id": object_id_str, "whitelist": whitelist})


async def handle_whitelist_patch(request: web.Request) -> web.Response:
    """PATCH /guilds/{guild_id}/security/whitelist/{object_type}/{object_id}"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = _get_security_cog(bot)
    if cog is None:
        return json_error("cog_unavailable", "Security cog is not loaded", 503)

    object_type = request.match_info["object_type"]
    object_id_str = request.match_info["object_id"]

    if object_type not in ("member", "role", "channel"):
        return json_error("bad_request", "object_type must be member, role, or channel", 400)

    try:
        object_id = int(object_id_str)
    except ValueError:
        return json_error("bad_request", "Invalid object_id", 400)

    try:
        body = await request.json()
    except Exception:
        return json_error("bad_request", "Invalid JSON body", 400)

    invalid_keys = [k for k in body if k not in VALID_WHITELIST_TYPES]
    if invalid_keys:
        return json_error(
            "bad_request",
            f"Unknown whitelist types: {invalid_keys}. Valid: {sorted(VALID_WHITELIST_TYPES)}",
            400,
        )
    if not body:
        return json_error("bad_request", "Body must contain at least one whitelist type", 400)

    # Read current, merge, write back
    current = await _get_whitelist(cog, guild, object_type, object_id)
    for k, v in body.items():
        current[k] = bool(v)

    await _set_whitelist(cog, guild, object_type, object_id, current)
    return web.json_response({"object_type": object_type, "object_id": object_id_str, "whitelist": current})


async def _get_whitelist(cog, guild: discord.Guild, object_type: str, object_id: int) -> dict:
    if object_type == "member":
        return await cog.config.member_from_ids(guild.id, object_id).whitelist()
    elif object_type == "role":
        role = guild.get_role(object_id)
        if role:
            return await cog.config.role(role).whitelist()
        return await cog.config.role_from_id(object_id).whitelist()
    else:  # channel
        channel = guild.get_channel(object_id)
        if channel:
            return await cog.config.channel(channel).whitelist()
        return await cog.config.channel_from_id(object_id).whitelist()


async def _set_whitelist(cog, guild: discord.Guild, object_type: str, object_id: int, value: dict):
    if object_type == "member":
        await cog.config.member_from_ids(guild.id, object_id).whitelist.set(value)
    elif object_type == "role":
        await cog.config.role_from_id(object_id).whitelist.set(value)
    else:  # channel
        await cog.config.channel_from_id(object_id).whitelist.set(value)


# ──────────────────────────── ExtendedModLog cog ─────────────────────────────


def _get_extmodlog_cog(bot: "Red"):
    return bot.get_cog("ExtendedModLog")


async def handle_extmodlog_settings_get(request: web.Request) -> web.Response:
    """GET /guilds/{guild_id}/modlog/settings — all 21 event configs."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = _get_extmodlog_cog(bot)
    if cog is None:
        return json_error("cog_unavailable", "ExtendedModLog cog is not loaded", 503)

    all_conf = await cog.config.guild(guild).all()
    result = {k: all_conf[k] for k in MODLOG_EVENT_KEYS if k in all_conf}
    return web.json_response(result)


async def handle_extmodlog_settings_patch(request: web.Request) -> web.Response:
    """PATCH /guilds/{guild_id}/modlog/settings — update one or more events."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = _get_extmodlog_cog(bot)
    if cog is None:
        return json_error("cog_unavailable", "ExtendedModLog cog is not loaded", 503)

    try:
        body = await request.json()
    except Exception:
        return json_error("bad_request", "Invalid JSON body", 400)

    invalid_keys = [k for k in body if k not in MODLOG_EVENT_KEYS]
    if invalid_keys:
        return json_error(
            "bad_request",
            f"Unknown event keys: {invalid_keys}. Valid: {sorted(MODLOG_EVENT_KEYS)}",
            400,
        )
    if not body:
        return json_error("bad_request", "Body must contain at least one event key", 400)

    updated = {}
    for event_key, event_cfg in body.items():
        if not isinstance(event_cfg, dict):
            return json_error("bad_request", f"Value for '{event_key}' must be an object", 400)
        current = await cog.config.guild(guild).get_raw(event_key, default={})
        current.update(event_cfg)
        await cog.config.guild(guild).set_raw(event_key, value=current)
        updated[event_key] = current

    # Invalidate in-memory settings cache if the cog maintains one
    if hasattr(cog, "settings") and isinstance(cog.settings, dict):
        cog.settings.pop(guild.id, None)

    return web.json_response(updated)


async def handle_ignored_channels_get(request: web.Request) -> web.Response:
    """GET /guilds/{guild_id}/modlog/ignored-channels"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = _get_extmodlog_cog(bot)
    if cog is None:
        return json_error("cog_unavailable", "ExtendedModLog cog is not loaded", 503)

    ignored = await cog.config.guild(guild).ignored_channels()
    return web.json_response([str(ch_id) for ch_id in ignored])


async def handle_ignored_channels_add(request: web.Request) -> web.Response:
    """POST /guilds/{guild_id}/modlog/ignored-channels — add a channel to ignore list."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = _get_extmodlog_cog(bot)
    if cog is None:
        return json_error("cog_unavailable", "ExtendedModLog cog is not loaded", 503)

    try:
        body = await request.json()
    except Exception:
        return json_error("bad_request", "Invalid JSON body", 400)

    ch_id_str = body.get("channel_id")
    if not ch_id_str:
        return json_error("bad_request", "channel_id is required", 400)

    try:
        ch_id = int(ch_id_str)
    except (ValueError, TypeError):
        return json_error("bad_request", "channel_id must be a snowflake ID", 400)

    async with cog.config.guild(guild).ignored_channels() as ignored:
        if ch_id not in ignored:
            ignored.append(ch_id)

    if hasattr(cog, "settings") and isinstance(cog.settings, dict):
        cog.settings.pop(guild.id, None)

    return web.json_response({"added": str(ch_id)}, status=201)


async def handle_ignored_channels_remove(request: web.Request) -> web.Response:
    """DELETE /guilds/{guild_id}/modlog/ignored-channels/{channel_id}"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = _get_extmodlog_cog(bot)
    if cog is None:
        return json_error("cog_unavailable", "ExtendedModLog cog is not loaded", 503)

    try:
        ch_id = int(request.match_info["channel_id"])
    except ValueError:
        return json_error("bad_request", "Invalid channel_id", 400)

    async with cog.config.guild(guild).ignored_channels() as ignored:
        if ch_id not in ignored:
            return json_error("not_found", f"Channel {ch_id} is not in the ignored list", 404)
        ignored.remove(ch_id)

    if hasattr(cog, "settings") and isinstance(cog.settings, dict):
        cog.settings.pop(guild.id, None)

    return web.json_response({"removed": str(ch_id)})
