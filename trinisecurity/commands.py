from __future__ import annotations

import io
import re
import time
from typing import Any, List, Literal, Optional, Union

import discord
from redbot.core import commands
from redbot.core.utils.chat_formatting import box, pagify
from redbot.core.utils.views import SimpleMenu

from .audit import (
    AuditReport,
    channel_visible_to_everyone,
    escalations,
    granted,
    is_private_category,
    manageable_roles,
    permission_origins,
)
from .constants import (
    action_label,
    ADMIN_PERMS,
    authority_label,
    AUTHORITY_LEVELS,
    COLOR_CRIT,
    COLOR_INFO,
    COLOR_OK,
    COLOR_WARN,
    DEFAULT_SCORES,
    DEFAULT_THRESHOLDS,
    EVERYONE_DANGEROUS,
    SEVERITY_EMOJI,
    WHITELIST_TYPES,
    perm_label,
)
from .views import ConfirmView, incident_view
from redbot.core.i18n import Translator

_ = Translator("TriniSecurity", __file__)

DURATION_RE = re.compile(r"(\d+)\s*([smhdw])", re.I)
UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2, "ok": 3}
NO_MENTIONS = discord.AllowedMentions.none()

WhitelistType = Literal["users", "roles", "bots", "webhooks", "channels", "invites"]


def parse_duration(text: str) -> Optional[int]:
    matches = DURATION_RE.findall(text or "")
    if not matches:
        return int(text) * 60 if text and text.isdigit() else None
    return sum(int(n) * UNITS[u.lower()] for n, u in matches)


def fmt_duration(seconds: int) -> str:
    parts = []
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60), ("s", 1)):
        if seconds >= size:
            parts.append(f"{seconds // size}{unit}")
            seconds %= size
    return " ".join(parts) or "0s"


async def is_security_staff(ctx: commands.Context) -> bool:
    if ctx.guild is None:
        return False
    cog = ctx.bot.get_cog("TriniSecurity")
    if cog is None:
        return False
    return await cog.get_authority_level(ctx.author) != "member"


