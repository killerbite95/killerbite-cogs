"""
Decorator for external cogs to register API routes with APIv2.

Usage in an external cog::

    try:
        from apiv2.decorator import api_route
    except ImportError:
        def api_route(method, path, **kwargs):
            def decorator(func):
                return func
            return decorator

    class MyCog(commands.Cog):
        @api_route("GET", "/api/v2/mycog/status")
        async def handle_status(self, request):
            from aiohttp import web
            return web.json_response({"status": "ok"})
"""

API_ROUTE_ATTR = "__api_route__"


def api_route(
    method: str,
    path: str,
    *,
    summary: str = "",
    description: str = "",
    tags: list[str] | None = None,
):
    """Mark a cog method as an API route.

    The method must accept ``(self, request)`` and return ``web.Response``.

    Args:
        method: HTTP method (GET, POST, PUT, PATCH, DELETE).
        path: URL path, e.g. ``/api/v2/mycog/data``.
        summary: Short summary for OpenAPI docs.
        description: Detailed description for OpenAPI docs.
        tags: OpenAPI tags.
    """
    def decorator(func):
        if not hasattr(func, API_ROUTE_ATTR):
            setattr(func, API_ROUTE_ATTR, [])
        getattr(func, API_ROUTE_ATTR).append({
            "method": method.upper(),
            "path": path,
            "summary": summary,
            "description": description,
            "tags": tags,
        })
        return func

    return decorator
