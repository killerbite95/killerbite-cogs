"""
Phase 9 — Utilities & Configuration
Covers: Welcome, Sticky, VoiceLogs, AutoNick, Mover
"""
from __future__ import annotations

import contextlib
import logging
from typing import Any, Dict

import discord
from aiohttp import web


log = logging.getLogger("red.killerbite95.apiv2.utilities")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _guild_or_404(request: web.Request) -> discord.Guild | None:
    bot = request.app["bot"]
    guild_id = int(request.match_info["guild_id"])
    return bot.get_guild(guild_id)


# ===========================================================================
# WELCOME
# ===========================================================================

VALID_EVENTS = {"join", "leave", "ban", "unban"}


async def get_welcome(request: web.Request) -> web.Response:
    guild = _guild_or_404(request)
    if guild is None:
        raise web.HTTPNotFound(reason="Guild not found")

    cog = request.app["bot"].get_cog("Welcome")
    if cog is None:
        raise web.HTTPServiceUnavailable(reason="Welcome cog not loaded")

    cfg = await cog.config.guild(guild).all()
    return web.json_response(cfg)


async def patch_welcome(request: web.Request) -> web.Response:
    guild = _guild_or_404(request)
    if guild is None:
        raise web.HTTPNotFound(reason="Guild not found")

    cog = request.app["bot"].get_cog("Welcome")
    if cog is None:
        raise web.HTTPServiceUnavailable(reason="Welcome cog not loaded")

    data: Dict[str, Any] = await request.json()
    allowed = {"enabled", "channel"}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        raise web.HTTPBadRequest(reason="No valid fields provided")

    guild_cfg = cog.config.guild(guild)
    for key, value in updates.items():
        await guild_cfg.get_attr(key).set(value)

    return web.json_response({"updated": list(updates.keys())})


async def get_welcome_messages(request: web.Request) -> web.Response:
    guild = _guild_or_404(request)
    if guild is None:
        raise web.HTTPNotFound(reason="Guild not found")

    event = request.match_info["event"]
    if event not in VALID_EVENTS:
        raise web.HTTPBadRequest(reason=f"event must be one of {sorted(VALID_EVENTS)}")

    cog = request.app["bot"].get_cog("Welcome")
    if cog is None:
        raise web.HTTPServiceUnavailable(reason="Welcome cog not loaded")

    messages = await cog.config.guild(guild).get_attr(event).messages()
    return web.json_response({"event": event, "messages": messages})


async def post_welcome_message(request: web.Request) -> web.Response:
    guild = _guild_or_404(request)
    if guild is None:
        raise web.HTTPNotFound(reason="Guild not found")

    event = request.match_info["event"]
    if event not in VALID_EVENTS:
        raise web.HTTPBadRequest(reason=f"event must be one of {sorted(VALID_EVENTS)}")

    cog = request.app["bot"].get_cog("Welcome")
    if cog is None:
        raise web.HTTPServiceUnavailable(reason="Welcome cog not loaded")

    data = await request.json()
    content = data.get("content", "").strip()
    if not content:
        raise web.HTTPBadRequest(reason="content is required")

    async with cog.config.guild(guild).get_attr(event).messages() as msgs:
        msgs.append(content)
        index = len(msgs) - 1

    return web.json_response({"event": event, "index": index, "content": content}, status=201)


async def delete_welcome_message(request: web.Request) -> web.Response:
    guild = _guild_or_404(request)
    if guild is None:
        raise web.HTTPNotFound(reason="Guild not found")

    event = request.match_info["event"]
    if event not in VALID_EVENTS:
        raise web.HTTPBadRequest(reason=f"event must be one of {sorted(VALID_EVENTS)}")

    try:
        index = int(request.match_info["index"])
    except ValueError:
        raise web.HTTPBadRequest(reason="index must be an integer")

    cog = request.app["bot"].get_cog("Welcome")
    if cog is None:
        raise web.HTTPServiceUnavailable(reason="Welcome cog not loaded")

    async with cog.config.guild(guild).get_attr(event).messages() as msgs:
        if index < 0 or index >= len(msgs):
            raise web.HTTPNotFound(reason="Index out of range")
        msgs.pop(index)

    return web.json_response({"deleted": True})