class CommandsMixin:
    bot: Any
    config: Any

    async def _require(self, ctx: commands.Context, minimum: str) -> bool:
        level = await self.get_authority_level(ctx.author)
        if AUTHORITY_LEVELS[level] >= AUTHORITY_LEVELS[minimum]:
            return True
        await ctx.send(
            _("🔒 You need to be **{value}** in Trini Security for this (your level: {value2}).").format(value=authority_label(minimum), value2=authority_label(level))
        )
        return False

    def _report_embeds(self, guild: discord.Guild, report: AuditReport, title: str) -> List[discord.Embed]:
        score = report.score
        color = COLOR_OK if score >= 80 else (COLOR_WARN if score >= 60 else COLOR_CRIT)
        header = _("Server: **{guild_name}**\nHealth Score: **{score} / 100**\n\n🔴 Critical risks: **{count}**\n🟠 Warnings: **{count2}**\n🔵 Notes: **{count3}**").format(guild_name=guild.name, score=score, count=report.count('critical'), count2=report.count('warning'), count3=report.count('info'))
        embeds: List[discord.Embed] = []
        current = discord.Embed(title=title, description=header, color=color)
        size = len(header)
        for f in sorted(report.findings, key=lambda x: SEVERITY_ORDER[x.severity]):
            name = f"{SEVERITY_EMOJI[f.severity]} {f.title}"[:256]
            value = (f.detail or "​")[:1024]
            if len(current.fields) >= 12 or size + len(name) + len(value) > 5000:
                embeds.append(current)
                current = discord.Embed(title=_("{title} (cont.)").format(title=title), color=color)
                size = 0
            current.add_field(name=name, value=value, inline=False)
            size += len(name) + len(value)
        embeds.append(current)
        for i, e in enumerate(embeds, 1):
            e.set_footer(text=_("Page {i}/{count} · Trini Security").format(i=i, count=len(embeds)))
        return embeds

    async def _send_pages(self, ctx: commands.Context, embeds: List[discord.Embed]) -> None:
        if len(embeds) == 1:
            await ctx.send(embed=embeds[0], allowed_mentions=NO_MENTIONS)
        else:
            await SimpleMenu(embeds, use_select_menu=len(embeds) > 5).start(ctx)

    # ==================================================================
    # Grupo principal
    # ==================================================================

    @commands.hybrid_group(name="security")
    @commands.guild_only()
    @commands.check(is_security_staff)
    async def security(self, ctx: commands.Context):
        """Trini Security: server audit and protection."""

    @security.command(name="audit")
    async def sec_audit(self, ctx: commands.Context):
        """Full server security audit."""
        async with ctx.typing():
            report = await self.compute_health(ctx.guild)
            await self.config.guild(ctx.guild).last_health.set(report.score)
            await self.config.guild(ctx.guild).last_findings.set(
                [f.title for f in report.findings if f.severity in ("critical", "warning")]
            )
        await self._send_pages(ctx, self._report_embeds(ctx.guild, report, _("🔐 Security Audit")))

    @security.command(name="health")
    async def sec_health(self, ctx: commands.Context):
        """Health Score with its penalties and bonuses."""
        async with ctx.typing():
            report = await self.compute_health(ctx.guild)
        lines = []
        for f in sorted(report.findings, key=lambda x: -x.penalty):
            if f.penalty:
                lines.append(f"**-{f.penalty}**  {f.title}")
        for pts, text in report.bonuses:
            lines.append(f"**+{pts}**  {text}")
        embed = discord.Embed(
            title=_("Security Health"),
            description=_("# {score} / 100\nBase {value} · penalties -{penalty} · bonuses +{bonus}\n\n").format(score=report.score, value=85, penalty=report.penalty, bonus=report.bonus)
            + ("\n".join(lines) or _("No penalties.")),
            color=COLOR_OK if report.score >= 80 else (COLOR_WARN if report.score >= 60 else COLOR_CRIT),
        )
        missing = []
        if not report.bonuses or all("Protected" not in b[1] for b in report.bonuses):
            missing.append(_("+5 Protected Roles (`security protectedrole add`)"))
        if all("Anti-Nuke" not in b[1] for b in report.bonuses):
            missing.append(_("+5 Anti-Nuke (`security antinuke enable`)"))
        if all("Watch" not in b[1] for b in report.bonuses):
            missing.append(_("+3 Security Watch (`security watch enable`)"))
        if all("Backups" not in b[1] for b in report.bonuses):
            missing.append(_("+2 Automatic backups (`backup schedule daily`)"))
        if missing:
            embed.add_field(name=_("How to raise the score"), value="\n".join(missing), inline=False)
        await ctx.send(embed=embed)

    @security.command(name="user")
    async def sec_user(self, ctx: commands.Context, member: discord.Member):
        """A user's effective permissions and where they really come from."""
        perms = member.guild_permissions
        shown = ADMIN_PERMS + ("mention_everyone", "manage_messages", "moderate_members", "view_audit_log")
        table = "\n".join(f"{perm_label(p):<20} {'✅' if getattr(perms, p) else '❌'}" for p in shown)
        origins = permission_origins(member)
        origin_lines = "\n".join(
            f"{perm_label(p):<20} {', '.join(src[:3])}{'…' if len(src) > 3 else ''}"
            for p, src in origins.items() if p in shown
        )
        level = await self.get_authority_level(member)
        embed = discord.Embed(title=f"🔎 {member}", color=COLOR_INFO)
        embed.add_field(name=_("Effective permissions"), value=box(table), inline=False)
        if origin_lines:
            embed.add_field(name=_("Source"), value=box(origin_lines)[:1024], inline=False)
        embed.add_field(name=_("Trini Security"), value=authority_label(level), inline=True)
        embed.add_field(name=_("Highest role"), value=member.top_role.mention, inline=True)
        quarantined = await self.config.guild(ctx.guild).quarantined()
        if str(member.id) in quarantined:
            embed.add_field(name=_("Status"), value=_("🔒 In quarantine"), inline=True)
        esc = escalations(member.top_role) if not perms.administrator else []
        if esc:
            embed.add_field(
                name=_("⚠️ Possible escalation"),
                value="\n".join(f"Puede asignar {r.mention}: {', '.join(perm_label(p) for p in extra)}" for r, extra in esc[:8])[:1024],
                inline=False,
            )
        admin_roles = [r.mention for r in member.roles if granted(r.permissions, ADMIN_PERMS) and not r.is_default()]
        if len(admin_roles) >= 2:
            embed.add_field(name=_("Stacked administrative roles"), value=", ".join(admin_roles)[:1024], inline=False)
        await ctx.send(embed=embed, allowed_mentions=NO_MENTIONS)

    @security.command(name="role")
    async def sec_role(self, ctx: commands.Context, role: discord.Role):
        """Role audit: permissions, hierarchy and roles it can modify."""
        perms = [perm_label(p) for p in EVERYONE_DANGEROUS if getattr(role.permissions, p)]
        embed = discord.Embed(title=f"🎭 {role.name}", color=role.color if role.color.value else COLOR_INFO)
        embed.add_field(name=_("Members"), value=str(len(role.members)), inline=True)
        embed.add_field(name=_("Position"), value=f"{role.position}/{len(ctx.guild.roles) - 1}", inline=True)
        embed.add_field(name=_("Managed"), value=_("yes (integration/bot)") if role.managed else "no", inline=True)
        embed.add_field(name=_("Sensitive permissions"), value=", ".join(perms) or "ninguno", inline=False)
        manage = manageable_roles(role)
        if manage:
            embed.add_field(
                name=_("Can modify ({count})").format(count=len(manage)),
                value=", ".join(r.mention for r in sorted(manage, reverse=True)[:25])[:1024],
                inline=False,
            )
        esc = escalations(role)
        if esc:
            embed.add_field(
                name=_("🔴 Privilege escalation"),
                value="\n".join(f"{r.mention}: {', '.join(perm_label(p) for p in extra)}" for r, extra in esc[:10])[:1024],
                inline=False,
            )
        assigners = [r.mention for r in ctx.guild.roles if r > role and (r.permissions.manage_roles or r.permissions.administrator) and not r.managed]
        if assigners:
            embed.add_field(name=_("Can assign it"), value=", ".join(assigners[:20])[:1024], inline=False)
        protected = (await self.config.guild(ctx.guild).protected_roles()).get(str(role.id))
        if protected:
            embed.add_field(name=_("🛡 Protected role"), value=box("\n".join(f"{k}: {v}" for k, v in protected.items()))[:1024], inline=False)
        await ctx.send(embed=embed, allowed_mentions=NO_MENTIONS)

    @security.command(name="channel")
    async def sec_channel(self, ctx: commands.Context, channel: Union[discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel, discord.ForumChannel, discord.StageChannel]):
        """Channel audit: overwrites, visibility and sync."""
        embed = discord.Embed(title=f"# {channel.name}", color=COLOR_INFO)
        visible = channel_visible_to_everyone(channel)
        embed.add_field(name=_("Visible to @everyone"), value="✅" if visible else "❌", inline=True)
        if not isinstance(channel, discord.CategoryChannel) and channel.category:
            priv = is_private_category(channel.category)
            embed.add_field(name=_("Category"), value=f"{channel.category.name} {'(privada)' if priv else ''}", inline=True)
            embed.add_field(name=_("Synced with category"), value="✅" if channel.permissions_synced else "❌", inline=True)
            if priv and visible:
                embed.add_field(name=_("🔴 Risk"), value=_("Channel visible to @everyone inside a private category."), inline=False)
        watched = ("view_channel", "send_messages", "create_instant_invite", "mention_everyone", "manage_messages", "manage_channels", "manage_webhooks", "manage_roles")
        lines = []
        for target, ow in channel.overwrites.items():
            allow, deny = ow.pair()
            parts = [f"+{perm_label(p)}" for p in watched if getattr(allow, p)] + [f"-{perm_label(p)}" for p in watched if getattr(deny, p)]
            if not parts:
                continue
            label = "@everyone" if isinstance(target, discord.Role) and target.is_default() else (f"@{target.name}" if isinstance(target, discord.Role) else f"{target}")
            lines.append(f"{label}: {' '.join(parts)}")
        embed.add_field(name=_("Overwrites ({count})").format(count=len(channel.overwrites)), value=box("\n".join(lines[:20]) or "ninguno")[:1024], inline=False)
        viewers = [r.mention for r in ctx.guild.roles if not r.is_default() and channel.permissions_for(r).view_channel and not r.permissions.administrator][:20] if not visible else []
        if viewers:
            embed.add_field(name=_("Roles with access"), value=", ".join(viewers)[:1024], inline=False)
        dangerous = []
        for target, ow in channel.overwrites.items():
            bad = [p for p in ADMIN_PERMS if getattr(ow, p) is True]
            if bad:
                dangerous.append(f"{getattr(target, 'mention', target)}: {', '.join(perm_label(p) for p in bad)}")
        if dangerous:
            embed.add_field(name=_("🟠 Administrative overwrites"), value="\n".join(dangerous)[:1024], inline=False)
        await ctx.send(embed=embed, allowed_mentions=NO_MENTIONS)

    @security.command(name="bot")
    async def sec_bot(self, ctx: commands.Context, bot: discord.Member):
        """Bot audit: permissions, whitelist and who added it."""
        if not bot.bot:
            return await ctx.send(_("That member isn't a bot."))
        perms = bot.guild_permissions
        wl = await self._get_whitelists(ctx.guild)
        embed = discord.Embed(title=f"🤖 {bot}", color=COLOR_WARN if perms.administrator else COLOR_INFO)
        embed.add_field(name=_("Administrator"), value=_("✅ (check whether it needs it)") if perms.administrator else "❌", inline=True)
        embed.add_field(name=_("Whitelist"), value="✅" if bot.id in wl["bots"] else "❌", inline=True)
        embed.add_field(name=_("Added"), value=f"<t:{int(bot.joined_at.timestamp())}:R>" if bot.joined_at else "?", inline=True)
        sens = [perm_label(p) for p in EVERYONE_DANGEROUS if getattr(perms, p)]
        embed.add_field(name=_("Sensitive permissions"), value=", ".join(sens) or "ninguno", inline=False)
        managed = [r for r in bot.roles if r.managed]
        if managed:
            embed.add_field(name=_("Integration role"), value=managed[0].mention, inline=True)
        events = await self.config.guild(ctx.guild).events()
        added = next((e for e in reversed(events) if e["type"] == "bot_add" and e["target"] == bot.id), None)
        if added:
            embed.add_field(name=_("Added by"), value=f"<@{added['actor']}> <t:{int(added['ts'])}:f>", inline=False)
        elif ctx.guild.me.guild_permissions.view_audit_log:
            try:
                async for entry in ctx.guild.audit_logs(action=discord.AuditLogAction.bot_add, limit=100):
                    if entry.target and entry.target.id == bot.id:
                        embed.add_field(name=_("Added by"), value=f"{entry.user.mention if entry.user else '?'} <t:{int(entry.created_at.timestamp())}:f>", inline=False)
                        break
            except discord.HTTPException:
                pass
        await ctx.send(embed=embed, allowed_mentions=NO_MENTIONS)

    @security.command(name="webhooks")
    async def sec_webhooks(self, ctx: commands.Context):
        """List the server's webhooks and their whitelist status."""
        try:
            hooks = await ctx.guild.webhooks()
        except discord.Forbidden:
            return await ctx.send(_("I need the **Manage Webhooks** permission."))
        wl = await self._get_whitelists(ctx.guild)
        if not hooks:
            return await ctx.send(_("🟢 There are no webhooks in the server."))
        lines = []
        for h in hooks:
            ok = h.id in wl["webhooks"] or h.channel_id in wl["channels"]
            creator = _(" by {user}").format(user=h.user) if h.user else ""
            lines.append(f"{'🟢' if ok else '🟠'} `{h.name}` <#{h.channel_id}> · {h.type.name}{creator} · `{h.id}`")
        for page in pagify("\n".join(lines), page_length=3900):
            await ctx.send(embed=discord.Embed(title=_("🪝 Webhooks ({count})").format(count=len(hooks)), description=page, color=COLOR_INFO), allowed_mentions=NO_MENTIONS)

    @security.command(name="invites")
    async def sec_invites(self, ctx: commands.Context):
        """List invites, flagging permanent ones."""
        try:
            invites = await ctx.guild.invites()
        except discord.Forbidden:
            return await ctx.send(_("I need the **Manage Server** permission."))
        wl = await self._get_whitelists(ctx.guild)
        if not invites:
            return await ctx.send(_("There are no active invites."))
        lines = []
        for i in sorted(invites, key=lambda x: x.uses or 0, reverse=True):
            perma = (i.max_age or 0) == 0
            icon = "🟢" if i.code in wl["invites"] else ("🟠" if perma else "⚪")
            exp = "permanente" if perma else _("expires <t:{timestamp}:R>").format(timestamp=int(i.expires_at.timestamp())) if i.expires_at else ""
            lines.append(_("{icon} `{code}` · {value} · {uses} uses · {exp}").format(icon=icon, code=i.code, value=i.inviter or '?', uses=i.uses, exp=exp))
        for page in pagify("\n".join(lines), page_length=3900):
            await ctx.send(embed=discord.Embed(title=_("✉️ Invites ({count})").format(count=len(invites)), description=page, color=COLOR_INFO), allowed_mentions=NO_MENTIONS)

    @security.command(name="timeline")
    async def sec_timeline(self, ctx: commands.Context, period: str = "15m", member: Optional[discord.Member] = None):
        """Security event timeline. E.g.: `security timeline 15m @user`."""
        seconds = parse_duration(period)
        if not seconds:
            return await ctx.send(_("Invalid period. E.g.: `15m`, `2h`, `1d`."))
        since = time.time() - seconds
        events = [
            e for e in await self.config.guild(ctx.guild).events()
            if e["ts"] >= since and (member is None or e["actor"] == member.id or e["target"] == member.id)
        ]
        if not events:
            return await ctx.send(_("No events in the last {value}.").format(value=fmt_duration(seconds)))
        lines = []
        for e in events:
            actor = f"<@{e['actor']}>" if e["actor"] else "?"
            label = action_label(e["type"]).lower()
            pts = f" `+{e['points']}`" if e["points"] else ""
            detail = f" — {e['detail']}" if e["detail"] else ""
            lines.append(f"{SEVERITY_EMOJI.get(e['severity'], '')} <t:{int(e['ts'])}:T> {actor} {label} **{e['target_name']}**{detail}{pts}")
        pages = list(pagify("\n".join(lines), page_length=3800))
        embeds = [
            discord.Embed(title=_("🕒 Security Timeline · {value}").format(value=fmt_duration(seconds)), description=p, color=COLOR_INFO).set_footer(text=_("{count} events · {i}/{count2}").format(count=len(events), i=i, count2=len(pages)))
            for i, p in enumerate(pages, 1)
        ]
        await self._send_pages(ctx, embeds)

    @security.command(name="settingslog")
    async def sec_settingslog(self, ctx: commands.Context):
        """Who changed the Security settings (and other Trini modules)."""
        entries = await self.config.guild(ctx.guild).settings_log()
        if not entries:
            return await ctx.send(_("No changes recorded."))
        lines = []
        for e in reversed(entries[-60:]):
            who = f"<@{e['actor']}>" if e.get("actor") else "sistema"
            lines.append(f"<t:{e['ts']}:f> · **{e['module']}** · {who} · `{e['action']}` {e['detail']}")
        pages = list(pagify("\n".join(lines), page_length=3800))
        embeds = [discord.Embed(title=_("⚙️ Security Settings Audit"), description=p, color=COLOR_INFO) for p in pages]
        await self._send_pages(ctx, embeds)

    @security.command(name="status")
    async def sec_status(self, ctx: commands.Context):
        """Status of every Trini Security module."""
        data = await self.config.guild(ctx.guild).all()
        an = self._merged_antinuke(data["antinuke"])
        open_inc = [i for i in data["incidents"].values() if not i.get("closed")]
        embed = discord.Embed(title=_("🔐 Trini Security · status"), color=COLOR_INFO)
        embed.add_field(name=_("Alert channel"), value=f"<#{data['log_channel']}>" if data["log_channel"] else _("❌ not set"), inline=True)
        embed.add_field(name=_("Alert role"), value=f"<@&{data['alert_role']}>" if data["alert_role"] else "—", inline=True)
        embed.add_field(name=_("Lockdown"), value=_("🔴 ACTIVE") if data["lockdown"].get("active") else _("🟢 no"), inline=True)
        embed.add_field(name=_("Security Watch"), value=f"{'🟢' if data['watch'].get('enabled') else '⚫'} {data['watch'].get('level', 'normal')}", inline=True)
        embed.add_field(name=_("Anti-Nuke"), value=_("{value} window {value2}").format(value='🟢' if an['enabled'] else '⚫', value2=fmt_duration(an['window'])), inline=True)
        embed.add_field(name=_("Protected Roles"), value=str(len(data["protected_roles"])), inline=True)
        embed.add_field(name=_("Authority"), value=_("{count} Extra Owners · {count2} Trusted Admins").format(count=len(data['authority']['extra_owners']), count2=len(data['authority']['trusted_admins'])), inline=False)
        embed.add_field(name=_("Whitelists"), value=" · ".join(f"{t}: {len(data['whitelists'].get(t, []))}" for t in WHITELIST_TYPES), inline=False)
        embed.add_field(name=_("Quarantine"), value=str(len(data["quarantined"])), inline=True)
        embed.add_field(name=_("Open incidents"), value=str(len(open_inc)), inline=True)
        embed.add_field(name=_("Recorded events"), value=str(len(data["events"])), inline=True)
        if data["last_health"] is not None:
            embed.add_field(name=_("Last Health Score"), value=f"{data['last_health']}/100", inline=True)
        if not ctx.guild.me.guild_permissions.view_audit_log:
            embed.add_field(name="⚠️", value=_("Without **View Audit Log**, Trini Security can't attribute actions."), inline=False)
        await ctx.send(embed=embed, allowed_mentions=NO_MENTIONS)

    # ==================================================================
    # Incidentes
    # ==================================================================

    @security.group(name="incident")
    async def sec_incident(self, ctx: commands.Context):
        """Incidents rebuilt by Anti-Nuke."""

    @sec_incident.command(name="view")
    async def sec_incident_view(self, ctx: commands.Context, incident_id: int):
        """View an incident."""
        incident = (await self.config.guild(ctx.guild).incidents()).get(str(incident_id))
        if incident is None:
            return await ctx.send(_("Incident not found."))
        embed = await self.incident_embed(ctx.guild, incident)
        q = await self.config.guild(ctx.guild).quarantined()
        view = incident_view(incident_id, incident["actor"] if str(incident["actor"]) in q else None, self._has_backups())
        await ctx.send(embed=embed, view=view, allowed_mentions=NO_MENTIONS)

    @sec_incident.command(name="list")
    async def sec_incident_list(self, ctx: commands.Context):
        """List recent incidents."""
        incidents = sorted((await self.config.guild(ctx.guild).incidents()).values(), key=lambda i: -i["id"])
        if not incidents:
            return await ctx.send(_("🟢 No incidents recorded."))
        lines = [
            _("`#{id}` <t:{start}:f> · <@{actor}> · {level} · {count} events{value}").format(id=i['id'], start=int(i['start']), actor=i['actor'], level=i['level'], count=len(i['events']), value=_(' · closed') if i.get('closed') else '')
            for i in incidents[:30]
        ]
        await ctx.send(embed=discord.Embed(title=_("📁 Incidents"), description="\n".join(lines), color=COLOR_INFO), allowed_mentions=NO_MENTIONS)

    @sec_incident.command(name="close")
    async def sec_incident_close(self, ctx: commands.Context, incident_id: int):
        """Close an incident."""
        if not await self._require(ctx, "trusted_admin"):
            return
        async with self.config.guild(ctx.guild).incidents() as incidents:
            inc = incidents.get(str(incident_id))
            if inc is None:
                return await ctx.send(_("Incident not found."))
            inc["closed"] = True
        await self._settings_log(ctx.guild, ctx.author, "incident_close", f"#{incident_id}")
        await ctx.send(_("Incident #{incident_id} closed.").format(incident_id=incident_id))

    @sec_incident.command(name="report")
    async def sec_incident_report(self, ctx: commands.Context, incident_id: int):
        """Generate a text report for an incident."""
        text = await self.build_incident_report(ctx.guild, incident_id)
        if text is None:
            return await ctx.send(_("Incident not found."))
        await ctx.send(file=discord.File(io.BytesIO(text.encode()), filename=f"incident-{incident_id}.txt"))

    # ==================================================================
    # Digest
    # ==================================================================

    @security.group(name="digest")
    async def sec_digest(self, ctx: commands.Context):
        """Weekly security summary."""

    @sec_digest.command(name="enable")
    async def sec_digest_enable(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Enable the weekly digest (in the given channel or the alert channel)."""
        if not await self._require(ctx, "extra_owner"):
            return
        async with self.config.guild(ctx.guild).digest() as d:
            d["enabled"] = True
            d["channel"] = channel.id if channel else None
            d["last_sent"] = int(time.time())
        await self._settings_log(ctx.guild, ctx.author, "digest_enable", channel.mention if channel else _("alert channel"))
        await ctx.send(_("📬 Weekly digest enabled."))

    @sec_digest.command(name="disable")
    async def sec_digest_disable(self, ctx: commands.Context):
        """Disable the weekly digest."""
        if not await self._require(ctx, "extra_owner"):
            return
        async with self.config.guild(ctx.guild).digest() as d:
            d["enabled"] = False
        await self._settings_log(ctx.guild, ctx.author, "digest_disable", "")
        await ctx.send(_("Weekly digest disabled."))

    @sec_digest.command(name="now")
    async def sec_digest_now(self, ctx: commands.Context, days: int = 7):
        """View the digest for the last N days."""
        await ctx.send(embed=await self.build_digest(ctx.guild, days=max(1, min(days, 30))))

    # ==================================================================
    # Configuracion general
    # ==================================================================

    @security.group(name="config")
    async def sec_config(self, ctx: commands.Context):
        """General Trini Security settings."""

    @sec_config.command(name="logchannel")
    async def sec_config_logchannel(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Security alert channel."""
        if not await self._require(ctx, "extra_owner"):
            return
        await self.config.guild(ctx.guild).log_channel.set(channel.id if channel else None)
        await self._settings_log(ctx.guild, ctx.author, "log_channel", channel.mention if channel else "ninguno")
        await ctx.send(_("Alert channel: {value}.").format(value=channel.mention if channel else 'ninguno'))

    @sec_config.command(name="alertrole")
    async def sec_config_alertrole(self, ctx: commands.Context, role: Optional[discord.Role] = None):
        """Role to mention on critical alerts."""
        if not await self._require(ctx, "extra_owner"):
            return
        await self.config.guild(ctx.guild).alert_role.set(role.id if role else None)
        await self._settings_log(ctx.guild, ctx.author, "alert_role", role.name if role else "ninguno")
        await ctx.send(_("Alert role: {value}.").format(value=role.mention if role else 'ninguno'), allowed_mentions=NO_MENTIONS)

    @sec_config.command(name="quarantinerole")
    async def sec_config_qrole(self, ctx: commands.Context, role: Optional[discord.Role] = None):
        """Optional role added to users in quarantine."""
        if not await self._require(ctx, "extra_owner"):
            return
        async with self.config.guild(ctx.guild).antinuke() as an:
            an["quarantine_role"] = role.id if role else None
        await self._settings_log(ctx.guild, ctx.author, "quarantine_role", role.name if role else "ninguno")
        await ctx.send(_("Quarantine role: {value}.").format(value=role.mention if role else 'ninguno'), allowed_mentions=NO_MENTIONS)

    @sec_config.command(name="botpolicy")
    async def sec_config_botpolicy(self, ctx: commands.Context, policy: Literal["kick", "alert"]):
        """What to do with non-whitelisted bots (with Anti-Nuke enabled)."""
        if not await self._require(ctx, "extra_owner"):
            return
        async with self.config.guild(ctx.guild).antinuke() as an:
            an["bot_policy"] = policy
        await self._settings_log(ctx.guild, ctx.author, "bot_policy", policy)
        await ctx.send(_("Unauthorized bot policy: `{policy}`.").format(policy=policy))

    # ==================================================================
    # Authority
    # ==================================================================

    @security.group(name="authority")
    async def sec_authority(self, ctx: commands.Context):
        """Trust model: Owner, Extra Owners and Trusted Admins."""

    @sec_authority.command(name="add")
    async def sec_authority_add(self, ctx: commands.Context, member: discord.Member, level: Literal["extra_owner", "trusted_admin"]):
        """Add an Extra Owner (Owner only) or Trusted Admin (Extra Owner+)."""
        if member.bot:
            return await ctx.send(_("A bot can't be given authority."))
        if not await self._require(ctx, "owner" if level == "extra_owner" else "extra_owner"):
            return
        async with self.config.guild(ctx.guild).authority() as auth:
            for key in ("extra_owners", "trusted_admins"):
                if member.id in auth[key]:
                    auth[key].remove(member.id)
            auth["extra_owners" if level == "extra_owner" else "trusted_admins"].append(member.id)
        await self._settings_log(ctx.guild, ctx.author, "authority_add", f"{member} → {level}")
        await ctx.send(_("{member} is now **{value}**.").format(member=member.mention, value=authority_label(level)), allowed_mentions=NO_MENTIONS)

    @sec_authority.command(name="remove")
    async def sec_authority_remove(self, ctx: commands.Context, member: discord.Member):
        """Remove a user's authority."""
        auth = await self.config.guild(ctx.guild).authority()
        if member.id in auth["extra_owners"]:
            if not await self._require(ctx, "owner"):
                return
        elif member.id in auth["trusted_admins"]:
            if not await self._require(ctx, "extra_owner"):
                return
        else:
            return await ctx.send(_("That user has no authority in Trini Security."))
        async with self.config.guild(ctx.guild).authority() as a:
            for key in ("extra_owners", "trusted_admins"):
                if member.id in a[key]:
                    a[key].remove(member.id)
        await self._settings_log(ctx.guild, ctx.author, "authority_remove", str(member))
        await ctx.send(_("{member} no longer has authority in Trini Security.").format(member=member.mention), allowed_mentions=NO_MENTIONS)

    @sec_authority.command(name="list")
    async def sec_authority_list(self, ctx: commands.Context):
        """List the trust hierarchy."""
        auth = await self.config.guild(ctx.guild).authority()
        embed = discord.Embed(title=_("🔱 Authority"), color=COLOR_INFO)
        embed.add_field(name=_("👑 Server Owner"), value=f"<@{ctx.guild.owner_id}>", inline=False)
        embed.add_field(name=_("🔱 Extra Owners"), value="\n".join(f"<@{u}>" for u in auth["extra_owners"]) or "—", inline=True)
        embed.add_field(name=_("🛡 Trusted Admins"), value="\n".join(f"<@{u}>" for u in auth["trusted_admins"]) or "—", inline=True)
        regular = [m.mention for m in ctx.guild.members if not m.bot and m.guild_permissions.administrator and m.id != ctx.guild.owner_id and m.id not in auth["extra_owners"] + auth["trusted_admins"]]
        if regular:
            embed.add_field(name=_("Administrators without Trini authority"), value=", ".join(regular[:30])[:1024], inline=False)
        embed.set_footer(text=_("Having Administrator in Discord doesn't make you a Trusted Admin in Trini Security."))
        await ctx.send(embed=embed, allowed_mentions=NO_MENTIONS)

    # ==================================================================
    # Protected Roles
    # ==================================================================

    @security.group(name="protectedrole", aliases=["protected-role", "prole"])
    async def sec_prole(self, ctx: commands.Context):
        """Critical roles that only authorized users can manage."""

    @sec_prole.command(name="add")
    async def sec_prole_add(self, ctx: commands.Context, role: discord.Role):
        """Protect a role."""
        if not await self._require(ctx, "extra_owner"):
            return
        if role.is_default() or role.managed:
            return await ctx.send(_("@everyone and integration-managed roles can't be protected."))
        if role >= ctx.guild.me.top_role:
            await ctx.send(_("⚠️ The role is above the bot: I can detect violations but not revert them."))
        async with self.config.guild(ctx.guild).protected_roles() as prot:
            prot[str(role.id)] = {
                "allowed": ["extra_owner", "trusted_admin"],
                "self_assign": False,
                "bots": False,
                "temporary_whitelist": True,
                "allowed_users": [],
                "allowed_roles": [],
            }
        await self._settings_log(ctx.guild, ctx.author, "protected_role_add", role.name)
        await ctx.send(_("🛡 {role} is now a protected role.").format(role=role.mention), allowed_mentions=NO_MENTIONS)

    @sec_prole.command(name="remove")
    async def sec_prole_remove(self, ctx: commands.Context, role: discord.Role):
        """Stop protecting a role."""
        if not await self._require(ctx, "extra_owner"):
            return
        async with self.config.guild(ctx.guild).protected_roles() as prot:
            if prot.pop(str(role.id), None) is None:
                return await ctx.send(_("That role isn't protected."))
        await self._settings_log(ctx.guild, ctx.author, "protected_role_remove", role.name)
        await ctx.send(_("{role} is no longer protected.").format(role=role.mention), allowed_mentions=NO_MENTIONS)

    @sec_prole.command(name="list")
    async def sec_prole_list(self, ctx: commands.Context):
        """List protected roles."""
        prot = await self.config.guild(ctx.guild).protected_roles()
        if not prot:
            return await ctx.send(_("There are no protected roles. `security protectedrole add @role`"))
        lines = []
        for rid, cfg in prot.items():
            role = ctx.guild.get_role(int(rid))
            name = role.mention if role else _("~~{rid}~~ (deleted)").format(rid=rid)
            lines.append(_("🛡 {name} · allowed: {join} · self: {get} · bots: {get2}").format(name=name, join=', '.join(cfg.get('allowed', [])), get=cfg.get('self_assign'), get2=cfg.get('bots')))
        await ctx.send(embed=discord.Embed(title=_("🛡 Protected Roles"), description="\n".join(lines)[:4000], color=COLOR_INFO), allowed_mentions=NO_MENTIONS)

    @sec_prole.command(name="config")
    async def sec_prole_config(
        self,
        ctx: commands.Context,
        role: discord.Role,
        option: Optional[Literal["allowed", "self_assign", "bots", "temporary_whitelist", "allow_user", "allow_role"]] = None,
        *,
        value: Optional[str] = None,
    ):
        """Configure a protected role. With no option it shows the settings.

        - allowed: allowed levels, e.g. `extra_owner,trusted_admin`
        - self_assign / bots / temporary_whitelist: true/false
        - allow_user / allow_role: add or remove (toggle) an authorized user or role
        """
        prot = await self.config.guild(ctx.guild).protected_roles()
        cfg = prot.get(str(role.id))
        if cfg is None:
            return await ctx.send(_("That role isn't protected."))
        if option is None:
            text = (
                _("Protected role: {role}\n\n**Allowed:**\n").format(role=role.mention) + "\n".join(f"- {a}" for a in cfg.get("allowed", []))
                + _("\n\nself_assign: `{get}`\nbots: `{get2}`\ntemporary_whitelist: `{get3}`").format(get=cfg.get('self_assign'), get2=cfg.get('bots'), get3=cfg.get('temporary_whitelist'))
                + (_("\nAuthorized users: {join}").format(join=', '.join(f'<@{u}>' for u in cfg.get('allowed_users', []))) if cfg.get("allowed_users") else "")
                + (_("\nAuthorized roles: {join}").format(join=', '.join(f'<@&{r}>' for r in cfg.get('allowed_roles', []))) if cfg.get("allowed_roles") else "")
            )
            return await ctx.send(embed=discord.Embed(description=text, color=COLOR_INFO), allowed_mentions=NO_MENTIONS)
        if not await self._require(ctx, "extra_owner"):
            return
        if value is None:
            return await ctx.send(_("The value is missing."))
        async with self.config.guild(ctx.guild).protected_roles() as p:
            c = p[str(role.id)]
            if option == "allowed":
                levels = [v.strip() for v in value.replace(" ", ",").split(",") if v.strip()]
                bad = [lv for lv in levels if lv not in ("extra_owner", "trusted_admin")]
                if bad:
                    return await ctx.send(_("Valid levels: `extra_owner`, `trusted_admin`."))
                c["allowed"] = levels
            elif option in ("self_assign", "bots", "temporary_whitelist"):
                c[option] = value.lower() in ("true", "si", "sí", "yes", "on", "1")
            elif option == "allow_user":
                try:
                    member = await commands.MemberConverter().convert(ctx, value)
                except commands.BadArgument:
                    return await ctx.send(_("User not found."))
                lst = c.setdefault("allowed_users", [])
                lst.remove(member.id) if member.id in lst else lst.append(member.id)
            elif option == "allow_role":
                try:
                    r = await commands.RoleConverter().convert(ctx, value)
                except commands.BadArgument:
                    return await ctx.send(_("Role not found."))
                lst = c.setdefault("allowed_roles", [])
                lst.remove(r.id) if r.id in lst else lst.append(r.id)
        await self._settings_log(ctx.guild, ctx.author, "protected_role_config", f"{role.name}: {option}={value}")
        await ctx.send(_("✅ {role}: `{option}` updated.").format(role=role.mention, option=option), allowed_mentions=NO_MENTIONS)

    # ==================================================================
    # Whitelists
    # ==================================================================

    @security.group(name="whitelist")
    async def sec_whitelist(self, ctx: commands.Context):
        """Whitelists by type: users, roles, bots, webhooks, channels, invites."""

    async def _resolve_wl_target(self, ctx: commands.Context, wtype: str, target: str) -> Optional[Union[int, str]]:
        target = target.strip()
        try:
            if wtype in ("users", "bots"):
                return (await commands.MemberConverter().convert(ctx, target)).id
            if wtype == "roles":
                return (await commands.RoleConverter().convert(ctx, target)).id
            if wtype == "channels":
                return (await commands.GuildChannelConverter().convert(ctx, target)).id
        except commands.BadArgument:
            pass
        if wtype == "invites":
            return target.rsplit("/", 1)[-1]
        digits = re.sub(r"\D", "", target)
        return int(digits) if digits else None

    @sec_whitelist.command(name="add")
    async def sec_whitelist_add(self, ctx: commands.Context, wtype: WhitelistType, *, target: str):
        """Add to a whitelist. E.g.: `security whitelist add bots @MyBot`."""
        if not await self._require(ctx, "extra_owner"):
            return
        value = await self._resolve_wl_target(ctx, wtype, target)
        if value is None:
            return await ctx.send(_("Couldn't understand the target."))
        async with self.config.guild(ctx.guild).whitelists() as wl:
            lst = wl.setdefault(wtype, [])
            if value in lst:
                return await ctx.send(_("It was already whitelisted."))
            lst.append(value)
        await self._settings_log(ctx.guild, ctx.author, "whitelist_add", f"{wtype}: {value}")
        await ctx.send(_("✅ Added to the **{wtype}** whitelist: `{value}`.").format(wtype=wtype, value=value))

    @sec_whitelist.command(name="remove")
    async def sec_whitelist_remove(self, ctx: commands.Context, wtype: WhitelistType, *, target: str):
        """Remove from a whitelist."""
        if not await self._require(ctx, "extra_owner"):
            return
        value = await self._resolve_wl_target(ctx, wtype, target)
        async with self.config.guild(ctx.guild).whitelists() as wl:
            lst = wl.setdefault(wtype, [])
            if value not in lst:
                return await ctx.send(_("It wasn't whitelisted."))
            lst.remove(value)
        await self._settings_log(ctx.guild, ctx.author, "whitelist_remove", f"{wtype}: {value}")
        await ctx.send(_("🗑 Removed from the **{wtype}** whitelist: `{value}`.").format(wtype=wtype, value=value))

    @sec_whitelist.command(name="list")
    async def sec_whitelist_list(self, ctx: commands.Context):
        """View every whitelist."""
        wl = await self._get_whitelists(ctx.guild)
        fmt = {
            "users": lambda v: f"<@{v}>", "bots": lambda v: f"<@{v}>", "roles": lambda v: f"<@&{v}>",
            "channels": lambda v: f"<#{v}>", "webhooks": lambda v: f"`{v}`", "invites": lambda v: f"`{v}`",
        }
        embed = discord.Embed(title=_("📃 Whitelists"), color=COLOR_INFO)
        for t in WHITELIST_TYPES:
            embed.add_field(name=t, value=", ".join(fmt[t](v) for v in wl[t][:30])[:1024] or "—", inline=False)
        temp = [t for t in await self.config.guild(ctx.guild).temp_whitelist() if t["expires"] > time.time()]
        if temp:
            embed.add_field(
                name=_("Temporary (protected roles)"),
                value="\n".join(f"<@&{t['role']}> → <@{t['user']}> hasta <t:{int(t['expires'])}:R>" for t in temp)[:1024],
                inline=False,
            )
        await ctx.send(embed=embed, allowed_mentions=NO_MENTIONS)

    @sec_whitelist.command(name="temp")
    async def sec_whitelist_temp(self, ctx: commands.Context, role: discord.Role, member: discord.Member, duration: str = "1h"):
        """Temporary whitelist for a protected role. E.g.: `security whitelist temp @Admin @Pepe 1h`."""
        if not await self._require(ctx, "trusted_admin"):
            return
        prot = await self.config.guild(ctx.guild).protected_roles()
        if str(role.id) not in prot:
            return await ctx.send(_("That role isn't protected."))
        if not prot[str(role.id)].get("temporary_whitelist", True):
            return await ctx.send(_("That role doesn't allow a temporary whitelist."))
        seconds = parse_duration(duration)
        if not seconds or seconds > 7 * 86400:
            return await ctx.send(_("Invalid duration (max 7d)."))
        async with self.config.guild(ctx.guild).temp_whitelist() as temp:
            temp.append({"role": role.id, "user": member.id, "expires": time.time() + seconds, "by": ctx.author.id})
        await self._settings_log(ctx.guild, ctx.author, "whitelist_temp", f"{role.name} → {member} ({fmt_duration(seconds)})")
        await ctx.send(_("⏳ {member} temporarily whitelisted for {role} for **{value}**.").format(member=member.mention, role=role.mention, value=fmt_duration(seconds)), allowed_mentions=NO_MENTIONS)

    # ==================================================================
    # Security Watch
    # ==================================================================

    @security.group(name="watch")
    async def sec_watch(self, ctx: commands.Context):
        """Monitoring of sensitive administrative changes."""

    @sec_watch.command(name="enable")
    async def sec_watch_enable(self, ctx: commands.Context):
        """Enable Security Watch."""
        if not await self._require(ctx, "extra_owner"):
            return
        async with self.config.guild(ctx.guild).watch() as w:
            w["enabled"] = True
        await self._settings_log(ctx.guild, ctx.author, "watch_enable", "")
        msg = _("👁 Security Watch enabled.")
        if not await self.config.guild(ctx.guild).log_channel():
            msg += _("\n⚠️ Set a channel: `security config logchannel #channel`.")
        await ctx.send(msg)

    @sec_watch.command(name="disable")
    async def sec_watch_disable(self, ctx: commands.Context):
        """Disable Security Watch."""
        if not await self._require(ctx, "extra_owner"):
            return
        async with self.config.guild(ctx.guild).watch() as w:
            w["enabled"] = False
        await self._settings_log(ctx.guild, ctx.author, "watch_disable", "")
        await ctx.send(_("Security Watch disabled."))

    @sec_watch.command(name="level")
    async def sec_watch_level(self, ctx: commands.Context, level: Literal["normal", "max"]):
        """Watch level."""
        if not await self._require(ctx, "extra_owner"):
            return
        async with self.config.guild(ctx.guild).watch() as w:
            w["level"] = level
        await self._settings_log(ctx.guild, ctx.author, "watch_level", level)
        await ctx.send(_("Security Watch level: `{level}`.").format(level=level))

    # ==================================================================
    # Anti-Nuke
    # ==================================================================

    @security.group(name="antinuke")
    async def sec_antinuke(self, ctx: commands.Context):
        """Nuke detection by thresholds and risk score."""

    @sec_antinuke.command(name="enable")
    async def sec_antinuke_enable(self, ctx: commands.Context):
        """Enable Anti-Nuke."""
        if not await self._require(ctx, "extra_owner"):
            return
        async with self.config.guild(ctx.guild).antinuke() as an:
            an["enabled"] = True
        await self._settings_log(ctx.guild, ctx.author, "antinuke_enable", "")
        warn = "" if ctx.guild.me.guild_permissions.view_audit_log else _("\n⚠️ I need **View Audit Log**.")
        await ctx.send(_("💣 Anti-Nuke enabled.") + warn)

    @sec_antinuke.command(name="disable")
    async def sec_antinuke_disable(self, ctx: commands.Context):
        """Disable Anti-Nuke."""
        if not await self._require(ctx, "extra_owner"):
            return
        async with self.config.guild(ctx.guild).antinuke() as an:
            an["enabled"] = False
        await self._settings_log(ctx.guild, ctx.author, "antinuke_disable", "")
        await ctx.send(_("Anti-Nuke disabled."))

    @sec_antinuke.command(name="status")
    async def sec_antinuke_status(self, ctx: commands.Context):
        """View thresholds, scores and levels."""
        an = self._merged_antinuke(await self.config.guild(ctx.guild).antinuke())
        th = "\n".join(f"{action_label(k):<24} {v[0] or '-'}/min  {v[1] or '-'}/h" for k, v in an["thresholds"].items())
        sc = "\n".join(f"{action_label(k):<28} {v} pts" for k, v in an["scores"].items())
        lv = an["levels"]
        levels = _("0 - {value}    Log\n{alert} - {value2}   Alert staff\n{block} - {value3}   Block sensitive actions\n{quarantine}+      Quarantine").format(value=lv['alert'] - 1, alert=lv['alert'], value2=lv['block'] - 1, block=lv['block'], value3=lv['quarantine'] - 1, quarantine=lv['quarantine'])
        embed = discord.Embed(title=_("💣 Anti-Nuke {value}").format(value='🟢' if an['enabled'] else '⚫'), color=COLOR_INFO)
        embed.add_field(name=_("Thresholds"), value=box(th), inline=False)
        embed.add_field(name=_("Risk score"), value=box(sc), inline=False)
        embed.add_field(name=_("Escalating response"), value=box(levels), inline=False)
        embed.add_field(name=_("Window"), value=fmt_duration(an["window"]), inline=True)
        embed.add_field(name=_("Trusted Admins immune"), value=str(an["trusted_immune"]), inline=True)
        embed.add_field(name=_("Unauthorized bots"), value=an["bot_policy"], inline=True)
        await ctx.send(embed=embed)

    @sec_antinuke.command(name="threshold")
    async def sec_antinuke_threshold(self, ctx: commands.Context, action: str, per_minute: int, per_hour: int = 0):
        """Change an action's threshold (0 = no limit)."""
        if not await self._require(ctx, "extra_owner"):
            return
        if action not in DEFAULT_THRESHOLDS:
            return await ctx.send("Acciones: " + ", ".join(f"`{a}`" for a in DEFAULT_THRESHOLDS))
        async with self.config.guild(ctx.guild).antinuke() as an:
            an.setdefault("thresholds", {})[action] = [max(0, per_minute), max(0, per_hour)]
        await self._settings_log(ctx.guild, ctx.author, "antinuke_threshold", _("{action}: {per_minute}/min {per_hour}/h").format(action=action, per_minute=per_minute, per_hour=per_hour))
        await ctx.send(_("Threshold `{action}`: {per_minute}/min · {per_hour}/h.").format(action=action, per_minute=per_minute, per_hour=per_hour))

    @sec_antinuke.command(name="score")
    async def sec_antinuke_score(self, ctx: commands.Context, action: str, points: int):
        """Change an action's risk points."""
        if not await self._require(ctx, "extra_owner"):
            return
        if action not in DEFAULT_SCORES:
            return await ctx.send("Acciones: " + ", ".join(f"`{a}`" for a in DEFAULT_SCORES))
        async with self.config.guild(ctx.guild).antinuke() as an:
            an.setdefault("scores", {})[action] = max(0, points)
        await self._settings_log(ctx.guild, ctx.author, "antinuke_score", f"{action}: {points}")
        await ctx.send(_("`{action}` = {points} points.").format(action=action, points=points))

    @sec_antinuke_threshold.autocomplete("action")
    async def _ac_threshold(self, interaction: discord.Interaction, current: str):
        return [discord.app_commands.Choice(name=action_label(a), value=a) for a in DEFAULT_THRESHOLDS if current.lower() in a][:25]

    @sec_antinuke_score.autocomplete("action")
    async def _ac_score(self, interaction: discord.Interaction, current: str):
        return [discord.app_commands.Choice(name=action_label(a), value=a) for a in DEFAULT_SCORES if current.lower() in a][:25]

    @sec_antinuke.command(name="levels")
    async def sec_antinuke_levels(self, ctx: commands.Context, alert: int, block: int, quarantine: int):
        """Response levels: alert, block and quarantine."""
        if not await self._require(ctx, "extra_owner"):
            return
        if not 0 < alert < block < quarantine:
            return await ctx.send(_("It must hold that 0 < alert < block < quarantine."))
        async with self.config.guild(ctx.guild).antinuke() as an:
            an["levels"] = {"alert": alert, "block": block, "quarantine": quarantine}
        await self._settings_log(ctx.guild, ctx.author, "antinuke_levels", f"{alert}/{block}/{quarantine}")
        await ctx.send(_("Levels: alert {alert} · block {block} · quarantine {quarantine}.").format(alert=alert, block=block, quarantine=quarantine))

    @sec_antinuke.command(name="window")
    async def sec_antinuke_window(self, ctx: commands.Context, duration: str):
        """Risk score accumulation window. E.g.: `10m`."""
        if not await self._require(ctx, "extra_owner"):
            return
        seconds = parse_duration(duration)
        if not seconds or not 60 <= seconds <= 3600:
            return await ctx.send(_("Between 1m and 1h."))
        async with self.config.guild(ctx.guild).antinuke() as an:
            an["window"] = seconds
        await self._settings_log(ctx.guild, ctx.author, "antinuke_window", fmt_duration(seconds))
        await ctx.send(_("Window: {value}.").format(value=fmt_duration(seconds)))

    @sec_antinuke.command(name="trustedimmune")
    async def sec_antinuke_trusted(self, ctx: commands.Context, enabled: bool):
        """Whether Trusted Admins are immune to Anti-Nuke."""
        if not await self._require(ctx, "extra_owner"):
            return
        async with self.config.guild(ctx.guild).antinuke() as an:
            an["trusted_immune"] = enabled
        await self._settings_log(ctx.guild, ctx.author, "antinuke_trusted_immune", str(enabled))
        await ctx.send(_("Trusted Admins immune: `{enabled}`.").format(enabled=enabled))

    @sec_antinuke.command(name="reset")
    async def sec_antinuke_reset(self, ctx: commands.Context):
        """Restore default thresholds, scores and levels."""
        if not await self._require(ctx, "extra_owner"):
            return
        async with self.config.guild(ctx.guild).antinuke() as an:
            an["thresholds"] = dict(DEFAULT_THRESHOLDS)
            an["scores"] = dict(DEFAULT_SCORES)
            an.pop("levels", None)
            an["window"] = 600
        await self._settings_log(ctx.guild, ctx.author, "antinuke_reset", "")
        await ctx.send(_("Defaults restored."))

    # ==================================================================
    # Lockdown
    # ==================================================================

    @security.group(name="lockdown")
    async def sec_lockdown(self, ctx: commands.Context):
        """Emergency Lockdown."""

    @sec_lockdown.command(name="enable")
    async def sec_lockdown_enable(self, ctx: commands.Context, pause_invites: bool = True):
        """Enable emergency mode."""
        if not await self._require(ctx, "trusted_admin"):
            return
        if (await self.config.guild(ctx.guild).lockdown()).get("active"):
            return await ctx.send(_("Lockdown is already active."))
        view = ConfirmView(ctx.author, label=_("Enable lockdown"), style=discord.ButtonStyle.red)
        msg = await ctx.send(_("Enable **SECURITY LOCKDOWN**? Only the Owner and Extra Owners will be able to disable it."), view=view)
        await view.wait()
        if not view.value:
            return await msg.edit(content=_("Cancelled."), view=None)
        async with ctx.typing():
            notes = await self.enable_lockdown(ctx.guild, ctx.author, disable_invites=pause_invites)
        embed = discord.Embed(
            title=_("🔐 SECURITY LOCKDOWN"),
            color=COLOR_CRIT,
            description=_("• New bots: **blocked**\n• New webhooks: **blocked**\n• Protected Roles: **blocked**\n• Administrative changes: **restricted**\n• Invites: **{value}**\n• Security Watch: **max level**").format(value='pausadas' if pause_invites else _('unchanged')),
            timestamp=discord.utils.utcnow(),
        )
        if notes:
            embed.add_field(name=_("Notes"), value="\n".join(notes), inline=False)
        embed.set_footer(text=_("Enabled by {author} · security lockdown disable").format(author=ctx.author))
        await msg.edit(content=None, embed=embed, view=None)
        await self._send_log(ctx.guild, embed, ping=True, critical=True)

    @sec_lockdown.command(name="disable")
    async def sec_lockdown_disable(self, ctx: commands.Context):
        """Exit emergency mode (Owner / Extra Owners)."""
        if not await self._require(ctx, "extra_owner"):
            return
        if not (await self.config.guild(ctx.guild).lockdown()).get("active"):
            return await ctx.send(_("There's no active lockdown."))
        notes = await self.disable_lockdown(ctx.guild, ctx.author)
        embed = discord.Embed(title=_("🔓 Lockdown disabled"), color=COLOR_OK, description="\n".join(notes) or None)
        embed.set_footer(text=_("By {author}").format(author=ctx.author))
        await ctx.send(embed=embed)
        await self._send_log(ctx.guild, embed)

    @sec_lockdown.command(name="status")
    async def sec_lockdown_status(self, ctx: commands.Context):
        """Lockdown status."""
        lk = await self.config.guild(ctx.guild).lockdown()
        if lk.get("active"):
            await ctx.send(_("🔴 Lockdown **active** since <t:{at}:R> (by <@{by}>).").format(at=lk['at'], by=lk['by']), allowed_mentions=NO_MENTIONS)
        else:
            await ctx.send(_("🟢 No lockdown."))

    # ==================================================================
    # Quarantine
    # ==================================================================

    @security.group(name="quarantine")
    async def sec_quarantine(self, ctx: commands.Context):
        """Users in quarantine."""

    @sec_quarantine.command(name="list")
    async def sec_quarantine_list(self, ctx: commands.Context):
        """List users in quarantine."""
        q = await self.config.guild(ctx.guild).quarantined()
        if not q:
            return await ctx.send(_("🟢 Nobody in quarantine."))
        lines = [_("<@{uid}> · <t:{at}:R> · {count} roles saved · {reason}").format(uid=uid, at=d['at'], count=len(d['roles']), reason=d['reason']) for uid, d in q.items()]
        await ctx.send(embed=discord.Embed(title=_("🔒 Quarantine"), description="\n".join(lines)[:4000], color=COLOR_WARN), allowed_mentions=NO_MENTIONS)

    @sec_quarantine.command(name="add")
    async def sec_quarantine_add(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Manual"):
        """Manually quarantine a user (removes dangerous roles)."""
        if not await self._require(ctx, "trusted_admin"):
            return
        target_level = await self.get_authority_level(member)
        my_level = await self.get_authority_level(ctx.author)
        if AUTHORITY_LEVELS[target_level] >= AUTHORITY_LEVELS[my_level]:
            return await ctx.send(_("You can't quarantine someone with the same or higher authority level."))
        ok, msg = await self.quarantine_member(ctx.guild, member, reason=_("{reason} (by {author})").format(reason=reason, author=ctx.author), by=ctx.author)
        await self._settings_log(ctx.guild, ctx.author, "quarantine_add", f"{member}: {reason}")
        await ctx.send(msg, allowed_mentions=NO_MENTIONS)

    @sec_quarantine.command(name="release")
    async def sec_quarantine_release(self, ctx: commands.Context, user: discord.User):
        """Release a user and restore their roles."""
        if not await self._require(ctx, "trusted_admin"):
            return
        if user.id == ctx.author.id:
            return await ctx.send(_("You can't release yourself."))
        ok, msg = await self.release_quarantine(ctx.guild, user.id, ctx.author)
        await ctx.send(msg, allowed_mentions=NO_MENTIONS)
