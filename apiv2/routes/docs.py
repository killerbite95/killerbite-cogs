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


# ---------------------------------------------------------------------------
# Path → Cog tag mapping
# Evaluated in order — first match wins.
# ---------------------------------------------------------------------------
_PATH_TAG_RULES: list[tuple[str, str]] = [
    # System
    (r"^/api/v2/health$",               "Core"),
    (r"^/api/v2/info$",                 "Core"),
    (r"^/api/v2/guilds$",               "Core"),
    (r"^/api/v2/guilds/\{[^}]+\}$",     "Core"),
    (r"^/api/v2/webhooks",              "Webhooks"),
    # Members & roles
    (r"/bans",                          "Moderation"),
    (r"/kick$",                         "Moderation"),
    (r"/timeout",                       "Moderation"),
    (r"/members/\{[^}]+\}/roles",       "Roles"),
    (r"/members",                       "Members"),
    (r"/guilds/\{[^}]+\}/roles",        "Roles"),
    # Channels & messaging
    (r"/channels/\{[^}]+\}/sticky",     "Sticky"),
    (r"/channels/\{[^}]+\}/messages",   "Messaging"),
    (r"/channels",                      "Channels"),
    (r"/stickies$",                     "Sticky"),
    # Economy
    (r"/economy",                       "Economy"),
    # Advanced moderation
    (r"/warnings",                      "Warnings"),
    (r"/cases",                         "Modlog"),
    (r"/security",                      "Security"),
    (r"/modlog",                        "ExtendedModLog"),
    # Cog-specific
    (r"/tickets",                       "Tickets"),
    (r"/suggestions",                   "Suggestions"),
    (r"/game-servers",                  "GameServerMonitor"),
    (r"/giveaways",                     "Giveaways"),
    (r"/tags",                          "Tags"),
    (r"/rolesbuttons",                  "RolesButtons"),
    (r"/rolesyncer",                    "RoleSyncer"),
    (r"/welcome",                       "Welcome"),
    (r"/voicelogs",                     "VoiceLogs"),
    (r"/autonick",                      "AutoNick"),
    (r"/voice/massmove",                "Mover"),    (r"/colacoins",                     "ColaCoins"),]

# Root-level tag definitions — controls display order + descriptions in Swagger UI
_TAG_DEFINITIONS: list[dict] = [
    {"name": "Core",             "description": "Health check, bot info, guild listing"},
    {"name": "Members",          "description": "Guild member lookup and nickname management"},
    {"name": "Roles",            "description": "Role assignment and bulk role management"},
    {"name": "Channels",         "description": "Channel listing"},
    {"name": "Messaging",        "description": "Send messages and embeds, add reactions"},
    {"name": "Moderation",       "description": "Kick, ban, unban, timeout"},
    {"name": "Webhooks",         "description": "Outgoing webhooks on Discord events"},
    {"name": "Economy",          "description": "Red bank balance, leaderboard, ExtendedEconomy costs — *cog optional*"},
    {"name": "Warnings",         "description": "User warnings via Red Mod cog"},
    {"name": "Modlog",           "description": "Modlog cases (ban, kick, warn…)"},
    {"name": "Security",         "description": "Security cog — quarantine, modules, whitelist — *requiere cog*"},
    {"name": "ExtendedModLog",   "description": "ExtendedModLog event settings — *requiere cog*"},
    {"name": "Tickets",          "description": "TicketsTrini — open/close/message tickets — *requiere cog*"},
    {"name": "Suggestions",      "description": "SimpleSuggestions cog — *requiere cog*"},
    {"name": "GameServerMonitor","description": "Game server status — *requiere cog*"},
    {"name": "Giveaways",        "description": "Create, end and reroll giveaways — *requiere cog*"},
    {"name": "Tags",             "description": "TagScript tags — CRUD + invoke with variables — *requiere cog*"},
    {"name": "RolesButtons",     "description": "Role-button panels — *requiere cog*"},
    {"name": "RoleSyncer",       "description": "One-way / two-way role sync rules — *requiere cog*"},
    {"name": "Welcome",          "description": "Join/leave/ban/unban messages and DM whispers — *requiere cog*"},
    {"name": "Sticky",           "description": "Sticky messages pinned to channels — *requiere cog*"},
    {"name": "VoiceLogs",        "description": "Voice channel session history — *requiere cog*"},
    {"name": "AutoNick",         "description": "Self-service nickname channel + forbidden word list — *requiere cog*"},
    {"name": "Mover",            "description": "Mass-move members between voice channels — *requiere cog*"},
    {"name": "ColaCoins",        "description": "ColaCoins custom currency — give, remove, balance, leaderboard — *requiere cog*"},
]

