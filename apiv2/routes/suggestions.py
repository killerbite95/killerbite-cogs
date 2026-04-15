"""
SimpleSuggestions API routes — requires SimpleSuggestions cog loaded.
"""

import logging
from typing import TYPE_CHECKING

from aiohttp import web

from ..server import APP_BOT_KEY, json_error

if TYPE_CHECKING:
    from redbot.core.bot import Red

logger = logging.getLogger("red.killerbite95.apiv2.routes.suggestions")

PREFIX = "/api/v2"

# Valid status values (mirrors SuggestionStatus enum)
VALID_STATUSES = {
    "pending", "in_review", "planned", "in_progress",
    "approved", "implemented", "denied", "duplicate", "wont_do",
}


def register_routes(app: web.Application):
    """Register SimpleSuggestions routes."""
    app.router.add_get(f"{PREFIX}/guilds/{{guild_id}}/suggestions", handle_suggestions_list)
    app.router.add_get(
        f"{PREFIX}/guilds/{{guild_id}}/suggestions/{{suggestion_id}}",
        handle_suggestion_detail,
    )
    app.router.add_patch(
        f"{PREFIX}/guilds/{{guild_id}}/suggestions/{{suggestion_id}}",
        handle_suggestion_update,
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
    cog = bot.get_cog("SimpleSuggestions")
    if cog is None:
        return None, json_error(503, "cog_unavailable", "SimpleSuggestions cog is not loaded")
    return cog, None


def _serialize_suggestion(s) -> dict:
    return {
        "id": s.suggestion_id,
        "message_id": str(s.message_id) if s.message_id else None,
        "content": s.content,
        "author_id": str(s.author_id),
        "status": s.status.value,
        "created_at": s.created_at,
        "thread_id": str(s.thread_id) if s.thread_id else None,
        "upvotes": s.upvotes,
        "downvotes": s.downvotes,
        "score": s.score,
        "reason": s.reason,
        "history": s.history,
    }


async def handle_suggestions_list(request: web.Request) -> web.Response:
    """GET /api/v2/guilds/{guild_id}/suggestions?status=pending&limit=50&offset=0"""
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

    # Get SuggestionStatus from the cog's storage module
    import sys
    storage_module = sys.modules.get(type(cog.storage).__module__)
    SuggestionStatus = getattr(storage_module, "SuggestionStatus", None) if storage_module else None

    filter_status = None
    if status_filter:
        if status_filter not in VALID_STATUSES:
            return json_error(422, "validation_error", f"Invalid status. Valid: {', '.join(sorted(VALID_STATUSES))}")
        if SuggestionStatus:
            filter_status = SuggestionStatus(status_filter)

    suggestions = await cog.storage.get_all_suggestions(guild, status_filter=filter_status)
    total = len(suggestions)
    suggestions = suggestions[offset : offset + limit]

    return web.json_response({
        "suggestions": [_serialize_suggestion(s) for s in suggestions],
        "count": len(suggestions),
        "total": total,
    })


async def handle_suggestion_detail(request: web.Request) -> web.Response:
    """GET /api/v2/guilds/{guild_id}/suggestions/{suggestion_id}"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild_or_error(bot, request.match_info["guild_id"])
    if err:
        return err
    cog, err = _get_cog_or_503(bot)
    if err:
        return err

    try:
        suggestion_id = int(request.match_info["suggestion_id"])
    except ValueError:
        return json_error(400, "bad_request", "suggestion_id must be an integer")

    suggestion = await cog.storage.get_suggestion(guild, suggestion_id)
    if suggestion is None:
        return json_error(404, "not_found", f"Suggestion #{suggestion_id} not found")

    return web.json_response(_serialize_suggestion(suggestion))


async def handle_suggestion_update(request: web.Request) -> web.Response:
    """PATCH /api/v2/guilds/{guild_id}/suggestions/{suggestion_id}
    
    Body: { "status": "approved", "reason": "...", "changed_by": 123456 }
    """
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild_or_error(bot, request.match_info["guild_id"])
    if err:
        return err
    cog, err = _get_cog_or_503(bot)
    if err:
        return err

    try:
        suggestion_id = int(request.match_info["suggestion_id"])
    except ValueError:
        return json_error(400, "bad_request", "suggestion_id must be an integer")

    try:
        body = await request.json()
    except Exception:
        return json_error(400, "bad_request", "Invalid JSON body")

    new_status_str = body.get("status")
    if not new_status_str or new_status_str not in VALID_STATUSES:
        return json_error(422, "validation_error", f"status is required. Valid: {', '.join(sorted(VALID_STATUSES))}")

    reason = body.get("reason")
    changed_by = body.get("changed_by", 0)
    if not isinstance(changed_by, int):
        return json_error(422, "validation_error", "changed_by must be a user ID integer")

    import sys
    storage_module = sys.modules.get(type(cog.storage).__module__)
    SuggestionStatus = getattr(storage_module, "SuggestionStatus", None)
    if not SuggestionStatus:
        return json_error(500, "internal_error", "Cannot resolve SuggestionStatus from cog")
    new_status = SuggestionStatus(new_status_str)

    updated = await cog.storage.update_status(
        guild, suggestion_id, new_status, changed_by, reason
    )
    if updated is None:
        return json_error(404, "not_found", f"Suggestion #{suggestion_id} not found")

    # Also update the Discord embed if possible
    try:
        # Get create_suggestion_embed from the cog's embeds module
        cog_pkg = type(cog).__module__.rsplit('.', 1)[0]
        embeds_module = sys.modules.get(f"{cog_pkg}.embeds")
        create_suggestion_embed = getattr(embeds_module, "create_suggestion_embed", None)
        if not create_suggestion_embed:
            raise ImportError("embeds module not found")

        channel_id = await cog.config.guild(guild).suggestion_channel()
        if channel_id:
            channel = guild.get_channel(channel_id)
            if channel and updated.message_id:
                try:
                    msg = await channel.fetch_message(updated.message_id)
                    author = guild.get_member(updated.author_id)
                    embed = create_suggestion_embed(updated, author)
                    await msg.edit(embed=embed)
                except Exception:
                    pass  # Non-critical — data is updated even if embed edit fails
    except Exception:
        pass

    return web.json_response({
        "ok": True,
        "suggestion": _serialize_suggestion(updated),
    })