async def get_welcome_whisper(request: web.Request) -> web.Response:
    guild = _guild_or_404(request)
    if guild is None:
        raise web.HTTPNotFound(reason="Guild not found")

    cog = request.app["bot"].get_cog("Welcome")
    if cog is None:
        raise web.HTTPServiceUnavailable(reason="Welcome cog not loaded")

    whisper = await cog.config.guild(guild).join.whisper()
    return web.json_response(whisper)


async def patch_welcome_whisper(request: web.Request) -> web.Response:
    guild = _guild_or_404(request)
    if guild is None:
        raise web.HTTPNotFound(reason="Guild not found")

    cog = request.app["bot"].get_cog("Welcome")
    if cog is None:
        raise web.HTTPServiceUnavailable(reason="Welcome cog not loaded")

    data = await request.json()
    allowed = {"state", "message"}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        raise web.HTTPBadRequest(reason="No valid fields provided (state, message)")

    async with cog.config.guild(guild).join.whisper() as whisper:
        whisper.update(updates)

    return web.json_response({"updated": list(updates.keys())})


# ===========================================================================
# STICKY
# ===========================================================================

async def list_stickies(request: web.Request) -> web.Response:
    guild = _guild_or_404(request)
    if guild is None:
        raise web.HTTPNotFound(reason="Guild not found")

    cog = request.app["bot"].get_cog("Sticky")
    if cog is None:
        raise web.HTTPServiceUnavailable(reason="Sticky cog not loaded")

    all_channels = await cog.conf.all_channels()
    guild_channel_ids = {ch.id for ch in guild.channels}
    result = []
    for channel_id_str, data in all_channels.items():
        channel_id = int(channel_id_str)
        if channel_id not in guild_channel_ids:
            continue
        # Has a sticky if stickied is set OR advstickied has content/embed
        has_sticky = bool(
            data.get("stickied")
            or (data.get("advstickied") or {}).get("content")
            or (data.get("advstickied") or {}).get("embed")
        )
        if has_sticky:
            result.append({
                "channel_id": str(channel_id),
                "stickied": data.get("stickied"),
                "header_enabled": data.get("header_enabled", True),
                "last_message_id": str(data["last"]) if data.get("last") else None,
            })
    return web.json_response(result)


async def get_sticky(request: web.Request) -> web.Response:
    guild = _guild_or_404(request)
    if guild is None:
        raise web.HTTPNotFound(reason="Guild not found")

    cog = request.app["bot"].get_cog("Sticky")
    if cog is None:
        raise web.HTTPServiceUnavailable(reason="Sticky cog not loaded")

    channel_id = int(request.match_info["channel_id"])
    channel = guild.get_channel(channel_id)
    if channel is None:
        raise web.HTTPNotFound(reason="Channel not found")

    data = await cog.conf.channel(channel).all()
    if not (data.get("stickied") or (data.get("advstickied") or {}).get("content") or (data.get("advstickied") or {}).get("embed")):
        raise web.HTTPNotFound(reason="No sticky set for this channel")

    return web.json_response({
        "channel_id": str(channel_id),
        "content": data.get("stickied"),
        "header_enabled": data.get("header_enabled", True),
        "last_message_id": str(data["last"]) if data.get("last") else None,
    })


async def put_sticky(request: web.Request) -> web.Response:
    guild = _guild_or_404(request)
    if guild is None:
        raise web.HTTPNotFound(reason="Guild not found")

    cog = request.app["bot"].get_cog("Sticky")
    if cog is None:
        raise web.HTTPServiceUnavailable(reason="Sticky cog not loaded")

    channel_id = int(request.match_info["channel_id"])
    channel = guild.get_channel(channel_id)
    if channel is None:
        raise web.HTTPNotFound(reason="Channel not found")

    data = await request.json()
    content = data.get("content", "").strip()
    if not content:
        raise web.HTTPBadRequest(reason="content is required")
    header_enabled = bool(data.get("header_enabled", True))

    settings = cog.conf.channel(channel)
    old_data = await settings.all()

    # Delete old sticky message if one exists
    if old_data.get("last"):
        with contextlib.suppress(discord.HTTPException):
            old_msg = channel.get_partial_message(old_data["last"])
            await old_msg.delete()

    # Build settings dict for _send_stickied_message
    settings_dict = {
        "stickied": content,
        "advstickied": {"content": None, "embed": {}},
        "header_enabled": header_enabled,
        "last": None,
    }
    new_msg = await cog._send_stickied_message(channel, settings_dict)

    await settings.set({
        "stickied": content,
        "advstickied": {"content": None, "embed": {}},
        "header_enabled": header_enabled,
        "last": new_msg.id,
    })

    return web.json_response({
        "channel_id": str(channel_id),
        "content": content,
        "header_enabled": header_enabled,
        "last_message_id": str(new_msg.id),
    }, status=201)


