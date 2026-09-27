from __future__ import annotations

import discord

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
    "administrator": "Administrator",
    "manage_guild": "Manage Guild",
    "manage_roles": "Manage Roles",
    "manage_channels": "Manage Channels",
    "manage_webhooks": "Manage Webhooks",
    "ban_members": "Ban Members",
    "kick_members": "Kick Members",
    "mention_everyone": "Mention @everyone",
    "manage_messages": "Manage Messages",
    "manage_threads": "Manage Threads",
    "moderate_members": "Timeout Members",
    "manage_nicknames": "Manage Nicknames",
    "manage_events": "Manage Events",
    "manage_expressions": "Manage Expressions",
    "view_audit_log": "View Audit Log",
    "create_instant_invite": "Create Invite",
    "view_channel": "View Channel",
    "send_messages": "Send Messages",
    "connect": "Connect",
}


PERM_ALIASES = {"read_messages": "view_channel", "manage_emojis": "manage_expressions", "use_slash_commands": "use_application_commands"}


def perm_label(name: str) -> str:
    name = PERM_ALIASES.get(name, name)
    return PERM_LABELS.get(name, name.replace("_", " ").title())


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
    "channel_delete": "Eliminar canal",
    "channel_create": "Crear canal",
    "channel_update": "Editar canal",
    "role_delete": "Eliminar rol",
    "role_create": "Crear rol",
    "role_update": "Editar rol",
    "admin_grant": "Otorgar Administrator",
    "everyone_change": "Cambiar @everyone",
    "dangerous_permission": "Permiso peligroso",
    "webhook_create": "Crear webhook",
    "webhook_delete": "Eliminar webhook",
    "ban": "Ban",
    "unban": "Unban",
    "kick": "Kick",
    "bot_add": "Añadir bot",
    "prune": "Prune",
    "member_role_update": "Cambio de roles",
    "protected_role_violation": "Violacion de rol protegido",
    "overwrite_update": "Cambio de permisos de canal",
    "invite_create": "Crear invitacion",
    "guild_update": "Editar servidor",
    "hierarchy_change": "Cambio de jerarquia",
    "quarantine": "Quarantine",
    "lockdown": "Lockdown",
    "security": "Trini Security",
}

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
    "owner": "👑 Server Owner",
    "extra_owner": "🔱 Extra Owner",
    "trusted_admin": "🛡 Trusted Admin",
    "admin": "Administrador",
    "member": "Miembro",
}

WHITELIST_TYPES = ("users", "roles", "bots", "webhooks", "channels", "invites")

COLOR_OK = discord.Color.green()
COLOR_WARN = discord.Color.orange()
COLOR_CRIT = discord.Color.red()
COLOR_INFO = discord.Color.from_rgb(52, 152, 219)
