"""
TicketsTrini API routes — requires TicketsTrini cog loaded.
"""

import logging
from typing import TYPE_CHECKING

import discord
from aiohttp import web

from ..server import APP_BOT_KEY, json_error

if TYPE_CHECKING:
    from redbot.core.bot import Red

logger = logging.getLogger("red.killerbite95.apiv2.routes.tickets")

PREFIX = "/api/v2"


def register_routes(app: web.Application):
    """Register TicketsTrini routes."""
    app.router.add_get(f"{PREFIX}/guilds/{{guild_id}}/tickets", handle_tickets_list)
    app.router.add_get(
        f"{PREFIX}/guilds/{{guild_id}}/tickets/panels", handle_panels_list
    )
    app.router.add_get(
        f"{PREFIX}/guilds/{{guild_id}}/tickets/{{channel_id}}", handle_ticket_detail
    )
    app.router.add_post(
        f"{PREFIX}/guilds/{{guild_id}}/tickets/{{channel_id}}/close",
        handle_ticket_close,
    )
    app.router.add_post(
        f"{PREFIX}/guilds/{{guild_id}}/tickets/{{channel_id}}/message",
        handle_ticket_message,
    )


def _get_guild_or_error(bot: "Red", guild_id_str: str):
    try:
        guild_id = int(guild_id_str)
    except ValueError:
        return None, json_error(400, "bad_request", "guild_id must be an integer")
    guild = bot.get_guild(guild_id)
    if guild is None:
        return None, json_error(404, "not_found", f"Guild {guild_id} not found")
    return guild, None


def _get_cog_or_503(bot: "Red"):
    cog = bot.get_cog("TicketsTrini")
    if cog is None:
        return None, json_error(503, "cog_unavailable", "TicketsTrini cog is not loaded")
    return cog, None


def _serialize_ticket(channel_id: str, owner_id: str, ticket: dict) -> dict:
    return {
        "channel_id": channel_id,
        "owner_id": owner_id,
        "panel": ticket.get("panel"),
        "status": ticket.get("status", "open"),
        "opened_at": ticket.get("opened"),
        "claimed_by": str(ticket["claimed_by"]) if ticket.get("claimed_by") else None,
        "claimed_at": ticket.get("claimed_at"),
        "escalated": ticket.get("escalated", False),
        "escalation_level": ticket.get("escalation_level", 0),
        "notes_count": len(ticket.get("notes", [])),
        "last_user_message": ticket.get("last_user_message"),
        "last_staff_message": ticket.get("last_staff_message"),
    }


async def handle_tickets_list(request: web.Request) -> web.Response:
    """GET /api/v2/guilds/{guild_id}/tickets?status=open&limit=50&offset=0"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild_or_error(bot, request.match_info["guild_id"])
    if err:
        return err
    cog, err = _get_cog_or_503(bot)
    if err:
        return err

    status_filter = request.query.get("status")
    try:
        limit = min(int(request.query.get("limit", "50")), 500)
        offset = int(request.query.get("offset", "0"))
    except ValueError:
        return json_error(400, "bad_request", "limit and offset must be integers")

    opened = await cog.config.guild(guild).opened()
    tickets = []
    for uid, channels in opened.items():
        for cid, ticket_data in channels.items():
            t = _serialize_ticket(cid, uid, ticket_data)
            if status_filter and t["status"] != status_filter:
                continue
            tickets.append(t)

    # Sort by opened_at descending
    tickets.sort(key=lambda t: t.get("opened_at", ""), reverse=True)
    total = len(tickets)
    tickets = tickets[offset : offset + limit]

    return web.json_response({"tickets": tickets, "count": len(tickets), "total": total})


async def handle_ticket_detail(request: web.Request) -> web.Response:
    """GET /api/v2/guilds/{guild_id}/tickets/{channel_id}"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild_or_error(bot, request.match_info["guild_id"])
    if err:
        return err
    cog, err = _get_cog_or_503(bot)
    if err:
        return err

    channel_id = request.match_info["channel_id"]

    opened = await cog.config.guild(guild).opened()
    for uid, channels in opened.items():
        if channel_id in channels:
            ticket = _serialize_ticket(channel_id, uid, channels[channel_id])
            ticket["notes"] = channels[channel_id].get("notes", [])
            return web.json_response(ticket)

    return json_error(404, "not_found", f"Ticket with channel {channel_id} not found")


