"""
Catalogo de modulos y perfiles predefinidos de La Trini.

Un "modulo" es una funcionalidad de La Trini respaldada por un cog de Red.
El estado de cada modulo se guarda por servidor y, opcionalmente, se
sincroniza con el sistema de ``enablecog/disablecog`` por servidor de Red.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ModuleInfo:
    key: str
    name: str
    cog: str
    description: str
    category: str
    emoji: str = "🧩"
    depends: tuple = ()
    # Paquete a instalar con ``[p]cog install`` (informativo).
    package: Optional[str] = None
    # Los modulos "core" no se pueden desactivar desde Profiles.
    core: bool = False


MODULES: Dict[str, ModuleInfo] = {
    m.key: m
    for m in [
        # --- Plataforma Trini ---
        ModuleInfo("profiles", "Profiles", "TriniProfiles", "Perfiles y modulos del servidor.", "Plataforma", "⚙️", core=True, package="triniprofiles"),
        ModuleInfo("security", "Trini Security", "TriniSecurity", "Auditoria, roles protegidos, anti-nuke e incidentes.", "Plataforma", "🔐", package="trinisecurity"),
        ModuleInfo("backups", "Trini Backups", "TriniBackups", "Snapshots estructurales, diff y restauracion segura.", "Plataforma", "📦", package="trinibackups"),
        ModuleInfo("events", "Trini Events", "TriniEvents", "Eventos con inscripciones, reservas y recordatorios.", "Comunidad", "📅", package="trinievents"),
        ModuleInfo("alienhost", "AlienHost Integration", "AlienHost", "Servidores de AlienHost (Pelican) desde Discord.", "Infraestructura", "🖥", package="alienhost"),
        ModuleInfo("apiv2", "APIv2", "APIv2", "API REST embebida para integraciones externas.", "Infraestructura", "🔌", package="apiv2"),
        # --- Cogs de killerbite-cogs ---
        ModuleInfo("gameservermonitor", "GameServerMonitor", "GameServerMonitor", "Monitorizacion de servidores de juego publicos.", "Gaming", "🎮", package="gameservermonitor"),
        ModuleInfo("tickets", "TicketsTrini", "TicketsTrini", "Sistema de tickets de soporte.", "Soporte", "🎫", package="ticketstrini"),
        ModuleInfo("suggestions", "Suggestions", "SimpleSuggestions", "Sugerencias con votacion.", "Comunidad", "💡", package="suggestions"),
        ModuleInfo("giveaways", "Giveaways", "Giveaways", "Sorteos.", "Comunidad", "🎁", package="giveaways"),
        ModuleInfo("honeypot", "Honeypot", "Honeypot", "Canal trampa contra selfbots y scams.", "Moderacion", "🍯", package="honeypot"),
        ModuleInfo("autonick", "AutoNick", "AutoNick", "Gestion automatica de apodos.", "Comunidad", "🏷", package="autonick"),
        ModuleInfo("colacoins", "ColaCoins", "ColaCoins", "Moneda virtual.", "Comunidad", "🪙", package="colacoins"),
        # --- Cogs de Red / terceros habituales en La Trini ---
        ModuleInfo("moderation", "Moderation", "Mod", "Moderacion basica de Red.", "Moderacion", "🛡"),
        ModuleInfo("warnings", "Warnings", "Warnings", "Sistema de avisos de Red.", "Moderacion", "⚠️"),
        ModuleInfo("reports", "Reports", "Reports", "Reportes de usuarios.", "Moderacion", "📣"),
        ModuleInfo("captcha", "Captcha", "Captcha", "Verificacion de nuevos miembros.", "Moderacion", "🤖"),
        ModuleInfo("welcome", "Welcome", "Welcome", "Mensajes de bienvenida.", "Comunidad", "👋"),
        ModuleInfo("rolesbuttons", "RolesButtons", "RolesButtons", "Roles por botones.", "Comunidad", "🔘"),
        ModuleInfo("autoroom", "AutoRoom", "AutoRoom", "Salas de voz automaticas.", "Comunidad", "🔊"),
        ModuleInfo("audio", "Audio", "Audio", "Musica.", "Comunidad", "🎵"),
        ModuleInfo("streams", "Streams", "Streams", "Avisos de directos.", "Comunidad", "📺"),
        ModuleInfo("youtube", "YouTube", "YouTube", "Avisos de videos de YouTube.", "Comunidad", "▶️"),
        ModuleInfo("economy", "Economy", "Economy", "Economia de Red.", "Comunidad", "💰"),
        ModuleInfo("applications", "Applications", "Applications", "Solicitudes de staff/whitelist.", "Soporte", "📝"),
        ModuleInfo("forms", "Forms", "Forms", "Formularios.", "Soporte", "📋"),
        ModuleInfo("status", "Status", "Status", "Paginas de estado de servicios.", "Infraestructura", "🟢"),
        ModuleInfo("incidents", "Incidents", "Incidents", "Comunicacion de incidencias.", "Infraestructura", "🚧"),
        ModuleInfo("arencup", "ArenCup", "ArenCup", "Integracion de torneos ArenCup.", "Esports", "🏆"),
    ]
}


ON = "on"
RECOMMENDED = "recommended"
OPTIONAL = "optional"

LEVEL_LABELS = {
    ON: "✅ activado",
    RECOMMENDED: "⭐ recomendado",
    OPTIONAL: "➖ opcional",
}


@dataclass(frozen=True)
class ProfileInfo:
    key: str
    name: str
    emoji: str
    description: str
    modules: Dict[str, str] = field(default_factory=dict)
    # Nivel de seguridad recomendado que TriniSecurity puede leer.
    security_level: str = "standard"
    # Roles que conviene proteger (se usan como sugerencia en la auditoria).
    protected_role_hints: tuple = ()


PROFILES: Dict[str, ProfileInfo] = {
    p.key: p
    for p in [
        ProfileInfo(
            "gaming",
            "Comunidad Gaming",
            "🎮",
            "Comunidad de jugadores con servidores de juego, directos y actividad social.",
            {
                "gameservermonitor": ON,
                "autoroom": ON,
                "giveaways": ON,
                "streams": ON,
                "youtube": ON,
                "welcome": ON,
                "rolesbuttons": ON,
                "audio": ON,
                "events": ON,
                "economy": OPTIONAL,
                "tickets": OPTIONAL,
                "security": RECOMMENDED,
                "backups": RECOMMENDED,
            },
            security_level="standard",
        ),
        ProfileInfo(
            "esports",
            "Esports / Torneos",
            "🏆",
            "Servidor de torneos (ArenCup): staff, arbitros, casters y equipos.",
            {
                "moderation": ON,
                "tickets": ON,
                "reports": ON,
                "events": ON,
                "rolesbuttons": ON,
                "welcome": ON,
                "captcha": ON,
                "security": ON,
                "backups": ON,
                "arencup": ON,
                "giveaways": OPTIONAL,
                "streams": OPTIONAL,
            },
            security_level="high",
            protected_role_hints=("staff", "arbitro", "árbitro", "organizador", "tournament", "caster", "admin"),
        ),
        ProfileInfo(
            "roleplay",
            "Roleplay",
            "🎭",
            "Servidor de rol con solicitudes, formularios y moderacion.",
            {
                "moderation": ON,
                "warnings": ON,
                "reports": ON,
                "tickets": ON,
                "autoroom": ON,
                "welcome": ON,
                "captcha": ON,
                "rolesbuttons": ON,
                "security": ON,
                "backups": ON,
                "applications": ON,
                "forms": ON,
                "events": RECOMMENDED,
            },
            security_level="standard",
            protected_role_hints=("staff", "admin", "moderador", "whitelist"),
        ),
        ProfileInfo(
            "hosting",
            "Hosting / Soporte",
            "🖥",
            "Servidor de soporte de AlienHost: clientes, tickets e infraestructura.",
            {
                "tickets": ON,
                "alienhost": ON,
                "apiv2": ON,
                "gameservermonitor": ON,
                "security": ON,
                "backups": ON,
                "reports": ON,
                "welcome": ON,
                "incidents": ON,
                "status": ON,
                "forms": ON,
                "suggestions": OPTIONAL,
            },
            security_level="strict",
            protected_role_hints=("staff", "admin", "soporte", "support", "host manager", "cliente"),
        ),
        ProfileInfo(
            "general",
            "Comunidad General",
            "🌐",
            "Comunidad generalista con lo basico bien configurado.",
            {
                "moderation": ON,
                "welcome": ON,
                "rolesbuttons": ON,
                "suggestions": ON,
                "giveaways": OPTIONAL,
                "events": RECOMMENDED,
                "security": RECOMMENDED,
                "backups": RECOMMENDED,
            },
            security_level="standard",
        ),
        ProfileInfo(
            "custom",
            "Personalizado",
            "⚙️",
            "Sin plantilla: activa manualmente lo que necesites con `trini modules`.",
            {"security": RECOMMENDED, "backups": RECOMMENDED},
            security_level="standard",
        ),
    ]
}


def resolve_dependencies(keys: List[str]) -> List[str]:
    """Devuelve las dependencias (transitivas) de ``keys`` que no estan en ``keys``."""
    result: List[str] = []
    stack = list(keys)
    seen = set(keys)
    while stack:
        key = stack.pop()
        info = MODULES.get(key)
        if info is None:
            continue
        for dep in info.depends:
            if dep not in seen:
                seen.add(dep)
                result.append(dep)
                stack.append(dep)
    return result


def dependents_of(key: str, active: List[str]) -> List[str]:
    """Modulos activos que dependen (directa o indirectamente) de ``key``."""
    result = []
    for other in active:
        if other == key:
            continue
        if key in resolve_dependencies([other]):
            result.append(other)
    return result
