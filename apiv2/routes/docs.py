"""
OpenAPI 3.0 specification and Swagger UI routes.
"""

import re
import logging

from aiohttp import web

from ..server import APP_BOT_KEY

logger = logging.getLogger("red.killerbite95.apiv2.routes.docs")

PREFIX = "/api/v2"


def register_routes(app: web.Application):
    """Register documentation routes (public, no auth required)."""
    app.router.add_get(f"{PREFIX}/openapi.json", handle_openapi)
    app.router.add_get(f"{PREFIX}/docs", handle_swagger_ui)


def _path_to_tag(path: str) -> str:
    """Extract a tag name from a route path."""
    parts = path.replace(f"{PREFIX}/", "").split("/")
    parts = [p for p in parts if not p.startswith("{")]
    if not parts:
        return "Core"
    tag = parts[0]
    return tag.replace("-", " ").title()


def generate_openapi_spec(app: web.Application) -> dict:
    """Auto-generate OpenAPI 3.0 spec from registered routes."""
    spec = {
        "openapi": "3.0.3",
        "info": {
            "title": "APIv2 — Red-DiscordBot REST API",
            "version": "2.0.0",
            "description": (
                "REST API embedded in Red-DiscordBot.\n\n"
                "Authenticate with `Authorization: Bearer <API_KEY>`.\n\n"
                "Rate limited per key (default 200 req/min)."
            ),
        },
        "servers": [{"url": "/", "description": "Current server"}],
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": "API key created with [p]apiv2 key create",
                }
            }
        },
        "security": [{"bearerAuth": []}],
        "paths": {},
    }

    skip_paths = {f"{PREFIX}/openapi.json", f"{PREFIX}/docs"}

    for resource in app.router.resources():
        info = resource.get_info()
        path = info.get("formatter") or info.get("path")
        if not path or not path.startswith(PREFIX) or path in skip_paths:
            continue

        for route in resource:
            method = route.method.lower()
            if method == "head":
                continue

            handler = route.handler
            doc = (handler.__doc__ or "").strip()
            # Extract summary from docstring: text after "—" or first line
            summary_line = doc.split("—")[-1].strip() if "—" in doc else doc.split("\n")[0]

            tag = _path_to_tag(path)

            operation = {
                "summary": summary_line,
                "tags": [tag],
                "responses": {
                    "200": {"description": "Success"},
                    "401": {"description": "Unauthorized"},
                    "429": {"description": "Rate limited"},
                },
            }

            # No auth for health check
            if path == f"{PREFIX}/health":
                operation["security"] = []

            # Extract path parameters
            params = re.findall(r"\{(\w+)\}", path)
            if params:
                operation["parameters"] = [
                    {
                        "name": p,
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                    for p in params
                ]

            # Methods that typically have a request body
            if method in ("post", "put", "patch"):
                operation["requestBody"] = {
                    "content": {
                        "application/json": {
                            "schema": {"type": "object"},
                        }
                    }
                }

            # Merge handler metadata if present (from @api_route decorator)
            meta = getattr(handler, "__api_meta__", None)
            if meta:
                if meta.get("summary"):
                    operation["summary"] = meta["summary"]
                if meta.get("description"):
                    operation["description"] = meta["description"]
                if meta.get("tags"):
                    operation["tags"] = meta["tags"]

            spec["paths"].setdefault(path, {})[method] = operation

    return spec


SWAGGER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>APIv2 — Swagger UI</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
    <style>
        body { margin: 0; padding: 0; background: #fafafa; }
        .swagger-ui .topbar { display: none; }
    </style>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script>
        SwaggerUIBundle({
            url: '/api/v2/openapi.json',
            dom_id: '#swagger-ui',
            deepLinking: true,
            presets: [
                SwaggerUIBundle.presets.apis,
                SwaggerUIBundle.SwaggerUIStandalonePreset
            ],
            layout: "BaseLayout",
        });
    </script>
</body>
</html>"""


async def handle_openapi(request: web.Request) -> web.Response:
    """GET /api/v2/openapi.json — Auto-generated OpenAPI 3.0 specification."""
    spec = generate_openapi_spec(request.app)
    return web.json_response(spec)


async def handle_swagger_ui(request: web.Request) -> web.Response:
    """GET /api/v2/docs — Swagger UI for interactive API exploration."""
    return web.Response(text=SWAGGER_HTML, content_type="text/html")
