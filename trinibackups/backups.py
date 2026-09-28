"""
Trini Backups - snapshots estructurales, diff, backups programados y
restauracion segura (no destructiva) para La Trini.

By Killerbite95
"""

from __future__ import annotations

import asyncio
import datetime
import gzip
import io
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import discord
from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path
from redbot.core.utils.chat_formatting import box, humanize_list
from redbot.core.utils.views import SimpleMenu

from .dashboard_integration import DashboardIntegration
from .snapshot import (
    FORMAT,
    VERSION,
    RestorePlan,
    build_plan,
    capture_structure,
    counts,
    diff_snapshots,
    diff_to_embeds,
    now_id,
    plan_details,
    plan_summary,
)
from redbot.core.i18n import Translator, cog_i18n, set_contextual_locales_from_guild

_ = Translator("TriniBackups", __file__)


def N_(text: str) -> str:
    """Marca un texto de una constante para traducirlo al usarlo con ``_()``."""
    return text

log = logging.getLogger("red.killerbite95.trinibackups")

KIND_ICON = {"manual": "💾", "auto": "🕒", "security": "🔐", "pre-restore": "⏪"}
COLOR = discord.Color.from_rgb(46, 204, 113)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class RestoreView(discord.ui.View):
    OPTIONS = (
        ("roles", N_("Roles"), "🎭"),
        ("channels", N_("Channels"), "#️⃣"),
        ("permissions", N_("Permissions"), "🔑"),
        ("positions", N_("Hierarchy"), "↕️"),
        ("trini", N_("Trini config"), "⚙️"),
    )

    def __init__(self, cog: "TriniBackups", ctx: commands.Context, meta: Dict[str, Any], snap: Dict[str, Any]):
        super().__init__(timeout=300)
        self.cog = cog
        self.ctx = ctx
        self.meta = meta
        self.snap = snap
        self.options = {"roles": True, "channels": True, "permissions": True, "positions": False, "trini": True}
        self.plan: Optional[RestorePlan] = None
        self.message: Optional[discord.Message] = None
        self.result: Optional[bool] = None
        for key, label, emoji in self.OPTIONS:
            button = discord.ui.Button(label=_(label), emoji=emoji, row=0, custom_id=f"opt:{key}")
            button.callback = self._make_toggle(key)
            self.add_item(button)
        self._style_buttons()

    def _style_buttons(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.custom_id and item.custom_id.startswith("opt:"):
                key = item.custom_id.split(":", 1)[1]
                item.style = discord.ButtonStyle.green if self.options[key] else discord.ButtonStyle.grey

    def _make_toggle(self, key: str):
        async def callback(interaction: discord.Interaction):
            self.options[key] = not self.options[key]
            self._style_buttons()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
        return callback

    def build_embed(self) -> discord.Embed:
        self.plan = build_plan(self.ctx.guild, self.snap, self.options)
        embed = discord.Embed(
            title=_("⏪ Restore backup `{id}`").format(id=self.meta['id']),
            description=box(plan_summary(self.plan), lang="diff"),
            color=discord.Color.orange(),
        )
        details = plan_details(self.plan)
        if details:
            embed.add_field(name=_("Details"), value=box("\n".join(details), lang="diff")[:1024], inline=False)
        if self.plan.skipped:
            embed.add_field(name=_("Will be skipped"), value="\n".join(f"• {s}" for s in self.plan.skipped[:10])[:1024], inline=False)
        embed.set_footer(text=_("{value} · {fromtimestamp:%d/%m/%Y %H:%M} UTC · green = included").format(value=self.meta.get('name') or '', fromtimestamp=datetime.datetime.fromtimestamp(self.meta['created_at'], datetime.timezone.utc)))
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        await set_contextual_locales_from_guild(interaction.client, interaction.guild)
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(_("Only whoever ran the command can use this."), ephemeral=True)
            return False
        return True

    @discord.ui.button(label=_("Continue"), style=discord.ButtonStyle.red, row=1)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.plan is None or self.plan.empty:
            return await interaction.response.send_message(_("There is nothing to restore."), ephemeral=True)
        self.result = True
        self.stop()
        await interaction.response.edit_message(view=None)

    @discord.ui.button(label=_("Cancel"), style=discord.ButtonStyle.grey, row=1)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = False
        self.stop()
        await interaction.response.edit_message(content=_("Restore cancelled."), embed=None, view=None)


class ConfirmView(discord.ui.View):
    def __init__(self, author: discord.abc.User, label: Optional[str] = None):
        super().__init__(timeout=60)
        self.author = author
        self.value: Optional[bool] = None
        self.yes.label = label or _("Confirm")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        await set_contextual_locales_from_guild(interaction.client, interaction.guild)
        return interaction.user.id == self.author.id

    @discord.ui.button(label=_("Confirm"), style=discord.ButtonStyle.red)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label=_("Cancel"), style=discord.ButtonStyle.grey)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.stop()
        await interaction.response.defer()


