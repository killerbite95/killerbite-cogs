"""
Phase 8 — Contenido e interacción: Giveaways, Tags, RolesButtons, RoleSyncer.

All four sections return 503 if the required cog is not loaded.
"""

import sys
import logging
from copy import deepcopy
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord
from aiohttp import web

from ..server import APP_BOT_KEY, json_error

if TYPE_CHECKING:
    from redbot.core.bot import Red

logger = logging.getLogger("red.killerbite95.apiv2.routes.phase8")

PREFIX = "/api/v2"

VALID_RB_MODES = frozenset({"add_or_remove", "add_only", "remove_only", "replace"})


# ──────────────────────────── route registration ─────────────────────────────


def register_routes(app: web.Application):
    g = "{guild_id}"
    m = "{message_id}"
    # Giveaways
    app.router.add_get(f"{PREFIX}/guilds/{g}/giveaways", handle_giveaways_list)
    app.router.add_post(f"{PREFIX}/guilds/{g}/giveaways", handle_giveaways_create)
    app.router.add_get(f"{PREFIX}/guilds/{g}/giveaways/{m}", handle_giveaway_get)
    app.router.add_post(f"{PREFIX}/guilds/{g}/giveaways/{m}/end", handle_giveaway_end)
    app.router.add_post(f"{PREFIX}/guilds/{g}/giveaways/{m}/reroll", handle_giveaway_reroll)
    app.router.add_delete(f"{PREFIX}/guilds/{g}/giveaways/{m}", handle_giveaway_delete)
    # Tags
    app.router.add_get(f"{PREFIX}/guilds/{g}/tags", handle_tags_list)
    app.router.add_post(f"{PREFIX}/guilds/{g}/tags", handle_tags_create)
    app.router.add_get(f"{PREFIX}/guilds/{g}/tags/{{name}}", handle_tag_get)
    app.router.add_put(f"{PREFIX}/guilds/{g}/tags/{{name}}", handle_tag_put)
    app.router.add_delete(f"{PREFIX}/guilds/{g}/tags/{{name}}", handle_tag_delete)
    app.router.add_post(f"{PREFIX}/guilds/{g}/tags/{{name}}/invoke", handle_tag_invoke)
    # RolesButtons
    app.router.add_get(f"{PREFIX}/guilds/{g}/rolesbuttons", handle_rb_list)
    app.router.add_get(f"{PREFIX}/guilds/{g}/rolesbuttons/{{channel_id}}/{m}", handle_rb_get)
    app.router.add_post(f"{PREFIX}/guilds/{g}/rolesbuttons/{{channel_id}}/{m}", handle_rb_add_button)
    app.router.add_delete(f"{PREFIX}/guilds/{g}/rolesbuttons/{{channel_id}}/{m}/{{button_id}}", handle_rb_delete_button)
    app.router.add_patch(f"{PREFIX}/guilds/{g}/rolesbuttons/{{channel_id}}/{m}/mode", handle_rb_mode_patch)
    # RoleSyncer
    app.router.add_get(f"{PREFIX}/guilds/{g}/rolesyncer", handle_rolesyncer_get)
    app.router.add_post(f"{PREFIX}/guilds/{g}/rolesyncer/onesync", handle_rolesyncer_add_one)
    app.router.add_post(f"{PREFIX}/guilds/{g}/rolesyncer/twosync", handle_rolesyncer_add_two)
    app.router.add_delete(f"{PREFIX}/guilds/{g}/rolesyncer/onesync/{{index}}", handle_rolesyncer_del_one)
    app.router.add_delete(f"{PREFIX}/guilds/{g}/rolesyncer/twosync/{{index}}", handle_rolesyncer_del_two)


# ──────────────────────────── shared helpers ─────────────────────────────────


def _get_guild(bot: "Red", guild_id_str: str):
    try:
        return bot.get_guild(int(guild_id_str))
    except ValueError:
        return None


# ═══════════════════════════════════════════════════════════════
# GIVEAWAYS
# ═══════════════════════════════════════════════════════════════