async def delete_sticky(request: web.Request) -> web.Response:
    guild = _guild_or_404(request)
    if guild is None:
        raise web.HTTPNotFound(reason="Guild not found")

    cog = request.app["bot"].get_cog("Sticky")
    if cog is None:
        raise web.HTTPServiceUnavailable(reason="Sticky cog not loaded")

    channel_id = int(request.match_info["channel_id"])
    channel = guild.get_channel(channel_id)
    if channel is None:
        raise web.HTTPNotFound(reason="Channel not found")

    settings = cog.conf.channel(channel)
    data = await settings.all()

    if not (data.get("stickied") or (data.get("advstickied") or {}).get("content")):
        raise web.HTTPNotFound(reason="No sticky set for this channel")

    if data.get("last"):
        with contextlib.suppress(discord.HTTPException):
            old_msg = channel.get_partial_message(data["last"])
            await old_msg.delete()

    await settings.set({
        "stickied": None,
        "advstickied": {"content": None, "embed": {}},
        "header_enabled": data.get("header_enabled", True),
        "last": None,
    })

    return web.json_response({"deleted": True})


async def patch_sticky(request: web.Request) -> web.Response:
    guild = _guild_or_404(request)
    if guild is None:
        raise web.HTTPNotFound(reason="Guild not found")

    cog = request.app["bot"].get_cog("Sticky")
    if cog is None:
        raise web.HTTPServiceUnavailable(reason="Sticky cog not loaded")

    channel_id = int(request.match_info["channel_id"])
    channel = guild.get_channel(channel_id)
    if channel is None:
        raise web.HTTPNotFound(reason="Channel not found")

    data = await request.json()
    if "header_enabled" not in data:
        raise web.HTTPBadRequest(reason="header_enabled field required")

    await cog.conf.channel(channel).header_enabled.set(bool(data["header_enabled"]))
    return web.json_response({"header_enabled": bool(data["header_enabled"])})


# ===========================================================================
# VOICELOGS
# ===========================================================================

def _entry_to_dict(entry: dict) -> dict:
    return {
        "channel_id": str(entry.get("channel_id", "")),
        "channel_name": entry.get("channel_name", ""),
        "joined_at": entry.get("joined_at"),
        "left_at": entry.get("left_at"),
        "duration_s": round(
            (entry["left_at"] - entry["joined_at"]) if entry.get("left_at") and entry.get("joined_at") else 0,
            2,
        ),
    }


async def get_voicelogs_settings(request: web.Request) -> web.Response:
    guild = _guild_or_404(request)
    if guild is None:
        raise web.HTTPNotFound(reason="Guild not found")

    cog = request.app["bot"].get_cog("VoiceLogs")
    if cog is None:
        raise web.HTTPServiceUnavailable(reason="VoiceLogs cog not loaded")

    toggle = await cog.config.guild(guild).toggle()
    return web.json_response({"enabled": toggle})


async def patch_voicelogs_settings(request: web.Request) -> web.Response:
    guild = _guild_or_404(request)
    if guild is None:
        raise web.HTTPNotFound(reason="Guild not found")

    cog = request.app["bot"].get_cog("VoiceLogs")
    if cog is None:
        raise web.HTTPServiceUnavailable(reason="VoiceLogs cog not loaded")

    data = await request.json()
    if "enabled" not in data:
        raise web.HTTPBadRequest(reason="enabled field required")

    await cog.config.guild(guild).toggle.set(bool(data["enabled"]))
    return web.json_response({"enabled": bool(data["enabled"])})