@cog_i18n(_)
class TriniBackups(DashboardIntegration, commands.Cog):
    """Structural server snapshots, diffs, scheduled backups and safe restores."""

    __author__ = "Killerbite95"
    __version__ = "1.0.0"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0x7121BAC0, force_registration=True)
        self.config.register_guild(
            snapshots={},
            schedule={"mode": "off", "hour": 3, "last_auto": 0},
            retention={"daily": 7, "weekly": 4, "monthly": 6},
            max_manual=30,
        )
        self.path: Path = cog_data_path(self) / "snapshots"
        self._locks: Dict[int, asyncio.Lock] = {}

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre = super().format_help_for_context(ctx)
        return _("{pre}\n\nVersion: {version}").format(pre=pre, version=self.__version__)

    async def red_delete_data_for_user(self, **kwargs) -> None:
        return

    async def cog_check(self, ctx: commands.Context) -> bool:
        # Los slash de discord.py NO heredan los checks del grupo en los
        # subcomandos (con prefijo si). Este cog_check se ejecuta en ambos casos.
        if ctx.guild is None:
            return False
        if await ctx.bot.is_owner(ctx.author) or await ctx.bot.is_admin(ctx.author):
            return True
        return ctx.author.guild_permissions.administrator

    async def cog_load(self) -> None:
        self.schedule_loop.start()
        self._dashboard_register()

    async def cog_unload(self) -> None:
        self.schedule_loop.cancel()

    def _lock(self, guild_id: int) -> asyncio.Lock:
        return self._locks.setdefault(guild_id, asyncio.Lock())

    # ------------------------------------------------------------------
    # Almacenamiento
    # ------------------------------------------------------------------

    def _file(self, guild_id: int, sid: str) -> Path:
        return self.path / str(guild_id) / f"{sid}.json.gz"

    @staticmethod
    def _write_file(path: Path, data: Dict[str, Any]) -> int:
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        with gzip.open(path, "wb") as fp:
            fp.write(raw)
        return path.stat().st_size

    @staticmethod
    def _read_file(path: Path) -> Dict[str, Any]:
        with gzip.open(path, "rb") as fp:
            return json.loads(fp.read().decode("utf-8"))

    async def load_snapshot(self, guild: discord.Guild, sid: str) -> Optional[Dict[str, Any]]:
        path = self._file(guild.id, sid)
        if not path.exists():
            return None
        return await asyncio.to_thread(self._read_file, path)

    async def _capture_trini(self, guild: discord.Guild) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for cog in list(self.bot.cogs.values()):
            if cog is self:
                continue
            exporter = getattr(cog, "trini_export", None)
            if exporter is None:
                continue
            try:
                out[cog.qualified_name] = _json_safe(await exporter(guild))
            except Exception:
                log.exception("No se pudo exportar %s", cog.qualified_name)
        return out

    async def capture(self, guild: discord.Guild) -> Dict[str, Any]:
        data = capture_structure(guild)
        data["trini"] = await self._capture_trini(guild)
        return data

    # ------------------------------------------------------------------
    # API publica (usada por TriniSecurity y TriniProfiles)
    # ------------------------------------------------------------------

    async def create_snapshot(
        self,
        guild: discord.Guild,
        *,
        name: Optional[str] = None,
        kind: str = "manual",
        author: Optional[discord.abc.User] = None,
    ) -> Dict[str, Any]:
        async with self._lock(guild.id):
            data = await self.capture(guild)
            snapshots = await self.config.guild(guild).snapshots()
            sid = now_id()
            n = 2
            while sid in snapshots:
                sid = f"{now_id()}-{n}"
                n += 1
            now = time.time()
            payload = {
                "format": FORMAT,
                "version": VERSION,
                "id": sid,
                "name": name,
                "kind": kind,
                "created_at": now,
                "author": author.id if author else None,
                **data,
            }
            size = await asyncio.to_thread(self._write_file, self._file(guild.id, sid), payload)
            meta = {
                "id": sid,
                "name": name,
                "kind": kind,
                "created_at": now,
                "author": author.id if author else None,
                "counts": counts(payload),
                "size": size,
            }
            async with self.config.guild(guild).snapshots() as snaps:
                snaps[sid] = meta
            await self._enforce_manual_limit(guild)
        return meta

    async def latest_snapshot_before(self, guild: discord.Guild, ts: float) -> Optional[Dict[str, Any]]:
        snaps = [m for m in (await self.config.guild(guild).snapshots()).values() if m["created_at"] < ts]
        if not snaps:
            return None
        return max(snaps, key=lambda m: m["created_at"])

    async def is_scheduled(self, guild: discord.Guild) -> bool:
        return (await self.config.guild(guild).schedule())["mode"] != "off"

    async def diff_current_embeds(self, guild: discord.Guild, sid: str) -> List[discord.Embed]:
        snap = await self.load_snapshot(guild, sid)
        if snap is None:
            return [discord.Embed(description=_("Backup not found."), color=discord.Color.red())]
        current = await self.capture(guild)
        diff = diff_snapshots(snap, current)
        subtitle = _("Backup: **{label}**\n<t:{created_at}:f> → now").format(label=self._label(snap), created_at=int(snap['created_at']))
        return diff_to_embeds(diff, _("📦 Differences since"), subtitle)

    def _label(self, meta: Dict[str, Any]) -> str:
        date = datetime.datetime.fromtimestamp(meta["created_at"], datetime.timezone.utc).strftime("%d/%m/%Y %H:%M")
        return f"{meta.get('name') or date} ({meta['id']})"

    async def trini_export(self, guild: discord.Guild) -> Dict[str, Any]:
        data = await self.config.guild(guild).all()
        return {"schedule": {**data["schedule"], "last_auto": 0}, "retention": data["retention"], "max_manual": data["max_manual"]}

    async def trini_import(self, guild: discord.Guild, data: Dict[str, Any], *, same_guild: bool) -> List[str]:
        for key in ("schedule", "retention", "max_manual"):
            if key in data:
                await self.config.guild(guild).set_raw(key, value=data[key])
        return []

    # ------------------------------------------------------------------
    # Retencion
    # ------------------------------------------------------------------

    async def _delete(self, guild: discord.Guild, sid: str) -> None:
        async with self.config.guild(guild).snapshots() as snaps:
            snaps.pop(sid, None)
        path = self._file(guild.id, sid)
        try:
            await asyncio.to_thread(path.unlink)
        except FileNotFoundError:
            pass

    async def _enforce_manual_limit(self, guild: discord.Guild) -> None:
        limit = await self.config.guild(guild).max_manual()
        snaps = await self.config.guild(guild).snapshots()
        others = sorted((m for m in snaps.values() if m["kind"] != "auto"), key=lambda m: m["created_at"], reverse=True)
        for meta in others[limit:]:
            await self._delete(guild, meta["id"])

    async def apply_retention(self, guild: discord.Guild) -> List[str]:
        """Politica GFS: ultimos N diarios + ultimo de cada semana + ultimo de cada mes."""
        ret = await self.config.guild(guild).retention()
        autos = sorted(
            (m for m in (await self.config.guild(guild).snapshots()).values() if m["kind"] == "auto"),
            key=lambda m: m["created_at"],
            reverse=True,
        )
        keep = {m["id"] for m in autos[: ret["daily"]]}
        weeks, months = [], []
        for m in autos:
            dt = datetime.datetime.fromtimestamp(m["created_at"], datetime.timezone.utc)
            week = dt.isocalendar()[:2]
            month = (dt.year, dt.month)
            if week not in weeks and len(weeks) < ret["weekly"]:
                weeks.append(week)
                keep.add(m["id"])
            if month not in months and len(months) < ret["monthly"]:
                months.append(month)
                keep.add(m["id"])
        removed = [m["id"] for m in autos if m["id"] not in keep]
        for sid in removed:
            await self._delete(guild, sid)
        return removed

    @tasks.loop(minutes=10)
    async def schedule_loop(self) -> None:
        now = datetime.datetime.now(datetime.timezone.utc)
        for guild in list(self.bot.guilds):
            try:
                sched = await self.config.guild(guild).schedule()
                if sched["mode"] == "off" or now.hour < sched["hour"]:
                    continue
                last = datetime.datetime.fromtimestamp(sched.get("last_auto", 0), datetime.timezone.utc)
                if sched["mode"] == "daily":
                    due = last.date() < now.date()
                else:
                    due = (now - last) >= datetime.timedelta(days=6, hours=20)
                if not due:
                    continue
                if await self.bot.cog_disabled_in_guild(self, guild):
                    continue
                await self.create_snapshot(guild, name=None, kind="auto")
                async with self.config.guild(guild).schedule() as s:
                    s["last_auto"] = now.timestamp()
                await self.apply_retention(guild)
            except Exception:
                log.exception("Error en backup programado de %s", guild.id)

    @schedule_loop.before_loop
    async def _before_schedule(self) -> None:
        await self.bot.wait_until_red_ready()

    # ------------------------------------------------------------------
    # Restauracion
    # ------------------------------------------------------------------

    async def _can_restore(self, member: discord.Member) -> bool:
        security = self.bot.get_cog("TriniSecurity")
        if security is not None and hasattr(security, "get_authority_level"):
            return await security.get_authority_level(member) in ("owner", "extra_owner", "trusted_admin")
        return member.guild_permissions.administrator or await self.bot.is_owner(member)

    async def execute_plan(
        self, guild: discord.Guild, snap: Dict[str, Any], plan: RestorePlan, author: discord.abc.User, progress
    ) -> List[str]:
        reason = _("Trini Backups: restore {id} by {author}").format(id=snap['id'], author=author)
        me = guild.me
        allowed_perms = discord.Permissions.all() if me.guild_permissions.administrator else me.guild_permissions
        log_lines: List[str] = []
        errors = 0

        async def step(text: str, coro) -> Any:
            nonlocal errors
            try:
                result = await coro
                log_lines.append(f"✅ {text}")
                return result
            except discord.HTTPException as exc:
                errors += 1
                log_lines.append(f"❌ {text}: {getattr(exc, 'text', exc)}")
            return None

        # 1. Roles nuevos (de abajo hacia arriba)
        for rs in sorted(plan.create_roles, key=lambda r: r["position"]):
            perms = discord.Permissions(rs["permissions"] & allowed_perms.value)
            role = await step(
                _("Create role @{name}").format(name=rs['name']),
                guild.create_role(
                    name=rs["name"], permissions=perms, colour=discord.Colour(rs["color"]),
                    hoist=rs["hoist"], mentionable=rs["mentionable"], reason=reason,
                ),
            )
            if role is not None:
                plan.role_map[rs["id"]] = role.id
        await progress(_("Roles created: {count}").format(count=len(plan.create_roles)))

        # 2. Roles existentes
        for role, changes, _details in plan.update_roles:
            if "permissions" in changes:
                changes = {**changes, "permissions": discord.Permissions(changes["permissions"].value & allowed_perms.value)}
            await step(_("Update @{role_name}").format(role_name=role.name), role.edit(**changes, reason=reason))

        # 3. Jerarquia
        if plan.reorder_roles:
            await step(_("Reorder {count} roles").format(count=len(plan.reorder_roles)), guild.edit_role_positions(positions=plan.reorder_roles, reason=reason))
        await progress(_("Roles updated"))

        # 4. Canales nuevos
        def build_overwrites(cs: Dict[str, Any]) -> Dict[Any, discord.PermissionOverwrite]:
            result = {}
            for ow in cs.get("overwrites", []):
                if ow["type"] == "role":
                    target = guild.get_role(plan.role_map.get(ow["id"], ow["id"]))
                else:
                    target = guild.get_member(ow["id"])
                if target is None:
                    continue
                result[target] = discord.PermissionOverwrite.from_pair(discord.Permissions(ow["allow"]), discord.Permissions(ow["deny"]))
            return result

        for cs in sorted(plan.create_channels, key=lambda c: (c["type"] != "category", c["position"])):
            overwrites = build_overwrites(cs)
            category = guild.get_channel(plan.channel_map.get(cs.get("category_id"), 0)) if cs.get("category_id") else None
            if not isinstance(category, discord.CategoryChannel):
                category = None
            kind = cs["type"]
            label = _("Create {kind} {name}").format(kind=kind, name=cs['name'])
            if kind == "category":
                coro = guild.create_category(cs["name"], overwrites=overwrites, reason=reason)
            elif kind in ("text", "news"):
                coro = guild.create_text_channel(
                    cs["name"], category=category, overwrites=overwrites, topic=cs.get("topic") or None,
                    nsfw=cs.get("nsfw", False), slowmode_delay=cs.get("slowmode") or 0, reason=reason,
                )
            elif kind == "voice":
                coro = guild.create_voice_channel(
                    cs["name"], category=category, overwrites=overwrites,
                    bitrate=min(cs.get("bitrate") or 64000, int(guild.bitrate_limit)),
                    user_limit=cs.get("user_limit") or 0, reason=reason,
                )
            elif kind == "stage":
                coro = guild.create_stage_channel(cs["name"], category=category, overwrites=overwrites, reason=reason)
            elif kind in ("forum", "media"):
                tags = [discord.ForumTag(name=t["name"], moderated=t.get("moderated", False)) for t in cs.get("tags", [])][:20]
                coro = guild.create_forum(
                    cs["name"], category=category, overwrites=overwrites, topic=cs.get("topic") or "",
                    nsfw=cs.get("nsfw", False), slowmode_delay=cs.get("slowmode") or 0, available_tags=tags, reason=reason,
                )
            else:
                continue
            channel = await step(label, coro)
            if channel is not None:
                plan.channel_map[cs["id"]] = channel.id
        await progress(_("Channels created: {count}").format(count=len(plan.create_channels)))

        # 5. Canales existentes
        for channel, changes, _details in plan.update_channels:
            changes = dict(changes)
            if "category_id" in changes:
                cat = guild.get_channel(changes.pop("category_id"))
                if isinstance(cat, discord.CategoryChannel):
                    changes["category"] = cat
            await step(_("Update {channel_name}").format(channel_name=channel.name), channel.edit(**changes, reason=reason))

        # 6. Overwrites
        for snap_cid, ow, label in plan.overwrites:
            channel = guild.get_channel(plan.channel_map.get(snap_cid, 0))
            if channel is None:
                continue
            target = guild.get_role(plan.role_map.get(ow["id"], ow["id"])) if ow["type"] == "role" else guild.get_member(ow["id"])
            if target is None:
                continue
            overwrite = discord.PermissionOverwrite.from_pair(discord.Permissions(ow["allow"]), discord.Permissions(ow["deny"]))
            await step(_("Overwrite {label}").format(label=label), channel.set_permissions(target, overwrite=overwrite, reason=reason))
        await progress(_("Permissions restored"))

        # 7. Configuracion Trini
        same_guild = snap.get("guild", {}).get("id") == guild.id
        for cog_name in plan.trini:
            cog = self.bot.get_cog(cog_name)
            importer = getattr(cog, "trini_import", None) if cog else None
            if importer is None:
                log_lines.append(_("⚠️ {cog_name}: not loaded or without import support").format(cog_name=cog_name))
                continue
            try:
                warnings = await importer(guild, snap["trini"][cog_name], same_guild=same_guild)
                log_lines.append(_("✅ Config {cog_name}").format(cog_name=cog_name) + (f" ({'; '.join(warnings)})" if warnings else ""))
            except Exception as exc:
                errors += 1
                log.exception("Error restaurando configuracion de %s", cog_name)
                log_lines.append(_("❌ Config {cog_name}: {exc}").format(cog_name=cog_name, exc=exc))
        log_lines.insert(0, _("Errors: {errors}").format(errors=errors))
        self.bot.dispatch("trini_settings_change", guild, "Backups", author, "restore", f"{snap['id']} ({errors} errores)")
        return log_lines

    # ------------------------------------------------------------------
    # Comandos
    # ------------------------------------------------------------------

    async def _snap_autocomplete(self, interaction: discord.Interaction, current: str):
        if interaction.guild is None:
            return []
        snaps = sorted((await self.config.guild(interaction.guild).snapshots()).values(), key=lambda m: -m["created_at"])
        current = current.lower()
        out = []
        for m in snaps:
            label = f"{KIND_ICON.get(m['kind'], '')} {m['id']} · {m.get('name') or m['kind']}"
            if current in label.lower():
                out.append(discord.app_commands.Choice(name=label[:100], value=m["id"]))
        return out[:25]

    async def _resolve(self, ctx: commands.Context, sid: Optional[str]) -> Optional[Dict[str, Any]]:
        snaps = await self.config.guild(ctx.guild).snapshots()
        if not snaps:
            await ctx.send(_("There are no backups. Create one with `backup create`."))
            return None
        if sid is None or sid.lower() in ("latest", "ultimo", "último"):
            return max(snaps.values(), key=lambda m: m["created_at"])
        if sid in snaps:
            return snaps[sid]
        matches = [m for m in snaps.values() if (m.get("name") or "").lower() == sid.lower() or m["id"].startswith(sid)]
        if len(matches) == 1:
            return matches[0]
        await ctx.send(_("Backup not found (use the ID from `backup list`)."))
        return None

    @commands.hybrid_group(name="backup")
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    async def backup(self, ctx: commands.Context):
        """Structural server snapshots."""

    @backup.command(name="create")
    async def backup_create(self, ctx: commands.Context, *, name: Optional[str] = None):
        """Create a snapshot. E.g.: `backup create Before the tournament`."""
        async with ctx.typing():
            meta = await self.create_snapshot(ctx.guild, name=(name or "").strip('"')[:80] or None, kind="manual", author=ctx.author)
        c = meta["counts"]
        embed = discord.Embed(
            title=_("💾 Backup created"),
            color=COLOR,
            description=(
                f"ID: `{meta['id']}`" + (_("\nName: **{name}**").format(name=meta['name']) if meta["name"] else "")
                + _("\n\n🎭 {roles} roles · 📁 {categories} categories · # {channels} channels · 🤖 {bots} bots").format(roles=c['roles'], categories=c['categories'], channels=c['channels'], bots=c['bots'])
                + _("\n⚙️ Trini config: {trini} modules\n📦 {value:.1f} KB").format(trini=c['trini'], value=meta['size'] / 1024)
            ),
        )
        await ctx.send(embed=embed)

    @backup.command(name="list")
    async def backup_list(self, ctx: commands.Context):
        """List backups."""
        snaps = sorted((await self.config.guild(ctx.guild).snapshots()).values(), key=lambda m: -m["created_at"])
        if not snaps:
            return await ctx.send(_("There are no backups. Create one with `backup create`."))
        lines = [
            f"{KIND_ICON.get(m['kind'], '•')} `{m['id']}` <t:{int(m['created_at'])}:f>{' · **' + m['name'] + '**' if m.get('name') else ''} · {m['counts']['roles']}R/{m['counts']['channels']}C"
            for m in snaps
        ]
        pages = [lines[i:i + 20] for i in range(0, len(lines), 20)]
        sched = await self.config.guild(ctx.guild).schedule()
        embeds = []
        for i, page in enumerate(pages, 1):
            e = discord.Embed(title=_("📦 Backups ({count})").format(count=len(snaps)), description="\n".join(page), color=COLOR)
            e.set_footer(text=_("Scheduled: {mode} · 💾 manual · 🕒 auto · 🔐 security · ⏪ pre-restore · {i}/{count}").format(mode=sched['mode'], i=i, count=len(pages)))
            embeds.append(e)
        if len(embeds) == 1:
            await ctx.send(embed=embeds[0])
        else:
            await SimpleMenu(embeds).start(ctx)

    @backup.command(name="inspect")
    async def backup_inspect(self, ctx: commands.Context, snapshot: Optional[str] = None):
        """Show the contents of a backup."""
        meta = await self._resolve(ctx, snapshot)
        if meta is None:
            return
        snap = await self.load_snapshot(ctx.guild, meta["id"])
        if snap is None:
            return await ctx.send(_("The backup file does not exist."))
        embed = discord.Embed(title=_("🔍 Backup {label}").format(label=self._label(meta)), color=COLOR)
        embed.add_field(name=_("Created"), value=f"<t:{int(meta['created_at'])}:F>", inline=True)
        embed.add_field(name=_("Type"), value=f"{KIND_ICON.get(meta['kind'], '')} {meta['kind']}", inline=True)
        embed.add_field(name=_("Author"), value=f"<@{meta['author']}>" if meta.get("author") else "sistema", inline=True)
        roles = [r for r in snap["roles"] if not r["default"]]
        roles.sort(key=lambda r: -r["position"])
        embed.add_field(name=_("Roles ({count})").format(count=len(roles)), value=", ".join(r["name"] for r in roles[:40])[:1024] or "—", inline=False)
        cats = {c["id"]: c for c in snap["channels"] if c["type"] == "category"}
        tree: Dict[Optional[int], List[str]] = {}
        for c in sorted(snap["channels"], key=lambda c: c["position"]):
            if c["type"] == "category":
                continue
            tree.setdefault(c.get("category_id"), []).append(c["name"])
        lines = []
        for cid, names in tree.items():
            header = f"📁 {cats[cid]['name']}" if cid in cats else _("No category")
            lines.append(f"{header}: {', '.join(names[:12])}{'…' if len(names) > 12 else ''}")
        embed.add_field(name=_("Channels ({value})").format(value=sum(len(v) for v in tree.values())), value="\n".join(lines)[:1024] or "—", inline=False)
        embed.add_field(name=_("Bots"), value=", ".join(b["name"] for b in snap.get("bots", []))[:1024] or "—", inline=False)
        if snap.get("trini"):
            embed.add_field(name=_("La Trini configuration"), value=humanize_list(list(snap["trini"].keys())), inline=False)
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @backup.command(name="diff")
    async def backup_diff(self, ctx: commands.Context, snapshot: Optional[str] = None):
        """Compare a backup (the latest by default) with the current state."""
        meta = await self._resolve(ctx, snapshot)
        if meta is None:
            return
        async with ctx.typing():
            embeds = await self.diff_current_embeds(ctx.guild, meta["id"])
        await self._send_embeds(ctx, embeds)

    @backup.command(name="compare")
    async def backup_compare(self, ctx: commands.Context, old: str, new: str):
        """Compare two backups."""
        a = await self._resolve(ctx, old)
        b = await self._resolve(ctx, new) if a else None
        if a is None or b is None:
            return
        if a["created_at"] > b["created_at"]:
            a, b = b, a
        sa, sb = await self.load_snapshot(ctx.guild, a["id"]), await self.load_snapshot(ctx.guild, b["id"])
        if sa is None or sb is None:
            return await ctx.send(_("The file of one of the backups was not found."))
        embeds = diff_to_embeds(diff_snapshots(sa, sb), _("📦 Backup comparison"), f"**{self._label(a)}** → **{self._label(b)}**")
        await self._send_embeds(ctx, embeds)

    async def _send_embeds(self, ctx: commands.Context, embeds: List[discord.Embed]) -> None:
        if len(embeds) == 1:
            await ctx.send(embed=embeds[0])
        else:
            for i, e in enumerate(embeds, 1):
                e.set_footer(text=f"{i}/{len(embeds)}")
            await SimpleMenu(embeds).start(ctx)

    @backup_inspect.autocomplete("snapshot")
    @backup_diff.autocomplete("snapshot")
    async def _ac_snapshot(self, interaction: discord.Interaction, current: str):
        return await self._snap_autocomplete(interaction, current)

    @backup_compare.autocomplete("old")
    @backup_compare.autocomplete("new")
    async def _ac_compare(self, interaction: discord.Interaction, current: str):
        return await self._snap_autocomplete(interaction, current)

    @backup.command(name="delete")
    async def backup_delete(self, ctx: commands.Context, snapshot: str):
        """Delete a backup."""
        meta = await self._resolve(ctx, snapshot)
        if meta is None:
            return
        view = ConfirmView(ctx.author, "Eliminar")
        msg = await ctx.send(_("Delete backup **{label}**? This can't be undone.").format(label=self._label(meta)), view=view)
        await view.wait()
        if not view.value:
            return await msg.edit(content=_("Cancelled."), view=None)
        await self._delete(ctx.guild, meta["id"])
        self.bot.dispatch("trini_settings_change", ctx.guild, "Backups", ctx.author, "backup_delete", meta["id"])
        await msg.edit(content=_("🗑 Backup `{id}` deleted.").format(id=meta['id']), view=None)

    @backup.command(name="restore")
    async def backup_restore(self, ctx: commands.Context, snapshot: str):
        """Safe restore: preview first; it only creates/updates, never deletes."""
        if not await self._can_restore(ctx.author):
            return await ctx.send(_("🔒 Restoring requires being Owner, Extra Owner or Trusted Admin in Trini Security."))
        meta = await self._resolve(ctx, snapshot)
        if meta is None:
            return
        snap = await self.load_snapshot(ctx.guild, meta["id"])
        if snap is None:
            return await ctx.send(_("The backup file does not exist."))
        view = RestoreView(self, ctx, meta, snap)
        view.message = await ctx.send(embed=view.build_embed(), view=view)
        await view.wait()
        if not view.result:
            if view.result is None:
                await view.message.edit(content=_("Timed out."), view=None)
            return
        plan = build_plan(ctx.guild, snap, view.options)
        pre = await self.create_snapshot(ctx.guild, name=f"pre-restore {meta['id']}", kind="pre-restore", author=ctx.author)
        status = await ctx.send(_("⏳ Restoring… (automatic pre-restore backup: `{id}`)").format(id=pre['id']))

        async def progress(text: str) -> None:
            try:
                await status.edit(content=f"⏳ {text}…")
            except discord.HTTPException:
                pass

        results = await self.execute_plan(ctx.guild, snap, plan, ctx.author, progress)
        report = "\n".join(results)
        await status.edit(content=_("✅ Restore completed. {value}\nPre-restore backup: `{id}`").format(value=results[0], id=pre['id']))
        await ctx.send(file=discord.File(io.BytesIO(report.encode()), filename=f"restore-{meta['id']}.txt"))

    @backup_delete.autocomplete("snapshot")
    @backup_restore.autocomplete("snapshot")
    async def _ac_snapshot2(self, interaction: discord.Interaction, current: str):
        return await self._snap_autocomplete(interaction, current)

    @backup.command(name="schedule")
    async def backup_schedule(self, ctx: commands.Context, mode: str, hour: Optional[int] = None):
        """Automatic backups: `off`, `daily` or `weekly`, at a UTC hour (0-23)."""
        mode = mode.lower()
        if mode not in ("off", "daily", "weekly"):
            return await ctx.send(_("Modes: `off`, `daily`, `weekly`."))
        if hour is not None and not 0 <= hour <= 23:
            return await ctx.send(_("The hour must be between 0 and 23 (UTC)."))
        async with self.config.guild(ctx.guild).schedule() as s:
            s["mode"] = mode
            if hour is not None:
                s["hour"] = hour
            h = s["hour"]
        ret = await self.config.guild(ctx.guild).retention()
        self.bot.dispatch("trini_settings_change", ctx.guild, "Backups", ctx.author, "schedule", f"{mode} {h}:00 UTC")
        if mode == "off":
            return await ctx.send(_("Automatic backups disabled."))
        await ctx.send(
            _("🕒 Automatic backups: **{mode}** at **{h:02d}:00 UTC**.\nRetention: last {daily} daily · {weekly} weekly · {monthly} monthly.").format(mode=mode, h=h, daily=ret['daily'], weekly=ret['weekly'], monthly=ret['monthly'])
        )

    @backup.command(name="retention")
    async def backup_retention(self, ctx: commands.Context, daily: int, weekly: int, monthly: int):
        """Retention policy for automatic backups."""
        if not (1 <= daily <= 60 and 0 <= weekly <= 52 and 0 <= monthly <= 24):
            return await ctx.send(_("Limits: daily 1-60, weekly 0-52, monthly 0-24."))
        await self.config.guild(ctx.guild).retention.set({"daily": daily, "weekly": weekly, "monthly": monthly})
        removed = await self.apply_retention(ctx.guild)
        self.bot.dispatch("trini_settings_change", ctx.guild, "Backups", ctx.author, "retention", f"{daily}/{weekly}/{monthly}")
        await ctx.send(_("Retention: {daily} daily · {weekly} weekly · {monthly} monthly.").format(daily=daily, weekly=weekly, monthly=monthly) + (_(" ({count} old backups deleted)").format(count=len(removed)) if removed else ""))

    @backup.command(name="export")
    async def backup_export(self, ctx: commands.Context, snapshot: Optional[str] = None):
        """Download a backup as JSON."""
        meta = await self._resolve(ctx, snapshot)
        if meta is None:
            return
        snap = await self.load_snapshot(ctx.guild, meta["id"])
        if snap is None:
            return await ctx.send(_("The backup file does not exist."))
        fp = io.BytesIO(json.dumps(snap, indent=1, ensure_ascii=False).encode("utf-8"))
        text = _("⚠️ It includes the structure and La Trini configuration. Share it carefully.")
        file = discord.File(fp, filename=f"trini-backup-{ctx.guild.id}-{meta['id']}.json")
        if ctx.interaction is not None:
            return await ctx.send(text, file=file, ephemeral=True)
        try:
            await ctx.author.send(text, file=file)
            await ctx.send(_("📬 I sent you the backup by DM."))
        except discord.HTTPException:
            await ctx.send(_("I can't send you DMs. Enable them or use the slash version of the command."))

    @backup.command(name="status")
    async def backup_status(self, ctx: commands.Context):
        """Backup status of the server."""
        data = await self.config.guild(ctx.guild).all()
        snaps = sorted(data["snapshots"].values(), key=lambda m: -m["created_at"])
        embed = discord.Embed(title=_("📦 Trini Backups"), color=COLOR)
        embed.add_field(name=_("Backups"), value=str(len(snaps)), inline=True)
        embed.add_field(name=_("Storage"), value=f"{sum(m['size'] for m in snaps) / 1024:.1f} KB", inline=True)
        s = data["schedule"]
        embed.add_field(name=_("Scheduled"), value=_("{mode} {hour:02d}:00 UTC").format(mode=s['mode'], hour=s['hour']) if s["mode"] != "off" else "no", inline=True)
        if snaps:
            embed.add_field(name=_("Latest"), value=f"`{snaps[0]['id']}` <t:{int(snaps[0]['created_at'])}:R>", inline=False)
        r = data["retention"]
        embed.add_field(name=_("Retention"), value=_("{daily} daily · {weekly} weekly · {monthly} monthly · max {max_manual} manual").format(daily=r['daily'], weekly=r['weekly'], monthly=r['monthly'], max_manual=data['max_manual']), inline=False)
        missing = [p for p in ("manage_roles", "manage_channels") if not getattr(ctx.guild.me.guild_permissions, p)]
        if missing:
            embed.add_field(name=_("⚠️ Permissions"), value=_("To restore I need: ") + ", ".join(missing), inline=False)
        await ctx.send(embed=embed)