GIVEAWAY_KEY = "giveaways"


def _giveaway_to_dict(giveaway, raw: dict | None = None) -> dict:
    """Serialize a Giveaway object (or raw config dict) to JSON-safe dict."""
    if raw is not None:
        endtime = raw.get("endtime")
        if isinstance(endtime, (int, float)):
            try:
                endtime = datetime.fromtimestamp(endtime, tz=timezone.utc).isoformat()
            except Exception:
                endtime = str(endtime)
        kwargs = raw.get("kwargs", {})
        return {
            "message_id": str(raw.get("messageid", "")),
            "channel_id": str(raw.get("channelid", "")),
            "prize": raw.get("prize"),
            "endtime": endtime,
            "ended": raw.get("ended", False),
            "entrant_count": len(raw.get("entrants", [])),
            "entrants": [str(e) for e in raw.get("entrants", [])],
            "emoji": raw.get("emoji", "🎉"),
            "winners": kwargs.get("winners", 1),
            "requirements": {
                "roles": [str(r) for r in kwargs.get("roles", [])],
                "blacklist": [str(r) for r in kwargs.get("blacklist", [])],
                "cost": kwargs.get("cost"),
                "min_join_days": kwargs.get("joined"),
                "min_account_days": kwargs.get("created"),
            },
        }
    # live Giveaway object
    endtime_raw = giveaway.endtime
    if isinstance(endtime_raw, datetime):
        endtime_str = endtime_raw.isoformat()
    else:
        endtime_str = str(endtime_raw)
    kw = giveaway.kwargs
    return {
        "message_id": str(giveaway.messageid),
        "channel_id": str(giveaway.channelid),
        "prize": giveaway.prize,
        "endtime": endtime_str,
        "ended": False,
        "entrant_count": len(giveaway.entrants),
        "entrants": [str(e) for e in giveaway.entrants],
        "emoji": giveaway.emoji,
        "winners": kw.get("winners", 1),
        "requirements": {
            "roles": [str(r) for r in kw.get("roles", [])],
            "blacklist": [str(r) for r in kw.get("blacklist", [])],
            "cost": kw.get("cost"),
            "min_join_days": kw.get("joined"),
            "min_account_days": kw.get("created"),
        },
    }


async def handle_giveaways_list(request: web.Request) -> web.Response:
    """GET /guilds/{guild_id}/giveaways?ended=false&limit=20&offset=0"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = bot.get_cog("Giveaways")
    if cog is None:
        return json_error("cog_unavailable", "Giveaways cog is not loaded", 503)

    show_ended = request.rel_url.query.get("ended", "false").lower() != "false"
    try:
        limit = max(1, min(100, int(request.rel_url.query.get("limit", 20))))
        offset = max(0, int(request.rel_url.query.get("offset", 0)))
    except ValueError:
        return json_error("bad_request", "Invalid limit or offset", 400)

    results = []

    # Active giveaways from in-memory cache
    if not show_ended:
        for msgid, gw in cog.giveaways.items():
            if gw.guildid == guild.id:
                results.append(_giveaway_to_dict(gw))
    else:
        # Load all from config (includes ended)
        all_data = await cog.config.custom(GIVEAWAY_KEY, str(guild.id)).all()
        for msgid, raw in all_data.items():
            raw.setdefault("messageid", int(msgid))
            raw.setdefault("guildid", guild.id)
            results.append(_giveaway_to_dict(None, raw))

    results.sort(key=lambda x: x["message_id"], reverse=True)
    total = len(results)
    return web.json_response({
        "total": total,
        "limit": limit,
        "offset": offset,
        "giveaways": results[offset: offset + limit],
    })


async def handle_giveaway_get(request: web.Request) -> web.Response:
    """GET /guilds/{guild_id}/giveaways/{message_id}"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = bot.get_cog("Giveaways")
    if cog is None:
        return json_error("cog_unavailable", "Giveaways cog is not loaded", 503)

    try:
        msg_id = int(request.match_info["message_id"])
    except ValueError:
        return json_error("bad_request", "Invalid message_id", 400)

    # Check live cache first
    if msg_id in cog.giveaways and cog.giveaways[msg_id].guildid == guild.id:
        return web.json_response(_giveaway_to_dict(cog.giveaways[msg_id]))

    # Fall back to config
    raw = await cog.config.custom(GIVEAWAY_KEY, str(guild.id), str(msg_id)).all()
    if not raw or "prize" not in raw:
        return json_error("not_found", f"Giveaway {msg_id} not found", 404)
    raw.setdefault("messageid", msg_id)
    raw.setdefault("guildid", guild.id)
    return web.json_response(_giveaway_to_dict(None, raw))


