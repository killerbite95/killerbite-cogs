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

from redbot.core.i18n import Translator

_ = Translator("TriniProfiles", __file__)


def N_(text: str) -> str:
    """Marca un texto de una constante para traducirlo al usarlo con ``_()``."""
    return text


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
        return _(template).format(package=self.package) if template else None


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
        ModuleInfo("profiles", "Profiles", "TriniProfiles", N_("Server profiles and modules."), N_("Platform"), "⚙️", core=True, package="triniprofiles", source=SOURCE_TRINI),
        ModuleInfo("security", "Trini Security", "TriniSecurity", N_("Audit, protected roles, anti-nuke and incidents."), N_("Platform"), "🔐", package="trinisecurity", source=SOURCE_TRINI),
        ModuleInfo("backups", "Trini Backups", "TriniBackups", N_("Structural snapshots, diff and safe restore."), N_("Platform"), "📦", package="trinibackups", source=SOURCE_TRINI),
        ModuleInfo("events", "Trini Events", "TriniEvents", N_("Events with sign-ups, waitlists and reminders."), N_("Platform"), "📅", package="trinievents", source=SOURCE_TRINI),
        ModuleInfo("alienhost", "AlienHost Integration", "AlienHost", N_("AlienHost (Pelican) servers from Discord."), N_("Infrastructure"), "🖥", package="alienhost", source=SOURCE_TRINI),

        # ================= killerbite-cogs =================
        ModuleInfo("apiv2", "APIv2", "APIv2", N_("Embedded REST API for external integrations."), N_("Infrastructure"), "🔌", package="apiv2"),
        ModuleInfo("gameservermonitor", "GameServerMonitor", "GameServerMonitor", N_("Public game server monitoring."), N_("Gaming"), "🎮", package="gameservermonitor"),
        ModuleInfo("tickets", "TicketsTrini", "TicketsTrini", N_("Support ticket system."), N_("Support"), "🎫", package="ticketstrini"),
        ModuleInfo("suggestions", "Suggestions", "SimpleSuggestions", N_("Suggestions with voting."), N_("Community"), "💡", package="suggestions"),
        ModuleInfo("giveaways", "Giveaways", "Giveaways", N_("Giveaways."), N_("Community"), "🎁", package="giveaways"),
        ModuleInfo("honeypot", "Honeypot", "Honeypot", N_("Trap channel against selfbots and scams."), N_("Moderation"), "🍯", package="honeypot"),
        ModuleInfo("autonick", "AutoNick", "AutoNick", N_("Automatic nickname management."), N_("Community"), "🏷", package="autonick"),
        ModuleInfo("colacoins", "ColaCoins", "ColaCoins", N_("Virtual currency with leaderboard."), N_("Community"), "🪙", package="colacoins"),
        ModuleInfo("adv_check", "Advanced Check", "Check", N_("Advanced user verification with an interactive UI."), N_("Moderation"), "🔍", package="adv_check"),
        ModuleInfo("autoprune", "AutoPrune", "PruneBans", N_("Clears the credits of users still banned after N days."), N_("Community"), "🧹", package="autoprune"),
        ModuleInfo("blackjack", "Blackjack", "Blackjack", N_("Blackjack card game."), N_("Community"), "🃏", package="blackjack"),
        ModuleInfo("day_counter", "Day Counter", "DayCounter", N_("Day counter since/until an event."), N_("Community"), "📆", package="day_counter_cog"),
        ModuleInfo("listroles", "List Roles", "ListRoles", N_("Lists the server roles with name and ID."), N_("Utility"), "📋", package="listroles"),
        ModuleInfo("maptrack", "Map Track", "MapTrack", N_("Obsolete: use GameServerMonitor's !gsmalerts."), N_("Gaming"), "🗺", package="maptrack"),
        ModuleInfo("rustmaps", "RustMaps Vote", "RustMapsVote", N_("Rust map votes with buttons."), N_("Gaming"), "🗳", package="rustmaps_vote"),
        ModuleInfo("trickortreat", "Trick or Treat", "TrickOrTreatV2", N_("Candy game with shop, streaks and events."), N_("Community"), "🍬", package="trickortreat"),

        # ================= Cogs de serie de Red =================
        # Nombre de clase conocido con certeza (viene con Red-DiscordBot).
        ModuleInfo("moderation", "Moderation", "Mod", N_("Basic Red moderation (text ban/kick/mute)."), N_("Moderation"), "🛡", package="mod", source=SOURCE_RED),
        ModuleInfo("warnings", "Warnings", "Warnings", N_("Red's warning system."), N_("Moderation"), "⚠️", package="warnings", source=SOURCE_RED),
        ModuleInfo("reports", "Reports", "Reports", N_("Red's user reports."), N_("Moderation"), "📣", package="reports", source=SOURCE_RED),
        ModuleInfo("modlog", "ModLog", "ModLog", N_("Red's moderation action log."), N_("Moderation"), "📕", package="modlog", source=SOURCE_RED),
        ModuleInfo("mutes", "Mutes", "Mutes", N_("Red's mute (timeout) system."), N_("Moderation"), "🔇", package="mutes", source=SOURCE_RED),
        ModuleInfo("filter", "Filter", "Filter", N_("Red's word filter."), N_("Moderation"), "🚫", package="filter", source=SOURCE_RED),
        ModuleInfo("cleanup", "Cleanup", "Cleanup", N_("Red bulk message deletion."), N_("Moderation"), "🧽", package="cleanup", source=SOURCE_RED),
        ModuleInfo("admin", "Admin", "Admin", N_("Red's low-level admin commands."), N_("Infrastructure"), "🛠", package="admin", source=SOURCE_RED),
        ModuleInfo("alias", "Alias", "Alias", N_("Red's command shortcuts/aliases."), N_("Utility"), "🔗", package="alias", source=SOURCE_RED),
        ModuleInfo("customcom", "Custom Commands", "CustomCommands", N_("Per-server custom commands."), N_("Utility"), "🧩", package="customcom", source=SOURCE_RED),
        ModuleInfo("general", "General", "General", N_("Red's general commands (8ball, choose, etc)."), N_("Utility"), "🎲", package="general", source=SOURCE_RED),
        ModuleInfo("trivia", "Trivia", "Trivia", N_("Trivia game."), N_("Community"), "❓", package="trivia", source=SOURCE_RED),
        ModuleInfo("image", "Image", "Image", N_("Image/GIF search."), N_("Community"), "🖼", package="image", source=SOURCE_RED),
        ModuleInfo("audio", "Audio", "Audio", N_("Music playback."), N_("Community"), "🎵", package="audio", source=SOURCE_RED),
        ModuleInfo("streams", "Streams", "Streams", N_("Stream alerts (Twitch/YouTube/etc)."), N_("Community"), "📺", package="streams", source=SOURCE_RED),
        ModuleInfo("economy", "Economy", "Economy", N_("Red's economy (currency)."), N_("Community"), "💰", package="economy", source=SOURCE_RED),
        ModuleInfo("downloader", "Downloader", "Downloader", N_("Cog repository manager. Required to install everything else."), N_("Infrastructure"), "📥", package="downloader", core=True, source=SOURCE_RED),
        ModuleInfo("permissions", "Permissions", "Permissions", N_("Red's custom permission rules."), N_("Infrastructure"), "🔑", package="permissions", core=True, source=SOURCE_RED),

        # ================= Terceros (nombre de clase no verificado) =================
        # ``cog=None``: se resuelven solo por el paquete con el que se cargan.
        ModuleInfo("captcha", "Captcha", "Captcha", N_("Captcha verification for new members."), N_("Moderation"), "🤖", package="captcha", source=SOURCE_THIRD_PARTY),
        ModuleInfo("antigifv", "AntiGifV", "AntiGifV", N_("Automatically suppresses GifV embeds (avoids videos that freeze clients)."), N_("Moderation"), "🎬", package="antigifv", source=SOURCE_THIRD_PARTY),
        ModuleInfo("linkwarner", "Link Warner", "LinkWarner", N_("Deletes messages with disallowed links and warns the user."), N_("Moderation"), "🔗", package="linkwarner", source=SOURCE_THIRD_PARTY),
        ModuleInfo("extendedmodlog", "Extended ModLog", "ExtendedModLog", N_("Extended server change log (messages, roles, channels, members...)."), N_("Moderation"), "📚", package="extendedmodlog", source=SOURCE_THIRD_PARTY),
        ModuleInfo("clearchannel", "Clear Channel", "ClearChannel", N_("Deletes ALL messages in a channel."), N_("Moderation"), "🗑", package="clearchannel", source=SOURCE_THIRD_PARTY),
        ModuleInfo("welcome", "Welcome", "Welcome", N_("Announces member joins, leaves and bans."), N_("Community"), "👋", package="welcome", source=SOURCE_THIRD_PARTY),
        ModuleInfo("rolesbuttons", "RolesButtons", "RolesButtons", N_("Self-assignable roles with buttons."), N_("Community"), "🔘", package="rolesbuttons", source=SOURCE_THIRD_PARTY),
        ModuleInfo("roleutils", "Role Utils", "RoleUtils", N_("Reaction roles, mass assignment and autoroles."), N_("Community"), "🎛", package="roleutils", source=SOURCE_THIRD_PARTY),
        ModuleInfo("rolesyncer", "Role Syncer", "RoleSyncer", N_("Syncs roles with each other (having one gives or removes another)."), N_("Community"), "🔃", package="rolesyncer", source=SOURCE_THIRD_PARTY),
        ModuleInfo("exclusiveroles", "Exclusive Roles", "ExclusiveRoles", N_("Truly exclusive roles: having one removes the others."), N_("Community"), "🚧", package="exclusiveroles", source=SOURCE_THIRD_PARTY),
        ModuleInfo("autoroom", "AutoRoom", "AutoRoom", N_("Automatic voice rooms."), N_("Community"), "🔊", package="autoroom", source=SOURCE_THIRD_PARTY),
        ModuleInfo("youtube", "YouTube", "YouTube", N_("New YouTube video alerts."), N_("Community"), "▶️", package="youtube", source=SOURCE_THIRD_PARTY),
        ModuleInfo("extendedeconomy", "Extended Economy", "ExtendedEconomy", N_("Extra features for Red's economy."), N_("Community"), "💹", package="extendedeconomy", source=SOURCE_THIRD_PARTY),
        ModuleInfo("battleroyale", "Battle Royale", "BattleRoyale", N_("Text battle royale minigame."), N_("Community"), "⚔️", package="battleroyale", source=SOURCE_THIRD_PARTY),
        ModuleInfo("disboardreminder", "Disboard Reminder", "DisboardReminder", N_("Reminds you to bump on Disboard."), N_("Community"), "⏰", package="disboardreminder", source=SOURCE_THIRD_PARTY),
        ModuleInfo("sticky", "Sticky", "Sticky", N_("Keeps a message pinned at the bottom of the channel."), N_("Community"), "📌", package="sticky", source=SOURCE_THIRD_PARTY),
        ModuleInfo("assistant", "Assistant", "Assistant", N_("AI assistant (ChatGPT/OpenAI) for the server."), N_("AI"), "🤖", package="assistant", source=SOURCE_THIRD_PARTY),
        ModuleInfo("assistantutils", "Assistant Utils", "AssistantUtils", N_("Extra functions for Assistant."), N_("AI"), "🧠", package="assistantutils", source=SOURCE_THIRD_PARTY, depends=("assistant",)),
        ModuleInfo("avatar", "Avatar", "Avatar", N_("Shows user avatars and banners."), N_("Utility"), "🖼", package="avatar", source=SOURCE_THIRD_PARTY),
        ModuleInfo("say", "Say", "Say", N_("Makes the bot send or repeat messages/embeds."), N_("Utility"), "💬", package="say", source=SOURCE_THIRD_PARTY),
        ModuleInfo("tags", "Tags", "Tags", N_("Reusable snippets/tags by command."), N_("Utility"), "🏷️", package="tags", source=SOURCE_THIRD_PARTY),
        ModuleInfo("timechannel", "Time Channel", "TimeChannel", N_("Shows the time in different time zones in voice channels."), N_("Utility"), "🕒", package="timechannel", source=SOURCE_THIRD_PARTY),
        ModuleInfo("urlbuttons", "URL Buttons", "UrlButtons", N_("Adds link buttons to messages."), N_("Utility"), "🔘", package="urlbuttons", source=SOURCE_THIRD_PARTY),
        ModuleInfo("embedcreator", "Embed Creator", "EmbedCreator", N_("Create and edit embeds with an interactive wizard."), N_("Utility"), "🖌", package="embedcreator", source=SOURCE_THIRD_PARTY),
        ModuleInfo("embedutils", "Embed Utils", "EmbedUtils", N_("Create, send and save embeds (also from the dashboard)."), N_("Utility"), "🧾", package="embedutils", source=SOURCE_THIRD_PARTY),
        ModuleInfo("discordmodals", "Discord Modals", "DiscordModals", N_("Forms (modals) with buttons for users."), N_("Utility"), "📝", package="discordmodals", source=SOURCE_THIRD_PARTY),
        ModuleInfo("easterhunt", "Easter Hunt", "EasterHunt", N_("Easter minigame: hunt eggs, work, gift and steal."), N_("Community"), "🥚", package="easterhunt", source=SOURCE_THIRD_PARTY),
        ModuleInfo("frases", "Frases", "TriniFrases", N_("La Trini's custom phrases."), N_("Community"), "💬", package="frases", source=SOURCE_THIRD_PARTY),
        ModuleInfo("reminders", "Reminders", "Reminders", N_("Reminders by DM or channel, command and message scheduler."), N_("Utility"), "⏰", package="reminders", source=SOURCE_THIRD_PARTY),
        ModuleInfo("dashboard", "Dashboard", "Dashboard", N_("Web admin panel for the bot."), N_("Infrastructure"), "🖥️", package="dashboard", source=SOURCE_THIRD_PARTY),

        # ================= Conceptuales del roadmap (aun sin cog instalado) =================
        # Sin ``package``: no se pueden resolver hasta que instales un cog real
        # para cubrir esta funcion y actualices esta entrada con su paquete.
        ModuleInfo("applications", "Applications", None, N_("Staff/whitelist applications. Install the cog you use for this."), N_("Support"), "📝", source=None),
        ModuleInfo("forms", "Forms", None, N_("Forms. Install the cog you use for this."), N_("Support"), "📋", source=None),
        ModuleInfo("status", "Status", None, N_("Service status pages. Install the cog you use for this."), N_("Infrastructure"), "🟢", source=None),
        ModuleInfo("incidents", "Incidents", None, N_("Incident communication. Install the cog you use for this."), N_("Infrastructure"), "🚧", source=None),
        ModuleInfo("arencup", "ArenCup", None, N_("ArenCup tournament integration. Install the cog you use for this."), N_("Esports"), "🏆", source=None),
    ]
}


