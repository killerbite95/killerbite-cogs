"""
Motor de auditoria de Trini Security.

Funciones puras (o casi) que inspeccionan el estado del servidor y devuelven
hallazgos con severidad y penalizacion para el Health Score.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Sequence

import discord

from .constants import ADMIN_PERMS, EVERYONE_DANGEROUS, perm_label
from redbot.core.i18n import Translator

_ = Translator("TriniSecurity", __file__)

log = logging.getLogger("red.killerbite95.trinisecurity.audit")

HEALTH_BASE = 85


@dataclass
class Finding:
    severity: str  # critical | warning | info | ok
    title: str
    detail: str = ""
    penalty: int = 0
    category: str = "guild"


@dataclass
class AuditReport:
    findings: List[Finding] = field(default_factory=list)
    bonuses: List[tuple] = field(default_factory=list)  # (points, text)

    def add(self, *args, **kwargs) -> Finding:
        f = Finding(*args, **kwargs)
        self.findings.append(f)
        return f

    def capped(self, severity: str, title: str, items: Sequence[str], per_item: int, cap: int, category: str, detail_prefix: str = "") -> None:
        if not items:
            return
        shown = list(items[:10])
        extra = len(items) - len(shown)
        detail = detail_prefix + "\n".join(f"• {i}" for i in shown)
        if extra > 0:
            detail += _("\n• … and {extra} more").format(extra=extra)
        self.add(severity, title, detail, min(cap, per_item * len(items)), category)

    @property
    def penalty(self) -> int:
        return sum(f.penalty for f in self.findings)

    @property
    def bonus(self) -> int:
        return sum(b[0] for b in self.bonuses)

    @property
    def score(self) -> int:
        return max(0, min(100, HEALTH_BASE - self.penalty + self.bonus))

    def count(self, severity: str) -> int:
        return sum(1 for f in self.findings if f.severity == severity)


def granted(perms: discord.Permissions, names: Iterable[str]) -> List[str]:
    return [n for n in names if getattr(perms, n, False)]


def overwrite_allows(ow: discord.PermissionOverwrite, names: Iterable[str]) -> List[str]:
    return [n for n in names if getattr(ow, n, None) is True]


def is_private_category(category: discord.CategoryChannel) -> bool:
    ow = category.overwrites_for(category.guild.default_role)
    return ow.view_channel is False


def channel_visible_to_everyone(channel: discord.abc.GuildChannel) -> bool:
    return channel.permissions_for(channel.guild.default_role).view_channel


def admin_roles(guild: discord.Guild) -> List[discord.Role]:
    return [r for r in guild.roles if r.permissions.administrator]


def manageable_roles(role: discord.Role) -> List[discord.Role]:
    """Roles que un miembro con ``role`` (como rol mas alto) podria asignar/editar."""
    if not (role.permissions.manage_roles or role.permissions.administrator):
        return []
    return [
        r
        for r in role.guild.roles
        if r < role and not r.is_default() and not r.managed
    ]


def escalations(role: discord.Role) -> List[tuple]:
    """Roles gestionables por ``role`` que otorgan permisos peligrosos que ``role`` no tiene."""
    if role.permissions.administrator:
        return []
    result = []
    for target in manageable_roles(role):
        extra = [
            p
            for p in ADMIN_PERMS
            if getattr(target.permissions, p) and not getattr(role.permissions, p)
        ]
        if extra:
            result.append((target, extra))
    return result


def permission_origins(member: discord.Member) -> Dict[str, List[str]]:
    """Para cada permiso peligroso, que roles lo conceden al miembro."""
    origins: Dict[str, List[str]] = {}
    if member.guild.owner_id == member.id:
        for p in EVERYONE_DANGEROUS:
            origins.setdefault(p, []).append(_("Server Owner"))
    for role in member.roles:
        for p in EVERYONE_DANGEROUS:
            if getattr(role.permissions, p):
                origins.setdefault(p, []).append("@everyone" if role.is_default() else role.name)
    return origins


async def run_guild_audit(
    guild: discord.Guild,
    *,
    whitelists: Dict[str, List[int]],
    protected_roles: Iterable[int],
    config_bonus: List[tuple],
    profile_hints: Sequence[str] = (),
    extra_findings: Sequence[Dict[str, Any]] = (),
    fetch_remote: bool = True,
) -> AuditReport:
    report = AuditReport()
    report.bonuses.extend(config_bonus)
    everyone = guild.default_role
    me = guild.me

    # --- @everyone a nivel de servidor ---
    ev_admin = granted(everyone.permissions, ADMIN_PERMS)
    if ev_admin:
        report.add(
            "critical",
            _("@everyone has administrative permissions"),
            ", ".join(perm_label(p) for p in ev_admin),
            min(30, 15 * len(ev_admin)),
            "everyone",
        )
    if everyone.permissions.mention_everyone:
        report.add("critical", _("@everyone can mention @everyone/@here"), "", 10, "everyone")
    other = granted(everyone.permissions, [p for p in EVERYONE_DANGEROUS if p not in ADMIN_PERMS and p != "mention_everyone"])
    if other:
        report.add(
            "warning",
            _("@everyone has moderation permissions"),
            ", ".join(perm_label(p) for p in other),
            min(10, 3 * len(other)),
            "everyone",
        )
    invite_channels: List[str] = []
    dangerous_ow: List[str] = []
    for channel in guild.channels:
        if channel.id in whitelists.get("channels", []):
            continue
        ow = channel.overwrites_for(everyone)
        bad = overwrite_allows(ow, ADMIN_PERMS + ("mention_everyone",))
        if bad:
            dangerous_ow.append(f"{channel.mention}: {', '.join(perm_label(p) for p in bad)}")
        if not isinstance(channel, discord.CategoryChannel) and channel.permissions_for(everyone).create_instant_invite and channel_visible_to_everyone(channel):
            invite_channels.append(channel.mention)
    report.capped("critical", _("Dangerous overwrites for @everyone"), dangerous_ow, 10, 20, "channels")
    if invite_channels:
        shown = ", ".join(invite_channels[:8]) + (_(" and {value} more").format(value=len(invite_channels) - 8) if len(invite_channels) > 8 else "")
        report.add(
            "warning",
            _("@everyone can create invites in {count} channel(s)").format(count=len(invite_channels)),
            shown,
            5,
            "everyone",
        )

    # --- Roles ---
    adm = [r for r in admin_roles(guild) if not r.managed]
    if len(adm) > 3:
        report.add(
            "warning",
            _("{count} roles have Administrator").format(count=len(adm)),
            ", ".join(r.mention for r in adm[:15]),
            5,
            "roles",
        )
    elif adm:
        report.add("info", _("{count} role(s) with Administrator").format(count=len(adm)), ", ".join(r.mention for r in adm), 0, "roles")

    webhook_roles = [r for r in guild.roles if r.permissions.manage_webhooks and not r.permissions.administrator and not r.managed]
    if len(webhook_roles) > 3:
        report.add(
            "warning",
            _("{count} roles have Manage Webhooks").format(count=len(webhook_roles)),
            ", ".join(r.mention for r in webhook_roles[:15]),
            3,
            "roles",
        )

    mention_roles = [r for r in guild.roles if r.permissions.mention_everyone and not r.permissions.administrator and not r.is_default()]
    report.capped("warning", _("Roles that can mention @everyone"), [r.mention for r in mention_roles], 2, 6, "roles")

    crit_esc, warn_esc = [], []
    for role in guild.roles:
        if role.is_default() or role.managed:
            continue
        for target, extra in escalations(role):
            text = _("{role} can assign {target} ({join})").format(role=role.mention, target=target.mention, join=', '.join(perm_label(p) for p in extra))
            if "administrator" in extra:
                crit_esc.append(text)
            else:
                warn_esc.append(text)
    report.capped("critical", _("Possible privilege escalation"), crit_esc, 10, 20, "roles",
                  _("A role with Manage Roles above more powerful roles:\n"))
    report.capped("warning", _("Manageable roles with more permissions"), warn_esc, 3, 9, "roles")

    prot = set(protected_roles)
    if profile_hints:
        suggested = [
            r.mention
            for r in guild.roles
            if r.id not in prot
            and not r.managed
            and not r.is_default()
            and any(h in r.name.lower() for h in profile_hints)
        ]
        report.capped("info", _("The profile recommends protecting these roles"), suggested, 2, 6, "roles")

    # --- Miembros ---
    stacked = []
    for member in guild.members:
        if member.bot:
            continue
        admin_like = [r for r in member.roles if granted(r.permissions, ADMIN_PERMS) and not r.is_default()]
        if len(admin_like) >= 3:
            stacked.append(_("{member}: {count} administrative roles").format(member=member.mention, count=len(admin_like)))
    report.capped("info", _("Users stacking administrative roles"), stacked, 0, 0, "users")

    # --- Bots ---
    bots_admin = [
        m for m in guild.members
        if m.bot and m.id != me.id and m.guild_permissions.administrator and m.id not in whitelists.get("bots", [])
    ]
    report.capped(
        "warning",
        _("{count} bot(s) with Administrator").format(count=len(bots_admin)),
        [_("{b} — check whether it really needs it").format(b=b.mention) for b in bots_admin],
        4,
        10,
        "bots",
    )
    risky_bots = [
        m for m in guild.members
        if m.bot and m.id != me.id and not m.guild_permissions.administrator
        and len(granted(m.guild_permissions, ADMIN_PERMS)) >= 4
        and m.id not in whitelists.get("bots", [])
    ]
    report.capped(
        "info",
        _("Bots with many administrative permissions"),
        [f"{b.mention}: {', '.join(perm_label(p) for p in granted(b.guild_permissions, ADMIN_PERMS))}" for b in risky_bots],
        1,
        4,
        "bots",
    )

    # --- Canales privados ---
    leaks, unsynced = [], []
    for category in guild.categories:
        if not is_private_category(category):
            continue
        for ch in category.channels:
            if ch.id in whitelists.get("channels", []):
                continue
            if channel_visible_to_everyone(ch):
                leaks.append(_("{ch} is visible to @everyone inside **{category_name}**").format(ch=ch.mention, category_name=category.name))
            elif not ch.permissions_synced:
                unsynced.append(f"{ch.mention} ({category.name})")
    report.capped("critical", _("Exposed channels in private categories"), leaks, 8, 16, "channels")
    report.capped("info", _("Private channels not synced with their category"), unsynced, 1, 5, "channels")

    # --- Configuracion del servidor ---
    if guild.mfa_level == discord.MFALevel.disabled:
        report.add("warning", _("2FA isn't required for moderators"), _("Server Settings → Safety Setup → Require 2FA."), 5, "guild")
    if guild.verification_level == discord.VerificationLevel.none:
        report.add("info", _("Verification level: none"), "", 3, "guild")

    # --- Permisos de La Trini ---
    missing = [p for p in ("view_audit_log", "manage_roles", "manage_webhooks", "kick_members") if not getattr(me.guild_permissions, p)]
    if missing:
        report.add(
            "warning",
            _("Trini Security doesn't have all the permissions it needs"),
            ", ".join(perm_label(p) for p in missing),
            5,
            "bot",
        )

    # --- Webhooks e invitaciones ---
    if fetch_remote:
        if me.guild_permissions.manage_webhooks:
            try:
                hooks = await guild.webhooks()
                unknown = [
                    h for h in hooks
                    if h.id not in whitelists.get("webhooks", [])
                    and (h.channel_id not in whitelists.get("channels", []))
                    and h.type == discord.WebhookType.incoming
                ]
                if unknown:
                    report.capped(
                        "info",
                        _("{count} webhook(s) not whitelisted").format(count=len(unknown)),
                        [_("`{name}` in <#{channel_id}> (ID {id})").format(name=h.name, channel_id=h.channel_id, id=h.id) for h in unknown],
                        1,
                        5,
                        "webhooks",
                    )
                else:
                    report.add("ok", _("No unknown webhooks detected"), "", 0, "webhooks")
            except discord.HTTPException:
                pass
        if me.guild_permissions.manage_guild:
            try:
                invites = await guild.invites()
                perma = [
                    i for i in invites
                    if (i.max_age or 0) == 0 and i.code not in whitelists.get("invites", [])
                ]
                report.capped(
                    "warning",
                    _("{count} permanent invite(s)").format(count=len(perma)),
                    [_("`{code}` by {value} · {uses} uses").format(code=i.code, value=i.inviter.mention if i.inviter else '?', uses=i.uses) for i in perma],
                    2,
                    6,
                    "invites",
                )
            except discord.HTTPException:
                pass

    for raw in extra_findings:
        try:
            report.add(
                raw.get("severity", "info"),
                raw["title"],
                raw.get("detail", ""),
                int(raw.get("penalty", 0)),
                raw.get("category", "integrations"),
            )
        except Exception:
            continue

    if not report.findings:
        report.add("ok", _("No problems detected"), "", 0)
    return report
