"""
GameServerMonitor API routes — requires GameServerMonitor cog loaded.
"""

import logging
from typing import TYPE_CHECKING

from aiohttp import web

from ..server import APP_BOT_KEY, json_error

if TYPE_CHECKING:
    from redbot.core.bot import Red

logger = logging.getLogger("red.killerbite95.apiv2.routes.servers")

PREFIX = "/api/v2"


def register_routes(app: web.Application):
    """Register GameServerMonitor routes."""
    app.router.add_get(f"{PREFIX}/guilds/{{guild_id}}/game-servers", handle_servers_list)
    app.router.add_get(
        f"{PREFIX}/guilds/{{guild_id}}/game-servers/{{server_key}}",
        handle_server_detail,
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
    cog = bot.get_cog("GameServerMonitor")
    if cog is None:
        return None, json_error(503, "cog_unavailable", "GameServerMonitor cog is not loaded")
    return cog, None


def _serialize_server(key: str, data: dict) -> dict:
    parts = key.rsplit(":", 1)
    ip = parts[0] if len(parts) == 2 else key
    port = parts[1] if len(parts) == 2 else "0"

    return {
        "key": key,
        "ip": ip,
        "port": int(port),
        "game": data.get("game", "unknown"),
        "domain": data.get("domain"),
        "channel_id": str(data.get("channel_id", 0)),
        "message_id": str(data["message_id"]) if data.get("message_id") else None,
        "last_status": data.get("last_status"),
        "last_online": data.get("last_online"),
        "last_offline": data.get("last_offline"),
        "total_queries": data.get("total_queries", 0),
        "successful_queries": data.get("successful_queries", 0),
        "server_id": data.get("server_id"),
    }


async def handle_servers_list(request: web.Request) -> web.Response:
    """GET /api/v2/guilds/{guild_id}/game-servers"""
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild_or_error(bot, request.match_info["guild_id"])
    if err:
        return err
    cog, err = _get_cog_or_503(bot)
    if err:
        return err

    servers = await cog.config.guild(guild).servers()
    result = [_serialize_server(key, data) for key, data in servers.items()]

    return web.json_response(result)


async def handle_server_detail(request: web.Request) -> web.Response:
    """GET /api/v2/guilds/{guild_id}/game-servers/{server_key}
    
    server_key format: ip:port (e.g. 1.2.3.4:27015)
    """
    bot: "Red" = request.app[APP_BOT_KEY]
    guild, err = _get_guild_or_error(bot, request.match_info["guild_id"])
    if err:
        return err
    cog, err = _get_cog_or_503(bot)
    if err:
        return err

    server_key = request.match_info["server_key"]
    servers = await cog.config.guild(guild).servers()

    if server_key not in servers:
        return json_error(404, "not_found", f"Server '{server_key}' not found")

    data = _serialize_server(server_key, servers[server_key])

    # Try live query for current status
    try:
        from gameservermonitor.models import GameType, ServerData

        server_data = ServerData.from_dict(server_key, servers[server_key])
        parts = server_key.rsplit(":", 1)
        host = parts[0]
        port = int(parts[1]) if len(parts) == 2 else 27015

        result = await cog.query_service.query_server(
            host=host,
            port=port,
            game=GameType(server_data.game),
            use_cache=True,
            fetch_players=True,
        )

        data["live"] = {
            "online": result.success,
            "status": result.status.value if result.status else "unknown",
            "players": result.players,
            "max_players": result.max_players,
            "map": result.map_name,
            "hostname": result.hostname,
            "is_passworded": result.is_passworded,
            "latency_ms": round(result.latency_ms, 1) if result.latency_ms else None,
            "player_list": result.player_list or [],
        }
    except Exception as e:
        data["live"] = {"error": str(e)}

    return web.json_response(data)
