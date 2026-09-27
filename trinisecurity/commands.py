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
    ACTION_LABELS,
    ADMIN_PERMS,
    AUTHORITY_LABELS,
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
            f"🔒 Necesitas ser **{AUTHORITY_LABELS[minimum]}** en Trini Security para esto "
            f"(tu nivel: {AUTHORITY_LABELS[level]})."
        )
        return False

    def _report_embeds(self, guild: discord.Guild, report: AuditReport, title: str) -> List[discord.Embed]:
        score = report.score
        color = COLOR_OK if score >= 80 else (COLOR_WARN if score >= 60 else COLOR_CRIT)
        header = (
            f"Servidor: **{guild.name}**\nHealth Score: **{score} / 100**\n\n"
            f"🔴 Riesgos criticos: **{report.count('critical')}**\n"
            f"🟠 Advertencias: **{report.count('warning')}**\n"
            f"🔵 Observaciones: **{report.count('info')}**"
        )
        embeds: List[discord.Embed] = []
        current = discord.Embed(title=title, description=header, color=color)
        size = len(header)
        for f in sorted(report.findings, key=lambda x: SEVERITY_ORDER[x.severity]):
            name = f"{SEVERITY_EMOJI[f.severity]} {f.title}"[:256]
            value = (f.detail or "​")[:1024]
            if len(current.fields) >= 12 or size + len(name) + len(value) > 5000:
                embeds.append(current)
                current = discord.Embed(title=f"{title} (cont.)", color=color)
                size = 0
            current.add_field(name=name, value=value, inline=False)
            size += len(name) + len(value)
        embeds.append(current)
        for i, e in enumerate(embeds, 1):
            e.set_footer(text=f"Pagina {i}/{len(embeds)} · Trini Security")
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
        """Trini Security: auditoria y proteccion del servidor."""

    @security.command(name="audit")
    async def sec_audit(self, ctx: commands.Context):
        """Auditoria completa de seguridad del servidor."""
        async with ctx.typing():
            report = await self.compute_health(ctx.guild)
            await self.config.guild(ctx.guild).last_health.set(report.score)
            await self.config.guild(ctx.guild).last_findings.set(
                [f.title for f in report.findings if f.severity in ("critical", "warning")]
            )
        await self._send_pages(ctx, self._report_embeds(ctx.guild, report, "🔐 Security Audit"))

    @security.command(name="health")
    async def sec_health(self, ctx: commands.Context):
        """Health Score con sus penalizaciones y mejoras."""
        async with ctx.typing():
            report = await self.compute_health(ctx.guild)
        lines = []
        for f in sorted(report.findings, key=lambda x: -x.penalty):
            if f.penalty:
                lines.append(f"**-{f.penalty}**  {f.title}")
        for pts, text in report.bonuses:
            lines.append(f"**+{pts}**  {text}")
        embed = discord.Embed(
            title="Security Health",
            description=f"# {report.score} / 100\nBase {85} · penalizaciones -{report.penalty} · mejoras +{report.bonus}\n\n"
            + ("\n".join(lines) or "Sin penalizaciones."),
            color=COLOR_OK if report.score >= 80 else (COLOR_WARN if report.score >= 60 else COLOR_CRIT),
        )
        missing = []
        if not report.bonuses or all("Protected" not in b[1] for b in report.bonuses):
            missing.append("+5 Protected Roles (`security protectedrole add`)")
        if all("Anti-Nuke" not in b[1] for b in report.bonuses):
            missing.append("+5 Anti-Nuke (`security antinuke enable`)")
        if all("Watch" not in b[1] for b in report.bonuses):
            missing.append("+3 Security Watch (`security watch enable`)")
        if all("Backups" not in b[1] for b in report.bonuses):
            missing.append("+2 Backups automaticos (`backup schedule daily`)")
        if missing:
            embed.add_field(name="Como subir la puntuacion", value="\n".join(missing), inline=False)
        await ctx.send(embed=embed)

    @security.command(name="user")
    async def sec_user(self, ctx: commands.Context, member: discord.Member):
        """Permisos efectivos de un usuario y su origen real."""
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
        embed.add_field(name="Permisos efectivos", value=box(table), inline=False)
        if origin_lines:
            embed.add_field(name="Origen", value=box(origin_lines)[:1024], inline=False)
        embed.add_field(name="Trini Security", value=AUTHORITY_LABELS[level], inline=True)
        embed.add_field(name="Rol mas alto", value=member.top_role.mention, inline=True)
        quarantined = await self.config.guild(ctx.guild).quarantined()
        if str(member.id) in quarantined:
            embed.add_field(name="Estado", value="🔒 En quarantine", inline=True)
        esc = escalations(member.top_role) if not perms.administrator else []
        if esc:
            embed.add_field(
                name="⚠️ Posible escalada",
                value="\n".join(f"Puede asignar {r.mention}: {', '.join(perm_label(p) for p in extra)}" for r, extra in esc[:8])[:1024],
                inline=False,
            )
        admin_roles = [r.mention for r in member.roles if granted(r.permissions, ADMIN_PERMS) and not r.is_default()]
        if len(admin_roles) >= 2:
            embed.add_field(name="Roles administrativos acumulados", value=", ".join(admin_roles)[:1024], inline=False)
        await ctx.send(embed=embed, allowed_mentions=NO_MENTIONS)

    @security.command(name="role")
    async def sec_role(self, ctx: commands.Context, role: discord.Role):
        """Auditoria de un rol: permisos, jerarquia y roles que puede modificar."""
        perms = [perm_label(p) for p in EVERYONE_DANGEROUS if getattr(role.permissions, p)]
        embed = discord.Embed(title=f"🎭 {role.name}", color=role.color if role.color.value else COLOR_INFO)
        embed.add_field(name="Miembros", value=str(len(role.members)), inline=True)
        embed.add_field(name="Posicion", value=f"{role.position}/{len(ctx.guild.roles) - 1}", inline=True)
        embed.add_field(name="Gestionado", value="si (integracion/bot)" if role.managed else "no", inline=True)
        embed.add_field(name="Permisos sensibles", value=", ".join(perms) or "ninguno", inline=False)
        manage = manageable_roles(role)
        if manage:
            embed.add_field(
                name=f"Puede modificar ({len(manage)})",
                value=", ".join(r.mention for r in sorted(manage, reverse=True)[:25])[:1024],
                inline=False,
            )
        esc = escalations(role)
        if esc:
            embed.add_field(
                name="🔴 Escalada de privilegios",
                value="\n".join(f"{r.mention}: {', '.join(perm_label(p) for p in extra)}" for r, extra in esc[:10])[:1024],
                inline=False,
            )
        assigners = [r.mention for r in ctx.guild.roles if r > role and (r.permissions.manage_roles or r.permissions.administrator) and not r.managed]
        if assigners:
            embed.add_field(name="Pueden asignarlo", value=", ".join(assigners[:20])[:1024], inline=False)
        protected = (await self.config.guild(ctx.guild).protected_roles()).get(str(role.id))
        if protected:
            embed.add_field(name="🛡 Rol protegido", value=box("\n".join(f"{k}: {v}" for k, v in protected.items()))[:1024], inline=False)
        await ctx.send(embed=embed, allowed_mentions=NO_MENTIONS)

    @security.command(name="channel")
    async def sec_channel(self, ctx: commands.Context, channel: Union[discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel, discord.ForumChannel, discord.StageChannel]):
        """Auditoria de un canal: overwrites, visibilidad y herencia."""
        embed = discord.Embed(title=f"# {channel.name}", color=COLOR_INFO)
        visible = channel_visible_to_everyone(channel)
        embed.add_field(name="Visible para @everyone", value="✅" if visible else "❌", inline=True)
        if not isinstance(channel, discord.CategoryChannel) and channel.category:
            priv = is_private_category(channel.category)
            embed.add_field(name="Categoria", value=f"{channel.category.name} {'(privada)' if priv else ''}", inline=True)
            embed.add_field(name="Hereda permisos", value="✅" if channel.permissions_synced else "❌", inline=True)
            if priv and visible:
                embed.add_field(name="🔴 Riesgo", value="Canal visible para @everyone dentro de una categoria privada.", inline=False)
        watched = ("view_channel", "send_messages", "create_instant_invite", "mention_everyone", "manage_messages", "manage_channels", "manage_webhooks", "manage_roles")
        lines = []
        for target, ow in channel.overwrites.items():
            allow, deny = ow.pair()
            parts = [f"+{perm_label(p)}" for p in watched if getattr(allow, p)] + [f"-{perm_label(p)}" for p in watched if getattr(deny, p)]
            if not parts:
                continue
            label = "@everyone" if isinstance(target, discord.Role) and target.is_default() else (f"@{target.name}" if isinstance(target, discord.Role) else f"{target}")
            lines.append(f"{label}: {' '.join(parts)}")
        embed.add_field(name=f"Overwrites ({len(channel.overwrites)})", value=box("\n".join(lines[:20]) or "ninguno")[:1024], inline=False)
        viewers = [r.mention for r in ctx.guild.roles if not r.is_default() and channel.permissions_for(r).view_channel and not r.permissions.administrator][:20] if not visible else []
        if viewers:
            embed.add_field(name="Roles con acceso", value=", ".join(viewers)[:1024], inline=False)
        dangerous = []
        for target, ow in channel.overwrites.items():
            bad = [p for p in ADMIN_PERMS if getattr(ow, p) is True]
            if bad:
                dangerous.append(f"{getattr(target, 'mention', target)}: {', '.join(perm_label(p) for p in bad)}")
        if dangerous:
            embed.add_field(name="🟠 Overwrites administrativos", value="\n".join(dangerous)[:1024], inline=False)
        await ctx.send(embed=embed, allowed_mentions=NO_MENTIONS)

    @security.command(name="bot")
    async def sec_bot(self, ctx: commands.Context, bot: discord.Member):
        """Auditoria de un bot: permisos, whitelist y quien lo añadio."""
        if not bot.bot:
            return await ctx.send("Ese miembro no es un bot.")
        perms = bot.guild_permissions
        wl = await self._get_whitelists(ctx.guild)
        embed = discord.Embed(title=f"🤖 {bot}", color=COLOR_WARN if perms.administrator else COLOR_INFO)
        embed.add_field(name="Administrator", value="✅ (revisa si lo necesita)" if perms.administrator else "❌", inline=True)
        embed.add_field(name="Whitelist", value="✅" if bot.id in wl["bots"] else "❌", inline=True)
        embed.add_field(name="Añadido", value=f"<t:{int(bot.joined_at.timestamp())}:R>" if bot.joined_at else "?", inline=True)
        sens = [perm_label(p) for p in EVERYONE_DANGEROUS if getattr(perms, p)]
        embed.add_field(name="Permisos sensibles", value=", ".join(sens) or "ninguno", inline=False)
        managed = [r for r in bot.roles if r.managed]
        if managed:
            embed.add_field(name="Rol de integracion", value=managed[0].mention, inline=True)
        events = await self.config.guild(ctx.guild).events()
        added = next((e for e in reversed(events) if e["type"] == "bot_add" and e["target"] == bot.id), None)
        if added:
            embed.add_field(name="Añadido por", value=f"<@{added['actor']}> <t:{int(added['ts'])}:f>", inline=False)
        elif ctx.guild.me.guild_permissions.view_audit_log:
            try:
                async for entry in ctx.guild.audit_logs(action=discord.AuditLogAction.bot_add, limit=100):
                    if entry.target and entry.target.id == bot.id:
                        embed.add_field(name="Añadido por", value=f"{entry.user.mention if entry.user else '?'} <t:{int(entry.created_at.timestamp())}:f>", inline=False)
                        break
            except discord.HTTPException:
                pass
        await ctx.send(embed=embed, allowed_mentions=NO_MENTIONS)

    @security.command(name="webhooks")
    async def sec_webhooks(self, ctx: commands.Context):
        """Listar webhooks del servidor y su estado de whitelist."""
        try:
            hooks = await ctx.guild.webhooks()
        except discord.Forbidden:
            return await ctx.send("Necesito el permiso **Manage Webhooks**.")
        wl = await self._get_whitelists(ctx.guild)
        if not hooks:
            return await ctx.send("🟢 No hay webhooks en el servidor.")
        lines = []
        for h in hooks:
            ok = h.id in wl["webhooks"] or h.channel_id in wl["channels"]
            creator = f" por {h.user}" if h.user else ""
            lines.append(f"{'🟢' if ok else '🟠'} `{h.name}` <#{h.channel_id}> · {h.type.name}{creator} · `{h.id}`")
        for page in pagify("\n".join(lines), page_length=3900):
            await ctx.send(embed=discord.Embed(title=f"🪝 Webhooks ({len(hooks)})", description=page, color=COLOR_INFO), allowed_mentions=NO_MENTIONS)

    @security.command(name="invites")
    async def sec_invites(self, ctx: commands.Context):
        """Listar invitaciones, marcando las permanentes."""
        try:
            invites = await ctx.guild.invites()
        except discord.Forbidden:
            return await ctx.send("Necesito el permiso **Manage Server**.")
        wl = await self._get_whitelists(ctx.guild)
        if not invites:
            return await ctx.send("No hay invitaciones activas.")
        lines = []
        for i in sorted(invites, key=lambda x: x.uses or 0, reverse=True):
            perma = (i.max_age or 0) == 0
            icon = "🟢" if i.code in wl["invites"] else ("🟠" if perma else "⚪")
            exp = "permanente" if perma else f"expira <t:{int(i.expires_at.timestamp())}:R>" if i.expires_at else ""
            lines.append(f"{icon} `{i.code}` · {i.inviter or '?'} · {i.uses} usos · {exp}")
        for page in pagify("\n".join(lines), page_length=3900):
            await ctx.send(embed=discord.Embed(title=f"✉️ Invitaciones ({len(invites)})", description=page, color=COLOR_INFO), allowed_mentions=NO_MENTIONS)

    @security.command(name="timeline")
    async def sec_timeline(self, ctx: commands.Context, period: str = "15m", member: Optional[discord.Member] = None):
        """Timeline de eventos de seguridad. Ej: `security timeline 15m @usuario`."""
        seconds = parse_duration(period)
        if not seconds:
            return await ctx.send("Periodo no valido. Ej: `15m`, `2h`, `1d`.")
        since = time.time() - seconds
        events = [
            e for e in await self.config.guild(ctx.guild).events()
            if e["ts"] >= since and (member is None or e["actor"] == member.id or e["target"] == member.id)
        ]
        if not events:
            return await ctx.send(f"Sin eventos en los ultimos {fmt_duration(seconds)}.")
        lines = []
        for e in events:
            actor = f"<@{e['actor']}>" if e["actor"] else "?"
            label = ACTION_LABELS.get(e["type"], e["type"]).lower()
            pts = f" `+{e['points']}`" if e["points"] else ""
            detail = f" — {e['detail']}" if e["detail"] else ""
            lines.append(f"{SEVERITY_EMOJI.get(e['severity'], '')} <t:{int(e['ts'])}:T> {actor} {label} **{e['target_name']}**{detail}{pts}")
        pages = list(pagify("\n".join(lines), page_length=3800))
        embeds = [
            discord.Embed(title=f"🕒 Security Timeline · {fmt_duration(seconds)}", description=p, color=COLOR_INFO).set_footer(text=f"{len(events)} eventos · {i}/{len(pages)}")
            for i, p in enumerate(pages, 1)
        ]
        await self._send_pages(ctx, embeds)

    @security.command(name="settingslog")
    async def sec_settingslog(self, ctx: commands.Context):
        """Quien cambio la configuracion de Security (y de otros modulos Trini)."""
        entries = await self.config.guild(ctx.guild).settings_log()
        if not entries:
            return await ctx.send("Sin cambios registrados.")
        lines = []
        for e in reversed(entries[-60:]):
            who = f"<@{e['actor']}>" if e.get("actor") else "sistema"
            lines.append(f"<t:{e['ts']}:f> · **{e['module']}** · {who} · `{e['action']}` {e['detail']}")
        pages = list(pagify("\n".join(lines), page_length=3800))
        embeds = [discord.Embed(title="⚙️ Security Settings Audit", description=p, color=COLOR_INFO) for p in pages]
        await self._send_pages(ctx, embeds)

    @security.command(name="status")
    async def sec_status(self, ctx: commands.Context):
        """Estado de todos los modulos de Trini Security."""
        data = await self.config.guild(ctx.guild).all()
        an = self._merged_antinuke(data["antinuke"])
        open_inc = [i for i in data["incidents"].values() if not i.get("closed")]
        embed = discord.Embed(title="🔐 Trini Security · estado", color=COLOR_INFO)
        embed.add_field(name="Canal de alertas", value=f"<#{data['log_channel']}>" if data["log_channel"] else "❌ sin configurar", inline=True)
        embed.add_field(name="Rol de alerta", value=f"<@&{data['alert_role']}>" if data["alert_role"] else "—", inline=True)
        embed.add_field(name="Lockdown", value="🔴 ACTIVO" if data["lockdown"].get("active") else "🟢 no", inline=True)
        embed.add_field(name="Security Watch", value=f"{'🟢' if data['watch'].get('enabled') else '⚫'} {data['watch'].get('level', 'normal')}", inline=True)
        embed.add_field(name="Anti-Nuke", value=f"{'🟢' if an['enabled'] else '⚫'} ventana {fmt_duration(an['window'])}", inline=True)
        embed.add_field(name="Protected Roles", value=str(len(data["protected_roles"])), inline=True)
        embed.add_field(name="Authority", value=f"{len(data['authority']['extra_owners'])} Extra Owners · {len(data['authority']['trusted_admins'])} Trusted Admins", inline=False)
        embed.add_field(name="Whitelists", value=" · ".join(f"{t}: {len(data['whitelists'].get(t, []))}" for t in WHITELIST_TYPES), inline=False)
        embed.add_field(name="Quarantine", value=str(len(data["quarantined"])), inline=True)
        embed.add_field(name="Incidentes abiertos", value=str(len(open_inc)), inline=True)
        embed.add_field(name="Eventos registrados", value=str(len(data["events"])), inline=True)
        if data["last_health"] is not None:
            embed.add_field(name="Ultimo Health Score", value=f"{data['last_health']}/100", inline=True)
        if not ctx.guild.me.guild_permissions.view_audit_log:
            embed.add_field(name="⚠️", value="Sin **View Audit Log** Trini Security no puede atribuir acciones.", inline=False)
        await ctx.send(embed=embed, allowed_mentions=NO_MENTIONS)

    # ==================================================================
    # Incidentes
    # ==================================================================

    @security.group(name="incident")
    async def sec_incident(self, ctx: commands.Context):
        """Incidentes reconstruidos por Anti-Nuke."""

    @sec_incident.command(name="view")
    async def sec_incident_view(self, ctx: commands.Context, incident_id: int):
        """Ver un incidente."""
        incident = (await self.config.guild(ctx.guild).incidents()).get(str(incident_id))
        if incident is None:
            return await ctx.send("Incidente no encontrado.")
        embed = await self.incident_embed(ctx.guild, incident)
        q = await self.config.guild(ctx.guild).quarantined()
        view = incident_view(incident_id, incident["actor"] if str(incident["actor"]) in q else None, self._has_backups())
        await ctx.send(embed=embed, view=view, allowed_mentions=NO_MENTIONS)

    @sec_incident.command(name="list")
    async def sec_incident_list(self, ctx: commands.Context):
        """Listar incidentes recientes."""
        incidents = sorted((await self.config.guild(ctx.guild).incidents()).values(), key=lambda i: -i["id"])
        if not incidents:
            return await ctx.send("🟢 No hay incidentes registrados.")
        lines = [
            f"`#{i['id']}` <t:{int(i['start'])}:f> · <@{i['actor']}> · {i['level']} · {len(i['events'])} eventos{' · cerrado' if i.get('closed') else ''}"
            for i in incidents[:30]
        ]
        await ctx.send(embed=discord.Embed(title="📁 Incidentes", description="\n".join(lines), color=COLOR_INFO), allowed_mentions=NO_MENTIONS)

    @sec_incident.command(name="close")
    async def sec_incident_close(self, ctx: commands.Context, incident_id: int):
        """Cerrar un incidente."""
        if not await self._require(ctx, "trusted_admin"):
            return
        async with self.config.guild(ctx.guild).incidents() as incidents:
            inc = incidents.get(str(incident_id))
            if inc is None:
                return await ctx.send("Incidente no encontrado.")
            inc["closed"] = True
        await self._settings_log(ctx.guild, ctx.author, "incident_close", f"#{incident_id}")
        await ctx.send(f"Incidente #{incident_id} cerrado.")

    @sec_incident.command(name="report")
    async def sec_incident_report(self, ctx: commands.Context, incident_id: int):
        """Generar informe en texto de un incidente."""
        text = await self.build_incident_report(ctx.guild, incident_id)
        if text is None:
            return await ctx.send("Incidente no encontrado.")
        await ctx.send(file=discord.File(io.BytesIO(text.encode()), filename=f"incident-{incident_id}.txt"))

    # ==================================================================
    # Digest
    # ==================================================================

    @security.group(name="digest")
    async def sec_digest(self, ctx: commands.Context):
        """Resumen semanal de seguridad."""

    @sec_digest.command(name="enable")
    async def sec_digest_enable(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Activar el digest semanal (en el canal indicado o en el de alertas)."""
        if not await self._require(ctx, "extra_owner"):
            return
        async with self.config.guild(ctx.guild).digest() as d:
            d["enabled"] = True
            d["channel"] = channel.id if channel else None
            d["last_sent"] = int(time.time())
        await self._settings_log(ctx.guild, ctx.author, "digest_enable", channel.mention if channel else "canal de alertas")
        await ctx.send("📬 Digest semanal activado.")

    @sec_digest.command(name="disable")
    async def sec_digest_disable(self, ctx: commands.Context):
        """Desactivar el digest semanal."""
        if not await self._require(ctx, "extra_owner"):
            return
        async with self.config.guild(ctx.guild).digest() as d:
            d["enabled"] = False
        await self._settings_log(ctx.guild, ctx.author, "digest_disable", "")
        await ctx.send("Digest semanal desactivado.")

    @sec_digest.command(name="now")
    async def sec_digest_now(self, ctx: commands.Context, days: int = 7):
        """Ver el digest de los ultimos N dias."""
        await ctx.send(embed=await self.build_digest(ctx.guild, days=max(1, min(days, 30))))

    # ==================================================================
    # Configuracion general
    # ==================================================================

    @security.group(name="config")
    async def sec_config(self, ctx: commands.Context):
        """Configuracion general de Trini Security."""

    @sec_config.command(name="logchannel")
    async def sec_config_logchannel(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Canal de alertas de seguridad."""
        if not await self._require(ctx, "extra_owner"):
            return
        await self.config.guild(ctx.guild).log_channel.set(channel.id if channel else None)
        await self._settings_log(ctx.guild, ctx.author, "log_channel", channel.mention if channel else "ninguno")
        await ctx.send(f"Canal de alertas: {channel.mention if channel else 'ninguno'}.")

    @sec_config.command(name="alertrole")
    async def sec_config_alertrole(self, ctx: commands.Context, role: Optional[discord.Role] = None):
        """Rol a mencionar en alertas criticas."""
        if not await self._require(ctx, "extra_owner"):
            return
        await self.config.guild(ctx.guild).alert_role.set(role.id if role else None)
        await self._settings_log(ctx.guild, ctx.author, "alert_role", role.name if role else "ninguno")
        await ctx.send(f"Rol de alerta: {role.mention if role else 'ninguno'}.", allowed_mentions=NO_MENTIONS)

    @sec_config.command(name="quarantinerole")
    async def sec_config_qrole(self, ctx: commands.Context, role: Optional[discord.Role] = None):
        """Rol opcional que se añade a los usuarios en quarantine."""
        if not await self._require(ctx, "extra_owner"):
            return
        async with self.config.guild(ctx.guild).antinuke() as an:
            an["quarantine_role"] = role.id if role else None
        await self._settings_log(ctx.guild, ctx.author, "quarantine_role", role.name if role else "ninguno")
        await ctx.send(f"Rol de quarantine: {role.mention if role else 'ninguno'}.", allowed_mentions=NO_MENTIONS)

    @sec_config.command(name="botpolicy")
    async def sec_config_botpolicy(self, ctx: commands.Context, policy: Literal["kick", "alert"]):
        """Que hacer con bots no incluidos en whitelist (con Anti-Nuke activo)."""
        if not await self._require(ctx, "extra_owner"):
            return
        async with self.config.guild(ctx.guild).antinuke() as an:
            an["bot_policy"] = policy
        await self._settings_log(ctx.guild, ctx.author, "bot_policy", policy)
        await ctx.send(f"Politica de bots no autorizados: `{policy}`.")

    # ==================================================================
    # Authority
    # ==================================================================

    @security.group(name="authority")
    async def sec_authority(self, ctx: commands.Context):
        """Modelo de confianza: Owner, Extra Owners y Trusted Admins."""

    @sec_authority.command(name="add")
    async def sec_authority_add(self, ctx: commands.Context, member: discord.Member, level: Literal["extra_owner", "trusted_admin"]):
        """Añadir un Extra Owner (solo Owner) o Trusted Admin (Extra Owner+)."""
        if member.bot:
            return await ctx.send("No se puede dar autoridad a un bot.")
        if not await self._require(ctx, "owner" if level == "extra_owner" else "extra_owner"):
            return
        async with self.config.guild(ctx.guild).authority() as auth:
            for key in ("extra_owners", "trusted_admins"):
                if member.id in auth[key]:
                    auth[key].remove(member.id)
            auth["extra_owners" if level == "extra_owner" else "trusted_admins"].append(member.id)
        await self._settings_log(ctx.guild, ctx.author, "authority_add", f"{member} → {level}")
        await ctx.send(f"{member.mention} ahora es **{AUTHORITY_LABELS[level]}**.", allowed_mentions=NO_MENTIONS)

    @sec_authority.command(name="remove")
    async def sec_authority_remove(self, ctx: commands.Context, member: discord.Member):
        """Quitar autoridad a un usuario."""
        auth = await self.config.guild(ctx.guild).authority()
        if member.id in auth["extra_owners"]:
            if not await self._require(ctx, "owner"):
                return
        elif member.id in auth["trusted_admins"]:
            if not await self._require(ctx, "extra_owner"):
                return
        else:
            return await ctx.send("Ese usuario no tiene autoridad en Trini Security.")
        async with self.config.guild(ctx.guild).authority() as a:
            for key in ("extra_owners", "trusted_admins"):
                if member.id in a[key]:
                    a[key].remove(member.id)
        await self._settings_log(ctx.guild, ctx.author, "authority_remove", str(member))
        await ctx.send(f"{member.mention} ya no tiene autoridad en Trini Security.", allowed_mentions=NO_MENTIONS)

    @sec_authority.command(name="list")
    async def sec_authority_list(self, ctx: commands.Context):
        """Listar la jerarquia de confianza."""
        auth = await self.config.guild(ctx.guild).authority()
        embed = discord.Embed(title="🔱 Authority", color=COLOR_INFO)
        embed.add_field(name="👑 Server Owner", value=f"<@{ctx.guild.owner_id}>", inline=False)
        embed.add_field(name="🔱 Extra Owners", value="\n".join(f"<@{u}>" for u in auth["extra_owners"]) or "—", inline=True)
        embed.add_field(name="🛡 Trusted Admins", value="\n".join(f"<@{u}>" for u in auth["trusted_admins"]) or "—", inline=True)
        regular = [m.mention for m in ctx.guild.members if not m.bot and m.guild_permissions.administrator and m.id != ctx.guild.owner_id and m.id not in auth["extra_owners"] + auth["trusted_admins"]]
        if regular:
            embed.add_field(name="Administradores sin autoridad Trini", value=", ".join(regular[:30])[:1024], inline=False)
        embed.set_footer(text="Tener Administrator en Discord no implica ser Trusted Admin en Trini Security.")
        await ctx.send(embed=embed, allowed_mentions=NO_MENTIONS)

    # ==================================================================
    # Protected Roles
    # ==================================================================

    @security.group(name="protectedrole", aliases=["protected-role", "prole"])
    async def sec_prole(self, ctx: commands.Context):
        """Roles criticos que solo pueden gestionar usuarios autorizados."""

    @sec_prole.command(name="add")
    async def sec_prole_add(self, ctx: commands.Context, role: discord.Role):
        """Proteger un rol."""
        if not await self._require(ctx, "extra_owner"):
            return
        if role.is_default() or role.managed:
            return await ctx.send("No se puede proteger @everyone ni roles gestionados por integraciones.")
        if role >= ctx.guild.me.top_role:
            await ctx.send("⚠️ El rol esta por encima del bot: podre detectar violaciones pero no revertirlas.")
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
        await ctx.send(f"🛡 {role.mention} ahora es un rol protegido.", allowed_mentions=NO_MENTIONS)

    @sec_prole.command(name="remove")
    async def sec_prole_remove(self, ctx: commands.Context, role: discord.Role):
        """Dejar de proteger un rol."""
        if not await self._require(ctx, "extra_owner"):
            return
        async with self.config.guild(ctx.guild).protected_roles() as prot:
            if prot.pop(str(role.id), None) is None:
                return await ctx.send("Ese rol no esta protegido.")
        await self._settings_log(ctx.guild, ctx.author, "protected_role_remove", role.name)
        await ctx.send(f"{role.mention} ya no esta protegido.", allowed_mentions=NO_MENTIONS)

    @sec_prole.command(name="list")
    async def sec_prole_list(self, ctx: commands.Context):
        """Listar roles protegidos."""
        prot = await self.config.guild(ctx.guild).protected_roles()
        if not prot:
            return await ctx.send("No hay roles protegidos. `security protectedrole add @rol`")
        lines = []
        for rid, cfg in prot.items():
            role = ctx.guild.get_role(int(rid))
            name = role.mention if role else f"~~{rid}~~ (eliminado)"
            lines.append(f"🛡 {name} · allowed: {', '.join(cfg.get('allowed', []))} · self: {cfg.get('self_assign')} · bots: {cfg.get('bots')}")
        await ctx.send(embed=discord.Embed(title="🛡 Protected Roles", description="\n".join(lines)[:4000], color=COLOR_INFO), allowed_mentions=NO_MENTIONS)

    @sec_prole.command(name="config")
    async def sec_prole_config(
        self,
        ctx: commands.Context,
        role: discord.Role,
        option: Optional[Literal["allowed", "self_assign", "bots", "temporary_whitelist", "allow_user", "allow_role"]] = None,
        *,
        value: Optional[str] = None,
    ):
        """Configurar un rol protegido. Sin opcion muestra la configuracion.

        - allowed: niveles permitidos, ej. `extra_owner,trusted_admin`
        - self_assign / bots / temporary_whitelist: true/false
        - allow_user / allow_role: añade o quita (toggle) un usuario o rol autorizado
        """
        prot = await self.config.guild(ctx.guild).protected_roles()
        cfg = prot.get(str(role.id))
        if cfg is None:
            return await ctx.send("Ese rol no esta protegido.")
        if option is None:
            text = (
                f"Rol protegido: {role.mention}\n\n**Allowed:**\n" + "\n".join(f"- {a}" for a in cfg.get("allowed", []))
                + f"\n\nself_assign: `{cfg.get('self_assign')}`\nbots: `{cfg.get('bots')}`\ntemporary_whitelist: `{cfg.get('temporary_whitelist')}`"
                + (f"\nUsuarios autorizados: {', '.join(f'<@{u}>' for u in cfg.get('allowed_users', []))}" if cfg.get("allowed_users") else "")
                + (f"\nRoles autorizados: {', '.join(f'<@&{r}>' for r in cfg.get('allowed_roles', []))}" if cfg.get("allowed_roles") else "")
            )
            return await ctx.send(embed=discord.Embed(description=text, color=COLOR_INFO), allowed_mentions=NO_MENTIONS)
        if not await self._require(ctx, "extra_owner"):
            return
        if value is None:
            return await ctx.send("Falta el valor.")
        async with self.config.guild(ctx.guild).protected_roles() as p:
            c = p[str(role.id)]
            if option == "allowed":
                levels = [v.strip() for v in value.replace(" ", ",").split(",") if v.strip()]
                bad = [lv for lv in levels if lv not in ("extra_owner", "trusted_admin")]
                if bad:
                    return await ctx.send("Niveles validos: `extra_owner`, `trusted_admin`.")
                c["allowed"] = levels
            elif option in ("self_assign", "bots", "temporary_whitelist"):
                c[option] = value.lower() in ("true", "si", "sí", "yes", "on", "1")
            elif option == "allow_user":
                try:
                    member = await commands.MemberConverter().convert(ctx, value)
                except commands.BadArgument:
                    return await ctx.send("Usuario no encontrado.")
                lst = c.setdefault("allowed_users", [])
                lst.remove(member.id) if member.id in lst else lst.append(member.id)
            elif option == "allow_role":
                try:
                    r = await commands.RoleConverter().convert(ctx, value)
                except commands.BadArgument:
                    return await ctx.send("Rol no encontrado.")
                lst = c.setdefault("allowed_roles", [])
                lst.remove(r.id) if r.id in lst else lst.append(r.id)
        await self._settings_log(ctx.guild, ctx.author, "protected_role_config", f"{role.name}: {option}={value}")
        await ctx.send(f"✅ {role.mention}: `{option}` actualizado.", allowed_mentions=NO_MENTIONS)

    # ==================================================================
    # Whitelists
    # ==================================================================

    @security.group(name="whitelist")
    async def sec_whitelist(self, ctx: commands.Context):
        """Whitelists por tipo: users, roles, bots, webhooks, channels, invites."""

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
        """Añadir a una whitelist. Ej: `security whitelist add bots @MiBot`."""
        if not await self._require(ctx, "extra_owner"):
            return
        value = await self._resolve_wl_target(ctx, wtype, target)
        if value is None:
            return await ctx.send("No se pudo interpretar el objetivo.")
        async with self.config.guild(ctx.guild).whitelists() as wl:
            lst = wl.setdefault(wtype, [])
            if value in lst:
                return await ctx.send("Ya estaba en la whitelist.")
            lst.append(value)
        await self._settings_log(ctx.guild, ctx.author, "whitelist_add", f"{wtype}: {value}")
        await ctx.send(f"✅ Añadido a la whitelist de **{wtype}**: `{value}`.")

    @sec_whitelist.command(name="remove")
    async def sec_whitelist_remove(self, ctx: commands.Context, wtype: WhitelistType, *, target: str):
        """Quitar de una whitelist."""
        if not await self._require(ctx, "extra_owner"):
            return
        value = await self._resolve_wl_target(ctx, wtype, target)
        async with self.config.guild(ctx.guild).whitelists() as wl:
            lst = wl.setdefault(wtype, [])
            if value not in lst:
                return await ctx.send("No estaba en la whitelist.")
            lst.remove(value)
        await self._settings_log(ctx.guild, ctx.author, "whitelist_remove", f"{wtype}: {value}")
        await ctx.send(f"🗑 Eliminado de la whitelist de **{wtype}**: `{value}`.")

    @sec_whitelist.command(name="list")
    async def sec_whitelist_list(self, ctx: commands.Context):
        """Ver todas las whitelists."""
        wl = await self._get_whitelists(ctx.guild)
        fmt = {
            "users": lambda v: f"<@{v}>", "bots": lambda v: f"<@{v}>", "roles": lambda v: f"<@&{v}>",
            "channels": lambda v: f"<#{v}>", "webhooks": lambda v: f"`{v}`", "invites": lambda v: f"`{v}`",
        }
        embed = discord.Embed(title="📃 Whitelists", color=COLOR_INFO)
        for t in WHITELIST_TYPES:
            embed.add_field(name=t, value=", ".join(fmt[t](v) for v in wl[t][:30])[:1024] or "—", inline=False)
        temp = [t for t in await self.config.guild(ctx.guild).temp_whitelist() if t["expires"] > time.time()]
        if temp:
            embed.add_field(
                name="Temporales (roles protegidos)",
                value="\n".join(f"<@&{t['role']}> → <@{t['user']}> hasta <t:{int(t['expires'])}:R>" for t in temp)[:1024],
                inline=False,
            )
        await ctx.send(embed=embed, allowed_mentions=NO_MENTIONS)

    @sec_whitelist.command(name="temp")
    async def sec_whitelist_temp(self, ctx: commands.Context, role: discord.Role, member: discord.Member, duration: str = "1h"):
        """Whitelist temporal de un rol protegido. Ej: `security whitelist temp @Admin @Pepe 1h`."""
        if not await self._require(ctx, "trusted_admin"):
            return
        prot = await self.config.guild(ctx.guild).protected_roles()
        if str(role.id) not in prot:
            return await ctx.send("Ese rol no esta protegido.")
        if not prot[str(role.id)].get("temporary_whitelist", True):
            return await ctx.send("Ese rol no admite whitelist temporal.")
        seconds = parse_duration(duration)
        if not seconds or seconds > 7 * 86400:
            return await ctx.send("Duracion no valida (maximo 7d).")
        async with self.config.guild(ctx.guild).temp_whitelist() as temp:
            temp.append({"role": role.id, "user": member.id, "expires": time.time() + seconds, "by": ctx.author.id})
        await self._settings_log(ctx.guild, ctx.author, "whitelist_temp", f"{role.name} → {member} ({fmt_duration(seconds)})")
        await ctx.send(f"⏳ {member.mention} en whitelist temporal para {role.mention} durante **{fmt_duration(seconds)}**.", allowed_mentions=NO_MENTIONS)

    # ==================================================================
    # Security Watch
    # ==================================================================

    @security.group(name="watch")
    async def sec_watch(self, ctx: commands.Context):
        """Vigilancia de cambios administrativos sensibles."""

    @sec_watch.command(name="enable")
    async def sec_watch_enable(self, ctx: commands.Context):
        """Activar Security Watch."""
        if not await self._require(ctx, "extra_owner"):
            return
        async with self.config.guild(ctx.guild).watch() as w:
            w["enabled"] = True
        await self._settings_log(ctx.guild, ctx.author, "watch_enable", "")
        msg = "👁 Security Watch activado."
        if not await self.config.guild(ctx.guild).log_channel():
            msg += "\n⚠️ Configura un canal: `security config logchannel #canal`."
        await ctx.send(msg)

    @sec_watch.command(name="disable")
    async def sec_watch_disable(self, ctx: commands.Context):
        """Desactivar Security Watch."""
        if not await self._require(ctx, "extra_owner"):
            return
        async with self.config.guild(ctx.guild).watch() as w:
            w["enabled"] = False
        await self._settings_log(ctx.guild, ctx.author, "watch_disable", "")
        await ctx.send("Security Watch desactivado.")

    @sec_watch.command(name="level")
    async def sec_watch_level(self, ctx: commands.Context, level: Literal["normal", "max"]):
        """Nivel de vigilancia."""
        if not await self._require(ctx, "extra_owner"):
            return
        async with self.config.guild(ctx.guild).watch() as w:
            w["level"] = level
        await self._settings_log(ctx.guild, ctx.author, "watch_level", level)
        await ctx.send(f"Nivel de Security Watch: `{level}`.")

    # ==================================================================
    # Anti-Nuke
    # ==================================================================

    @security.group(name="antinuke")
    async def sec_antinuke(self, ctx: commands.Context):
        """Deteccion de nukes por thresholds y risk score."""

    @sec_antinuke.command(name="enable")
    async def sec_antinuke_enable(self, ctx: commands.Context):
        """Activar Anti-Nuke."""
        if not await self._require(ctx, "extra_owner"):
            return
        async with self.config.guild(ctx.guild).antinuke() as an:
            an["enabled"] = True
        await self._settings_log(ctx.guild, ctx.author, "antinuke_enable", "")
        warn = "" if ctx.guild.me.guild_permissions.view_audit_log else "\n⚠️ Necesito **View Audit Log**."
        await ctx.send("💣 Anti-Nuke activado." + warn)

    @sec_antinuke.command(name="disable")
    async def sec_antinuke_disable(self, ctx: commands.Context):
        """Desactivar Anti-Nuke."""
        if not await self._require(ctx, "extra_owner"):
            return
        async with self.config.guild(ctx.guild).antinuke() as an:
            an["enabled"] = False
        await self._settings_log(ctx.guild, ctx.author, "antinuke_disable", "")
        await ctx.send("Anti-Nuke desactivado.")

    @sec_antinuke.command(name="status")
    async def sec_antinuke_status(self, ctx: commands.Context):
        """Ver thresholds, puntuaciones y niveles."""
        an = self._merged_antinuke(await self.config.guild(ctx.guild).antinuke())
        th = "\n".join(f"{ACTION_LABELS.get(k, k):<24} {v[0] or '-'}/min  {v[1] or '-'}/h" for k, v in an["thresholds"].items())
        sc = "\n".join(f"{ACTION_LABELS.get(k, k):<28} {v} pts" for k, v in an["scores"].items())
        lv = an["levels"]
        levels = f"0 - {lv['alert'] - 1}    Log\n{lv['alert']} - {lv['block'] - 1}   Alertar staff\n{lv['block']} - {lv['quarantine'] - 1}   Bloquear acciones sensibles\n{lv['quarantine']}+      Quarantine"
        embed = discord.Embed(title=f"💣 Anti-Nuke {'🟢' if an['enabled'] else '⚫'}", color=COLOR_INFO)
        embed.add_field(name="Thresholds", value=box(th), inline=False)
        embed.add_field(name="Risk score", value=box(sc), inline=False)
        embed.add_field(name="Respuesta escalonada", value=box(levels), inline=False)
        embed.add_field(name="Ventana", value=fmt_duration(an["window"]), inline=True)
        embed.add_field(name="Trusted Admins inmunes", value=str(an["trusted_immune"]), inline=True)
        embed.add_field(name="Bots no autorizados", value=an["bot_policy"], inline=True)
        await ctx.send(embed=embed)

    @sec_antinuke.command(name="threshold")
    async def sec_antinuke_threshold(self, ctx: commands.Context, action: str, per_minute: int, per_hour: int = 0):
        """Cambiar threshold de una accion (0 = sin limite)."""
        if not await self._require(ctx, "extra_owner"):
            return
        if action not in DEFAULT_THRESHOLDS:
            return await ctx.send("Acciones: " + ", ".join(f"`{a}`" for a in DEFAULT_THRESHOLDS))
        async with self.config.guild(ctx.guild).antinuke() as an:
            an.setdefault("thresholds", {})[action] = [max(0, per_minute), max(0, per_hour)]
        await self._settings_log(ctx.guild, ctx.author, "antinuke_threshold", f"{action}: {per_minute}/min {per_hour}/h")
        await ctx.send(f"Threshold `{action}`: {per_minute}/min · {per_hour}/h.")

    @sec_antinuke.command(name="score")
    async def sec_antinuke_score(self, ctx: commands.Context, action: str, points: int):
        """Cambiar los puntos de riesgo de una accion."""
        if not await self._require(ctx, "extra_owner"):
            return
        if action not in DEFAULT_SCORES:
            return await ctx.send("Acciones: " + ", ".join(f"`{a}`" for a in DEFAULT_SCORES))
        async with self.config.guild(ctx.guild).antinuke() as an:
            an.setdefault("scores", {})[action] = max(0, points)
        await self._settings_log(ctx.guild, ctx.author, "antinuke_score", f"{action}: {points}")
        await ctx.send(f"`{action}` = {points} puntos.")

    @sec_antinuke_threshold.autocomplete("action")
    async def _ac_threshold(self, interaction: discord.Interaction, current: str):
        return [discord.app_commands.Choice(name=ACTION_LABELS.get(a, a), value=a) for a in DEFAULT_THRESHOLDS if current.lower() in a][:25]

    @sec_antinuke_score.autocomplete("action")
    async def _ac_score(self, interaction: discord.Interaction, current: str):
        return [discord.app_commands.Choice(name=ACTION_LABELS.get(a, a), value=a) for a in DEFAULT_SCORES if current.lower() in a][:25]

    @sec_antinuke.command(name="levels")
    async def sec_antinuke_levels(self, ctx: commands.Context, alert: int, block: int, quarantine: int):
        """Umbrales de respuesta: alerta, bloqueo y quarantine."""
        if not await self._require(ctx, "extra_owner"):
            return
        if not 0 < alert < block < quarantine:
            return await ctx.send("Debe cumplirse 0 < alert < block < quarantine.")
        async with self.config.guild(ctx.guild).antinuke() as an:
            an["levels"] = {"alert": alert, "block": block, "quarantine": quarantine}
        await self._settings_log(ctx.guild, ctx.author, "antinuke_levels", f"{alert}/{block}/{quarantine}")
        await ctx.send(f"Niveles: alerta {alert} · bloqueo {block} · quarantine {quarantine}.")

    @sec_antinuke.command(name="window")
    async def sec_antinuke_window(self, ctx: commands.Context, duration: str):
        """Ventana de acumulacion del risk score. Ej: `10m`."""
        if not await self._require(ctx, "extra_owner"):
            return
        seconds = parse_duration(duration)
        if not seconds or not 60 <= seconds <= 3600:
            return await ctx.send("Entre 1m y 1h.")
        async with self.config.guild(ctx.guild).antinuke() as an:
            an["window"] = seconds
        await self._settings_log(ctx.guild, ctx.author, "antinuke_window", fmt_duration(seconds))
        await ctx.send(f"Ventana: {fmt_duration(seconds)}.")

    @sec_antinuke.command(name="trustedimmune")
    async def sec_antinuke_trusted(self, ctx: commands.Context, enabled: bool):
        """Si los Trusted Admins son inmunes a Anti-Nuke."""
        if not await self._require(ctx, "extra_owner"):
            return
        async with self.config.guild(ctx.guild).antinuke() as an:
            an["trusted_immune"] = enabled
        await self._settings_log(ctx.guild, ctx.author, "antinuke_trusted_immune", str(enabled))
        await ctx.send(f"Trusted Admins inmunes: `{enabled}`.")

    @sec_antinuke.command(name="reset")
    async def sec_antinuke_reset(self, ctx: commands.Context):
        """Restaurar thresholds, puntuaciones y niveles por defecto."""
        if not await self._require(ctx, "extra_owner"):
            return
        async with self.config.guild(ctx.guild).antinuke() as an:
            an["thresholds"] = dict(DEFAULT_THRESHOLDS)
            an["scores"] = dict(DEFAULT_SCORES)
            an.pop("levels", None)
            an["window"] = 600
        await self._settings_log(ctx.guild, ctx.author, "antinuke_reset", "")
        await ctx.send("Valores por defecto restaurados.")

    # ==================================================================
    # Lockdown
    # ==================================================================

    @security.group(name="lockdown")
    async def sec_lockdown(self, ctx: commands.Context):
        """Emergency Lockdown."""

    @sec_lockdown.command(name="enable")
    async def sec_lockdown_enable(self, ctx: commands.Context, pause_invites: bool = True):
        """Activar el modo emergencia."""
        if not await self._require(ctx, "trusted_admin"):
            return
        if (await self.config.guild(ctx.guild).lockdown()).get("active"):
            return await ctx.send("El lockdown ya esta activo.")
        view = ConfirmView(ctx.author, label="Activar lockdown", style=discord.ButtonStyle.red)
        msg = await ctx.send("¿Activar **SECURITY LOCKDOWN**? Solo Owner y Extra Owners podran desactivarlo.", view=view)
        await view.wait()
        if not view.value:
            return await msg.edit(content="Cancelado.", view=None)
        async with ctx.typing():
            notes = await self.enable_lockdown(ctx.guild, ctx.author, disable_invites=pause_invites)
        embed = discord.Embed(
            title="🔐 SECURITY LOCKDOWN",
            color=COLOR_CRIT,
            description=(
                "• Nuevos bots: **bloqueados**\n"
                "• Webhooks nuevos: **bloqueados**\n"
                "• Protected Roles: **bloqueados**\n"
                "• Cambios administrativos: **restringidos**\n"
                f"• Invitaciones: **{'pausadas' if pause_invites else 'sin cambios'}**\n"
                "• Security Watch: **maximo nivel**"
            ),
            timestamp=discord.utils.utcnow(),
        )
        if notes:
            embed.add_field(name="Notas", value="\n".join(notes), inline=False)
        embed.set_footer(text=f"Activado por {ctx.author} · security lockdown disable")
        await msg.edit(content=None, embed=embed, view=None)
        await self._send_log(ctx.guild, embed, ping=True, critical=True)

    @sec_lockdown.command(name="disable")
    async def sec_lockdown_disable(self, ctx: commands.Context):
        """Salir del modo emergencia (Owner / Extra Owners)."""
        if not await self._require(ctx, "extra_owner"):
            return
        if not (await self.config.guild(ctx.guild).lockdown()).get("active"):
            return await ctx.send("No hay lockdown activo.")
        notes = await self.disable_lockdown(ctx.guild, ctx.author)
        embed = discord.Embed(title="🔓 Lockdown desactivado", color=COLOR_OK, description="\n".join(notes) or None)
        embed.set_footer(text=f"Por {ctx.author}")
        await ctx.send(embed=embed)
        await self._send_log(ctx.guild, embed)

    @sec_lockdown.command(name="status")
    async def sec_lockdown_status(self, ctx: commands.Context):
        """Estado del lockdown."""
        lk = await self.config.guild(ctx.guild).lockdown()
        if lk.get("active"):
            await ctx.send(f"🔴 Lockdown **activo** desde <t:{lk['at']}:R> (por <@{lk['by']}>).", allowed_mentions=NO_MENTIONS)
        else:
            await ctx.send("🟢 Sin lockdown.")

    # ==================================================================
    # Quarantine
    # ==================================================================

    @security.group(name="quarantine")
    async def sec_quarantine(self, ctx: commands.Context):
        """Usuarios en quarantine."""

    @sec_quarantine.command(name="list")
    async def sec_quarantine_list(self, ctx: commands.Context):
        """Listar usuarios en quarantine."""
        q = await self.config.guild(ctx.guild).quarantined()
        if not q:
            return await ctx.send("🟢 Nadie en quarantine.")
        lines = [f"<@{uid}> · <t:{d['at']}:R> · {len(d['roles'])} roles guardados · {d['reason']}" for uid, d in q.items()]
        await ctx.send(embed=discord.Embed(title="🔒 Quarantine", description="\n".join(lines)[:4000], color=COLOR_WARN), allowed_mentions=NO_MENTIONS)

    @sec_quarantine.command(name="add")
    async def sec_quarantine_add(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Manual"):
        """Poner manualmente a un usuario en quarantine (retira roles peligrosos)."""
        if not await self._require(ctx, "trusted_admin"):
            return
        target_level = await self.get_authority_level(member)
        my_level = await self.get_authority_level(ctx.author)
        if AUTHORITY_LEVELS[target_level] >= AUTHORITY_LEVELS[my_level]:
            return await ctx.send("No puedes poner en quarantine a alguien con tu mismo nivel de autoridad o superior.")
        ok, msg = await self.quarantine_member(ctx.guild, member, reason=f"{reason} (por {ctx.author})", by=ctx.author)
        await self._settings_log(ctx.guild, ctx.author, "quarantine_add", f"{member}: {reason}")
        await ctx.send(msg, allowed_mentions=NO_MENTIONS)

    @sec_quarantine.command(name="release")
    async def sec_quarantine_release(self, ctx: commands.Context, user: discord.User):
        """Liberar a un usuario y restaurar sus roles."""
        if not await self._require(ctx, "trusted_admin"):
            return
        if user.id == ctx.author.id:
            return await ctx.send("No puedes liberarte a ti mismo.")
        ok, msg = await self.release_quarantine(ctx.guild, user.id, ctx.author)
        await ctx.send(msg, allowed_mentions=NO_MENTIONS)