async def handle_giveaways_create(request: web.Request) -> web.Response:
    """POST /guilds/{guild_id}/giveaways — create a new giveaway."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = bot.get_cog("Giveaways")
    if cog is None:
        return json_error("cog_unavailable", "Giveaways cog is not loaded", 503)

    try:
        body = await request.json()
    except Exception:
        return json_error("bad_request", "Invalid JSON body", 400)

    channel_id = body.get("channel_id")
    prize = body.get("prize")
    duration_seconds = body.get("duration_seconds")
    if not channel_id or not prize or not duration_seconds:
        return json_error("bad_request", "channel_id, prize, and duration_seconds are required", 400)

    channel = guild.get_channel(int(channel_id))
    if channel is None:
        return json_error("not_found", f"Channel {channel_id} not found", 404)

    winners = int(body.get("winners", 1))
    end = datetime.now(timezone.utc).replace(microsecond=0)
    from datetime import timedelta
    end = end + timedelta(seconds=int(duration_seconds))

    embed = discord.Embed(
        title=prize,
        description=f"\nClick the button below to enter\n\nEnds: <t:{int(end.timestamp())}:R>",
        color=discord.Color.blue(),
    )

    # Import cog internals via sys.modules
    cog_pkg = type(cog).__module__.rsplit(".", 1)[0]
    menu_mod = sys.modules.get(f"{cog_pkg}.menu")
    objects_mod = sys.modules.get(f"{cog_pkg}.objects")

    if menu_mod is None or objects_mod is None:
        return json_error("internal_error", "Could not load Giveaways internal modules", 500)

    GiveawayView = getattr(menu_mod, "GiveawayView")
    GiveawayButton = getattr(menu_mod, "GiveawayButton")
    Giveaway = getattr(objects_mod, "Giveaway")

    kwargs = {
        "congratulate": True,
        "notify": True,
        "winners": winners,
    }
    if body.get("required_roles"):
        kwargs["roles"] = [int(r) for r in body["required_roles"]]
    if body.get("blacklist_roles"):
        kwargs["blacklist"] = [int(r) for r in body["blacklist_roles"]]
    if body.get("cost") is not None:
        kwargs["cost"] = int(body["cost"])
    if body.get("min_join_days") is not None:
        kwargs["joined"] = int(body["min_join_days"])

    try:
        msg = await channel.send(embed=embed)
        view = GiveawayView(cog)
        view.add_item(GiveawayButton(label="Join Giveaway", style="green", emoji="🎉", cog=cog, id=msg.id))
        bot.add_view(view)
        await msg.edit(view=view)

        giveaway_obj = Giveaway(guild.id, channel.id, msg.id, end, prize, "🎉", **kwargs)
        cog.giveaways[msg.id] = giveaway_obj

        giveaway_dict = deepcopy(giveaway_obj.__dict__)
        giveaway_dict["endtime"] = giveaway_dict["endtime"].timestamp()
        await cog.config.custom(GIVEAWAY_KEY, str(guild.id), str(msg.id)).set(giveaway_dict)
    except discord.HTTPException as e:
        return json_error("internal_error", f"Discord error: {e}", 500)

    return web.json_response(_giveaway_to_dict(giveaway_obj), status=201)


async def handle_giveaway_end(request: web.Request) -> web.Response:
    """POST /guilds/{guild_id}/giveaways/{message_id}/end — force-end a giveaway."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = bot.get_cog("Giveaways")
    if cog is None:
        return json_error("cog_unavailable", "Giveaways cog is not loaded", 503)

    try:
        msg_id = int(request.match_info["message_id"])
    except ValueError:
        return json_error("bad_request", "Invalid message_id", 400)

    if msg_id not in cog.giveaways or cog.giveaways[msg_id].guildid != guild.id:
        return json_error("not_found", f"Active giveaway {msg_id} not found", 404)

    try:
        await cog.draw_winner(cog.giveaways[msg_id])
        del cog.giveaways[msg_id]
        gw = await cog.config.custom(GIVEAWAY_KEY, str(guild.id), str(msg_id)).all()
        gw["ended"] = True
        await cog.config.custom(GIVEAWAY_KEY, str(guild.id), str(msg_id)).set(gw)
    except Exception as e:
        return json_error("internal_error", str(e), 500)

    return web.json_response({"ended": True, "message_id": str(msg_id)})