# x-tagGroups for Redoc (ignored by SwaggerUI but harmless)
_TAG_GROUPS: list[dict] = [
    {"name": "🤖 Sistema",            "tags": ["Core", "Webhooks"]},
    {"name": "👥 Miembros & Roles",   "tags": ["Members", "Roles", "Moderation"]},
    {"name": "💬 Canales",            "tags": ["Channels", "Messaging"]},
    {"name": "💰 Economía",           "tags": ["Economy", "ColaCoins"]},
    {"name": "🔨 Moderación avanzada","tags": ["Warnings", "Modlog", "Security", "ExtendedModLog"]},
    {"name": "🎫 Cogs — Gestión",     "tags": ["Tickets", "Suggestions", "GameServerMonitor"]},
    {"name": "🎉 Comunidad",          "tags": ["Giveaways", "Tags", "RolesButtons", "RoleSyncer"]},
    {"name": "⚙️ Configuración",      "tags": ["Welcome", "Sticky", "VoiceLogs", "AutoNick", "Mover"]},
]


def _path_to_tag(path: str) -> str:
    """Map a route path to the appropriate cog/section tag."""
    for pattern, tag in _PATH_TAG_RULES:
        if re.search(pattern, path):
            return tag
    return "Core"


def generate_openapi_spec(app: web.Application) -> dict:
    """Auto-generate OpenAPI 3.0 spec from registered routes."""
    spec = {
        "openapi": "3.0.3",
        "info": {
            "title": "APIv2 — Red-DiscordBot REST API",
            "version": "2.0.0",
            "description": (
                "REST API embebida en Red-DiscordBot.\n\n"
                "Autentícate con `Authorization: Bearer <API_KEY>`.\n\n"
                "Rate limit por key: 200 req/min por defecto.\n\n"
                "Los endpoints marcados con *requiere cog* devuelven `503` si el cog no está cargado."
            ),
        },
        "servers": [{"url": "/", "description": "Bot actual"}],
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": "API key creada con [p]apiv2 key create",
                }
            }
        },
        "security": [{"bearerAuth": []}],
        "tags": _TAG_DEFINITIONS,
        "x-tagGroups": _TAG_GROUPS,
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
            summary_line = doc.split("—")[-1].strip() if "—" in doc else doc.split("\n")[0]

            tag = _path_to_tag(path)

            operation = {
                "summary": summary_line,
                "tags": [tag],
                "responses": {
                    "200": {"description": "Success"},
                    "201": {"description": "Created"},
                    "400": {"description": "Bad request"},
                    "401": {"description": "Unauthorized — invalid or missing API key"},
                    "404": {"description": "Not found"},
                    "429": {"description": "Rate limited"},
                    "503": {"description": "Cog not loaded"},
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
                        "description": p.replace("_", " "),
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
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>APIv2 — Red-DiscordBot</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
    <style>
        :root {
            --brand: #5865F2;   /* Discord blurple */
            --brand-dark: #404EED;
        }
        * { box-sizing: border-box; }
        body { margin: 0; background: #0f0f13; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }

        /* Top bar */
        #topbar {
            background: linear-gradient(90deg, #1a1a2e 0%, #16213e 100%);
            border-bottom: 2px solid var(--brand);
            padding: 0 24px;
            display: flex;
            align-items: center;
            gap: 16px;
            height: 56px;
        }
        #topbar .logo { font-size: 20px; font-weight: 700; color: #fff; letter-spacing: -0.5px; }
        #topbar .logo span { color: var(--brand); }
        #topbar .badge {
            background: var(--brand);
            color: #fff;
            font-size: 11px;
            font-weight: 600;
            padding: 2px 8px;
            border-radius: 99px;
            letter-spacing: 0.5px;
        }
        #topbar .links { margin-left: auto; display: flex; gap: 12px; }
        #topbar a { color: #9aa5b4; text-decoration: none; font-size: 13px; }
        #topbar a:hover { color: #fff; }

        /* Swagger UI overrides */
        .swagger-ui .topbar { display: none !important; }
        .swagger-ui { background: #0f0f13 !important; }

        .swagger-ui .info { margin: 28px 0 12px; }
        .swagger-ui .info .title { color: #e2e8f0 !important; font-size: 28px !important; }
        .swagger-ui .info .description p, .swagger-ui .info p { color: #94a3b8 !important; }
        .swagger-ui .info code { background: #1e293b; color: #7dd3fc; padding: 1px 5px; border-radius: 4px; }

        .swagger-ui .scheme-container { background: #1a1a2e !important; box-shadow: none !important; border-bottom: 1px solid #2d2d44; }

        /* Tag headings */
        .swagger-ui .opblock-tag {
            border-bottom: 1px solid #2d2d44 !important;
            color: #e2e8f0 !important;
            font-size: 16px !important;
        }
        .swagger-ui .opblock-tag:hover { background: #1a1a2e !important; }
        .swagger-ui .opblock-tag-section.is-open .opblock-tag { border-bottom-color: var(--brand) !important; }

        /* Tag descriptions */
        .swagger-ui .opblock-tag small { color: #64748b !important; font-weight: 400; font-size: 13px; }

        /* Operation blocks */
        .swagger-ui .opblock { border-radius: 8px !important; margin: 6px 0 !important; border: 1px solid #2d2d44 !important; }
        .swagger-ui .opblock .opblock-summary { border-radius: 6px; }
        .swagger-ui .opblock.opblock-get    { background: #0d1f38 !important; border-color: #1d4ed8 !important; }
        .swagger-ui .opblock.opblock-post   { background: #0d2414 !important; border-color: #15803d !important; }
        .swagger-ui .opblock.opblock-put    { background: #271d08 !important; border-color: #b45309 !important; }
        .swagger-ui .opblock.opblock-patch  { background: #1f1436 !important; border-color: #7c3aed !important; }
        .swagger-ui .opblock.opblock-delete { background: #2d0f0f !important; border-color: #b91c1c !important; }

        .swagger-ui .opblock-body pre.microlight { background: #0f172a !important; color: #94a3b8 !important; }

        /* Buttons */
        .swagger-ui .btn.execute { background: var(--brand) !important; border-color: var(--brand-dark) !important; border-radius: 6px; }
        .swagger-ui .btn.execute:hover { background: var(--brand-dark) !important; }
        .swagger-ui .btn.cancel { border-radius: 6px; }

        /* Auth */
        .swagger-ui .auth-wrapper .authorize { border-color: var(--brand) !important; color: var(--brand) !important; border-radius: 6px; }

        /* Misc */
        .swagger-ui select, .swagger-ui input[type=text], .swagger-ui textarea {
            background: #1e293b !important; color: #e2e8f0 !important; border-color: #334155 !important; border-radius: 6px;
        }
        .swagger-ui .model-box { background: #1e293b !important; }
        .swagger-ui table thead tr td, .swagger-ui table thead tr th { color: #94a3b8 !important; border-color: #2d2d44 !important; }
    </style>
</head>
<body>
    <div id="topbar">
        <div class="logo">API<span>v2</span></div>
        <div class="badge">Red-DiscordBot</div>
        <div class="links">
            <a href="/api/v2/openapi.json" target="_blank">openapi.json</a>
            <a href="/api/v2/health" target="_blank">/health</a>
        </div>
    </div>
    <div id="swagger-ui"></div>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script>
        SwaggerUIBundle({
            url: '/api/v2/openapi.json',
            dom_id: '#swagger-ui',
            deepLinking: true,
            tryItOutEnabled: true,
            displayRequestDuration: true,
            defaultModelsExpandDepth: -1,
            tagsSorter: 'alpha',
            operationsSorter: 'alpha',
            persistAuthorization: true,
            filter: true,
            presets: [
                SwaggerUIBundle.presets.apis,
                SwaggerUIBundle.SwaggerUIStandalonePreset,
            ],
            layout: "BaseLayout",
            syntaxHighlight: { activate: true, theme: "agate" },
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