async def get_voicelogs_user(request: web.Request) -> web.Response:
    guild = _guild_or_404(request)
    if guild is None:
        raise web.HTTPNotFound(reason="Guild not found")

    cog = request.app["bot"].get_cog("VoiceLogs")
    if cog is None:
        raise web.HTTPServiceUnavailable(reason="VoiceLogs cog not loaded")

    user_id = int(request.match_info["user_id"])
    # VoiceLogs stores history globally per user; filter to this guild's channels
    guild_channel_ids = {ch.id for ch in guild.channels}

    history = await cog.config.user_from_id(user_id).history()
    guild_entries = [e for e in history if e.get("channel_id") in guild_channel_ids]

    # Sort by joined_at desc, take last 25
    sorted_entries = sorted(guild_entries, key=lambda e: e.get("joined_at", 0), reverse=True)[:25]
    return web.json_response([_entry_to_dict(e) for e in sorted_entries])


async def get_voicelogs_channel(request: web.Request) -> web.Response:
    guild = _guild_or_404(request)
    if guild is None:
        raise web.HTTPNotFound(reason="Guild not found")

    cog = request.app["bot"].get_cog("VoiceLogs")
    if cog is None:
        raise web.HTTPServiceUnavailable(reason="VoiceLogs cog not loaded")

    channel_id = int(request.match_info["channel_id"])
    channel = guild.get_channel(channel_id)
    if channel is None:
        raise web.HTTPNotFound(reason="Channel not found")

    all_users = await cog.config.all_users()
    entries = []
    for uid_str, user_data in all_users.items():
        history = user_data.get("history", [])
        for e in history:
            if e.get("channel_id") == channel_id:
                d = _entry_to_dict(e)
                d["user_id"] = str(uid_str)
                entries.append(d)

    entries.sort(key=lambda e: e.get("joined_at") or 0, reverse=True)
    return web.json_response(entries[:25])


# ===========================================================================
# AUTONICK
# ===========================================================================

async def get_autonick_settings(request: web.Request) -> web.Response:
    guild = _guild_or_404(request)
    if guild is None:
        raise web.HTTPNotFound(reason="Guild not found")

    cog = request.app["bot"].get_cog("AutoNick")
    if cog is None:
        raise web.HTTPServiceUnavailable(reason="AutoNick cog not loaded")

    channel_id = await cog.config.guild(guild).channel()
    cooldown = await cog.config.guild(guild).cooldown()
    return web.json_response({
        "channel": str(channel_id) if channel_id else None,
        "cooldown": cooldown,
    })


async def patch_autonick_settings(request: web.Request) -> web.Response:
    guild = _guild_or_404(request)
    if guild is None:
        raise web.HTTPNotFound(reason="Guild not found")

    cog = request.app["bot"].get_cog("AutoNick")
    if cog is None:
        raise web.HTTPServiceUnavailable(reason="AutoNick cog not loaded")

    data = await request.json()
    allowed = {"channel", "cooldown"}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        raise web.HTTPBadRequest(reason="No valid fields provided (channel, cooldown)")

    guild_cfg = cog.config.guild(guild)
    for key, value in updates.items():
        await guild_cfg.get_attr(key).set(value)

    return web.json_response({"updated": list(updates.keys())})


async def get_autonick_forbidden(request: web.Request) -> web.Response:

    cog = request.app["bot"].get_cog("AutoNick")
    if cog is None:
        raise web.HTTPServiceUnavailable(reason="AutoNick cog not loaded")

    names = await cog.config.forbidden_names()
    return web.json_response({"forbidden_names": names})


async def post_autonick_forbidden(request: web.Request) -> web.Response:

    cog = request.app["bot"].get_cog("AutoNick")
    if cog is None:
        raise web.HTTPServiceUnavailable(reason="AutoNick cog not loaded")

    data = await request.json()
    word = data.get("word", "").strip().lower()
    if not word:
        raise web.HTTPBadRequest(reason="word is required")

    async with cog.config.forbidden_names() as names:
        if word in names:
            raise web.HTTPConflict(reason="Word already in forbidden list")
        names.append(word)

    return web.json_response({"word": word}, status=201)


async def delete_autonick_forbidden(request: web.Request) -> web.Response:

    cog = request.app["bot"].get_cog("AutoNick")
    if cog is None:
        raise web.HTTPServiceUnavailable(reason="AutoNick cog not loaded")

    word = request.match_info["word"].strip().lower()

    async with cog.config.forbidden_names() as names:
        if word not in names:
            raise web.HTTPNotFound(reason="Word not found in forbidden list")
        names.remove(word)

    return web.json_response({"deleted": word})


# ===========================================================================
# MOVER
# ===========================================================================