async def handle_giveaway_reroll(request: web.Request) -> web.Response:
    """POST /guilds/{guild_id}/giveaways/{message_id}/reroll"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = bot.get_cog("Giveaways")
    if cog is None:
        return json_error("cog_unavailable", "Giveaways cog is not loaded", 503)

    try:
        msg_id = int(request.match_info["message_id"])
    except ValueError:
        return json_error("bad_request", "Invalid message_id", 400)

    objects_mod = sys.modules.get(f"{type(cog).__module__.rsplit('.', 1)[0]}.objects")
    Giveaway = getattr(objects_mod, "Giveaway") if objects_mod else None
    if Giveaway is None:
        return json_error("internal_error", "Could not load Giveaways internal modules", 500)

    data = await cog.config.custom(GIVEAWAY_KEY, str(guild.id)).all()
    if str(msg_id) not in data:
        return json_error("not_found", f"Giveaway {msg_id} not found", 404)

    gw_dict = deepcopy(data[str(msg_id)])
    gw_dict["endtime"] = datetime.fromtimestamp(gw_dict["endtime"]).replace(tzinfo=timezone.utc)
    giveaway = Giveaway(**gw_dict)

    try:
        await cog.draw_winner(giveaway)
    except Exception as e:
        return json_error("internal_error", str(e), 500)

    return web.json_response({"rerolled": True, "message_id": str(msg_id)})


async def handle_giveaway_delete(request: web.Request) -> web.Response:
    """DELETE /guilds/{guild_id}/giveaways/{message_id}"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = bot.get_cog("Giveaways")
    if cog is None:
        return json_error("cog_unavailable", "Giveaways cog is not loaded", 503)

    try:
        msg_id = int(request.match_info["message_id"])
    except ValueError:
        return json_error("bad_request", "Invalid message_id", 400)

    # Remove from in-memory cache
    if msg_id in cog.giveaways and cog.giveaways[msg_id].guildid == guild.id:
        del cog.giveaways[msg_id]

    # Remove from config
    await cog.config.custom(GIVEAWAY_KEY, str(guild.id), str(msg_id)).clear()

    return web.json_response({"deleted": str(msg_id)})


# ═══════════════════════════════════════════════════════════════
# TAGS
# ═══════════════════════════════════════════════════════════════

TAGSCRIPT_LIMIT = 10_000


def _tag_obj_to_dict(tag) -> dict:
    return {
        "name": tag.name,
        "tagscript": tag.tagscript,
        "uses": tag.uses,
        "author_id": str(tag.author_id) if tag.author_id else None,
        "created_at": tag.created_at.isoformat() if tag.created_at else None,
        "aliases": tag.aliases,
    }


