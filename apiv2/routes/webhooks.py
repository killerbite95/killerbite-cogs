"""
Webhook management API routes.
"""

import logging

from aiohttp import web

from ..server import APP_WEBHOOK_MANAGER_KEY, json_error
from ..webhooks import SUPPORTED_EVENTS

logger = logging.getLogger("red.killerbite95.apiv2.routes.webhooks")

PREFIX = "/api/v2"


def register_routes(app: web.Application):
    """Register webhook management routes."""
    app.router.add_get(f"{PREFIX}/webhooks", handle_list)
    app.router.add_post(f"{PREFIX}/webhooks", handle_create)
    app.router.add_delete(f"{PREFIX}/webhooks/{{name}}", handle_delete)
    app.router.add_post(f"{PREFIX}/webhooks/{{name}}/test", handle_test)


async def handle_list(request: web.Request) -> web.Response:
    """GET /api/v2/webhooks — List all configured outgoing webhooks."""
    wh = request.app[APP_WEBHOOK_MANAGER_KEY]
    webhooks = await wh.list_webhooks()
    return web.json_response(webhooks)


async def handle_create(request: web.Request) -> web.Response:
    """POST /api/v2/webhooks — Create a new outgoing webhook."""
    wh = request.app[APP_WEBHOOK_MANAGER_KEY]

    try:
        data = await request.json()
    except Exception:
        return json_error(400, "bad_request", "Invalid JSON body")

    name = data.get("name")
    url = data.get("url")
    events = data.get("events", [])
    guild_id = data.get("guild_id")

    if not name or not isinstance(name, str):
        return json_error(400, "bad_request", "Missing or invalid 'name'")
    if not url or not isinstance(url, str):
        return json_error(400, "bad_request", "Missing or invalid 'url'")
    if not url.startswith(("https://", "http://")):
        return json_error(400, "bad_request", "URL must start with http:// or https://")
    if not events or not isinstance(events, list):
        return json_error(400, "bad_request", "'events' must be a non-empty list")

    invalid = set(events) - SUPPORTED_EVENTS
    if invalid:
        return json_error(
            400, "bad_request",
            f"Invalid events: {', '.join(sorted(invalid))}. "
            f"Supported: {', '.join(sorted(SUPPORTED_EVENTS))}",
        )

    if guild_id is not None:
        try:
            guild_id = int(guild_id)
        except (ValueError, TypeError):
            return json_error(400, "bad_request", "'guild_id' must be an integer")

    secret = await wh.create(name, url, events, guild_id)
    if secret is None:
        return json_error(409, "conflict", f"Webhook '{name}' already exists")

    return web.json_response({
        "name": name,
        "url": url,
        "events": events,
        "guild_id": guild_id,
        "secret": secret,
        "message": "Webhook created. Save the secret for signature verification.",
    }, status=201)


async def handle_delete(request: web.Request) -> web.Response:
    """DELETE /api/v2/webhooks/{name} — Delete a webhook."""
    wh = request.app[APP_WEBHOOK_MANAGER_KEY]
    name = request.match_info["name"]

    success = await wh.delete(name)
    if not success:
        return json_error(404, "not_found", f"Webhook '{name}' not found")

    return web.json_response({"message": f"Webhook '{name}' deleted"})


async def handle_test(request: web.Request) -> web.Response:
    """POST /api/v2/webhooks/{name}/test — Send a test ping to a webhook."""
    wh = request.app[APP_WEBHOOK_MANAGER_KEY]
    name = request.match_info["name"]

    result = await wh.test(name)
    if result is None:
        return json_error(404, "not_found", f"Webhook '{name}' not found")

    if isinstance(result, int):
        return web.json_response({
            "message": f"Test ping sent to '{name}'",
            "response_status": result,
        })

    return web.json_response({
        "message": f"Test ping failed for '{name}'",
        "error": result,
    }, status=502)
