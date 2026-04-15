"""
aiohttp application factory and middlewares for APIv2.
"""

import time
import logging
from typing import TYPE_CHECKING

from aiohttp import web

from .auth import KeyManager, RateLimiter

if TYPE_CHECKING:
    from redbot.core.bot import Red

logger = logging.getLogger("red.killerbite95.apiv2.server")

# Key used to store bot reference in app dict
APP_BOT_KEY = "bot"
APP_KEY_MANAGER_KEY = "key_manager"
APP_RATE_LIMITER_KEY = "rate_limiter"
APP_START_TIME_KEY = "start_time"
APP_WEBHOOK_MANAGER_KEY = "webhook_manager"


def json_error(status: int, error: str, message: str) -> web.Response:
    """Create a standardized JSON error response."""
    return web.json_response(
        {"error": error, "message": message, "status": status},
        status=status,
    )


@web.middleware
async def auth_middleware(request: web.Request, handler):
    """Validate API key from Authorization header.
    
    Exempt paths (like /health) skip auth.
    """
    # Allow public endpoints without auth
    if request.path in ("/api/v2/health", "/api/v2/docs", "/api/v2/openapi.json"):
        return await handler(request)

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return json_error(401, "unauthorized", "Missing or invalid Authorization header. Use: Bearer <API_KEY>")

    token = auth_header[7:]  # Strip "Bearer "
    key_manager: KeyManager = request.app[APP_KEY_MANAGER_KEY]
    key_data = key_manager.validate_token(token)

    if key_data is None:
        return json_error(401, "unauthorized", "Invalid or revoked API key")

    # Store key info in request for logging
    request["api_key_name"] = key_data["name"]

    # Rate limiting
    rate_limiter: RateLimiter = request.app[APP_RATE_LIMITER_KEY]
    allowed, remaining = rate_limiter.is_allowed(key_data["name"])

    if not allowed:
        retry_after = rate_limiter.get_retry_after(key_data["name"])
        resp = json_error(429, "rate_limited", f"Rate limit exceeded. Retry after {retry_after:.0f}s")
        resp.headers["Retry-After"] = str(int(retry_after))
        resp.headers["X-RateLimit-Remaining"] = "0"
        return resp

    resp = await handler(request)
    resp.headers["X-RateLimit-Remaining"] = str(remaining)

    # Record usage asynchronously (fire and forget)
    request.app.loop.create_task(key_manager.record_usage(token))

    return resp


@web.middleware
async def logging_middleware(request: web.Request, handler):
    """Log every request with timing."""
    start = time.monotonic()
    try:
        response = await handler(request)
    except web.HTTPException as e:
        elapsed = (time.monotonic() - start) * 1000
        key_name = request.get("api_key_name", "-")
        ip = request.headers.get("X-Real-IP", request.remote)
        logger.info(
            f"{request.method} {request.path} → {e.status} ({elapsed:.1f}ms) "
            f"[key={key_name} ip={ip}]"
        )
        raise
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        key_name = request.get("api_key_name", "-")
        ip = request.headers.get("X-Real-IP", request.remote)
        logger.error(
            f"{request.method} {request.path} → 500 ({elapsed:.1f}ms) "
            f"[key={key_name} ip={ip}] ERROR: {e}"
        )
        return json_error(500, "internal_error", "An internal error occurred")

    elapsed = (time.monotonic() - start) * 1000
    key_name = request.get("api_key_name", "-")
    ip = request.headers.get("X-Real-IP", request.remote)
    logger.info(
        f"{request.method} {request.path} → {response.status} ({elapsed:.1f}ms) "
        f"[key={key_name} ip={ip}]"
    )
    return response


@web.middleware
async def cors_middleware(request: web.Request, handler):
    """Handle CORS preflight and add headers to every response."""
    if request.method == "OPTIONS":
        resp = web.Response(status=204)
    else:
        try:
            resp = await handler(request)
        except web.HTTPException as exc:
            resp = exc

    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
    resp.headers["Access-Control-Max-Age"] = "86400"
    return resp


@web.middleware
async def error_middleware(request: web.Request, handler):
    """Catch unhandled exceptions and return JSON errors."""
    try:
        return await handler(request)
    except web.HTTPNotFound:
        return json_error(404, "not_found", f"Endpoint not found: {request.method} {request.path}")
    except web.HTTPMethodNotAllowed:
        return json_error(405, "method_not_allowed", f"Method {request.method} not allowed for {request.path}")
    except web.HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unhandled error on {request.method} {request.path}: {e}", exc_info=True)
        return json_error(500, "internal_error", "An internal error occurred")


def create_app(bot: "Red", key_manager: KeyManager, rate_limiter: RateLimiter, webhook_manager=None) -> web.Application:
    """Create the aiohttp application with all middlewares."""
    app = web.Application(
        middlewares=[
            cors_middleware,
            error_middleware,
            logging_middleware,
            auth_middleware,
        ]
    )
    app[APP_BOT_KEY] = bot
    app[APP_KEY_MANAGER_KEY] = key_manager
    app[APP_RATE_LIMITER_KEY] = rate_limiter
    app[APP_START_TIME_KEY] = time.monotonic()
    app[APP_WEBHOOK_MANAGER_KEY] = webhook_manager
    return app