async def handle_panels_list(request: web.Request) -> web.Response:
    """GET /api/v2/guilds/{guild_id}/tickets/panels"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild_or_error(bot, request.match_info["guild_id"])
    if err:
        return err
    cog, err = _get_cog_or_503(bot)
    if err:
        return err

    panels = await cog.config.guild(guild).panels()
    result = []
    for name, panel in panels.items():
        result.append({
            "name": name,
            "category_id": str(panel.get("category_id", 0)),
            "channel_id": str(panel.get("channel_id", 0)),
            "message_id": str(panel.get("message_id", 0)),
            "disabled": panel.get("disabled", False),
            "button_text": panel.get("button_text", "Open a Ticket"),
            "button_color": panel.get("button_color", "blue"),
            "threads": panel.get("threads", False),
            "ticket_num": panel.get("ticket_num", 0),
            "log_channel": str(panel.get("log_channel", 0)) if panel.get("log_channel") else None,
            "max_claims": panel.get("max_claims", 1),
            "cooldown": panel.get("cooldown", 0),
            "priority": panel.get("priority", 0),
        })

    return web.json_response(result)


async def handle_ticket_close(request: web.Request) -> web.Response:
    """POST /api/v2/guilds/{guild_id}/tickets/{channel_id}/close"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild_or_error(bot, request.match_info["guild_id"])
    if err:
        return err
    cog, err = _get_cog_or_503(bot)
    if err:
        return err

    channel_id_str = request.match_info["channel_id"]
    try:
        channel_id = int(channel_id_str)
    except ValueError:
        return json_error(400, "bad_request", "channel_id must be an integer")

    try:
        body = await request.json()
    except Exception:
        body = {}

    reason = body.get("reason", "Closed via API")

    # Find ticket owner
    opened = await cog.config.guild(guild).opened()
    owner_id = None
    for uid, channels in opened.items():
        if channel_id_str in channels:
            owner_id = int(uid)
            break

    if owner_id is None:
        return json_error(404, "not_found", f"Ticket with channel {channel_id} not found")

    channel = guild.get_channel_or_thread(channel_id)
    if channel is None:
        return json_error(404, "not_found", f"Channel {channel_id} no longer exists")

    member = guild.get_member(owner_id)
    if member is None:
        # User may have left — create a stub Object
        member = discord.Object(id=owner_id)
        member.name = str(owner_id)
        member.display_name = str(owner_id)

    conf = await cog.config.guild(guild).all()

    try:
        import sys
        cog_pkg = type(cog).__module__.rsplit('.', 1)[0]
        utils_module = sys.modules.get(f"{cog_pkg}.common.utils")
        close_ticket = getattr(utils_module, "close_ticket", None)
        if not close_ticket:
            return json_error(500, "internal_error", "Cannot resolve close_ticket from cog")
        await close_ticket(
            bot=bot,
            member=member,
            guild=guild,
            channel=channel,
            conf=conf,
            reason=reason,
            closedby="APIv2",
            config=cog.config,
        )
    except Exception as e:
        logger.error(f"Failed to close ticket {channel_id}: {e}", exc_info=True)
        return json_error(500, "internal_error", f"Failed to close ticket: {e}")

    return web.json_response({"ok": True, "action": "ticket_closed", "channel_id": channel_id_str})


async def handle_ticket_message(request: web.Request) -> web.Response:
    """POST /api/v2/guilds/{guild_id}/tickets/{channel_id}/message"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild_or_error(bot, request.match_info["guild_id"])
    if err:
        return err
    cog, err = _get_cog_or_503(bot)
    if err:
        return err

    try:
        channel_id = int(request.match_info["channel_id"])
    except ValueError:
        return json_error(400, "bad_request", "channel_id must be an integer")

    # Verify this channel is an open ticket
    opened = await cog.config.guild(guild).opened()
    found = False
    for uid, channels in opened.items():
        if str(channel_id) in channels:
            found = True
            break
    if not found:
        return json_error(404, "not_found", f"Ticket with channel {channel_id} not found")

    channel = guild.get_channel_or_thread(channel_id)
    if channel is None:
        return json_error(404, "not_found", f"Channel {channel_id} no longer exists")

    try:
        body = await request.json()
    except Exception:
        return json_error(400, "bad_request", "Invalid JSON body")

    content = body.get("content")
    if not content:
        return json_error(422, "validation_error", "content is required")

    try:
        msg = await channel.send(content)
    except discord.Forbidden:
        return json_error(403, "forbidden", "Bot lacks permission to send in this channel")

    return web.json_response({
        "ok": True,
        "message_id": str(msg.id),
        "channel_id": str(channel_id),
    })
