from __future__ import annotations

import discord
from redbot.core.i18n import Translator

_ = Translator("TriniSecurity", __file__)


def N_(text: str) -> str:
    """Marca un texto de una constante para traducirlo al usarlo con ``_()``."""
    return text

# Permisos considerados "administrativos".
ADMIN_PERMS = (
    "administrator",
    "manage_guild",
    "manage_roles",
    "manage_channels",
    "manage_webhooks",
    "ban_members",
    "kick_members",
)

# Permisos peligrosos para @everyone (ademas de los administrativos).
EVERYONE_DANGEROUS = ADMIN_PERMS + (
    "mention_everyone",
    "manage_messages",
    "manage_threads",
    "moderate_members",
    "manage_nicknames",
    "manage_events",
    "manage_expressions",
    "view_audit_log",
)

PERM_LABELS = {
    "administrator": N_("Administrator"),
    "manage_guild": N_("Manage Guild"),
    "manage_roles": N_("Manage Roles"),
    "manage_channels": N_("Manage Channels"),
    "manage_webhooks": N_("Manage Webhooks"),
    "ban_members": N_("Ban Members"),
    "kick_members": N_("Kick Members"),
    "mention_everyone": N_("Mention @everyone"),
    "manage_messages": N_("Manage Messages"),
    "manage_threads": N_("Manage Threads"),
    "moderate_members": N_("Timeout Members"),
    "manage_nicknames": N_("Manage Nicknames"),
    "manage_events": N_("Manage Events"),
    "manage_expressions": N_("Manage Expressions"),
    "view_audit_log": N_("View Audit Log"),
    "create_instant_invite": N_("Create Invite"),
    "view_channel": N_("View Channel"),
    "send_messages": N_("Send Messages"),
    "connect": N_("Connect"),
}


PERM_ALIASES = {"read_messages": "view_channel", "manage_emojis": "manage_expressions", "use_slash_commands": "use_application_commands"}


def perm_label(name: str) -> str:
    name = PERM_ALIASES.get(name, name)
    return _(PERM_LABELS[name]) if name in PERM_LABELS else name.replace("_", " ").title()


# Umbrales anti-nuke por accion: (por minuto, por hora). 0 = sin limite.
DEFAULT_THRESHOLDS = {
    "channel_delete": [5, 10],
    "channel_create": [10, 30],
    "role_delete": [3, 8],
    "role_create": [8, 20],
    "ban": [10, 30],
    "kick": [10, 30],
    "webhook_create": [3, 10],
    "dangerous_permission": [1, 0],
    "bot_add": [2, 5],
    "prune": [1, 2],
}

# Puntos de riesgo por accion.
DEFAULT_SCORES = {
    "channel_delete": 20,
    "channel_create": 3,
    "role_delete": 25,
    "role_create": 3,
    "admin_grant": 50,
    "everyone_change": 40,
    "dangerous_permission": 20,
    "webhook_create": 10,
    "ban": 5,
    "kick": 3,
    "bot_add": 15,
    "prune": 30,
    "protected_role_violation": 30,
}

ACTION_LABELS = {
    "channel_delete": N_("Delete channel"),
    "channel_create": N_("Create channel"),
    "channel_update": N_("Edit channel"),
    "role_delete": N_("Delete role"),
    "role_create": N_("Create role"),
    "role_update": N_("Edit role"),
    "admin_grant": N_("Grant Administrator"),
    "everyone_change": N_("Change @everyone"),
    "dangerous_permission": N_("Dangerous permission"),
    "webhook_create": N_("Create webhook"),
    "webhook_delete": N_("Delete webhook"),
    "ban": N_("Ban"),
    "unban": N_("Unban"),
    "kick": N_("Kick"),
    "bot_add": N_("Add bot"),
    "prune": N_("Prune"),
    "member_role_update": N_("Role change"),
    "protected_role_violation": N_("Protected role violation"),
    "overwrite_update": N_("Channel permission change"),
    "invite_create": N_("Create invite"),
    "guild_update": N_("Edit server"),
    "hierarchy_change": N_("Hierarchy change"),
    "quarantine": N_("Quarantine"),
    "lockdown": N_("Lockdown"),
    "security": N_("Trini Security"),
}

def action_label(kind: str) -> str:
    return _(ACTION_LABELS[kind]) if kind in ACTION_LABELS else kind


# Niveles de respuesta escalonada.
DEFAULT_LEVELS = {"alert": 30, "block": 50, "quarantine": 70}

SEVERITY_EMOJI = {
    "critical": "🔴",
    "warning": "🟠",
    "info": "🔵",
    "ok": "🟢",
}

AUTHORITY_LEVELS = {
    "owner": 100,
    "extra_owner": 80,
    "trusted_admin": 60,
    "admin": 40,
    "member": 0,
}

AUTHORITY_LABELS = {
    "owner": N_("👑 Server Owner"),
    "extra_owner": N_("🔱 Extra Owner"),
    "trusted_admin": N_("🛡 Trusted Admin"),
    "admin": N_("Administrator"),
    "member": N_("Member"),
}

WHITELIST_TYPES = ("users", "roles", "bots", "webhooks", "channels", "invites")

COLOR_OK = discord.Color.green()
COLOR_WARN = discord.Color.orange()
COLOR_CRIT = discord.Color.red()
COLOR_INFO = discord.Color.from_rgb(52, 152, 219)


def authority_label(level: str) -> str:
    return _(AUTHORITY_LABELS[level]) if level in AUTHORITY_LABELS else level