async def handle_tags_list(request: web.Request) -> web.Response:
    """GET /guilds/{guild_id}/tags?limit=50&offset=0&search="""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = bot.get_cog("Tags")
    if cog is None:
        return json_error("cog_unavailable", "Tags cog is not loaded", 503)

    try:
        limit = max(1, min(200, int(request.rel_url.query.get("limit", 50))))
        offset = max(0, int(request.rel_url.query.get("offset", 0)))
    except ValueError:
        return json_error("bad_request", "Invalid limit or offset", 400)

    search = request.rel_url.query.get("search", "").lower()

    # Use in-memory cache (guilds) — only real tags (not aliases pointing to same object)
    cache = cog.guild_tag_cache.get(guild.id, {})
    seen = set()
    tags = []
    for name, tag in cache.items():
        if tag.name in seen:
            continue  # skip duplicates from alias keys
        seen.add(tag.name)
        if search and search not in tag.name.lower():
            continue
        tags.append(tag)

    tags.sort(key=lambda t: t.name)
    total = len(tags)
    return web.json_response({
        "total": total,
        "limit": limit,
        "offset": offset,
        "tags": [_tag_obj_to_dict(t) for t in tags[offset: offset + limit]],
    })


async def handle_tag_get(request: web.Request) -> web.Response:
    """GET /guilds/{guild_id}/tags/{name}"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = bot.get_cog("Tags")
    if cog is None:
        return json_error("cog_unavailable", "Tags cog is not loaded", 503)

    name = request.match_info["name"]
    tag = cog.guild_tag_cache.get(guild.id, {}).get(name)
    if tag is None:
        return json_error("not_found", f"Tag '{name}' not found", 404)

    return web.json_response(_tag_obj_to_dict(tag))


async def handle_tags_create(request: web.Request) -> web.Response:
    """POST /guilds/{guild_id}/tags — create a new tag."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = bot.get_cog("Tags")
    if cog is None:
        return json_error("cog_unavailable", "Tags cog is not loaded", 503)

    try:
        body = await request.json()
    except Exception:
        return json_error("bad_request", "Invalid JSON body", 400)

    name = body.get("name", "").strip()
    tagscript = body.get("tagscript", "")
    if not name or not tagscript:
        return json_error("bad_request", "name and tagscript are required", 400)
    if len(tagscript) > TAGSCRIPT_LIMIT:
        return json_error("bad_request", f"tagscript exceeds {TAGSCRIPT_LIMIT} character limit", 400)

    cache = cog.guild_tag_cache.get(guild.id, {})
    if name in cache:
        return json_error("bad_request", f"Tag '{name}' already exists", 409)

    objects_mod = sys.modules.get(f"{type(cog).__module__.rsplit('.', 1)[0]}.objects")
    Tag = getattr(objects_mod, "Tag") if objects_mod else None
    if Tag is None:
        return json_error("internal_error", "Could not load Tags internal modules", 500)

    tag = Tag(
        cog,
        name,
        tagscript,
        guild_id=guild.id,
        author_id=None,
        aliases=body.get("aliases", []),
    )
    await tag.initialize()

    return web.json_response(_tag_obj_to_dict(tag), status=201)


async def handle_tag_put(request: web.Request) -> web.Response:
    """PUT /guilds/{guild_id}/tags/{name} — update a tag's tagscript and/or aliases."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = bot.get_cog("Tags")
    if cog is None:
        return json_error("cog_unavailable", "Tags cog is not loaded", 503)

    name = request.match_info["name"]
    tag = cog.guild_tag_cache.get(guild.id, {}).get(name)
    if tag is None:
        return json_error("not_found", f"Tag '{name}' not found", 404)

    try:
        body = await request.json()
    except Exception:
        return json_error("bad_request", "Invalid JSON body", 400)

    if "tagscript" in body:
        ts = body["tagscript"]
        if len(ts) > TAGSCRIPT_LIMIT:
            return json_error("bad_request", f"tagscript exceeds {TAGSCRIPT_LIMIT} characters", 400)
        tag.tagscript = ts

    if "aliases" in body:
        new_aliases = list(body["aliases"])
        # Remove old aliases from cache
        tag.remove_from_cache()
        tag._aliases = new_aliases
        tag.add_to_cache()

    await tag.update_config()
    return web.json_response(_tag_obj_to_dict(tag))


async def handle_tag_delete(request: web.Request) -> web.Response:
    """DELETE /guilds/{guild_id}/tags/{name}"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = bot.get_cog("Tags")
    if cog is None:
        return json_error("cog_unavailable", "Tags cog is not loaded", 503)

    name = request.match_info["name"]
    tag = cog.guild_tag_cache.get(guild.id, {}).get(name)
    if tag is None:
        return json_error("not_found", f"Tag '{name}' not found", 404)

    await tag.delete()
    return web.json_response({"deleted": name})


