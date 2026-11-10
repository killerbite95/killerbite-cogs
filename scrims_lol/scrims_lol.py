"""
Scrims LoL - board de scrims por servidor.

Equipos con capitan, roster de titulares y suplentes, y board de scrims:
posts de equipo, mix o abierto, apuntados, TTL, hilo privado al cerrar el
emparejamiento, cierre con marcador obligatorio y fotos opcionales por partida.

Modelo de un scrim::

    scrim = {
        "id": int,
        "author_id": int,
        "channel_id": int,
        "message_id": int | None,
        "side": {"kind": "team" | "mix" | "open", "team_id": int | None,
                  "label": str, "signups": [int, ...]},
        "looks_for": "team" | "mix" | "open",
        "start": int,                       # timestamp UTC
        "bo": int,                          # 1, 3 o 5
        "fearless": bool,
        "tier_min": str,
        "tier_max": str,
        "contact": str,
        "status": "open" | "matched" | "closed" | "cancelled" | "expired",
        "rival": {..} | None,               # mismo formato que "side"
        "score": {"us": int, "them": int} | None,
        "photos": [{"game": int, "channel_id": int, "message_id": int, "url": str}],
        "thread_id": int | None,
        "created_at": int,
    }

El registro depende del tipo de lado: un lado de equipo se guarda como equipo
(no importa quien jugo, representa al equipo), y un lado mixto o abierto se
guarda con los apuntados uno a uno. Las fotos son opcionales y solo sirven
como prueba.

Comandos: /scrims create, /scrims list, /scrims info, /scrims join,
/scrims leave, /scrims close, /scrims cancel, /scrims photo y /scrims team ...
Los mensajes de gestion son privados (efimeros en slash, borrados en prefijo);
solo el post de la scrim se publica en el canal.

By Killerbite95
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import re
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n, set_contextual_locales_from_guild

from .dashboard_integration import DashboardIntegration

_ = Translator("ScrimsLoL", __file__)
log = logging.getLogger("red.killerbite-cogs.scrims_lol")

MAX_TEAM_NAME = 32
MAX_TEAM_TAG = 8
MAX_MEMBERS = 15
STARTER_SLOTS = 5
MEMBERSHIP_ROLES = ("player", "sub")
ROLE_LABELS = {"player": "Player", "sub": "Sub"}

SIDE_KINDS = ("team", "mix", "open")
GRACE_SECONDS = 3 * 3600
PRIVATE_DELETE_AFTER = 20.0

COLOR_TEAM = discord.Color.from_rgb(0xC8, 0xAA, 0x6E)
COLOR_DANGER = discord.Color.from_rgb(0xE8, 0x4A, 0x4A)
COLOR_MATCHED = discord.Color.from_rgb(0x4A, 0xE8, 0x8A)
COLOR_MUTED = discord.Color.from_rgb(0x9A, 0x9A, 0x9A)
STATUS_COLORS = {
    "open": COLOR_TEAM,
    "matched": COLOR_MATCHED,
    "closed": COLOR_MUTED,
    "cancelled": COLOR_DANGER,
    "expired": COLOR_MUTED,
}

_WHEN_TIME = re.compile(r"^(\d{1,2}):(\d{2})$")
_WHEN_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})$")
_WHEN_DATE = re.compile(r"^(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\s+(\d{1,2}):(\d{2})$")
_WHEN_HOURS = re.compile(r"^(\d+)h(\d{1,2})?$")
_WHEN_MINUTES = re.compile(r"^(\d+)m?$")
_SCORE = re.compile(r"^\s*(\d{1,2})\s*[-:x]\s*(\d{1,2})\s*$")


def _bar(filled: int, total: int = STARTER_SLOTS) -> str:
    filled = max(0, min(filled, total))
    return "▰" * filled + "▱" * (total - filled)


def _role_label(role: str) -> str:
    return _(ROLE_LABELS.get(role, "Player"))


def _clean(value: str) -> str:
    return " ".join(str(value).split())


def _parse_when(value: str, tz: str = "UTC") -> int:
    """Convierte +90, +2h30, 21:00, 15/11 21:00 o 2026-11-15 21:00 a epoch UTC."""
    raw = value.strip().lower()
    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        zone = ZoneInfo(tz)
    except Exception:
        zone = datetime.timezone.utc

    if raw.startswith("+"):
        body = raw[1:].replace(" ", "")
        if "h" in body:
            match = _WHEN_HOURS.fullmatch(body)
            if not match:
                raise ValueError("when")
            minutes = int(match.group(1)) * 60 + int(match.group(2) or 0)
        else:
            match = _WHEN_MINUTES.fullmatch(body)
            if not match:
                raise ValueError("when")
            minutes = int(match.group(1))
        if minutes <= 0 or minutes > 60 * 24 * 30:
            raise ValueError("when")
        return int((now + datetime.timedelta(minutes=minutes)).timestamp())

    match = _WHEN_TIME.fullmatch(raw)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
        if hour > 23 or minute > 59:
            raise ValueError("when")
        now_local = now.astimezone(zone)
        start = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if start <= now_local:
            start += datetime.timedelta(days=1)
        return int(start.timestamp())

    match = _WHEN_ISO.fullmatch(raw)
    if match:
        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
        hour, minute = int(match.group(4)), int(match.group(5))
        try:
            start = datetime.datetime(year, month, day, hour, minute, tzinfo=zone)
        except ValueError:
            raise ValueError("when")
        return int(start.timestamp())

    match = _WHEN_DATE.fullmatch(raw)
    if match:
        day, month = int(match.group(1)), int(match.group(2))
        year = int(match.group(3)) if match.group(3) else now.astimezone(zone).year
        if year < 100:
            year += 2000
        hour, minute = int(match.group(4)), int(match.group(5))
        try:
            start = datetime.datetime(year, month, day, hour, minute, tzinfo=zone)
        except ValueError:
            raise ValueError("when")
        if not match.group(3) and start.timestamp() <= now.timestamp():
            try:
                start = start.replace(year=year + 1)
            except ValueError:
                raise ValueError("when")
        return int(start.timestamp())

    raise ValueError("when")


def _parse_score(value: str) -> Tuple[int, int]:
    match = _SCORE.fullmatch(str(value))
    if not match:
        raise ValueError("score")
    us, them = int(match.group(1)), int(match.group(2))
    if us > 9 or them > 9:
        raise ValueError("score")
    return us, them


def _fmt_when(timestamp: int) -> str:
    return "<t:{ts}:F>".format(ts=int(timestamp))


def _fmt_relative(timestamp: int) -> str:
    return "<t:{ts}:R>".format(ts=int(timestamp))


def _side_kind_label(kind: str) -> str:
    labels = {"team": _("Team"), "mix": _("Mix"), "open": _("Open")}
    return labels.get(kind, _("Mix"))


def _status_label(status: str) -> str:
    labels = {
        "open": _("Open"),
        "matched": _("Matched"),
        "closed": _("Closed"),
        "cancelled": _("Cancelled"),
        "expired": _("Expired"),
    }
    return labels.get(status, status)


def _member_lines(guild: discord.Guild, user_ids: List[str], captain_id: Optional[str] = None) -> str:
    lines: List[str] = []
    for uid in user_ids:
        try:
            member = guild.get_member(int(uid))
        except (TypeError, ValueError):
            member = None
        who = member.mention if member else f"<@{uid}>"
        if captain_id is not None and str(uid) == str(captain_id):
            who = f"{who} 👑"
        lines.append(who)
    return "\n".join(lines) or "—"


def _mentions(user_ids: List[int]) -> str:
    return "\n".join(f"<@{uid}>" for uid in user_ids) or "—"


def _command_path(ctx: commands.Context, *parts: str) -> str:
    base = f"{ctx.clean_prefix}scrims team"
    return " ".join([base, *parts])


def _scrims_path(ctx: commands.Context, *parts: str) -> str:
    return " ".join([f"{ctx.clean_prefix}scrims", *parts])


class ScoreModal(discord.ui.Modal):
    """Captura el marcador al cerrar un scrim."""

    def __init__(self, cog: "ScrimsLoL", scrim_id: int) -> None:
        super().__init__(title=_("Close scrim #{id}").format(id=scrim_id))
        self.cog = cog
        self.scrim_id = scrim_id
        self.us = discord.ui.TextInput(label=_("Our maps"), placeholder="2", max_length=1)
        self.them = discord.ui.TextInput(label=_("Their maps"), placeholder="1", max_length=1)
        self.add_item(self.us)
        self.add_item(self.them)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(_("This only works in a server."), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        ok, message = await self.cog.apply_close(
            interaction.guild, self.scrim_id, f"{self.us.value}-{self.them.value}", interaction.user
        )
        await interaction.followup.send(message, ephemeral=True)


class ConfirmView(discord.ui.View):
    """Confirmacion de una accion destructiva."""

    def __init__(self, author_id: int, timeout: float = 60.0) -> None:
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.value: Optional[bool] = None
        self.confirm_button.label = _("Delete")
        self.cancel_button.label = _("Cancel")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(_("This confirmation is not for you."), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.value = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.value = False
        self.stop()
        await interaction.response.defer()


class ScrimView(discord.ui.View):
    """Botones persistentes de un post de scrim."""

    def __init__(self, cog: "ScrimsLoL") -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.join_button.label = _("Join")
        self.leave_button.label = _("Leave")
        self.accept_button.label = _("Accept as team")
        self.close_button.label = _("Close")
        self.cancel_button.label = _("Cancel")

    async def _scrim(self, interaction: discord.Interaction) -> Optional[dict]:
        if interaction.guild is None:
            await interaction.response.send_message(_("This only works in a server."), ephemeral=True)
            return None
        scrim = await self.cog.scrim_by_message(interaction.guild, interaction.message.id)
        if scrim is None:
            await interaction.response.send_message(_("This scrim no longer exists."), ephemeral=True)
            return None
        return scrim

    @discord.ui.button(label="Join", emoji="🙋", style=discord.ButtonStyle.success, custom_id="scrims:join")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        scrim = await self._scrim(interaction)
        if scrim is None:
            return
        await interaction.response.defer(ephemeral=True)
        ok, message = await self.cog.apply_join(interaction.guild, scrim["id"], interaction.user)
        await interaction.followup.send(message, ephemeral=True)

    @discord.ui.button(label="Leave", emoji="🚪", style=discord.ButtonStyle.secondary, custom_id="scrims:leave")
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        scrim = await self._scrim(interaction)
        if scrim is None:
            return
        await interaction.response.defer(ephemeral=True)
        ok, message = await self.cog.apply_leave(interaction.guild, scrim["id"], interaction.user)
        await interaction.followup.send(message, ephemeral=True)

    @discord.ui.button(label="Accept as team", emoji="🛡️", style=discord.ButtonStyle.primary, custom_id="scrims:accept")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        scrim = await self._scrim(interaction)
        if scrim is None:
            return
        await interaction.response.defer(ephemeral=True)
        ok, message = await self.cog.apply_accept(interaction.guild, scrim["id"], interaction.user)
        await interaction.followup.send(message, ephemeral=True)

    @discord.ui.button(label="Close", emoji="🏁", style=discord.ButtonStyle.primary, custom_id="scrims:close")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        scrim = await self._scrim(interaction)
        if scrim is None:
            return
        if not await self.cog.can_manage(interaction.guild, interaction.user, scrim):
            await interaction.response.send_message(
                _("Only the participants or the staff can close this scrim."), ephemeral=True
            )
            return
        await interaction.response.send_modal(ScoreModal(self.cog, scrim["id"]))

    @discord.ui.button(label="Cancel", emoji="✖️", style=discord.ButtonStyle.danger, custom_id="scrims:cancel")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        scrim = await self._scrim(interaction)
        if scrim is None:
            return
        await interaction.response.defer(ephemeral=True)
        ok, message = await self.cog.apply_cancel(interaction.guild, scrim["id"], interaction.user)
        await interaction.followup.send(message, ephemeral=True)


@cog_i18n(_)
class ScrimsLoL(DashboardIntegration, commands.Cog):
    """Scrim board for League of Legends: teams, sign-ups and match records."""

    __author__ = "Killerbite95"
    __version__ = "0.3.0"

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0x5C21A0B1, force_registration=True)
        self.config.register_guild(
            teams={},
            next_team_id=1,
            scrims={},
            next_scrim_id=1,
            timezone="Europe/Madrid",
        )
        self._locks: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def cog_load(self) -> None:
        await super().cog_load()
        self.bot.add_view(ScrimView(self))
        if not self.expire_loop.is_running():
            self.expire_loop.start()

    def cog_unload(self) -> None:
        self.expire_loop.cancel()

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre = super().format_help_for_context(ctx)
        return _("{pre}\n\nVersion: {version}").format(pre=pre, version=self.__version__)

    async def red_delete_data_for_user(self, *, requester: str, user_id: int) -> None:
        uid = str(user_id)
        for guild_id in await self.config.all_guilds():
            guild_conf = self.config.guild_from_id(guild_id)
            async with guild_conf.teams() as teams:
                for team_id in list(teams):
                    team = teams[team_id]
                    members = team.get("members", {})
                    if uid not in members:
                        continue
                    if team.get("captain_id") == user_id:
                        remaining = [member for member in members if member != uid]
                        if not remaining:
                            del teams[team_id]
                            continue
                        team["captain_id"] = int(remaining[0])
                        members[remaining[0]] = "captain"
                    members.pop(uid, None)
            async with guild_conf.scrims() as scrims:
                for scrim_id in list(scrims):
                    scrim = scrims[scrim_id]
                    if scrim.get("author_id") == user_id:
                        scrim["author_id"] = 0
                    for side_key in ("side", "rival"):
                        side = scrim.get(side_key)
                        if not side:
                            continue
                        side["signups"] = [value for value in side.get("signups", []) if int(value) != user_id]

    # ------------------------------------------------------------------ helpers

    async def _reply(
        self,
        ctx: commands.Context,
        content: Optional[str] = None,
        *,
        embed: Optional[discord.Embed] = None,
        view: Optional[discord.ui.View] = None,
        keep: bool = False,
    ) -> Optional[discord.Message]:
        """Responde en privado: efimero en slash, autoborrado en prefijo."""
        if ctx.interaction is not None:
            return await ctx.send(content, embed=embed, view=view, ephemeral=True)
        return await ctx.send(
            content,
            embed=embed,
            view=view,
            delete_after=None if keep else PRIVATE_DELETE_AFTER,
        )

    async def _require_guild(self, ctx: commands.Context) -> Optional[discord.Guild]:
        if ctx.guild is None:
            await self._reply(ctx, _("This command only works in a server."))
            return None
        return ctx.guild

    @staticmethod
    def _find_by_user(teams: Dict[str, dict], user_id: int) -> Optional[Tuple[str, dict]]:
        uid = str(user_id)
        for team_id, team in teams.items():
            if uid in team.get("members", {}):
                return team_id, team
        return None

    @staticmethod
    def _find_by_name(teams: Dict[str, dict], name: str) -> Optional[Tuple[str, dict]]:
        wanted = name.casefold()
        for team_id, team in teams.items():
            if str(team.get("name", "")).casefold() == wanted:
                return team_id, team
        return None

    @staticmethod
    def _find_by_tag(teams: Dict[str, dict], tag: str) -> Optional[Tuple[str, dict]]:
        wanted = tag.casefold()
        for team_id, team in teams.items():
            if str(team.get("tag", "")).casefold() == wanted:
                return team_id, team
        return None

    def _team_card(self, ctx: commands.Context, guild: discord.Guild, team: dict) -> discord.Embed:
        name = team.get("name", "?")
        tag = team.get("tag") or ""
        title = _("🛡️ {name} · [{tag}]").format(name=name, tag=tag) if tag else _("🛡️ {name}").format(name=name)
        embed = discord.Embed(title=title, colour=COLOR_TEAM)

        members = team.get("members", {})
        starters = [uid for uid, role in members.items() if role != "sub"]
        subs = [uid for uid, role in members.items() if role == "sub"]

        captain_id = str(team.get("captain_id", ""))
        embed.add_field(
            name=_("🎯 Starters ({count}/{total})").format(count=len(starters), total=STARTER_SLOTS),
            value=f"{_bar(len(starters))}\n{_member_lines(guild, starters, captain_id)}",
            inline=False,
        )
        embed.add_field(
            name=_("🪑 Subs ({count})").format(count=len(subs)),
            value=_member_lines(guild, subs),
            inline=False,
        )
        if tag:
            embed.add_field(name=_("🏷️ Tag"), value=f"`{tag}`", inline=True)

        embed.set_footer(text=_("Scrims LoL · Team #{id}").format(id=team.get("id", "?")))
        created = team.get("created_at")
        if created:
            embed.timestamp = datetime.datetime.fromtimestamp(int(created), tz=datetime.timezone.utc)
        if ctx.bot.user is not None:
            embed.set_author(name=_("Scrims LoL"), icon_url=ctx.bot.user.display_avatar.url)
        return embed

    async def _captain_team(self, ctx: commands.Context, guild: discord.Guild) -> Optional[Tuple[str, dict]]:
        teams = await self.config.guild(guild).teams()
        found = self._find_by_user(teams, ctx.author.id)
        if found is None:
            await self._reply(
                ctx, _("You do not belong to any team. Create one with `{cmd}`.").format(cmd=_command_path(ctx, "create"))
            )
            return None
        if found[1].get("captain_id") != ctx.author.id:
            await self._reply(ctx, _("Only the captain can do this."))
            return None
        return found

    async def scrim_by_message(self, guild: discord.Guild, message_id: int) -> Optional[dict]:
        scrims = await self.config.guild(guild).scrims()
        for scrim in scrims.values():
            if scrim.get("message_id") == message_id:
                return scrim
        return None

    async def _get_scrim(self, guild: discord.Guild, scrim_id: int) -> Optional[dict]:
        scrims = await self.config.guild(guild).scrims()
        return scrims.get(str(scrim_id))

    async def _side_user_ids(self, guild: discord.Guild, side: Optional[dict]) -> List[int]:
        if not side:
            return []
        if side.get("kind") == "team" and side.get("team_id"):
            teams = await self.config.guild(guild).teams()
            team = teams.get(str(side["team_id"]))
            if team:
                return [int(uid) for uid in team.get("members", {})]
        return [int(uid) for uid in side.get("signups", [])]

    async def can_manage(self, guild: discord.Guild, user: discord.abc.User, scrim: dict) -> bool:
        if user.id == scrim.get("author_id"):
            return True
        member = guild.get_member(user.id)
        if member is not None:
            if member.guild_permissions.manage_guild or await self.bot.is_mod(member):
                return True
        teams = await self.config.guild(guild).teams()
        for side_key in ("side", "rival"):
            side = scrim.get(side_key) or {}
            if user.id in [int(value) for value in side.get("signups", [])]:
                return True
            team_id = side.get("team_id")
            if team_id and str(team_id) in teams and str(user.id) in teams[str(team_id)].get("members", {}):
                return True
        return False

    # ------------------------------------------------------------------- board

    def _side_value(self, guild: discord.Guild, side: Optional[dict]) -> str:
        if not side:
            return "—"
        if side.get("kind") == "team":
            return _("🛡️ **{name}**").format(name=side.get("label", "?"))
        return _mentions([int(uid) for uid in side.get("signups", [])])

    def _scrim_embed(self, guild: discord.Guild, scrim: dict) -> discord.Embed:
        status = scrim.get("status", "open")
        title = _("🎯 Scrim #{id} · {side}").format(id=scrim.get("id", "?"), side=scrim.get("side", {}).get("label", "?"))
        embed = discord.Embed(title=title, colour=STATUS_COLORS.get(status, COLOR_TEAM))

        embed.add_field(name=_("Status"), value=_status_label(status), inline=True)
        embed.add_field(name=_("Looking for"), value=_side_kind_label(scrim.get("looks_for", "team")), inline=True)
        embed.add_field(name=_("Format"), value=self._format_text(scrim), inline=True)

        embed.add_field(name=_("My side"), value=self._side_value(guild, scrim.get("side")), inline=False)
        embed.add_field(
            name=_("Opponent"),
            value=self._side_value(guild, scrim.get("rival")) if scrim.get("rival") else _("Not claimed yet."),
            inline=False,
        )

        start = int(scrim.get("start", 0))
        embed.add_field(
            name=_("Start"),
            value=_("{time} ({relative})").format(time=_fmt_when(start), relative=_fmt_relative(start)),
            inline=False,
        )

        rank = self._rank_text(scrim)
        if rank:
            embed.add_field(name=_("Rank"), value=rank, inline=True)
        if scrim.get("contact"):
            embed.add_field(name=_("Contact"), value=str(scrim["contact"]), inline=True)

        if scrim.get("score"):
            score = scrim["score"]
            embed.add_field(
                name=_("Score"),
                value=_("{us} - {them}").format(us=score.get("us", 0), them=score.get("them", 0)),
                inline=False,
            )
        if scrim.get("photos"):
            embed.add_field(name=_("Photos"), value=str(len(scrim["photos"])), inline=True)

        embed.set_footer(text=_("Scrims LoL · #{id}").format(id=scrim.get("id", "?")))
        author = guild.get_member(int(scrim.get("author_id") or 0))
        if author is not None:
            embed.set_author(name=author.display_name, icon_url=author.display_avatar.url)
        created = scrim.get("created_at")
        if created:
            embed.timestamp = datetime.datetime.fromtimestamp(int(created), tz=datetime.timezone.utc)
        return embed

    @staticmethod
    def _format_text(scrim: dict) -> str:
        text = "BO{bo}".format(bo=scrim.get("bo", 1))
        if scrim.get("fearless"):
            text = "{text} · Fearless".format(text=text)
        return text

    @staticmethod
    def _rank_text(scrim: dict) -> str:
        low = scrim.get("tier_min") or ""
        high = scrim.get("tier_max") or ""
        if low and high:
            return "{low} – {high}".format(low=low, high=high)
        return low or high or ""

    @staticmethod
    def _my_side_full(scrim: dict) -> bool:
        side = scrim.get("side") or {}
        if side.get("kind") == "team":
            return True
        return len(side.get("signups", [])) >= STARTER_SLOTS

    @staticmethod
    def _rival_full(scrim: dict) -> bool:
        if scrim.get("looks_for") == "team":
            return (scrim.get("rival") or {}).get("kind") == "team"
        return len((scrim.get("rival") or {}).get("signups", [])) >= STARTER_SLOTS

    def _board_view(self, scrim: dict) -> Optional[discord.ui.View]:
        status = scrim.get("status")
        if status in ("closed", "cancelled", "expired"):
            return None
        view = ScrimView(self)
        if status != "open":
            # Emparejada: solo quedan Cerrar y Cancelar.
            view.remove_item(view.join_button)
            view.remove_item(view.leave_button)
            view.remove_item(view.accept_button)
            return view
        if scrim.get("looks_for") == "team":
            view.remove_item(view.join_button)
            view.remove_item(view.leave_button)
        else:
            view.remove_item(view.accept_button)
        return view

    async def _refresh_board(self, guild: discord.Guild, scrim: dict) -> None:
        channel = guild.get_channel(int(scrim.get("channel_id") or 0))
        if channel is None or not scrim.get("message_id"):
            return
        try:
            message = await channel.fetch_message(int(scrim["message_id"]))
        except (discord.NotFound, discord.HTTPException, ValueError):
            return
        view = self._board_view(scrim)
        try:
            await message.edit(embed=self._scrim_embed(guild, scrim), view=view)
        except discord.HTTPException:
            pass

    async def _open_thread(self, guild: discord.Guild, scrim: dict) -> Optional[int]:
        channel = guild.get_channel(int(scrim.get("channel_id") or 0))
        if channel is None:
            return None
        rival = scrim.get("rival") or {}
        name = "Scrim #{id}: {mine} vs {theirs}".format(
            id=scrim.get("id", "?"),
            mine=scrim.get("side", {}).get("label", "?"),
            theirs=rival.get("label", "?"),
        )
        try:
            thread = await channel.create_thread(
                name=name[:90],
                type=discord.ChannelType.private_thread,
                invitable=False,
                auto_archive_duration=1440,
            )
        except (discord.Forbidden, discord.HTTPException):
            try:
                thread = await channel.create_thread(
                    name=name[:90],
                    type=discord.ChannelType.public_thread,
                    auto_archive_duration=1440,
                )
            except (discord.Forbidden, discord.HTTPException):
                log.warning("No se pudo crear el hilo del scrim %s", scrim.get("id"))
                return None

        users: List[int] = []
        users.extend(await self._side_user_ids(guild, scrim.get("side")))
        users.extend(await self._side_user_ids(guild, rival))
        for uid in dict.fromkeys(users):
            member = guild.get_member(uid)
            if member is None:
                continue
            try:
                await thread.add_user(member)
            except discord.DiscordException:
                pass

        try:
            await thread.send(embed=self._thread_embed(guild, scrim))
        except discord.HTTPException:
            pass
        return thread.id

    def _thread_embed(self, guild: discord.Guild, scrim: dict) -> discord.Embed:
        embed = discord.Embed(
            title=_("Scrim #{id} matched").format(id=scrim.get("id", "?")),
            colour=COLOR_MATCHED,
            description=_("This private thread is for both sides to agree on the details."),
        )
        embed.add_field(name=_("My side"), value=self._side_value(guild, scrim.get("side")), inline=False)
        embed.add_field(name=_("Opponent"), value=self._side_value(guild, scrim.get("rival")), inline=False)
        start = int(scrim.get("start", 0))
        embed.add_field(name=_("Start"), value=_fmt_when(start), inline=False)
        embed.add_field(name=_("Format"), value=self._format_text(scrim), inline=True)
        if scrim.get("contact"):
            embed.add_field(name=_("Contact"), value=str(scrim["contact"]), inline=True)
        return embed

    # ---------------------------------------------------------------- mutations

    async def apply_join(self, guild: discord.Guild, scrim_id: int, user: discord.abc.User) -> Tuple[bool, str]:
        async with self._locks[guild.id]:
            scrims = await self.config.guild(guild).scrims()
            scrim = scrims.get(str(scrim_id))
            if scrim is None:
                return False, _("That scrim does not exist.")
            if scrim.get("status") != "open":
                return False, _("That scrim is not open.")
            if user.id == scrim.get("author_id"):
                return False, _("You are already signed up.")

            side = scrim.get("side") or {}
            rival = scrim.get("rival") or {}
            my_open = side.get("kind") in ("mix", "open")
            rival_open = scrim.get("looks_for") in ("mix", "open")
            my_signups = [int(value) for value in side.get("signups", [])]
            rival_signups = [int(value) for value in rival.get("signups", [])]

            if user.id in my_signups or user.id in rival_signups:
                return False, _("You are already signed up.")

            if my_open and len(my_signups) < STARTER_SLOTS:
                my_signups.append(user.id)
                side["signups"] = my_signups
                scrim["side"] = side
            elif rival_open and len(rival_signups) < STARTER_SLOTS:
                rival_signups.append(user.id)
                rival["signups"] = rival_signups
                rival["kind"] = scrim.get("looks_for")
                rival["label"] = _side_kind_label(scrim.get("looks_for", "mix"))
                scrim["rival"] = rival
            elif not my_open and not rival_open:
                return False, _("This scrim is looking for a team: a captain has to accept it.")
            else:
                return False, _("The scrim is full.")

            if self._my_side_full(scrim) and self._rival_full(scrim):
                scrim["status"] = "matched"
            await self.config.guild(guild).scrims.set(scrims)

        if scrim.get("status") == "matched":
            thread_id = await self._open_thread(guild, scrim)
            if thread_id:
                async with self._locks[guild.id]:
                    scrims = await self.config.guild(guild).scrims()
                    if str(scrim_id) in scrims:
                        scrims[str(scrim_id)]["thread_id"] = thread_id
                        await self.config.guild(guild).scrims.set(scrims)
                scrim["thread_id"] = thread_id
        await self._refresh_board(guild, scrim)
        if scrim.get("status") == "matched":
            return True, _("✅ You joined and the scrim is complete.")
        return True, _("✅ You joined the scrim.")

    async def apply_leave(self, guild: discord.Guild, scrim_id: int, user: discord.abc.User) -> Tuple[bool, str]:
        async with self._locks[guild.id]:
            scrims = await self.config.guild(guild).scrims()
            scrim = scrims.get(str(scrim_id))
            if scrim is None:
                return False, _("That scrim does not exist.")
            if scrim.get("status") != "open":
                return False, _("That scrim is not open.")
            if user.id == scrim.get("author_id"):
                return False, _("You cannot leave your own scrim.")

            side = scrim.get("side") or {}
            rival = scrim.get("rival") or {}
            my_signups = [int(value) for value in side.get("signups", [])]
            rival_signups = [int(value) for value in rival.get("signups", [])]

            if user.id in my_signups:
                my_signups.remove(user.id)
                side["signups"] = my_signups
                scrim["side"] = side
            elif user.id in rival_signups:
                rival_signups.remove(user.id)
                rival["signups"] = rival_signups
                scrim["rival"] = rival
            else:
                return False, _("You are not signed up.")
            await self.config.guild(guild).scrims.set(scrims)
        await self._refresh_board(guild, scrim)
        return True, _("✅ You left the scrim.")

    async def apply_accept(self, guild: discord.Guild, scrim_id: int, user: discord.abc.User) -> Tuple[bool, str]:
        async with self._locks[guild.id]:
            scrims = await self.config.guild(guild).scrims()
            scrim = scrims.get(str(scrim_id))
            if scrim is None:
                return False, _("That scrim does not exist.")
            if scrim.get("status") != "open":
                return False, _("That scrim is not open.")
            if scrim.get("looks_for") != "team":
                return False, _("This scrim is not looking for a team.")
            if scrim.get("rival"):
                return False, _("This scrim already has a rival.")
            teams = await self.config.guild(guild).teams()
            found = self._find_by_user(teams, user.id)
            if found is None:
                return False, _("You do not belong to any team.")
            team_id, team = found
            if team.get("captain_id") != user.id:
                return False, _("Only the captain can accept a scrim.")
            if scrim.get("side", {}).get("team_id") == int(team_id):
                return False, _("You cannot accept your own scrim.")
            scrim["rival"] = {
                "kind": "team",
                "team_id": int(team_id),
                "label": team.get("name", "?"),
                "signups": [],
            }
            if self._my_side_full(scrim) and self._rival_full(scrim):
                scrim["status"] = "matched"
            await self.config.guild(guild).scrims.set(scrims)

        if scrim.get("status") == "matched":
            thread_id = await self._open_thread(guild, scrim)
            if thread_id:
                async with self._locks[guild.id]:
                    scrims = await self.config.guild(guild).scrims()
                    if str(scrim_id) in scrims:
                        scrims[str(scrim_id)]["thread_id"] = thread_id
                        await self.config.guild(guild).scrims.set(scrims)
                scrim["thread_id"] = thread_id
        await self._refresh_board(guild, scrim)
        if scrim.get("status") == "matched":
            return True, _("✅ Scrim matched. A private thread was created.")
        return True, _("✅ Team accepted. Waiting for your side to be complete.")

    async def apply_cancel(self, guild: discord.Guild, scrim_id: int, user: discord.abc.User) -> Tuple[bool, str]:
        scrim = await self._get_scrim(guild, scrim_id)
        if scrim is None:
            return False, _("That scrim does not exist.")
        if not await self.can_manage(guild, user, scrim):
            return False, _("Only the author or the staff can cancel this scrim.")
        async with self._locks[guild.id]:
            scrims = await self.config.guild(guild).scrims()
            current = scrims.get(str(scrim_id))
            if current is None:
                return False, _("That scrim does not exist.")
            if current.get("status") in ("closed", "cancelled", "expired"):
                return False, _("That scrim is already finished.")
            current["status"] = "cancelled"
            await self.config.guild(guild).scrims.set(scrims)
        await self._refresh_board(guild, current)
        return True, _("✅ Scrim cancelled.")

    async def apply_close(
        self, guild: discord.Guild, scrim_id: int, score: str, user: discord.abc.User
    ) -> Tuple[bool, str]:
        try:
            us, them = _parse_score(score)
        except ValueError:
            return False, _("The score must look like `2-1`.")
        scrim = await self._get_scrim(guild, scrim_id)
        if scrim is None:
            return False, _("That scrim does not exist.")
        if not await self.can_manage(guild, user, scrim):
            return False, _("Only the participants or the staff can close this scrim.")
        async with self._locks[guild.id]:
            scrims = await self.config.guild(guild).scrims()
            current = scrims.get(str(scrim_id))
            if current is None:
                return False, _("That scrim does not exist.")
            if current.get("status") in ("closed", "cancelled", "expired"):
                return False, _("That scrim is already finished.")
            if current.get("status") != "matched":
                return False, _("The scrim has no opponent yet.")
            current["score"] = {"us": us, "them": them}
            current["status"] = "closed"
            await self.config.guild(guild).scrims.set(scrims)
        await self._refresh_board(guild, current)
        await self._archive_thread(guild, current)
        return True, _("✅ Scrim closed with {us}-{them}.").format(us=us, them=them)

    async def _archive_thread(self, guild: discord.Guild, scrim: dict) -> None:
        thread_id = scrim.get("thread_id")
        if not thread_id:
            return
        thread = guild.get_thread(int(thread_id))
        if thread is None:
            return
        try:
            await thread.edit(archived=True)
        except discord.HTTPException:
            pass

    # ------------------------------------------------------------------- loops

    @tasks.loop(minutes=1)
    async def expire_loop(self) -> None:
        now = int(time.time())
        for guild in self.bot.guilds:
            try:
                if await self.bot.cog_disabled_in_guild(self, guild):
                    continue
                await set_contextual_locales_from_guild(self.bot, guild)
                scrims = await self.config.guild(guild).scrims()
                changed = False
                for scrim in scrims.values():
                    status = scrim.get("status")
                    start = int(scrim.get("start", 0))
                    if status == "open" and now >= start:
                        scrim["status"] = "expired"
                        changed = True
                        await self._refresh_board(guild, scrim)
                    elif status == "matched" and now >= start + GRACE_SECONDS:
                        scrim["status"] = "expired"
                        changed = True
                        await self._refresh_board(guild, scrim)
                if changed:
                    await self.config.guild(guild).scrims.set(scrims)
            except Exception:
                log.exception("Fallo en el TTL de scrims del servidor %s", guild.id)

    # --------------------------------------------------------------- commands

    @commands.hybrid_group(name="scrims")
    async def scrims(self, ctx: commands.Context) -> None:
        """Scrims of League of Legends."""
        if ctx.invoked_subcommand is None:
            await self._reply(ctx, self._scrims_help_text(ctx))

    def _scrims_help_text(self, ctx: commands.Context) -> str:
        return _(
            "**Scrims**\n"
            "`{create}` — publish a scrim.\n"
            "`{list}` — see the open scrims.\n"
            "`{info}` — details of one scrim.\n"
            "`{join}` / `{leave}` — sign up or leave the opponent side.\n"
            "`{close}` — close it with a score.\n"
            "`{cancel}` — cancel it.\n"
            "`{photo}` — attach a screenshot of a game.\n"
            "`{team}` — manage teams."
        ).format(
            create=_scrims_path(ctx, "create"),
            list=_scrims_path(ctx, "list"),
            info=_scrims_path(ctx, "info"),
            join=_scrims_path(ctx, "join"),
            leave=_scrims_path(ctx, "leave"),
            close=_scrims_path(ctx, "close"),
            cancel=_scrims_path(ctx, "cancel"),
            photo=_scrims_path(ctx, "photo"),
            team=_scrims_path(ctx, "team"),
        )

    @scrims.command(name="create")
    @app_commands.rename(
        side="lado",
        looks_for="busca",
        when="cuando",
        bo="formato",
        fearless="fearless",
        tier_min="rango_min",
        tier_max="rango_max",
        contact="contacto",
    )
    @app_commands.describe(
        side="Cómo se presenta tu lado.",
        looks_for="Qué tipo de rival buscas.",
        when="Cuándo: +90, +2h, 21:00, 15/11 21:00 o 2026-11-15 21:00.",
        bo="Al mejor de 1, 3 o 5.",
        fearless="Modo fearless.",
        tier_min="Rango mínimo (opcional).",
        tier_max="Rango máximo (opcional).",
        contact="Contacto (por defecto, se avisa al autor).",
    )
    @app_commands.choices(
        side=[
            app_commands.Choice(name="Equipo", value="team"),
            app_commands.Choice(name="Mix", value="mix"),
            app_commands.Choice(name="Abierto", value="open"),
        ],
        looks_for=[
            app_commands.Choice(name="Equipo", value="team"),
            app_commands.Choice(name="Mix", value="mix"),
            app_commands.Choice(name="Abierto", value="open"),
        ],
        bo=[
            app_commands.Choice(name="BO1", value=1),
            app_commands.Choice(name="BO3", value=3),
            app_commands.Choice(name="BO5", value=5),
        ],
    )
    async def scrims_create(
        self,
        ctx: commands.Context,
        side: str = "mix",
        looks_for: str = "team",
        when: str = "+60",
        bo: int = 1,
        fearless: bool = False,
        tier_min: Optional[str] = None,
        tier_max: Optional[str] = None,
        contact: Optional[str] = None,
    ) -> None:
        """Publish a scrim on the board."""
        guild = await self._require_guild(ctx)
        if guild is None:
            return
        side = str(side).casefold()
        looks_for = str(looks_for).casefold()
        if side not in SIDE_KINDS or looks_for not in SIDE_KINDS:
            await self._reply(ctx, _("The side and the search must be team, mix or open."))
            return
        tz = await self.config.guild(guild).timezone()
        try:
            start = _parse_when(when, tz)
        except ValueError:
            await self._reply(
                ctx,
                _("I could not read that time. Use `+90`, `+2h`, `21:00`, `15/11 21:00` or `2026-11-15 21:00`."),
            )
            return
        if start <= int(time.time()) + 60:
            await self._reply(ctx, _("The scrim must start in the future."))
            return

        teams = await self.config.guild(guild).teams()
        if side == "team":
            found = self._find_by_user(teams, ctx.author.id)
            if found is None:
                await self._reply(ctx, _("To post as a team you must belong to one."))
                return
            team_id, team = found
            if team.get("captain_id") != ctx.author.id:
                await self._reply(ctx, _("Only the captain can post a scrim for the team."))
                return
            my_side = {"kind": "team", "team_id": int(team_id), "label": team.get("name", "?"), "signups": []}
        else:
            my_side = {
                "kind": side,
                "team_id": None,
                "label": _side_kind_label(side),
                "signups": [ctx.author.id],
            }

        clean_contact = _clean(contact)[:100] if contact else ""

        async with self._locks[guild.id]:
            scrims = await self.config.guild(guild).scrims()
            scrim_id = await self.config.guild(guild).next_scrim_id()
            scrims[str(scrim_id)] = {
                "id": scrim_id,
                "author_id": ctx.author.id,
                "channel_id": ctx.channel.id,
                "message_id": None,
                "side": my_side,
                "looks_for": looks_for,
                "start": start,
                "bo": int(bo),
                "fearless": bool(fearless),
                "tier_min": _clean(tier_min or "")[:32],
                "tier_max": _clean(tier_max or "")[:32],
                "contact": clean_contact,
                "status": "open",
                "rival": None,
                "score": None,
                "photos": [],
                "thread_id": None,
                "created_at": int(time.time()),
            }
            await self.config.guild(guild).scrims.set(scrims)
            await self.config.guild(guild).next_scrim_id.set(scrim_id + 1)
            scrim = scrims[str(scrim_id)]

        message = await ctx.send(embed=self._scrim_embed(guild, scrim), view=self._board_view(scrim))
        async with self._locks[guild.id]:
            scrims = await self.config.guild(guild).scrims()
            if str(scrim_id) in scrims:
                scrims[str(scrim_id)]["message_id"] = message.id
                await self.config.guild(guild).scrims.set(scrims)

    @scrims.command(name="list")
    async def scrims_list(self, ctx: commands.Context) -> None:
        """List the open scrims of this server."""
        guild = await self._require_guild(ctx)
        if guild is None:
            return
        scrims = await self.config.guild(guild).scrims()
        open_scrims = sorted(
            (scrim for scrim in scrims.values() if scrim.get("status") == "open"),
            key=lambda item: int(item.get("start", 0)),
        )
        if not open_scrims:
            await self._reply(ctx, _("There are no open scrims right now."))
            return
        lines: List[str] = []
        for scrim in open_scrims[:20]:
            lines.append(
                _("#{id} · {side} → {looks} · {start}").format(
                    id=scrim.get("id", "?"),
                    side=scrim.get("side", {}).get("label", "?"),
                    looks=_side_kind_label(scrim.get("looks_for", "team")),
                    start=_fmt_relative(int(scrim.get("start", 0))),
                )
            )
        embed = discord.Embed(
            title=_("🎯 Open scrims ({count})").format(count=len(open_scrims)),
            description="\n".join(lines),
            colour=COLOR_TEAM,
        )
        await self._reply(ctx, embed=embed)

    @scrims.command(name="info")
    @app_commands.rename(scrim_id="id")
    @app_commands.describe(scrim_id="ID of the scrim.")
    async def scrims_info(self, ctx: commands.Context, scrim_id: int) -> None:
        """Show one scrim."""
        guild = await self._require_guild(ctx)
        if guild is None:
            return
        scrim = await self._get_scrim(guild, scrim_id)
        if scrim is None:
            await self._reply(ctx, _("That scrim does not exist."))
            return
        await self._reply(ctx, embed=self._scrim_embed(guild, scrim))

    @scrims.command(name="join")
    @app_commands.rename(scrim_id="id")
    @app_commands.describe(scrim_id="ID of the scrim.")
    async def scrims_join(self, ctx: commands.Context, scrim_id: int) -> None:
        """Join the opponent side of a mix or open scrim."""
        guild = await self._require_guild(ctx)
        if guild is None:
            return
        await ctx.defer(ephemeral=True)
        ok, message = await self.apply_join(guild, scrim_id, ctx.author)
        await self._reply(ctx, message)

    @scrims.command(name="leave")
    @app_commands.rename(scrim_id="id")
    @app_commands.describe(scrim_id="ID of the scrim.")
    async def scrims_leave(self, ctx: commands.Context, scrim_id: int) -> None:
        """Leave the opponent side of a scrim."""
        guild = await self._require_guild(ctx)
        if guild is None:
            return
        await ctx.defer(ephemeral=True)
        ok, message = await self.apply_leave(guild, scrim_id, ctx.author)
        await self._reply(ctx, message)

    @scrims.command(name="close")
    @app_commands.rename(scrim_id="id", score="marcador")
    @app_commands.describe(scrim_id="ID of the scrim.", score="Score, for example 2-1.")
    async def scrims_close(self, ctx: commands.Context, scrim_id: int, score: str) -> None:
        """Close a scrim with its score."""
        guild = await self._require_guild(ctx)
        if guild is None:
            return
        await ctx.defer(ephemeral=True)
        ok, message = await self.apply_close(guild, scrim_id, score, ctx.author)
        await self._reply(ctx, message)

    @scrims.command(name="cancel")
    @app_commands.rename(scrim_id="id")
    @app_commands.describe(scrim_id="ID of the scrim.")
    async def scrims_cancel(self, ctx: commands.Context, scrim_id: int) -> None:
        """Cancel a scrim you posted."""
        guild = await self._require_guild(ctx)
        if guild is None:
            return
        await ctx.defer(ephemeral=True)
        ok, message = await self.apply_cancel(guild, scrim_id, ctx.author)
        await self._reply(ctx, message)

    @scrims.command(name="photo")
    @app_commands.rename(scrim_id="id", game="partida", url="enlace")
    @app_commands.describe(
        scrim_id="ID of the scrim.",
        game="Game number.",
        url="Image link. In prefix you can attach the image instead.",
    )
    async def scrims_photo(
        self, ctx: commands.Context, scrim_id: int, game: int, url: Optional[str] = None
    ) -> None:
        """Attach an optional screenshot to a game."""
        guild = await self._require_guild(ctx)
        if guild is None:
            return
        await ctx.defer(ephemeral=True)
        scrim = await self._get_scrim(guild, scrim_id)
        if scrim is None:
            await self._reply(ctx, _("That scrim does not exist."))
            return
        if not await self.can_manage(guild, ctx.author, scrim):
            await self._reply(ctx, _("Only the participants or the staff can add photos."))
            return
        if game < 1 or game > 9:
            await self._reply(ctx, _("The game must be between 1 and 9."))
            return

        attachment = None
        if ctx.message is not None and getattr(ctx.message, "attachments", None):
            attachment = ctx.message.attachments[0]
        if attachment is None:
            link = _clean(url or "")
            if not link.startswith(("http://", "https://")):
                await self._reply(
                    ctx,
                    _("Attach the image in prefix or pass an `https://` link with `{cmd}`.").format(
                        cmd=_scrims_path(ctx, "photo")
                    ),
                )
                return
        else:
            link = ""

        thread = guild.get_thread(int(scrim["thread_id"])) if scrim.get("thread_id") else None
        target = thread or guild.get_channel(int(scrim.get("channel_id") or 0))
        if target is None:
            await self._reply(ctx, _("I cannot find the channel of that scrim."))
            return

        embed = discord.Embed(colour=COLOR_TEAM)
        embed.set_footer(text=_("Scrim #{id} · Game {game}").format(id=scrim_id, game=game))
        try:
            if attachment is not None:
                file = await attachment.to_file()
                embed.set_image(url="attachment://{name}".format(name=file.filename))
                posted = await target.send(embed=embed, file=file)
            else:
                embed.set_image(url=link)
                posted = await target.send(embed=embed)
        except discord.HTTPException:
            await self._reply(ctx, _("I could not post the image."))
            return

        fresh = None
        async with self._locks[guild.id]:
            scrims = await self.config.guild(guild).scrims()
            current = scrims.get(str(scrim_id))
            if current is not None:
                photos = [p for p in current.get("photos", []) if p.get("game") != game]
                photos.append(
                    {
                        "game": game,
                        "channel_id": posted.channel.id,
                        "message_id": posted.id,
                        "url": posted.attachments[0].url if posted.attachments else link,
                    }
                )
                current["photos"] = sorted(photos, key=lambda p: int(p.get("game", 0)))
                await self.config.guild(guild).scrims.set(scrims)
                fresh = current
        if fresh is None:
            fresh = scrim
        await self._refresh_board(guild, fresh)
        await self._reply(ctx, _("✅ Screenshot saved for game {game}.").format(game=game))

    @scrims.command(name="timezone")
    @app_commands.rename(tz="zona")
    @app_commands.describe(tz="Zona horaria IANA, p. ej. Europe/Madrid o America/Buenos_Aires.")
    async def scrims_timezone(self, ctx: commands.Context, tz: Optional[str] = None) -> None:
        """Set the timezone for interpreting scrim times."""
        guild = await self._require_guild(ctx)
        if guild is None:
            return
        member = ctx.author
        if not (
            member.guild_permissions.manage_guild
            or await self.bot.is_mod(member)
            or await self.bot.is_admin(member)
        ):
            await self._reply(ctx, _("Only admins can change the timezone."))
            return
        if tz is None:
            current = await self.config.guild(guild).timezone()
            await self._reply(ctx, _("The timezone is `{tz}`.").format(tz=current))
            return
        try:
            ZoneInfo(tz)
        except Exception:
            await self._reply(ctx, _("That timezone is not valid. Use an IANA name like `Europe/Madrid`."))
            return
        await self.config.guild(guild).timezone.set(tz)
        await self._reply(ctx, _("✅ Timezone set to `{tz}`.").format(tz=tz))

    # -------------------------------------------------------------------- team

    @scrims.group(name="team")
    async def scrims_team(self, ctx: commands.Context) -> None:
        """Manage scrim teams."""
        if ctx.invoked_subcommand is None:
            await self._reply(
                ctx,
                " · ".join(
                    _scrims_path(ctx, "team", part)
                    for part in ("create", "info", "list", "add", "remove", "leave", "transfer", "delete")
                ),
            )

    @scrims_team.command(name="create")
    @app_commands.rename(name="nombre", tag="etiqueta")
    @app_commands.describe(
        name="Nombre del equipo (entre 2 y 32 caracteres).",
        tag="Etiqueta corta opcional para mostrar junto al nombre (máximo 8).",
    )
    async def scrims_team_create(self, ctx: commands.Context, name: str, tag: Optional[str] = None) -> None:
        """Create a team. You become its captain."""
        guild = await self._require_guild(ctx)
        if guild is None:
            return
        clean_name = _clean(name)
        if not 2 <= len(clean_name) <= MAX_TEAM_NAME:
            await self._reply(ctx, _("The team name must be between 2 and 32 characters."))
            return
        clean_tag = _clean(tag or "").replace(" ", "")[:MAX_TEAM_TAG].upper()

        async with self._locks[guild.id]:
            teams = await self.config.guild(guild).teams()
            existing = self._find_by_user(teams, ctx.author.id)
            if existing is not None:
                await self._reply(
                    ctx,
                    _("You are already in the team **{team}**. Leave it before creating another one.").format(
                        team=existing[1]["name"]
                    ),
                )
                return
            if self._find_by_name(teams, clean_name) is not None:
                await self._reply(ctx, _("There is already a team named **{name}**.").format(name=clean_name))
                return
            if clean_tag and self._find_by_tag(teams, clean_tag) is not None:
                await self._reply(ctx, _("There is already a team with the tag **{tag}**.").format(tag=clean_tag))
                return

            team_id = await self.config.guild(guild).next_team_id()
            teams[str(team_id)] = {
                "id": team_id,
                "name": clean_name,
                "tag": clean_tag,
                "captain_id": ctx.author.id,
                "members": {str(ctx.author.id): "captain"},
                "created_at": int(time.time()),
                "arencup_team_id": None,
            }
            await self.config.guild(guild).teams.set(teams)
            await self.config.guild(guild).next_team_id.set(team_id + 1)
            card = self._team_card(ctx, guild, teams[str(team_id)])

        await self._reply(
            ctx, _("✅ Team **{name}** created. You are the captain.").format(name=clean_name), embed=card
        )

    @scrims_team.command(name="info")
    @app_commands.rename(member="miembro")
    @app_commands.describe(member="Miembro del equipo a consultar. Si se omite, se muestra el tuyo.")
    async def scrims_team_info(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
        """Show a team and its roster."""
        guild = await self._require_guild(ctx)
        if guild is None:
            return
        target = member or ctx.author
        teams = await self.config.guild(guild).teams()
        found = self._find_by_user(teams, target.id)
        if found is None:
            if member is None:
                await self._reply(
                    ctx,
                    _("You do not belong to any team. Create one with `{cmd}`.").format(
                        cmd=_command_path(ctx, "create")
                    ),
                )
            else:
                await self._reply(ctx, _("{member} does not belong to any team.").format(member=target.mention))
            return
        await self._reply(ctx, embed=self._team_card(ctx, guild, found[1]))

    @scrims_team.command(name="list")
    async def scrims_team_list(self, ctx: commands.Context) -> None:
        """List the teams of this server."""
        guild = await self._require_guild(ctx)
        if guild is None:
            return
        teams = await self.config.guild(guild).teams()
        if not teams:
            await self._reply(
                ctx,
                _("This server has no teams yet. Create the first one with `{cmd}`.").format(
                    cmd=_command_path(ctx, "create")
                ),
            )
            return

        lines: List[str] = []
        ordered = sorted(teams.values(), key=lambda item: str(item.get("name", "")).casefold())
        for index, team in enumerate(ordered, start=1):
            captain_id = int(team.get("captain_id", 0))
            captain = guild.get_member(captain_id)
            who = captain.mention if captain else f"<@{captain_id}>"
            display = f"{team.get('name', '?')} [{team['tag']}]" if team.get("tag") else str(team.get("name", "?"))
            lines.append(
                _("{index}. **{name}** — {captain} · {count} members").format(
                    index=index,
                    name=display,
                    captain=who,
                    count=len(team.get("members", {})),
                )
            )

        body_lines: List[str] = []
        for line in lines:
            if len("\n".join(body_lines + [line])) > 3500:
                break
            body_lines.append(line)
        description = "\n".join(body_lines) or "—"
        if len(body_lines) < len(ordered):
            description += "\n" + _("… and {n} more.").format(n=len(ordered) - len(body_lines))
        embed = discord.Embed(
            title=_("📋 Teams ({count})").format(count=len(ordered)),
            description=description,
            colour=COLOR_TEAM,
        )
        embed.set_footer(text=_("Scrims LoL"))
        await self._reply(ctx, embed=embed)

    @scrims_team.command(name="add")
    @app_commands.rename(member="miembro", role="rol")
    @app_commands.describe(member="Usuario que se añade al equipo.", role="Titular o suplente.")
    @app_commands.choices(
        role=[
            app_commands.Choice(name="Titular", value="player"),
            app_commands.Choice(name="Suplente", value="sub"),
        ]
    )
    async def scrims_team_add(self, ctx: commands.Context, member: discord.Member, role: str = "player") -> None:
        """Add a member to your team (captain only)."""
        guild = await self._require_guild(ctx)
        if guild is None:
            return
        found = await self._captain_team(ctx, guild)
        if found is None:
            return
        team_id, _team = found
        role = role.casefold()
        if role not in MEMBERSHIP_ROLES:
            await self._reply(ctx, _("Role must be `player` or `sub`."))
            return
        if member.bot:
            await self._reply(ctx, _("That user cannot be added to a team."))
            return

        async with self._locks[guild.id]:
            teams = await self.config.guild(guild).teams()
            current = teams.get(team_id)
            if current is None:
                await self._reply(ctx, _("This team no longer exists."))
                return
            other = self._find_by_user(teams, member.id)
            if other is not None:
                await self._reply(
                    ctx,
                    _("{member} is already in the team **{team}**.").format(
                        member=member.mention, team=other[1]["name"]
                    ),
                )
                return
            if len(current.get("members", {})) >= MAX_MEMBERS:
                await self._reply(ctx, _("The roster is full (15 members)."))
                return
            current.setdefault("members", {})[str(member.id)] = role
            await self.config.guild(guild).teams.set(teams)

        await self._reply(
            ctx,
            _("✅ {member} joined the team as {role}.").format(member=member.mention, role=_role_label(role)),
        )

    @scrims_team.command(name="remove")
    @app_commands.rename(member="miembro")
    @app_commands.describe(member="Usuario que se elimina del equipo.")
    async def scrims_team_remove(self, ctx: commands.Context, member: discord.Member) -> None:
        """Remove a member from your team (captain only)."""
        guild = await self._require_guild(ctx)
        if guild is None:
            return
        found = await self._captain_team(ctx, guild)
        if found is None:
            return
        team_id, _team = found

        async with self._locks[guild.id]:
            teams = await self.config.guild(guild).teams()
            current = teams.get(team_id)
            if current is None:
                await self._reply(ctx, _("This team no longer exists."))
                return
            members = current.get("members", {})
            if str(member.id) not in members:
                await self._reply(ctx, _("{member} is not in your team.").format(member=member.mention))
                return
            if current.get("captain_id") == member.id:
                await self._reply(ctx, _("The captain cannot be removed. Transfer the captaincy first."))
                return
            members.pop(str(member.id), None)
            await self.config.guild(guild).teams.set(teams)

        await self._reply(ctx, _("✅ {member} was removed from the team.").format(member=member.mention))

    @scrims_team.command(name="leave")
    async def scrims_team_leave(self, ctx: commands.Context) -> None:
        """Leave your team."""
        guild = await self._require_guild(ctx)
        if guild is None:
            return
        async with self._locks[guild.id]:
            teams = await self.config.guild(guild).teams()
            found = self._find_by_user(teams, ctx.author.id)
            if found is None:
                await self._reply(
                    ctx,
                    _("You do not belong to any team. Create one with `{cmd}`.").format(
                        cmd=_command_path(ctx, "create")
                    ),
                )
                return
            team_id, team = found
            if team.get("captain_id") == ctx.author.id:
                await self._reply(ctx, _("You cannot leave a team you captain. Transfer the captaincy or delete the team."))
                return
            team.get("members", {}).pop(str(ctx.author.id), None)
            await self.config.guild(guild).teams.set(teams)
            name = team.get("name", "?")

        await self._reply(ctx, _("✅ You left the team **{name}**.").format(name=name))

    @scrims_team.command(name="transfer")
    @app_commands.rename(member="miembro")
    @app_commands.describe(member="Miembro que pasa a ser el nuevo capitán.")
    async def scrims_team_transfer(self, ctx: commands.Context, member: discord.Member) -> None:
        """Transfer the captaincy to another member."""
        guild = await self._require_guild(ctx)
        if guild is None:
            return
        found = await self._captain_team(ctx, guild)
        if found is None:
            return
        team_id, _team = found

        async with self._locks[guild.id]:
            teams = await self.config.guild(guild).teams()
            current = teams.get(team_id)
            if current is None:
                await self._reply(ctx, _("This team no longer exists."))
                return
            members = current.get("members", {})
            if str(member.id) not in members:
                await self._reply(ctx, _("{member} is not in your team.").format(member=member.mention))
                return
            if current.get("captain_id") == member.id:
                await self._reply(ctx, _("That member is already the captain."))
                return
            members[str(ctx.author.id)] = "player"
            members[str(member.id)] = "captain"
            current["captain_id"] = member.id
            await self.config.guild(guild).teams.set(teams)
            name = current.get("name", "?")

        await self._reply(
            ctx, _("✅ {member} is now the captain of **{name}**.").format(member=member.mention, name=name)
        )

    @scrims_team.command(name="delete")
    async def scrims_team_delete(self, ctx: commands.Context) -> None:
        """Delete your team (captain only)."""
        guild = await self._require_guild(ctx)
        if guild is None:
            return
        found = await self._captain_team(ctx, guild)
        if found is None:
            return
        team_id, team = found

        view = ConfirmView(ctx.author.id)
        embed = discord.Embed(
            title=_("Delete the team {name}?").format(name=team.get("name", "?")),
            description=_("Its {count} members lose the team. This cannot be undone.").format(
                count=len(team.get("members", {}))
            ),
            colour=COLOR_DANGER,
        )
        message = await self._reply(ctx, embed=embed, view=view, keep=True)
        if message is None:
            return
        await view.wait()
        try:
            await message.edit(view=None)
        except discord.HTTPException:
            pass
        if not view.value:
            await self._reply(ctx, _("Cancelled."))
            return

        async with self._locks[guild.id]:
            teams = await self.config.guild(guild).teams()
            teams.pop(team_id, None)
            await self.config.guild(guild).teams.set(teams)

        await self._reply(ctx, _("✅ Team **{name}** deleted.").format(name=team.get("name", "?")))
