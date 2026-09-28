"""
Motor en tiempo real de Trini Security.

Escucha ``on_audit_log_entry_create`` (requiere el permiso View Audit Log) para
atribuir cada accion a su autor, registrar el timeline, aplicar Protected
Roles, Lockdown, Security Watch y Anti-Nuke, y abrir incidentes.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Deque, Dict, List, Optional, Tuple

import discord
from redbot.core import commands

from .audit import granted
from .constants import (
    action_label,
    ADMIN_PERMS,
    COLOR_CRIT,
    COLOR_WARN,
    EVERYONE_DANGEROUS,
    perm_label,
)
from .views import compare_view, incident_view
from redbot.core.i18n import Translator, set_contextual_locales_from_guild

_ = Translator("TriniSecurity", __file__)

log = logging.getLogger("red.killerbite95.trinisecurity.engine")

A = discord.AuditLogAction
MAX_EVENTS = 3000
EVENT_RETENTION = 30 * 86400
INCIDENT_MERGE_WINDOW = 15 * 60
ALERTS_PER_MINUTE = 8

# Accion -> clave de threshold.
THRESHOLD_KEY = {
    "admin_grant": "dangerous_permission",
    "everyone_change": "dangerous_permission",
    "dangerous_permission": "dangerous_permission",
    "protected_role_violation": "dangerous_permission",
}

Revert = Optional[Callable[[], Awaitable[str]]]


@dataclass
class Ctx:
    """Configuracion relevante para procesar un evento."""

    authority: Dict[str, List[int]]
    watch: Dict[str, Any]
    antinuke: Dict[str, Any]
    lockdown: Dict[str, Any]
    protected: Dict[str, Dict[str, Any]]
    whitelists: Dict[str, List[int]]
    temp_whitelist: List[Dict[str, Any]]
    extra: Dict[str, Any] = field(default_factory=dict)


def _perm_changes(before: Optional[discord.Permissions], after: Optional[discord.Permissions]) -> Tuple[List[str], List[str]]:
    if before is None or after is None:
        return [], []
    added = [p for p, v in after if v and not getattr(before, p)]
    removed = [p for p, v in before if v and not getattr(after, p)]
    return added, removed


def _ow_state(allow: Optional[discord.Permissions], deny: Optional[discord.Permissions], perm: str) -> Optional[bool]:
    if allow is not None and getattr(allow, perm, False):
        return True
    if deny is not None and getattr(deny, perm, False):
        return False
    return None


STATE_ICON = {True: "✅", False: "❌", None: "➖"}


def _target_label(target: Any, fallback_id: Optional[int]) -> str:
    """Nombre legible de un usuario del audit log (puede ser solo un ``discord.Object``)."""
    if isinstance(target, (discord.User, discord.Member)):
        return f"{target} ({target.id})"
    tid = getattr(target, "id", None) or fallback_id
    return f"<@{tid}>" if tid else "?"


class EngineMixin:
    """Mixin con el procesamiento de eventos. Requiere los atributos de TriniSecurity."""

    bot: Any
    config: Any

    def _engine_init(self) -> None:
        # guild_id -> actor_id -> deque[(ts, type, points, event_id)]
        self._risk: Dict[int, Dict[int, Deque[Tuple[float, str, int, int]]]] = defaultdict(lambda: defaultdict(deque))
        # guild_id -> actor_id -> expires
        self._restricted: Dict[int, Dict[int, float]] = defaultdict(dict)
        self._locks: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        # Serializa las quarantines por servidor: durante un nuke llegan muchos
        # eventos a la vez y dos quarantines simultaneas del mismo usuario
        # sobrescribirian la lista de roles guardados con una vacia.
        self._q_locks: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._alert_times: Dict[int, Deque[float]] = defaultdict(deque)
        self._alert_muted_notice: Dict[int, float] = {}

    # ------------------------------------------------------------------
    # Contexto / autoridad
    # ------------------------------------------------------------------

    async def _load_ctx(self, guild: discord.Guild) -> Ctx:
        g = self.config.guild(guild)
        return Ctx(
            authority=await g.authority(),
            watch=await g.watch(),
            antinuke=self._merged_antinuke(await g.antinuke()),
            lockdown=await g.lockdown(),
            protected=await g.protected_roles(),
            whitelists=await self._get_whitelists(guild),
            temp_whitelist=await g.temp_whitelist(),
        )

    def _authority_sync(self, guild: discord.Guild, user_id: int, ctx: Ctx) -> str:
        if user_id == guild.owner_id:
            return "owner"
        if user_id in ctx.authority.get("extra_owners", []) or user_id in getattr(self.bot, "owner_ids", set()):
            return "extra_owner"
        if user_id in ctx.authority.get("trusted_admins", []):
            return "trusted_admin"
        member = guild.get_member(user_id)
        if member is not None and (member.guild_permissions.administrator or member.guild_permissions.manage_guild):
            return "admin"
        return "member"

    def _antinuke_immune(self, guild: discord.Guild, user_id: int, level: str, ctx: Ctx) -> bool:
        if level in ("owner", "extra_owner"):
            return True
        if level == "trusted_admin" and ctx.antinuke.get("trusted_immune", True):
            return True
        if user_id in ctx.whitelists.get("users", []):
            return True
        member = guild.get_member(user_id)
        if member is not None and any(r.id in ctx.whitelists.get("roles", []) for r in member.roles):
            return True
        return False

    def _temp_whitelisted(self, role_id: int, user_ids: List[int], ctx: Ctx) -> bool:
        now = time.time()
        for entry in ctx.temp_whitelist:
            if entry["role"] == role_id and entry["user"] in user_ids and entry["expires"] > now:
                return True
        return False

    def _can_manage_protected(
        self, guild: discord.Guild, role: discord.Role, actor_id: int, target_id: int, level: str, ctx: Ctx
    ) -> Tuple[bool, str]:
        cfg = ctx.protected.get(str(role.id))
        if cfg is None:
            return True, ""
        if level == "owner":
            return True, ""
        if ctx.lockdown.get("active") and level != "extra_owner":
            return False, _("Lockdown active: only the Owner and Extra Owners can manage protected roles.")
        actor = guild.get_member(actor_id)
        if actor is not None and actor.bot and not cfg.get("bots", False):
            return False, _("Bots can't assign this protected role.")
        if actor_id == target_id and not cfg.get("self_assign", False) and level != "extra_owner":
            return False, _("Self-assigning this protected role isn't allowed.")
        if level in cfg.get("allowed", ["extra_owner", "trusted_admin"]):
            return True, ""
        if level == "extra_owner":
            return True, ""
        if actor_id in cfg.get("allowed_users", []):
            return True, ""
        if actor is not None and any(r.id in cfg.get("allowed_roles", []) for r in actor.roles):
            return True, ""
        if cfg.get("temporary_whitelist", True) and self._temp_whitelisted(role.id, [actor_id, target_id], ctx):
            return True, ""
        return False, _("The user isn't authorized to manage this role.")

    # ------------------------------------------------------------------
    # Registro de eventos
    # ------------------------------------------------------------------

    async def record_event(
        self,
        guild: discord.Guild,
        etype: str,
        *,
        actor_id: Optional[int],
        target_id: Optional[int] = None,
        target_name: str = "",
        detail: str = "",
        severity: str = "info",
        points: int = 0,
    ) -> Dict[str, Any]:
        now = time.time()
        async with self._locks[guild.id]:
            eid = await self.config.guild(guild).next_event_id()
            await self.config.guild(guild).next_event_id.set(eid + 1)
            event = {
                "id": eid,
                "ts": round(now, 2),
                "type": etype,
                "actor": actor_id,
                "target": target_id,
                "target_name": target_name[:100],
                "detail": detail[:400],
                "severity": severity,
                "points": points,
            }
            async with self.config.guild(guild).events() as events:
                events.append(event)
                cutoff = now - EVENT_RETENTION
                while events and (len(events) > MAX_EVENTS or events[0]["ts"] < cutoff):
                    events.pop(0)
        return event

    # ------------------------------------------------------------------
    # Alertas
    # ------------------------------------------------------------------

    async def _send_log(
        self,
        guild: discord.Guild,
        embed: discord.Embed,
        *,
        view: Optional[discord.ui.View] = None,
        ping: bool = False,
        critical: bool = False,
    ) -> Optional[discord.Message]:
        channel_id = await self.config.guild(guild).log_channel()
        channel = guild.get_channel_or_thread(channel_id) if channel_id else None
        if channel is None:
            return None
        now = time.time()
        times = self._alert_times[guild.id]
        while times and now - times[0] > 60:
            times.popleft()
        if len(times) >= ALERTS_PER_MINUTE and not critical:
            if now - self._alert_muted_notice.get(guild.id, 0) > 60:
                self._alert_muted_notice[guild.id] = now
                try:
                    await channel.send(_("🔇 Too many alerts: non-critical ones are muted for a minute. Use `security timeline`."))
                except discord.HTTPException:
                    pass
            return None
        times.append(now)
        content = None
        mentions = discord.AllowedMentions.none()
        if ping:
            role_id = await self.config.guild(guild).alert_role()
            role = guild.get_role(role_id) if role_id else None
            if role is not None:
                content = role.mention
                mentions = discord.AllowedMentions(roles=[role])
        try:
            kwargs: Dict[str, Any] = {"content": content, "embed": embed, "allowed_mentions": mentions}
            if view is not None:
                kwargs["view"] = view
            return await channel.send(**kwargs)
        except discord.HTTPException:
            log.warning("No se pudo enviar alerta en %s", guild.id)
            return None

    def _has_backups(self) -> bool:
        return self.bot.get_cog("TriniBackups") is not None

    async def _watch_alert(
        self,
        guild: discord.Guild,
        ctx: Ctx,
        title: str,
        *,
        actor_id: Optional[int],
        target: str,
        changes: List[str] = (),
        risk: List[str] = (),
        action_taken: str = "",
        critical: bool = False,
        health_delta: bool = False,
    ) -> None:
        if not ctx.watch.get("enabled") and not ctx.lockdown.get("active") and not action_taken:
            return
        embed = discord.Embed(
            title=f"{'🚨' if critical else '⚠️'} {title}",
            color=COLOR_CRIT if critical else COLOR_WARN,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name=_("Target"), value=target[:1024] or "—", inline=True)
        embed.add_field(name=_("Done by"), value=f"<@{actor_id}>" if actor_id else _("unknown"), inline=True)
        if changes:
            embed.add_field(name=_("CHANGES"), value="\n".join(changes)[:1024], inline=False)
        if risk:
            embed.add_field(name=_("RISK"), value="\n".join(risk)[:1024], inline=False)
        if action_taken:
            embed.add_field(name=_("Action"), value=action_taken[:1024], inline=False)
        if health_delta:
            try:
                previous = await self.config.guild(guild).last_health()
                report = await self.compute_health(guild, fetch_remote=False)
                await self.config.guild(guild).last_health.set(report.score)
                if previous is not None and previous != report.score:
                    diff = report.score - previous
                    embed.add_field(name=_("Security Score"), value=f"{'+' if diff > 0 else ''}{diff} → **{report.score}**/100", inline=False)
            except Exception:
                log.exception("Error calculando health delta")
        view = compare_view(0) if self._has_backups() and critical else None
        await self._send_log(guild, embed, view=view, ping=critical, critical=critical)

    # ------------------------------------------------------------------
    # Listener principal
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry) -> None:
        guild = entry.guild
        if guild is None or self.bot.user is None:
            return
        if entry.user_id is None or entry.user_id == self.bot.user.id:
            return
        await set_contextual_locales_from_guild(self.bot, guild)
        try:
            if await self.bot.cog_disabled_in_guild(self, guild):
                return
            await self._handle_entry(entry)
        except Exception:
            log.exception("Error procesando entrada de audit log %s en %s", entry.action, guild.id)

    async def _handle_entry(self, entry: discord.AuditLogEntry) -> None:
        guild = entry.guild
        ctx = await self._load_ctx(guild)
        actor_id = entry.user_id
        level = self._authority_sync(guild, actor_id, ctx)
        action = entry.action
        before, after = entry.before, entry.after
        scores = ctx.antinuke["scores"]
        lockdown = ctx.lockdown.get("active", False)
        high_trust = level in ("owner", "extra_owner")

        etype: Optional[str] = None
        target_id: Optional[int] = getattr(entry.target, "id", None)
        target_name = ""
        detail = ""
        severity = "info"
        points = 0
        revert: Revert = None
        force_revert = False
        # Las alertas se envian al final, DESPUES de intentar revertir, para que
        # "Accion" refleje lo que de verdad ha pasado (y no lo que se intento).
        alerts: List[Dict[str, Any]] = []

        def alert(title: str, *, from_revert: bool = False, **kw: Any) -> None:
            kw.setdefault("actor_id", actor_id)
            alerts.append({"title": title, "from_revert": from_revert, **kw})

        if action == A.channel_delete:
            etype = "channel_delete"
            target_name = f"#{getattr(before, 'name', target_id)}"
            points, severity = scores["channel_delete"], "warning"

        elif action == A.channel_create:
            etype = "channel_create"
            target_name = f"#{getattr(after, 'name', target_id)}"
            points = scores["channel_create"]
            channel = guild.get_channel(target_id) if target_id else None
            if channel is not None:
                async def revert() -> str:
                    await channel.delete(reason="Trini Security: accion bloqueada")
                    return _("Channel {target_name} deleted.").format(target_name=target_name)

        elif action == A.channel_update:
            etype = "channel_update"
            target_name = f"<#{target_id}>"
            if getattr(before, "name", None) and getattr(after, "name", None):
                detail = _("name: {before_name} → {after_name}").format(before_name=before.name, after_name=after.name)

        elif action in (A.overwrite_create, A.overwrite_update, A.overwrite_delete):
            etype, target_name, detail, severity, points, revert, ow_alert = await self._handle_overwrite(entry, ctx)
            if lockdown and severity == "critical" and revert is not None and level not in ("owner", "extra_owner", "trusted_admin"):
                force_revert = True
            if ow_alert:
                alert(ow_alert[0], target=target_name, changes=ow_alert[1], risk=ow_alert[2],
                      critical=severity == "critical", from_revert=force_revert)

        elif action == A.role_create:
            perms = getattr(after, "permissions", None) or discord.Permissions.none()
            role = guild.get_role(target_id) if target_id else None
            target_name = f"@{getattr(after, 'name', target_id)}"
            if perms.administrator:
                etype, severity, points = "admin_grant", "critical", scores["admin_grant"]
                detail = _("Role created with Administrator")
            elif granted(perms, ADMIN_PERMS):
                etype, severity, points = "dangerous_permission", "warning", scores["dangerous_permission"]
                detail = _("Role created with ") + ", ".join(perm_label(p) for p in granted(perms, ADMIN_PERMS))
            else:
                etype, points = "role_create", scores["role_create"]
            if role is not None:
                async def revert() -> str:
                    await role.delete(reason="Trini Security: accion bloqueada")
                    return _("Role {target_name} deleted.").format(target_name=target_name)
            if etype != "role_create":
                if lockdown and not high_trust and level != "trusted_admin" and revert is not None:
                    force_revert = True
                alert(_("Administrative role created"), target=target_name, changes=[detail],
                      critical=severity == "critical", health_delta=True, from_revert=force_revert)

        elif action == A.role_update:
            etype, target_name, detail, severity, points, revert, force_revert, sub_alert = await self._handle_role_update(entry, ctx, level)
            if sub_alert:
                alert(**sub_alert)

        elif action == A.role_delete:
            etype = "role_delete"
            target_name = f"@{getattr(before, 'name', target_id)}"
            points, severity = scores["role_delete"], "warning"
            if str(target_id) in ctx.protected:
                severity = "critical"
                points += scores["protected_role_violation"] if level not in ("owner", "extra_owner") else 0
                alert(_("Protected role deleted"), target=target_name,
                      risk=[_("Use `backup restore` to recover it if it wasn't intended.")], critical=True,
                      action_taken=_("Logged. A deleted role can't be reverted automatically."))

        elif action == A.member_role_update:
            etype, target_name, detail, severity, points, revert, force_revert, sub_alert = await self._handle_member_roles(entry, ctx, level)
            if sub_alert:
                alert(**sub_alert)

        elif action == A.webhook_create:
            etype = "webhook_create"
            channel = getattr(after, "channel", None)
            channel_id = getattr(channel, "id", None)
            target_name = _("webhook `{value}`").format(value=getattr(after, 'name', target_id))
            detail = _("in <#{channel_id}>").format(channel_id=channel_id) if channel_id else ""
            points, severity = scores["webhook_create"], "warning"
            whitelisted = channel_id in ctx.whitelists.get("channels", []) or target_id in ctx.whitelists.get("webhooks", [])
            hook_id = target_id

            async def revert() -> str:
                for hook in await guild.webhooks():
                    if hook.id == hook_id:
                        await hook.delete(reason="Trini Security: webhook bloqueado")
                        return _("Webhook deleted.")
                return _("Webhook not found.")

            if lockdown and not high_trust:
                force_revert = True
            if not whitelisted:
                alert(_("New webhook"), target=f"{target_name} {detail}", from_revert=force_revert)

        elif action == A.webhook_delete:
            etype = "webhook_delete"
            target_name = _("webhook `{value}`").format(value=getattr(before, 'name', target_id))

        elif action == A.bot_add:
            etype = "bot_add"
            bot_member = guild.get_member(target_id) if target_id else None
            target_name = str(bot_member or target_id)
            points, severity = scores["bot_add"], "warning"
            whitelisted = target_id in ctx.whitelists.get("bots", [])
            policy_kick = (ctx.antinuke.get("enabled") and ctx.antinuke.get("bot_policy") == "kick") or lockdown
            if not whitelisted and not high_trust and policy_kick and target_id:
                force_revert = True
                bot_id = target_id

                async def revert() -> str:
                    # Aunque el bot aun no este en la cache se puede expulsar por ID.
                    await guild.kick(discord.Object(bot_id), reason="Trini Security: bot no autorizado")
                    return _("Bot kicked automatically.")
            if not whitelisted:
                alert(_("Unauthorized bot") if not high_trust else _("New bot"),
                      target=f"<@{target_id}> ({target_name})",
                      risk=[_("It isn't in the bot whitelist (`security whitelist add bots`).")],
                      critical=force_revert, from_revert=force_revert)
            else:
                severity, points = "info", 0

        elif action == A.ban:
            etype, points, severity = "ban", scores["ban"], "warning"
            target_name = _target_label(entry.target, target_id)
        elif action == A.unban:
            etype = "unban"
            target_name = _target_label(entry.target, target_id)
        elif action == A.kick:
            etype, points, severity = "kick", scores["kick"], "warning"
            target_name = _target_label(entry.target, target_id)
        elif action == A.member_prune:
            etype, points, severity = "prune", scores["prune"], "critical"
            removed = getattr(entry.extra, "members_removed", "?")
            detail = _("{removed} members kicked").format(removed=removed)
            alert(_("Member prune"), target=detail, critical=True)

        elif action == A.invite_create:
            etype = "invite_create"
            code = getattr(after, "code", None)
            max_age = getattr(after, "max_age", None)
            target_name = _("invite `{code}`").format(code=code)
            permanent = max_age == 0
            detail = _("permanent") if permanent else _("expires in {max_age}s").format(max_age=max_age)
            if lockdown and not high_trust and code:
                force_revert = True

                async def revert() -> str:
                    invite = await self.bot.fetch_invite(code)
                    await invite.delete(reason="Trini Security: lockdown")
                    return _("Invite deleted (lockdown).")
            if permanent and code not in ctx.whitelists.get("invites", []):
                severity = "warning"
                alert(_("Permanent invite created"), target=target_name, from_revert=force_revert)

        elif action == A.guild_update:
            etype = "guild_update"
            target_name = guild.name
            changes = []
            for attr, label in (("mfa_level", "2FA"), ("verification_level", _("Verification")), ("vanity_url_code", _("Vanity URL")), ("name", _("Name")), ("owner", "Owner")):
                if hasattr(after, attr):
                    changes.append(f"{label}: {getattr(before, attr, '?')} → {getattr(after, attr, '?')}")
            detail = "; ".join(changes)
            if any(c.startswith(("2FA", "Verificacion", "Owner", "Vanity")) for c in changes):
                severity = "warning"
                alert(_("Server settings change"), target=guild.name, changes=changes)

        if etype is None:
            for a in alerts:
                a.pop("from_revert", None)
                await self._watch_alert(guild, ctx, a.pop("title"), **a)
            return

        event = await self.record_event(
            guild, etype, actor_id=actor_id, target_id=target_id, target_name=target_name,
            detail=detail, severity=severity, points=points,
        )

        restricted = self._restricted[guild.id].get(actor_id, 0) > time.time()
        revert_result: Optional[str] = None
        if force_revert or (restricted and points > 0 and revert is not None):
            reason = "lockdown" if (force_revert and lockdown) else (_("protection") if force_revert else _("restricted user"))
            revert_result = await self._do_revert(guild, revert, event, reason=reason)
            revert = None

        for a in alerts:
            from_revert = a.pop("from_revert", False)
            if revert_result and (from_revert or not a.get("action_taken")):
                a["action_taken"] = revert_result
            await self._watch_alert(guild, ctx, a.pop("title"), **a)

        if points > 0 and ctx.antinuke.get("enabled") and not self._antinuke_immune(guild, actor_id, level, ctx):
            await self._escalate(guild, actor_id, event, ctx, revert)

    async def _do_revert(self, guild: discord.Guild, revert: Revert, event: Dict[str, Any], *, reason: str) -> Optional[str]:
        if revert is None:
            return None
        try:
            result = await revert()
        except discord.HTTPException as exc:
            result = _("Couldn't revert: {value}").format(value=exc.text if hasattr(exc, 'text') else exc)
        except Exception as exc:  # pragma: no cover - defensivo
            log.exception("Error revirtiendo accion")
            result = _("Couldn't revert: {exc}").format(exc=exc)
        await self.record_event(
            guild, "security", actor_id=self.bot.user.id, target_name=_("revert #{id}").format(id=event['id']),
            detail=f"{result} ({reason})", severity="info",
        )
        return result

    # ------------------------------------------------------------------
    # Handlers especificos
    # ------------------------------------------------------------------

    async def _handle_overwrite(self, entry: discord.AuditLogEntry, ctx: Ctx):
        guild = entry.guild
        channel = entry.target if isinstance(entry.target, discord.abc.GuildChannel) else guild.get_channel(getattr(entry.target, "id", 0))
        extra = entry.extra
        target = guild.get_role(getattr(extra, "id", 0)) or guild.get_member(getattr(extra, "id", 0))
        target_label = "@everyone" if isinstance(target, discord.Role) and target.is_default() else (
            f"@{target.name}" if isinstance(target, discord.Role) else (target.mention if target else str(getattr(extra, "id", "?")))
        )
        ch_label = channel.mention if channel else f"<#{getattr(entry.target, 'id', '?')}>"
        b_allow, b_deny = getattr(entry.before, "allow", None), getattr(entry.before, "deny", None)
        a_allow, a_deny = getattr(entry.after, "allow", None), getattr(entry.after, "deny", None)
        watched = ("view_channel", "send_messages", "connect", "create_instant_invite") + EVERYONE_DANGEROUS
        changes = []
        granted_now = []
        for perm in watched:
            old = _ow_state(b_allow, b_deny, perm)
            new = _ow_state(a_allow, a_deny, perm)
            if old != new:
                changes.append(f"{perm_label(perm)}: {target_label} {STATE_ICON[old]} → {STATE_ICON[new]}")
                if new is True:
                    granted_now.append(perm)
        detail = "; ".join(changes)[:400]
        severity, points = "info", 0
        is_everyone = isinstance(target, discord.Role) and target.is_default()
        private = False
        if channel is not None:
            cat = channel.category if not isinstance(channel, discord.CategoryChannel) else channel
            private = bool(cat and cat.overwrites_for(guild.default_role).view_channel is False) or (
                channel.overwrites_for(guild.default_role).view_channel is False
            )
        alert = None
        if channel is not None and channel.id in ctx.whitelists.get("channels", []):
            return "overwrite_update", f"{ch_label}", detail, severity, points, None, None
        dangerous = [p for p in granted_now if p in EVERYONE_DANGEROUS]
        if is_everyone and (dangerous or ("view_channel" in granted_now and private)):
            severity, points = "critical", ctx.antinuke["scores"]["everyone_change"]
            alert = (_("@everyone permissions changed"), changes, [_("Private channel exposed to @everyone.")] if "view_channel" in granted_now else [])
        elif dangerous:
            severity = "warning"
            points = ctx.antinuke["scores"]["dangerous_permission"]
            alert = (_("Dangerous channel permissions"), changes, [])
        elif private and changes:
            severity = "warning"
            alert = (_("Private channel change"), changes, [])

        revert: Revert = None
        if channel is not None and target is not None and severity != "info":
            before_ow = discord.PermissionOverwrite.from_pair(b_allow or discord.Permissions.none(), b_deny or discord.Permissions.none())

            async def revert() -> str:
                if entry.action == A.overwrite_create:
                    await channel.set_permissions(target, overwrite=None, reason="Trini Security: accion bloqueada")
                else:
                    await channel.set_permissions(target, overwrite=before_ow, reason="Trini Security: accion bloqueada")
                return _("Permissions of {ch_label} restored.").format(ch_label=ch_label)
        return "overwrite_update", f"{ch_label}", detail, severity, points, revert, alert

    async def _handle_role_update(self, entry: discord.AuditLogEntry, ctx: Ctx, level: str):
        guild = entry.guild
        role = guild.get_role(getattr(entry.target, "id", 0))
        before_p = getattr(entry.before, "permissions", None)
        after_p = getattr(entry.after, "permissions", None)
        added, removed = _perm_changes(before_p, after_p)
        name = role.name if role else str(getattr(entry.target, "id", "?"))
        is_default = role is not None and role.is_default()
        target_name = "@everyone" if is_default else f"@{name}"
        scores = ctx.antinuke["scores"]
        changes = [f"{perm_label(p)}\n❌ → ✅" for p in added] + [f"{perm_label(p)}\n✅ → ❌" for p in removed]
        others = []
        for attr in ("name", "color", "hoist", "mentionable"):
            if hasattr(entry.after, attr):
                others.append(f"{attr}: {getattr(entry.before, attr, '?')} → {getattr(entry.after, attr, '?')}")
        detail = "; ".join([f"+{p}" for p in added] + [f"-{p}" for p in removed] + others)
        etype, severity, points = "role_update", "info", 0
        protected = role is not None and str(role.id) in ctx.protected
        lockdown = ctx.lockdown.get("active", False)

        revert: Revert = None
        if role is not None and before_p is not None and after_p is not None and (added or removed):
            async def revert() -> str:
                await role.edit(permissions=before_p, reason="Trini Security: cambio revertido")
                return _("Permissions of {target_name} restored.").format(target_name=target_name)

        dangerous_added = [p for p in added if p in EVERYONE_DANGEROUS]
        if is_default and dangerous_added:
            etype, severity, points = "everyone_change", "critical", scores["everyone_change"]
        elif "administrator" in added:
            etype, severity, points = "admin_grant", "critical", scores["admin_grant"]
        elif any(p in ADMIN_PERMS for p in added):
            etype, severity, points = "dangerous_permission", "warning", scores["dangerous_permission"]
        elif is_default and "create_instant_invite" in added:
            severity = "warning"

        force = False
        if protected and level not in ("owner", "extra_owner") and level not in ctx.protected[str(role.id)].get("allowed", []):
            severity = "critical"
            points += scores["protected_role_violation"]
            etype = "protected_role_violation"
            force = revert is not None
        elif lockdown and etype != "role_update" and level not in ("owner", "extra_owner", "trusted_admin"):
            force = revert is not None

        sub_alert = None
        if etype != "role_update" or (severity != "info" and changes):
            risk = []
            if role is not None and ("manage_roles" in added or "administrator" in added):
                can = [r.mention for r in guild.roles if r < role and not r.is_default() and not r.managed]
                if can:
                    risk.append(_("This role can now modify:\n") + "\n".join(f"• {r}" for r in can[:10]) + (_("\n• … and {value} more").format(value=len(can) - 10) if len(can) > 10 else ""))
            sub_alert = {
                "title": _("Critical change") if severity == "critical" else _("Permission change"),
                "target": target_name, "changes": changes, "risk": risk,
                "critical": severity == "critical", "health_delta": True, "from_revert": force,
            }
        return etype, target_name, detail, severity, points, revert, force, sub_alert

    async def _handle_member_roles(self, entry: discord.AuditLogEntry, ctx: Ctx, level: str):
        guild = entry.guild
        target_id = getattr(entry.target, "id", 0)
        member = guild.get_member(target_id)
        if member is None and target_id:
            try:
                member = await guild.fetch_member(target_id)
            except discord.HTTPException:
                member = None
        added = [guild.get_role(r.id) for r in (getattr(entry.after, "roles", None) or [])]
        removed = [guild.get_role(r.id) for r in (getattr(entry.before, "roles", None) or [])]
        added = [r for r in added if r is not None]
        removed = [r for r in removed if r is not None]
        scores = ctx.antinuke["scores"]
        target_name = member.mention if member else f"<@{target_id}>"
        etype, severity, points, detail = None, "info", 0, ""
        revert: Revert = None
        force = False

        violations = []
        for role in added:
            if str(role.id) not in ctx.protected:
                continue
            ok, reason = self._can_manage_protected(guild, role, entry.user_id, target_id, level, ctx)
            if not ok:
                violations.append((role, reason))
        if violations and member is not None:
            roles = [r for r, _v in violations]
            etype, severity = "protected_role_violation", "critical"
            points = scores["protected_role_violation"] if level not in ("owner", "extra_owner") else 0
            detail = _("Attempt to assign ") + ", ".join(r.name for r in roles)
            try:
                await member.remove_roles(*roles, reason="Trini Security: rol protegido")
                taken = _("Assignment reverted.")
                self.bot.dispatch("trini_protected_role_blocked", guild, entry.user_id, member, roles)
            except discord.HTTPException:
                taken = _("⚠️ Couldn't revert (hierarchy/permissions).")
            embed = discord.Embed(title=_("🚨 Protected Role violation"), color=COLOR_CRIT, timestamp=discord.utils.utcnow())
            embed.description = _("<@{user_id}> tried to assign:\n{join}\n\nTo:\n{member}\n\n**Action:**\n{taken}\n\n**Reason:**\n{value}").format(user_id=entry.user_id, join=', '.join(r.mention for r in roles), member=member.mention, taken=taken, value=violations[0][1])
            await self._send_log(guild, embed, ping=True, critical=True)
            return etype, target_name, detail, severity, points, None, False, None

        admin_added = [r for r in added if r.permissions.administrator]
        dangerous_added = [r for r in added if granted(r.permissions, ADMIN_PERMS)]
        protected_removed = [r for r in removed if str(r.id) in ctx.protected]
        if admin_added:
            etype, severity, points = "admin_grant", "critical", scores["admin_grant"]
        elif dangerous_added:
            etype, severity, points = "dangerous_permission", "warning", scores["dangerous_permission"]
        elif protected_removed or any(str(r.id) in ctx.protected for r in added):
            etype, severity = "member_role_update", "warning"
        else:
            return None, target_name, "", "info", 0, None, False, None

        detail = " ".join([f"+{r.name}" for r in added] + [f"-{r.name}" for r in removed])
        roles_to_revert = dangerous_added
        if member is not None and roles_to_revert:
            async def revert() -> str:
                await member.remove_roles(*roles_to_revert, reason="Trini Security: accion bloqueada")
                return _("Roles removed from {member}.").format(member=member)
        if ctx.lockdown.get("active") and dangerous_added and level not in ("owner", "extra_owner", "trusted_admin"):
            force = revert is not None
        sub_alert = None
        if etype in ("admin_grant", "dangerous_permission"):
            sub_alert = {
                "title": _("Administrator granted") if admin_added else _("Administrative roles assigned"),
                "target": target_name, "changes": [f"+ {r.mention}" for r in dangerous_added],
                "critical": bool(admin_added), "from_revert": force,
            }
        elif protected_removed:
            sub_alert = {
                "title": _("Protected role removed"), "target": target_name,
                "changes": [f"- {r.mention}" for r in protected_removed],
            }
        return etype, target_name, detail, severity, points, revert, force, sub_alert

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        """Detecta cambios de jerarquia: un rol con poder que pasa por encima de roles protegidos."""
        guild = after.guild
        if before.position == after.position or not granted(after.permissions, ("administrator", "manage_roles")):
            return
        await set_contextual_locales_from_guild(self.bot, guild)
        try:
            if await self.bot.cog_disabled_in_guild(self, guild):
                return
            ctx = await self._load_ctx(guild)
            if not ctx.watch.get("enabled") or not ctx.protected:
                return
            now_below = [
                guild.get_role(int(rid)) for rid in ctx.protected
                if guild.get_role(int(rid)) is not None and guild.get_role(int(rid)) < after
            ]
            new = [r for r in now_below if r.position >= before.position and r != after]
            if not new:
                return
            await self.record_event(
                guild, "hierarchy_change", actor_id=None, target_id=after.id, target_name=f"@{after.name}",
                detail=_("Now above ") + ", ".join(r.name for r in new), severity="warning",
            )
            await self._watch_alert(
                guild, ctx, _("Hierarchy change"), actor_id=None, target=after.mention,
                risk=[_("With Manage Roles it can now manage protected roles:\n") + "\n".join(f"• {r.mention}" for r in new)],
            )
        except Exception:
            log.exception("Error en on_guild_role_update")

    # ------------------------------------------------------------------
    # Anti-nuke
    # ------------------------------------------------------------------

    async def _escalate(self, guild: discord.Guild, actor_id: int, event: Dict[str, Any], ctx: Ctx, revert: Revert) -> None:
        an = ctx.antinuke
        now = time.time()
        tracker = self._risk[guild.id][actor_id]
        tracker.append((now, event["type"], event["points"], event["id"]))
        while tracker and now - tracker[0][0] > 3600:
            tracker.popleft()
        window = an.get("window", 600)
        score = sum(p for ts, _t, p, _e in tracker if now - ts <= window)

        key = THRESHOLD_KEY.get(event["type"], event["type"])
        per_min, per_hour = (an["thresholds"].get(key) or [0, 0])[:2]
        same = [ts for ts, t, _p, _e in tracker if THRESHOLD_KEY.get(t, t) == key]
        c_min = sum(1 for ts in same if now - ts <= 60)
        c_hour = len(same)
        threshold_hit = (per_min and c_min >= per_min) or (per_hour and c_hour >= per_hour)

        levels = an["levels"]
        if score >= levels["quarantine"]:
            response = "quarantine"
        elif score >= levels["block"] or threshold_hit:
            response = "block"
        elif score >= levels["alert"]:
            response = "alert"
        else:
            return

        actions: List[str] = []
        if response in ("block", "quarantine"):
            self._restricted[guild.id][actor_id] = now + window
            result = await self._do_revert(guild, revert, event, reason=f"anti-nuke ({response})")
            if result:
                actions.append(result)
            actions.append(_("Sensitive actions temporarily blocked."))
        quarantined_user = None
        if response == "quarantine":
            member = guild.get_member(actor_id)
            if member is not None and str(actor_id) not in await self.config.guild(guild).quarantined():
                ok, msg = await self.quarantine_member(guild, member, reason=f"Anti-Nuke: risk score {score}", by=None)
                actions.append(msg)
                if ok:
                    quarantined_user = actor_id

        event_ids = [eid for ts, _t, _p, eid in tracker if now - ts <= window]
        incident = await self._upsert_incident(
            guild, actor_id, event_ids, response, score, actions,
            threshold=_("{get} {c_min}/min · {c_hour}/h").format(get=action_label(key), c_min=c_min, c_hour=c_hour) if threshold_hit else "",
        )
        await self._publish_incident(guild, incident, quarantined_user=quarantined_user, new_actions=actions)

    # ------------------------------------------------------------------
    # Incidentes
    # ------------------------------------------------------------------

    async def _upsert_incident(
        self, guild: discord.Guild, actor_id: int, event_ids: List[int], level: str, score: int,
        actions: List[str], threshold: str = "",
    ) -> Dict[str, Any]:
        now = time.time()
        events = {e["id"]: e for e in await self.config.guild(guild).events() if e["id"] in set(event_ids)}
        async with self._locks[guild.id]:
            async with self.config.guild(guild).incidents() as incidents:
                current = None
                for inc in incidents.values():
                    if inc["actor"] == actor_id and not inc.get("closed") and now - inc["end"] <= INCIDENT_MERGE_WINDOW:
                        current = inc
                        break
                if current is None:
                    iid = await self.config.guild(guild).next_incident_id()
                    await self.config.guild(guild).next_incident_id.set(iid + 1)
                    start = min((e["ts"] for e in events.values()), default=now)
                    current = {
                        "id": iid,
                        "actor": actor_id,
                        "start": start,
                        "end": now,
                        "events": [],
                        "level": level,
                        "max_score": score,
                        "actions": [],
                        "closed": False,
                        "backup": None,
                        "alert": None,
                        "threshold": threshold,
                    }
                    incidents[str(iid)] = current
                ids = set(current["events"]) | set(events.keys())
                current["events"] = sorted(ids)
                current["end"] = now
                rank = ["alert", "block", "quarantine"]
                if rank.index(level) > rank.index(current["level"]):
                    current["level"] = level
                current["max_score"] = max(current["max_score"], score)
                current["actions"] = (current["actions"] + [x for x in actions if x not in current["actions"]])[-30:]
                if threshold:
                    current["threshold"] = threshold
                if current["backup"] is None:
                    backups = self.bot.get_cog("TriniBackups")
                    if backups is not None and hasattr(backups, "latest_snapshot_before"):
                        try:
                            meta = await backups.latest_snapshot_before(guild, current["start"])
                            if meta:
                                current["backup"] = {"id": meta["id"], "ts": meta["created_at"], "name": meta.get("name")}
                        except Exception:
                            log.exception("No se pudo consultar backups")
                result = dict(current)
            if len(incidents) > 200:
                async with self.config.guild(guild).incidents() as incs:
                    for key in sorted(incs, key=lambda k: int(k))[:-200]:
                        del incs[key]
        return result

    async def incident_embed(self, guild: discord.Guild, incident: Dict[str, Any]) -> discord.Embed:
        events = [e for e in await self.config.guild(guild).events() if e["id"] in set(incident["events"])]
        # Eventos relacionados: todo lo ocurrido en la ventana, de cualquier actor.
        window_events = [
            e for e in await self.config.guild(guild).events()
            if incident["start"] - 60 <= e["ts"] <= incident["end"] + 5 and e["type"] != "security"
        ]
        counts: Dict[str, int] = defaultdict(int)
        for e in window_events:
            counts[e["type"]] += 1
        level_label = {"alert": "🟠 Alerta", "block": "⛔ Bloqueo", "quarantine": "🔒 Quarantine"}[incident["level"]]
        embed = discord.Embed(
            title=_("INCIDENT #{id}").format(id=incident['id']),
            color=COLOR_CRIT if incident["level"] != "alert" else COLOR_WARN,
            timestamp=discord.utils.utcnow(),
        )
        embed.description = (
            _("**Start:** <t:{start}:T>\n**End:** <t:{end}:T>\n\n**Main actor:** <@{actor}>\n**Level:** {level_label} · Max risk score **{max_score}**\n").format(start=int(incident['start']), end=int(incident['end']), actor=incident['actor'], level_label=level_label, max_score=incident['max_score'])
            + (_("**Threshold:** {threshold}\n").format(threshold=incident['threshold']) if incident.get("threshold") else "")
            + _("\n**Actor's events:** {count}\n**Related events:** {count2}").format(count=len(events), count2=len(window_events))
            + (_(" · CLOSED") if incident.get("closed") else "")
        )
        summary = [
            ("channel_delete", _("Channels deleted")), ("channel_create", _("Channels created")),
            ("role_delete", _("Roles deleted")), ("role_update", _("Roles modified")),
            ("admin_grant", _("Administrator granted")), ("everyone_change", _("@everyone changes")),
            ("dangerous_permission", _("Dangerous permissions")), ("ban", _("Users banned")),
            ("kick", _("Users kicked")), ("webhook_create", _("Webhooks created")),
            ("bot_add", _("Bots added")), ("protected_role_violation", _("Protected role violations")),
        ]
        lines = [f"{label}: **{counts[k]}**" for k, label in summary if counts.get(k)]
        if lines:
            embed.add_field(name=_("Summary"), value="\n".join(lines), inline=False)
        if incident.get("actions"):
            embed.add_field(name=_("Trini Security actions"), value="\n".join(f"• {a}" for a in incident["actions"][-8:])[:1024], inline=False)
        backup = incident.get("backup")
        embed.add_field(
            name=_("Previous backup"),
            value=(f"<t:{int(backup['ts'])}:f> · `{backup['id']}`" if backup else (_("None") if self._has_backups() else _("Trini Backups not loaded"))),
            inline=False,
        )
        return embed

    async def _publish_incident(self, guild: discord.Guild, incident: Dict[str, Any], *, quarantined_user: Optional[int], new_actions: List[str]) -> None:
        embed = await self.incident_embed(guild, incident)
        quarantined = await self.config.guild(guild).quarantined()
        q_user = quarantined_user or (incident["actor"] if str(incident["actor"]) in quarantined else None)
        view = incident_view(incident["id"], q_user, self._has_backups())
        channel_id = await self.config.guild(guild).log_channel()
        channel = guild.get_channel_or_thread(channel_id) if channel_id else None
        alert = incident.get("alert")
        if alert and channel is not None and alert[0] == channel.id:
            try:
                msg = channel.get_partial_message(alert[1])
                await msg.edit(embed=embed, view=view)
                if quarantined_user:
                    await self._notify_owners(guild, incident)
                return
            except discord.HTTPException:
                pass
        msg = await self._send_log(guild, embed, view=view, ping=True, critical=True)
        if msg is not None:
            async with self.config.guild(guild).incidents() as incidents:
                if str(incident["id"]) in incidents:
                    incidents[str(incident["id"])]["alert"] = [msg.channel.id, msg.id]
        if incident["level"] == "quarantine" or quarantined_user:
            await self._notify_owners(guild, incident)

    async def _notify_owners(self, guild: discord.Guild, incident: Dict[str, Any]) -> None:
        async with self.config.guild(guild).incidents() as incidents:
            inc = incidents.get(str(incident["id"]))
            if inc is None or inc.get("owners_notified"):
                return
            inc["owners_notified"] = True
        authority = await self.config.guild(guild).authority()
        ids = {guild.owner_id, *authority.get("extra_owners", []), *authority.get("trusted_admins", [])}
        embed = await self.incident_embed(guild, incident)
        embed.set_author(name=_("Trini Security · {guild_name}").format(guild_name=guild.name))
        for uid in ids:
            member = guild.get_member(uid)
            if member is None or member.bot:
                continue
            try:
                await member.send(embed=embed)
            except discord.HTTPException:
                continue

    async def build_incident_report(self, guild: discord.Guild, incident_id: int) -> Optional[str]:
        incident = (await self.config.guild(guild).incidents()).get(str(incident_id))
        if incident is None:
            return None
        events = [
            e for e in await self.config.guild(guild).events()
            if incident["start"] - 60 <= e["ts"] <= incident["end"] + 5
        ]
        def who(uid):
            if uid is None:
                return "desconocido"
            m = guild.get_member(uid)
            return f"{m} ({uid})" if m else str(uid)
        lines = [
            _("TRINI SECURITY - INCIDENT #{id}").format(id=incident['id']),
            _("Server: {guild_name} ({guild_id})").format(guild_name=guild.name, guild_id=guild.id),
            _("Start: {strftime} UTC").format(strftime=time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(incident['start']))),
            _("End:   {strftime} UTC").format(strftime=time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(incident['end']))),
            _("Main actor: {value}").format(value=who(incident['actor'])),
            _("Level: {level} · Max risk score: {max_score}").format(level=incident['level'], max_score=incident['max_score']),
            _("Threshold: {value}").format(value=incident.get('threshold') or '-'),
            _("Previous backup: {value}").format(value=incident['backup']['id'] if incident.get('backup') else '-'),
            "",
            _("TRINI SECURITY ACTIONS"),
            *[f"  - {a}" for a in incident.get("actions", [])],
            "",
            "TIMELINE",
        ]
        for e in events:
            mark = "*" if e["id"] in incident["events"] else " "
            lines.append(
                f"{mark} {time.strftime('%H:%M:%S', time.gmtime(e['ts']))}  #{e['id']:<6} {who(e['actor']):<40} "
                f"{action_label(e['type']):<28} {e['target_name']}  {e['detail']}"
                + (f"  (+{e['points']})" if e["points"] else "")
            )
        lines.append("")
        lines.append(_("* = event attributed to the main actor"))
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Quarantine
    # ------------------------------------------------------------------

    async def quarantine_member(
        self, guild: discord.Guild, member: discord.Member, *, reason: str, by: Optional[discord.abc.User]
    ) -> Tuple[bool, str]:
        async with self._q_locks[guild.id]:
            if str(member.id) in await self.config.guild(guild).quarantined():
                return False, _("{member} was already in quarantine.").format(member=member.mention)
            return await self._quarantine_member_locked(guild, member, reason=reason, by=by)

    async def _quarantine_member_locked(
        self, guild: discord.Guild, member: discord.Member, *, reason: str, by: Optional[discord.abc.User]
    ) -> Tuple[bool, str]:
        me = guild.me
        if member.id == guild.owner_id:
            return False, _("The Owner can't be quarantined.")
        if member.top_role >= me.top_role:
            return False, _("⚠️ Couldn't quarantine {member}: their role is above the bot.").format(member=member)
        if member.bot:
            try:
                await member.kick(reason=f"Trini Security quarantine: {reason}")
                await self.record_event(guild, "quarantine", actor_id=by.id if by else self.bot.user.id, target_id=member.id,
                                        target_name=str(member), detail=_("Bot kicked · {reason}").format(reason=reason), severity="critical")
                return True, _("Bot {member} kicked (quarantine).").format(member=member)
            except discord.HTTPException:
                return False, _("Couldn't kick the bot {member}.").format(member=member)
        dangerous = [
            r for r in member.roles
            if not r.is_default() and not r.managed and r < me.top_role
            and (granted(r.permissions, ADMIN_PERMS + ("mention_everyone", "manage_messages", "moderate_members")))
        ]
        try:
            if dangerous:
                await member.remove_roles(*dangerous, reason=f"Trini Security quarantine: {reason}")
            q_role_id = (await self.config.guild(guild).antinuke()).get("quarantine_role")
            q_role = guild.get_role(q_role_id) if q_role_id else None
            if q_role is not None and q_role < me.top_role:
                await member.add_roles(q_role, reason="Trini Security quarantine")
        except discord.HTTPException as exc:
            return False, _("Error applying quarantine: {exc}").format(exc=exc)
        async with self.config.guild(guild).quarantined() as q:
            q[str(member.id)] = {
                "roles": [r.id for r in dangerous],
                "at": int(time.time()),
                "reason": reason,
                "by": by.id if by else None,
            }
        await self.record_event(
            guild, "quarantine", actor_id=by.id if by else self.bot.user.id, target_id=member.id,
            target_name=str(member), detail=_("{count} roles removed · {reason}").format(count=len(dangerous), reason=reason), severity="critical",
        )
        self._restricted[guild.id][member.id] = time.time() + 3600
        return True, _("Quarantine applied to {member}: {count} role(s) removed.").format(member=member.mention, count=len(dangerous))

    async def release_quarantine(self, guild: discord.Guild, user_id: int, by: discord.abc.User) -> Tuple[bool, str]:
        async with self._q_locks[guild.id]:
            async with self.config.guild(guild).quarantined() as q:
                data = q.pop(str(user_id), None)
        if data is None:
            return False, _("That user isn't in quarantine.")
        member = guild.get_member(user_id)
        self._restricted[guild.id].pop(user_id, None)
        self._risk[guild.id].pop(user_id, None)
        restored = []
        if member is not None:
            roles = [guild.get_role(rid) for rid in data["roles"]]
            roles = [r for r in roles if r is not None and r < guild.me.top_role]
            try:
                if roles:
                    await member.add_roles(*roles, reason=f"Trini Security: quarantine liberada por {by}")
                    restored = roles
                q_role_id = (await self.config.guild(guild).antinuke()).get("quarantine_role")
                q_role = guild.get_role(q_role_id) if q_role_id else None
                if q_role is not None and q_role in member.roles:
                    await member.remove_roles(q_role, reason="Trini Security: quarantine liberada")
            except discord.HTTPException as exc:
                return False, _("Quarantine removed but roles couldn't be restored: {exc}").format(exc=exc)
        await self.record_event(
            guild, "quarantine", actor_id=by.id, target_id=user_id, target_name=str(member or user_id),
            detail=_("Released · {count} roles restored").format(count=len(restored)), severity="info",
        )
        await self._settings_log(guild, by, "quarantine_release", f"<@{user_id}>")
        return True, _("🔓 Quarantine released. Roles restored: {value}.").format(value=', '.join(r.mention for r in restored) or _('none'))

    # ------------------------------------------------------------------
    # Lockdown
    # ------------------------------------------------------------------

    async def enable_lockdown(self, guild: discord.Guild, by: discord.abc.User, *, disable_invites: bool) -> List[str]:
        notes: List[str] = []
        backups = self.bot.get_cog("TriniBackups")
        if backups is not None and hasattr(backups, "create_snapshot"):
            try:
                meta = await backups.create_snapshot(guild, name=f"pre-lockdown-{time.strftime('%Y-%m-%d-%H%M')}", kind="security", author=by)
                notes.append(_("Automatic backup: `{id}`").format(id=meta['id']))
            except Exception:
                log.exception("No se pudo crear backup pre-lockdown")
        invites_by_us = False
        if disable_invites:
            if "INVITES_DISABLED" in guild.features:
                notes.append(_("Invites were already paused."))
            else:
                try:
                    await guild.edit(invites_disabled=True, reason=f"Trini Security lockdown por {by}")
                    invites_by_us = True
                    notes.append(_("Invites paused."))
                except discord.HTTPException:
                    notes.append(_("⚠️ Couldn't pause invites."))
        async with self.config.guild(guild).lockdown() as lk:
            lk.update({"active": True, "by": by.id, "at": int(time.time()), "invites_disabled_by_us": invites_by_us})
        async with self.config.guild(guild).watch() as watch:
            watch["previous_level"] = watch.get("level", "normal")
            watch["previous_enabled"] = watch.get("enabled", False)
            watch["enabled"] = True
            watch["level"] = "max"
        await self.record_event(guild, "lockdown", actor_id=by.id, target_name=guild.name, detail=_("Lockdown enabled"), severity="critical")
        await self._settings_log(guild, by, "lockdown_enable", "; ".join(notes))
        return notes

    async def disable_lockdown(self, guild: discord.Guild, by: discord.abc.User) -> List[str]:
        notes: List[str] = []
        lk = await self.config.guild(guild).lockdown()
        if lk.get("invites_disabled_by_us"):
            try:
                await guild.edit(invites_disabled=False, reason=f"Trini Security: fin de lockdown por {by}")
                notes.append(_("Invites resumed."))
            except discord.HTTPException:
                notes.append(_("⚠️ Couldn't resume invites."))
        async with self.config.guild(guild).lockdown() as lk:
            lk.update({"active": False, "by": by.id, "at": int(time.time()), "invites_disabled_by_us": False})
        async with self.config.guild(guild).watch() as watch:
            watch["level"] = watch.pop("previous_level", "normal")
            watch["enabled"] = watch.pop("previous_enabled", watch.get("enabled", False))
        await self.record_event(guild, "lockdown", actor_id=by.id, target_name=guild.name, detail=_("Lockdown disabled"), severity="warning")
        await self._settings_log(guild, by, "lockdown_disable", "; ".join(notes))
        return notes