async def handle_tag_invoke(request: web.Request) -> web.Response:
    """POST /guilds/{guild_id}/tags/{name}/invoke — send a tag to a channel."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = bot.get_cog("Tags")
    if cog is None:
        return json_error("cog_unavailable", "Tags cog is not loaded", 503)

    name = request.match_info["name"]
    tag = cog.guild_tag_cache.get(guild.id, {}).get(name)
    if tag is None:
        return json_error("not_found", f"Tag '{name}' not found", 404)

    try:
        body = await request.json()
    except Exception:
        return json_error("bad_request", "Invalid JSON body", 400)

    channel_id = body.get("channel_id")
    user_id = body.get("user_id")
    if not channel_id:
        return json_error("bad_request", "channel_id is required", 400)

    channel = guild.get_channel(int(channel_id))
    if channel is None:
        return json_error("not_found", f"Channel {channel_id} not found", 404)

    # Build minimal seed variables (TSE)
    try:
        import TagScriptEngine as tse
        seed = {
            "server": tse.GuildAdapter(guild),
            "guild": tse.GuildAdapter(guild),
            "channel": tse.ChannelAdapter(channel),
        }
        if user_id:
            member = guild.get_member(int(user_id))
            if member:
                seed["author"] = tse.MemberAdapter(member)
                seed["user"] = tse.MemberAdapter(member)
            elif (user := bot.get_user(int(user_id))):
                seed["author"] = tse.UserAdapter(user)
                seed["user"] = tse.UserAdapter(user)
    except Exception:
        seed = {}

    try:
        output = await tag.run(seed)
        await cog.send_tag_response(channel=channel, seed_variables=seed, response=output)
    except Exception as e:
        return json_error("internal_error", f"Tag execution failed: {e}", 500)

    tag.uses += 1
    await tag.update_config()

    return web.json_response({"invoked": name, "uses": tag.uses})


# ═══════════════════════════════════════════════════════════════
# ROLESBUTTONS
# ═══════════════════════════════════════════════════════════════

def _rb_key(channel_id: int, message_id: int) -> str:
    return f"{channel_id}-{message_id}"


def _rb_data_to_dict(key: str, buttons: dict, mode: str) -> dict:
    parts = key.split("-")
    return {
        "channel_id": parts[0],
        "message_id": parts[1],
        "mode": mode,
        "buttons": [
            {
                "id": btn_id,
                "emoji": btn.get("emoji"),
                "role_id": str(btn["role"]) if "role" in btn else None,
            }
            for btn_id, btn in buttons.items()
        ],
    }


async def handle_rb_list(request: web.Request) -> web.Response:
    """GET /guilds/{guild_id}/rolesbuttons"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = bot.get_cog("RolesButtons")
    if cog is None:
        return json_error("cog_unavailable", "RolesButtons cog is not loaded", 503)

    all_cfg = await cog.config.guild(guild).all()
    buttons_cfg = all_cfg.get("roles_buttons", {})
    modes_cfg = all_cfg.get("modes", {})

    result = []
    for key, buttons in buttons_cfg.items():
        mode = modes_cfg.get(key, "add_or_remove")
        result.append(_rb_data_to_dict(key, buttons, mode))

    return web.json_response(result)