async def post_massmove(request: web.Request) -> web.Response:
    guild = _guild_or_404(request)
    if guild is None:
        raise web.HTTPNotFound(reason="Guild not found")

    cog = request.app["bot"].get_cog("Mover")
    if cog is None:
        raise web.HTTPServiceUnavailable(reason="Mover cog not loaded")

    data = await request.json()
    try:
        target_id = int(data["target_channel_id"])
    except (KeyError, ValueError, TypeError):
        raise web.HTTPBadRequest(reason="target_channel_id (int) is required")

    target = guild.get_channel(target_id)
    if target is None or not isinstance(target, discord.VoiceChannel):
        raise web.HTTPNotFound(reason="Target voice channel not found")

    source_id = data.get("source_channel_id")
    if source_id is not None:
        source = guild.get_channel(int(source_id))
        if source is None or not isinstance(source, discord.VoiceChannel):
            raise web.HTTPNotFound(reason="Source voice channel not found")
        sources = [source]
    else:
        # Move from all voice channels in the guild (except target)
        sources = [ch for ch in guild.voice_channels if ch.id != target_id]

    moved = 0
    for source_ch in sources:
        for member in list(source_ch.members):
            try:
                await member.move_to(target, reason="APIv2 massmove")
                moved += 1
            except discord.HTTPException:
                pass

    return web.json_response({
        "target_channel_id": str(target_id),
        "moved": moved,
    })


# ===========================================================================
# Registration
# ===========================================================================

def register_routes(app: web.Application) -> None:
    app.router.add_route("GET",    "/api/v2/guilds/{guild_id}/welcome",                              get_welcome)
    app.router.add_route("PATCH",  "/api/v2/guilds/{guild_id}/welcome",                              patch_welcome)
    app.router.add_route("GET",    "/api/v2/guilds/{guild_id}/welcome/{event}/messages",              get_welcome_messages)
    app.router.add_route("POST",   "/api/v2/guilds/{guild_id}/welcome/{event}/messages",              post_welcome_message)
    app.router.add_route("DELETE", "/api/v2/guilds/{guild_id}/welcome/{event}/messages/{index}",      delete_welcome_message)
    app.router.add_route("GET",    "/api/v2/guilds/{guild_id}/welcome/join/whisper",                  get_welcome_whisper)
    app.router.add_route("PATCH",  "/api/v2/guilds/{guild_id}/welcome/join/whisper",                  patch_welcome_whisper)

    app.router.add_route("GET",    "/api/v2/guilds/{guild_id}/stickies",                              list_stickies)
    app.router.add_route("GET",    "/api/v2/guilds/{guild_id}/channels/{channel_id}/sticky",          get_sticky)
    app.router.add_route("PUT",    "/api/v2/guilds/{guild_id}/channels/{channel_id}/sticky",          put_sticky)
    app.router.add_route("DELETE", "/api/v2/guilds/{guild_id}/channels/{channel_id}/sticky",          delete_sticky)
    app.router.add_route("PATCH",  "/api/v2/guilds/{guild_id}/channels/{channel_id}/sticky",          patch_sticky)

    app.router.add_route("GET",    "/api/v2/guilds/{guild_id}/voicelogs/settings",                    get_voicelogs_settings)
    app.router.add_route("PATCH",  "/api/v2/guilds/{guild_id}/voicelogs/settings",                    patch_voicelogs_settings)
    app.router.add_route("GET",    "/api/v2/guilds/{guild_id}/voicelogs/users/{user_id}",             get_voicelogs_user)
    app.router.add_route("GET",    "/api/v2/guilds/{guild_id}/voicelogs/channels/{channel_id}",       get_voicelogs_channel)

    app.router.add_route("GET",    "/api/v2/guilds/{guild_id}/autonick/settings",                     get_autonick_settings)
    app.router.add_route("PATCH",  "/api/v2/guilds/{guild_id}/autonick/settings",                     patch_autonick_settings)
    app.router.add_route("GET",    "/api/v2/autonick/forbidden-names",                                get_autonick_forbidden)
    app.router.add_route("POST",   "/api/v2/autonick/forbidden-names",                                post_autonick_forbidden)
    app.router.add_route("DELETE", "/api/v2/autonick/forbidden-names/{word}",                         delete_autonick_forbidden)

    app.router.add_route("POST",   "/api/v2/guilds/{guild_id}/voice/massmove",                        post_massmove)
