"""
Catalogo de modulos y perfiles predefinidos de La Trini.

Un "modulo" es una funcionalidad de La Trini respaldada por un cog de Red.
El estado de cada modulo se guarda por servidor y, opcionalmente, se
sincroniza con el sistema de ``enablecog/disablecog`` por servidor de Red.

Resolucion de cogs
-------------------
Para nuestros propios cogs (Trini* y los de killerbite-cogs) y para los cogs
que trae Red de serie conocemos el nombre exacto de la clase, asi que
``ModuleInfo.cog`` lo fija con certeza.

Para cogs de terceros (por ejemplo los de AAA3A-Cogs) no tenemos su codigo
fuente delante y adivinar el nombre de la clase es fragil: si nos
equivocamos, el modulo nunca se marcaria como "cargado" aunque SI lo este.
Para esos casos dejamos ``cog=None`` y solo rellenamos ``package`` (la
carpeta/extension con la que se hace ``[p]load <package>``); ``resolve_cog``
busca entonces, entre los cogs realmente cargados en el bot, cual viene de
ese paquete, sin importar como se llame su clase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


#: De donde sale el cog, para saber como se instala/carga y que tan segura
#: es su descripcion:
#:   - "trini": uno de los cogs de La Trini (TriniSecurity, TriniBackups...).
#:   - "killerbite": otro cog de este mismo repo (killerbite-cogs).
#:   - "red": viene de serie con Red-DiscordBot, solo hay que cargarlo.
#:   - "third_party": de un repositorio externo que no conocemos; el nombre
#:     de su clase y su descripcion exacta no estan garantizados.
#:   - None: modulo conceptual del roadmap para el que aun no hay un cog
#:     concreto asignado.
SOURCE_KILLERBITE = "killerbite"
SOURCE_TRINI = "trini"
SOURCE_RED = "red"
SOURCE_THIRD_PARTY = "third_party"

INSTALL_HINTS = {
    SOURCE_TRINI: "`[p]cog install killerbite-cogs {package}` y `[p]load {package}`",
    SOURCE_KILLERBITE: "`[p]cog install killerbite-cogs {package}` y `[p]load {package}`",
    SOURCE_RED: "ya viene con Red: `[p]load {package}`",
    SOURCE_THIRD_PARTY: "instala el repo de terceros que lo trae y `[p]load {package}`",
}


@dataclass(frozen=True)
class ModuleInfo:
    key: str
    name: str
    # Nombre exacto de la clase del cog, solo cuando se conoce con certeza.
    # ``None`` si es un cog de terceros cuyo nombre de clase no podemos
    # garantizar: en ese caso se resuelve por ``package``.
    cog: Optional[str]
    description: str
    category: str
    emoji: str = "🧩"
    depends: tuple = ()
    # Paquete/extension real con la que se instala y se hace ``[p]load``.
    package: Optional[str] = None
    # Los modulos "core" no se pueden desactivar desde Profiles (o son
    # demasiado sensibles para que Profiles los apague por error, como
    # Downloader o Permissions).
    core: bool = False
    source: Optional[str] = SOURCE_KILLERBITE

    @property
    def third_party(self) -> bool:
        return self.source == SOURCE_THIRD_PARTY

    def install_hint(self) -> Optional[str]:
        if not self.package or self.source is None:
            return None
        template = INSTALL_HINTS.get(self.source)
        return template.format(package=self.package) if template else None


def resolve_cog(bot: Any, info: "ModuleInfo") -> Optional[Any]:
    """Cog realmente cargado en ``bot`` que corresponde a ``info``, o ``None``.

    Primero prueba el nombre de clase exacto (rapido y fiable para nuestros
    cogs y los de Red). Si no coincide, y conocemos el paquete, busca entre
    los cogs cargados cual viene de ese paquete, comparando por el modulo
    Python del que procede su clase en lugar de su nombre de clase.
    """
    if info.cog:
        cog = bot.get_cog(info.cog)
        if cog is not None:
            return cog
    if info.package:
        target = info.package.lower()
        for cog in bot.cogs.values():
            module_root = type(cog).__module__.split(".")[0].lower()
            if module_root == target:
                return cog
    return None


def resolve_qualified_name(bot: Any, info: "ModuleInfo") -> str:
    """Nombre a pasar a ``enablecog``/``disablecog`` de Red.

    Si el cog esta cargado ahora mismo, se usa su nombre real (siempre
    correcto). Si no esta cargado, se usa la mejor suposicion disponible,
    para que la orden quede guardada y se aplique en cuanto se cargue.
    """
    cog = resolve_cog(bot, info)
    if cog is not None:
        return cog.qualified_name
    return info.cog or info.name.replace(" ", "").replace("/", "")


MODULES: Dict[str, ModuleInfo] = {
    m.key: m
    for m in [
        # ================= Plataforma Trini =================
        ModuleInfo("profiles", "Profiles", "TriniProfiles", "Perfiles y modulos del servidor.", "Plataforma", "⚙️", core=True, package="triniprofiles", source=SOURCE_TRINI),
        ModuleInfo("security", "Trini Security", "TriniSecurity", "Auditoria, roles protegidos, anti-nuke e incidentes.", "Plataforma", "🔐", package="trinisecurity", source=SOURCE_TRINI),
        ModuleInfo("backups", "Trini Backups", "TriniBackups", "Snapshots estructurales, diff y restauracion segura.", "Plataforma", "📦", package="trinibackups", source=SOURCE_TRINI),
        ModuleInfo("events", "Trini Events", "TriniEvents", "Eventos con inscripciones, reservas y recordatorios.", "Plataforma", "📅", package="trinievents", source=SOURCE_TRINI),
        ModuleInfo("alienhost", "AlienHost Integration", "AlienHost", "Servidores de AlienHost (Pelican) desde Discord.", "Infraestructura", "🖥", package="alienhost", source=SOURCE_TRINI),

        # ================= killerbite-cogs =================
        ModuleInfo("apiv2", "APIv2", "APIv2", "API REST embebida para integraciones externas.", "Infraestructura", "🔌", package="apiv2"),
        ModuleInfo("gameservermonitor", "GameServerMonitor", "GameServerMonitor", "Monitorizacion de servidores de juego publicos.", "Gaming", "🎮", package="gameservermonitor"),
        ModuleInfo("tickets", "TicketsTrini", "TicketsTrini", "Sistema de tickets de soporte.", "Soporte", "🎫", package="ticketstrini"),
        ModuleInfo("suggestions", "Suggestions", "SimpleSuggestions", "Sugerencias con votacion.", "Comunidad", "💡", package="suggestions"),
        ModuleInfo("giveaways", "Giveaways", "Giveaways", "Sorteos.", "Comunidad", "🎁", package="giveaways"),
        ModuleInfo("honeypot", "Honeypot", "Honeypot", "Canal trampa contra selfbots y scams.", "Moderacion", "🍯", package="honeypot"),
        ModuleInfo("autonick", "AutoNick", "AutoNick", "Gestion automatica de apodos.", "Comunidad", "🏷", package="autonick"),
        ModuleInfo("colacoins", "ColaCoins", "ColaCoins", "Moneda virtual con clasificacion.", "Comunidad", "🪙", package="colacoins"),
        ModuleInfo("adv_check", "Advanced Check", "Check", "Verificacion avanzada de usuarios con UI interactiva.", "Moderacion", "🔍", package="adv_check"),
        ModuleInfo("autoprune", "AutoPrune", "PruneBans", "Borra los creditos de los usuarios que siguen baneados pasados N dias.", "Comunidad", "🧹", package="autoprune"),
        ModuleInfo("blackjack", "Blackjack", "Blackjack", "Juego de cartas Blackjack.", "Comunidad", "🃏", package="blackjack"),
        ModuleInfo("day_counter", "Day Counter", "DayCounter", "Contador de dias desde/hasta un evento.", "Comunidad", "📆", package="day_counter_cog"),
        ModuleInfo("listroles", "List Roles", "ListRoles", "Lista los roles del servidor con nombre e ID.", "Utilidad", "📋", package="listroles"),
        ModuleInfo("maptrack", "Map Track", "MapTrack", "Obsoleto: usa !gsmalerts de GameServerMonitor.", "Gaming", "🗺", package="maptrack"),
        ModuleInfo("rustmaps", "RustMaps Vote", "RustMapsVote", "Votaciones de mapas de Rust con botones.", "Gaming", "🗳", package="rustmaps_vote"),
        ModuleInfo("trickortreat", "Trick or Treat", "TrickOrTreatV2", "Juego de caramelos con tienda, rachas y eventos.", "Comunidad", "🍬", package="trickortreat"),

        # ================= Cogs de serie de Red =================
        # Nombre de clase conocido con certeza (viene con Red-DiscordBot).
        ModuleInfo("moderation", "Moderation", "Mod", "Moderacion basica de Red (ban/kick/mute por texto).", "Moderacion", "🛡", package="mod", source=SOURCE_RED),
        ModuleInfo("warnings", "Warnings", "Warnings", "Sistema de avisos de Red.", "Moderacion", "⚠️", package="warnings", source=SOURCE_RED),
        ModuleInfo("reports", "Reports", "Reports", "Reportes de usuarios de Red.", "Moderacion", "📣", package="reports", source=SOURCE_RED),
        ModuleInfo("modlog", "ModLog", "ModLog", "Registro de acciones de moderacion de Red.", "Moderacion", "📕", package="modlog", source=SOURCE_RED),
        ModuleInfo("mutes", "Mutes", "Mutes", "Sistema de silencios (timeout) de Red.", "Moderacion", "🔇", package="mutes", source=SOURCE_RED),
        ModuleInfo("filter", "Filter", "Filter", "Filtro de palabras de Red.", "Moderacion", "🚫", package="filter", source=SOURCE_RED),
        ModuleInfo("cleanup", "Cleanup", "Cleanup", "Borrado masivo de mensajes de Red.", "Moderacion", "🧽", package="cleanup", source=SOURCE_RED),
        ModuleInfo("admin", "Admin", "Admin", "Comandos de administracion de bajo nivel de Red.", "Infraestructura", "🛠", package="admin", source=SOURCE_RED),
        ModuleInfo("alias", "Alias", "Alias", "Atajos/alias de comandos de Red.", "Utilidad", "🔗", package="alias", source=SOURCE_RED),
        ModuleInfo("customcom", "Custom Commands", "CustomCommands", "Comandos personalizados por servidor.", "Utilidad", "🧩", package="customcom", source=SOURCE_RED),
        ModuleInfo("general", "General", "General", "Comandos generales de Red (8ball, choose, etc).", "Utilidad", "🎲", package="general", source=SOURCE_RED),
        ModuleInfo("trivia", "Trivia", "Trivia", "Juego de preguntas y respuestas.", "Comunidad", "❓", package="trivia", source=SOURCE_RED),
        ModuleInfo("image", "Image", "Image", "Busqueda de imagenes/GIFs.", "Comunidad", "🖼", package="image", source=SOURCE_RED),
        ModuleInfo("audio", "Audio", "Audio", "Reproduccion de musica.", "Comunidad", "🎵", package="audio", source=SOURCE_RED),
        ModuleInfo("streams", "Streams", "Streams", "Avisos de directos (Twitch/YouTube/etc).", "Comunidad", "📺", package="streams", source=SOURCE_RED),
        ModuleInfo("economy", "Economy", "Economy", "Economia (moneda) de Red.", "Comunidad", "💰", package="economy", source=SOURCE_RED),
        ModuleInfo("downloader", "Downloader", "Downloader", "Gestor de repositorios de cogs. Necesario para instalar el resto.", "Infraestructura", "📥", package="downloader", core=True, source=SOURCE_RED),
        ModuleInfo("permissions", "Permissions", "Permissions", "Reglas de permisos personalizadas de Red.", "Infraestructura", "🔑", package="permissions", core=True, source=SOURCE_RED),

        # ================= Terceros (nombre de clase no verificado) =================
        # ``cog=None``: se resuelven solo por el paquete con el que se cargan.
        ModuleInfo("captcha", "Captcha", None, "Verificacion de nuevos miembros (captcha).", "Moderacion", "🤖", package="advancedcaptcha", source=SOURCE_THIRD_PARTY),
        ModuleInfo("antigifv", "AntiGifV", None, "Proteccion frente a contenido/spam especifico. Revisa la documentacion del cog para el detalle exacto.", "Moderacion", "🎬", package="antigifv", source=SOURCE_THIRD_PARTY),
        ModuleInfo("linkwarner", "Link Warner", None, "Avisa o elimina enlaces no permitidos.", "Moderacion", "🔗", package="linkwarner", source=SOURCE_THIRD_PARTY),
        ModuleInfo("extendedmodlog", "Extended ModLog", None, "Registro de moderacion ampliado (mas eventos que ModLog).", "Moderacion", "📚", package="extendedmodlog", source=SOURCE_THIRD_PARTY),
        ModuleInfo("clearchannel", "Clear Channel", None, "Vaciar canales rapidamente.", "Moderacion", "🗑", package="clearchannel", source=SOURCE_THIRD_PARTY),
        ModuleInfo("welcome", "Welcome", None, "Mensajes de bienvenida.", "Comunidad", "👋", package="welcome", source=SOURCE_THIRD_PARTY),
        ModuleInfo("rolesbuttons", "RolesButtons", None, "Roles asignables por botones.", "Comunidad", "🔘", package="rolesbuttons", source=SOURCE_THIRD_PARTY),
        ModuleInfo("roleutils", "Role Utils", None, "Utilidades de gestion de roles (reaction roles, etc).", "Comunidad", "🎛", package="roleutils", source=SOURCE_THIRD_PARTY),
        ModuleInfo("rolesyncer", "Role Syncer", None, "Sincroniza un rol entre varios servidores.", "Comunidad", "🔃", package="rolesyncer", source=SOURCE_THIRD_PARTY),
        ModuleInfo("exclusiveroles", "Exclusive Roles", None, "Roles que se excluyen entre si al asignarse.", "Comunidad", "🚧", package="exclusiveroles", source=SOURCE_THIRD_PARTY),
        ModuleInfo("autoroom", "AutoRoom", None, "Salas de voz automaticas.", "Comunidad", "🔊", package="autoroom", source=SOURCE_THIRD_PARTY),
        ModuleInfo("youtube", "YouTube", None, "Avisos de nuevos videos de YouTube.", "Comunidad", "▶️", package="youtube", source=SOURCE_THIRD_PARTY),
        ModuleInfo("extendedeconomy", "Extended Economy", None, "Extensiones e integraciones para la economia de Red.", "Comunidad", "💹", package="extendedeconomy", source=SOURCE_THIRD_PARTY),
        ModuleInfo("battleroyale", "Battle Royale", None, "Minijuego de battle royale por texto.", "Comunidad", "⚔️", package="battleroyale", source=SOURCE_THIRD_PARTY),
        ModuleInfo("disboardreminder", "Disboard Reminder", None, "Recuerda hacer bump en Disboard.", "Comunidad", "⏰", package="disboardreminder", source=SOURCE_THIRD_PARTY),
        ModuleInfo("sticky", "Sticky", None, "Mantiene un mensaje fijado al final del canal.", "Comunidad", "📌", package="sticky", source=SOURCE_THIRD_PARTY),
        ModuleInfo("assistant", "Assistant", None, "Asistente conversacional con IA para el servidor.", "IA", "🤖", package="assistant", source=SOURCE_THIRD_PARTY),
        ModuleInfo("assistantutils", "Assistant Utils", None, "Utilidades internas usadas por Assistant.", "IA", "🧠", package="assistantutils", source=SOURCE_THIRD_PARTY, depends=("assistant",)),
        ModuleInfo("avatar", "Avatar", None, "Muestra avatares y banners de usuarios.", "Utilidad", "🖼", package="avatar", source=SOURCE_THIRD_PARTY),
        ModuleInfo("say", "Say", None, "Hace que el bot envie o repita mensajes/embeds.", "Utilidad", "💬", package="say", source=SOURCE_THIRD_PARTY),
        ModuleInfo("tags", "Tags", None, "Snippets/tags reutilizables por comando.", "Utilidad", "🏷️", package="tags", source=SOURCE_THIRD_PARTY),
        ModuleInfo("timechannel", "Time Channel", None, "Muestra la hora actual en el nombre de un canal.", "Utilidad", "🕒", package="timechannel", source=SOURCE_THIRD_PARTY),
        ModuleInfo("urlbuttons", "URL Buttons", None, "Añade botones con enlaces a los mensajes.", "Utilidad", "🔘", package="urlbuttons", source=SOURCE_THIRD_PARTY),
        ModuleInfo("embedcreator", "Embed Creator", None, "Crear y editar embeds con un asistente interactivo.", "Utilidad", "🖌", package="embedcreator", source=SOURCE_THIRD_PARTY),
        ModuleInfo("embedutils", "Embed Utils", None, "Guardar y reenviar embeds reutilizables.", "Utilidad", "🧾", package="embedutils", source=SOURCE_THIRD_PARTY),
        ModuleInfo("discordmodals", "Discord Modals", None, "Utilidad base para crear formularios (modals).", "Utilidad", "📝", package="discordmodals", source=SOURCE_THIRD_PARTY),
        ModuleInfo("dashboard", "Dashboard", None, "Panel web de administracion del bot.", "Infraestructura", "🖥️", package="dashboard", source=SOURCE_THIRD_PARTY),

        # ================= Conceptuales del roadmap (aun sin cog instalado) =================
        # Sin ``package``: no se pueden resolver hasta que instales un cog real
        # para cubrir esta funcion y actualices esta entrada con su paquete.
        ModuleInfo("applications", "Applications", None, "Solicitudes de staff/whitelist. Instala el cog que uses para esto.", "Soporte", "📝", source=None),
        ModuleInfo("forms", "Forms", None, "Formularios. Instala el cog que uses para esto.", "Soporte", "📋", source=None),
        ModuleInfo("status", "Status", None, "Paginas de estado de servicios. Instala el cog que uses para esto.", "Infraestructura", "🟢", source=None),
        ModuleInfo("incidents", "Incidents", None, "Comunicacion de incidencias. Instala el cog que uses para esto.", "Infraestructura", "🚧", source=None),
        ModuleInfo("arencup", "ArenCup", None, "Integracion de torneos ArenCup. Instala el cog que uses para esto.", "Esports", "🏆", source=None),
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


_PREDEFINED_PROFILES = [
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
    ProfileInfo(
        "all_on",
        "Todo activado",
        "🟢",
        "Activa todos los modulos que La Trini conoce (incluidos los de terceros que "
        "tengas cargados). Pensado para probar el bot entero o para servidores que "
        "quieren tenerlo todo disponible desde el primer dia; despues puedes afinar "
        "con `trini modules`.",
        {key: ON for key, info in MODULES.items() if not info.core},
        security_level="strict",
    ),
]

PROFILES: Dict[str, ProfileInfo] = {p.key: p for p in _PREDEFINED_PROFILES}


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