async def handle_rb_get(request: web.Request) -> web.Response:
    """GET /guilds/{guild_id}/rolesbuttons/{channel_id}/{message_id}"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = bot.get_cog("RolesButtons")
    if cog is None:
        return json_error("cog_unavailable", "RolesButtons cog is not loaded", 503)

    try:
        channel_id = int(request.match_info["channel_id"])
        message_id = int(request.match_info["message_id"])
    except ValueError:
        return json_error("bad_request", "Invalid channel_id or message_id", 400)

    key = _rb_key(channel_id, message_id)
    all_cfg = await cog.config.guild(guild).all()
    buttons = all_cfg.get("roles_buttons", {}).get(key)
    if buttons is None:
        return json_error("not_found", f"No roles-buttons configured for {key}", 404)

    mode = all_cfg.get("modes", {}).get(key, "add_or_remove")
    return web.json_response(_rb_data_to_dict(key, buttons, mode))


async def handle_rb_add_button(request: web.Request) -> web.Response:
    """POST /guilds/{guild_id}/rolesbuttons/{channel_id}/{message_id} — add a button."""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = bot.get_cog("RolesButtons")
    if cog is None:
        return json_error("cog_unavailable", "RolesButtons cog is not loaded", 503)

    try:
        channel_id = int(request.match_info["channel_id"])
        message_id = int(request.match_info["message_id"])
    except ValueError:
        return json_error("bad_request", "Invalid channel_id or message_id", 400)

    try:
        body = await request.json()
    except Exception:
        return json_error("bad_request", "Invalid JSON body", 400)

    role_id = body.get("role_id")
    emoji = body.get("emoji")
    if not role_id:
        return json_error("bad_request", "role_id is required", 400)

    role = guild.get_role(int(role_id))
    if role is None:
        return json_error("not_found", f"Role {role_id} not found", 404)

    # Import CogsUtils for key generation
    cog_pkg = type(cog).__module__.rsplit(".", 1)[0]
    aaa3a_pkg = sys.modules.get("AAA3A_utils")
    CogsUtils = getattr(aaa3a_pkg, "CogsUtils") if aaa3a_pkg else None

    key = _rb_key(channel_id, message_id)
    async with cog.config.guild(guild).roles_buttons() as rb:
        if key not in rb:
            rb[key] = {}
        # Generate button ID
        if CogsUtils is not None:
            btn_id = CogsUtils.generate_key(length=5, existing_keys=rb[key])
        else:
            import uuid
            btn_id = str(uuid.uuid4())[:5]
        rb[key][btn_id] = {"role": role.id, "emoji": emoji}

    return web.json_response({"added": btn_id, "role_id": str(role.id), "emoji": emoji}, status=201)


async def handle_rb_delete_button(request: web.Request) -> web.Response:
    """DELETE /guilds/{guild_id}/rolesbuttons/{channel_id}/{message_id}/{button_id}"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = bot.get_cog("RolesButtons")
    if cog is None:
        return json_error("cog_unavailable", "RolesButtons cog is not loaded", 503)

    try:
        channel_id = int(request.match_info["channel_id"])
        message_id = int(request.match_info["message_id"])
    except ValueError:
        return json_error("bad_request", "Invalid channel_id or message_id", 400)

    key = _rb_key(channel_id, message_id)
    btn_id = request.match_info["button_id"]

    async with cog.config.guild(guild).roles_buttons() as rb:
        if key not in rb or btn_id not in rb[key]:
            return json_error("not_found", f"Button '{btn_id}' not found in {key}", 404)
        del rb[key][btn_id]
        if not rb[key]:
            del rb[key]
            # Also remove mode entry
            async with cog.config.guild(guild).modes() as modes:
                modes.pop(key, None)

    return web.json_response({"deleted": btn_id})


