"""
Channels and messaging API routes.
"""

import logging
from typing import TYPE_CHECKING

import discord
from aiohttp import web

from ..server import APP_BOT_KEY, json_error

if TYPE_CHECKING:
    from redbot.core.bot import Red

logger = logging.getLogger("red.killerbite95.apiv2.routes.messaging")

PREFIX = "/api/v2"


def register_routes(app: web.Application):
    """Register channel and messaging routes."""
    app.router.add_get(f"{PREFIX}/guilds/{{guild_id}}/channels", handle_channels_list)
    app.router.add_post(
        f"{PREFIX}/guilds/{{guild_id}}/channels/{{channel_id}}/messages",
        handle_send_message,
    )
    app.router.add_post(
        f"{PREFIX}/guilds/{{guild_id}}/channels/{{channel_id}}/messages/{{message_id}}/react",
        handle_add_reaction,
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


async def handle_channels_list(request: web.Request) -> web.Response:
    """GET /api/v2/guilds/{guild_id}/channels"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild_or_error(bot, request.match_info["guild_id"])
    if err:
        return err

    channels = []
    for ch in guild.channels:
        data = {
            "id": str(ch.id),
            "name": ch.name,
            "type": str(ch.type),
            "position": ch.position,
            "category_id": str(ch.category_id) if ch.category_id else None,
            "category_name": ch.category.name if ch.category else None,
        }
        if isinstance(ch, (discord.TextChannel, discord.VoiceChannel)):
            data["nsfw"] = getattr(ch, "nsfw", False)
        if isinstance(ch, discord.TextChannel):
            data["topic"] = ch.topic
        if isinstance(ch, discord.VoiceChannel):
            data["bitrate"] = ch.bitrate
            data["user_limit"] = ch.user_limit
        channels.append(data)

    channels.sort(key=lambda c: c["position"])
    return web.json_response(channels)


async def handle_send_message(request: web.Request) -> web.Response:
    """POST /api/v2/guilds/{guild_id}/channels/{channel_id}/messages"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild_or_error(bot, request.match_info["guild_id"])
    if err:
        return err

    try:
        channel_id = int(request.match_info["channel_id"])
    except ValueError:
        return json_error(400, "bad_request", "channel_id must be an integer")

    channel = guild.get_channel(channel_id) or guild.get_thread(channel_id)
    if channel is None:
        return json_error(404, "not_found", f"Channel {channel_id} not found in guild")

    if not isinstance(channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
        return json_error(422, "validation_error", "Cannot send messages to this channel type")

    try:
        body = await request.json()
    except Exception:
        return json_error(400, "bad_request", "Invalid JSON body")

    content = body.get("content")
    embed_data = body.get("embed")

    if not content and not embed_data:
        return json_error(422, "validation_error", "Provide content and/or embed")

    embed = None
    if embed_data:
        try:
            embed = discord.Embed(
                title=embed_data.get("title"),
                description=embed_data.get("description"),
                color=embed_data.get("color"),
                url=embed_data.get("url"),
            )
            for field in embed_data.get("fields", []):
                embed.add_field(
                    name=field.get("name", "\u200b"),
                    value=field.get("value", "\u200b"),
                    inline=field.get("inline", True),
                )
            if embed_data.get("footer"):
                embed.set_footer(text=embed_data["footer"].get("text", ""))
            if embed_data.get("thumbnail"):
                embed.set_thumbnail(url=embed_data["thumbnail"])
            if embed_data.get("image"):
                embed.set_image(url=embed_data["image"])
        except Exception as e:
            return json_error(422, "validation_error", f"Invalid embed: {e}")

    try:
        msg = await channel.send(content=content, embed=embed)
    except discord.Forbidden:
        return json_error(403, "forbidden", "Bot lacks permission to send messages in this channel")
    except Exception as e:
        return json_error(500, "internal_error", f"Send failed: {e}")

    return web.json_response({
        "ok": True,
        "message_id": str(msg.id),
        "channel_id": str(channel.id),
    })


async def handle_add_reaction(request: web.Request) -> web.Response:
    """POST /api/v2/guilds/{guild_id}/channels/{channel_id}/messages/{message_id}/react"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild_or_error(bot, request.match_info["guild_id"])
    if err:
        return err

    try:
        channel_id = int(request.match_info["channel_id"])
        message_id = int(request.match_info["message_id"])
    except ValueError:
        return json_error(400, "bad_request", "channel_id and message_id must be integers")

    channel = guild.get_channel(channel_id) or guild.get_thread(channel_id)
    if channel is None:
        return json_error(404, "not_found", f"Channel {channel_id} not found")

    try:
        body = await request.json()
    except Exception:
        return json_error(400, "bad_request", "Invalid JSON body")

    emoji = body.get("emoji")
    if not emoji:
        return json_error(422, "validation_error", "emoji is required")

    try:
        msg = await channel.fetch_message(message_id)
    except discord.NotFound:
        return json_error(404, "not_found", f"Message {message_id} not found")
    except discord.Forbidden:
        return json_error(403, "forbidden", "Bot lacks permission to read messages")

    try:
        await msg.add_reaction(emoji)
    except discord.HTTPException as e:
        return json_error(422, "validation_error", f"Invalid emoji or reaction failed: {e}")

    return web.json_response({"ok": True, "emoji": emoji, "message_id": str(message_id)})