ON = "on"
RECOMMENDED = "recommended"
OPTIONAL = "optional"

LEVEL_LABELS = {
    ON: N_("✅ enabled"),
    RECOMMENDED: N_("⭐ recommended"),
    OPTIONAL: N_("➖ optional"),
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
        N_("Gaming Community"),
        "🎮",
        N_("Gaming community with game servers, streams and social activity."),
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
        N_("Esports / Tournaments"),
        "🏆",
        N_("Tournament server (ArenCup): staff, referees, casters and teams."),
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
        N_("Roleplay"),
        "🎭",
        N_("Roleplay server with applications, forms and moderation."),
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
        N_("Hosting / Support"),
        "🖥",
        N_("AlienHost support server: customers, tickets and infrastructure."),
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
        N_("General Community"),
        "🌐",
        N_("General community with the basics properly set up."),
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
        N_("Custom"),
        "⚙️",
        N_("No template: manually enable what you need with `trini modules`."),
        {"security": RECOMMENDED, "backups": RECOMMENDED},
        security_level="standard",
    ),
    ProfileInfo(
        "all_on",
        N_("Everything enabled"),
        "🟢",
        N_("Enables every module La Trini knows about (including loaded third-party ones). Meant for trying the whole bot or for servers that want everything available from day one; you can fine-tune later with `trini modules`."),
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