async def handle_rb_mode_patch(request: web.Request) -> web.Response:
    """PATCH /guilds/{guild_id}/rolesbuttons/{channel_id}/{message_id}/mode"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = bot.get_cog("RolesButtons")
    if cog is None:
        return json_error("cog_unavailable", "RolesButtons cog is not loaded", 503)

    try:
        channel_id = int(request.match_info["channel_id"])
        message_id = int(request.match_info["message_id"])
    except ValueError:
        return json_error("bad_request", "Invalid channel_id or message_id", 400)

    try:
        body = await request.json()
    except Exception:
        return json_error("bad_request", "Invalid JSON body", 400)

    mode = body.get("mode")
    if mode not in VALID_RB_MODES:
        return json_error("bad_request", f"mode must be one of: {sorted(VALID_RB_MODES)}", 400)

    key = _rb_key(channel_id, message_id)
    rb = await cog.config.guild(guild).roles_buttons()
    if key not in rb:
        return json_error("not_found", f"No roles-buttons configured for {key}", 404)

    await cog.config.guild(guild).modes.set_raw(key, value=mode)
    return web.json_response({"key": key, "mode": mode})


# ═══════════════════════════════════════════════════════════════
# ROLESYNCER
# ═══════════════════════════════════════════════════════════════


async def handle_rolesyncer_get(request: web.Request) -> web.Response:
    """GET /guilds/{guild_id}/rolesyncer"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = bot.get_cog("RoleSyncer")
    if cog is None:
        return json_error("cog_unavailable", "RoleSyncer cog is not loaded", 503)

    cfg = await cog.config.guild(guild).all()
    return web.json_response({
        "onesync": [[str(r) for r in pair] for pair in cfg.get("onesync", [])],
        "twosync": [[str(r) for r in pair] for pair in cfg.get("twosync", [])],
    })


async def _rolesyncer_add(request: web.Request, sync_type: str) -> web.Response:
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = bot.get_cog("RoleSyncer")
    if cog is None:
        return json_error("cog_unavailable", "RoleSyncer cog is not loaded", 503)

    try:
        body = await request.json()
    except Exception:
        return json_error("bad_request", "Invalid JSON body", 400)

    r1_id = body.get("role1_id")
    r2_id = body.get("role2_id")
    if not r1_id or not r2_id:
        return json_error("bad_request", "role1_id and role2_id are required", 400)

    try:
        r1, r2 = int(r1_id), int(r2_id)
    except (ValueError, TypeError):
        return json_error("bad_request", "role IDs must be integers", 400)

    if guild.get_role(r1) is None:
        return json_error("not_found", f"Role {r1} not found", 404)
    if guild.get_role(r2) is None:
        return json_error("not_found", f"Role {r2} not found", 404)

    async with getattr(cog.config.guild(guild), sync_type)() as syncs:
        pair = [r1, r2]
        if pair in syncs:
            return json_error("bad_request", "This sync pair already exists", 409)
        syncs.append(pair)

    return web.json_response({"added": [str(r1), str(r2)], "type": sync_type}, status=201)


async def handle_rolesyncer_add_one(request: web.Request) -> web.Response:
    return await _rolesyncer_add(request, "onesync")


async def handle_rolesyncer_add_two(request: web.Request) -> web.Response:
    return await _rolesyncer_add(request, "twosync")


async def _rolesyncer_delete(request: web.Request, sync_type: str) -> web.Response:
    bot: "Red" = request.app[APP_BOT_KEY]
    guild = _get_guild(bot, request.match_info["guild_id"])
    if guild is None:
        return json_error("not_found", "Guild not found", 404)

    cog = bot.get_cog("RoleSyncer")
    if cog is None:
        return json_error("cog_unavailable", "RoleSyncer cog is not loaded", 503)

    try:
        idx = int(request.match_info["index"])
    except ValueError:
        return json_error("bad_request", "index must be an integer", 400)

    async with getattr(cog.config.guild(guild), sync_type)() as syncs:
        if idx < 0 or idx >= len(syncs):
            return json_error("not_found", f"Index {idx} out of range (0–{len(syncs)-1})", 404)
        removed = syncs.pop(idx)

    return web.json_response({"deleted_index": idx, "pair": [str(r) for r in removed]})


async def handle_rolesyncer_del_one(request: web.Request) -> web.Response:
    return await _rolesyncer_delete(request, "onesync")


async def handle_rolesyncer_del_two(request: web.Request) -> web.Response:
    return await _rolesyncer_delete(request, "twosync")
