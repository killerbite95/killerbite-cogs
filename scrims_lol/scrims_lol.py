"""
Scrims LoL - board de scrims por servidor.

Primera entrega: equipos con capitan, roster de titulares y suplentes. Sobre
estas tablas se construye la board de scrims (posts, apuntados, cierre de
partida y fotos).

Modelo previsto de un scrim (siguiente entrega)::

    scrim = {
        "id": int,
        "author_id": int,
        "mode": "team" | "mix" | "open",       # como se presenta mi lado
        "looks_for": "team" | "mix" | "open",  # que busco
        "start": int,                           # timestamp UTC
        "bo": int,                              # 1, 2, 3 o 5
        "fearless": bool,
        "tier_min": str,
        "tier_max": str,
        "contact": str,
        "channel_id": int,
        "message_id": int,
        "status": "open" | "full" | "closed" | "expired" | "cancelled",
        "a": {"label": str, "team_id": int | None, "signups": [int, ...]},
        "b": {"label": str, "team_id": int | None, "signups": [int, ...]},
        "score": {"a": int, "b": int} | None,   # obligatorio al cerrar
        "photos": [{"game": int, "channel_id": int, "message_id": int, "url": str}],
    }

El registro depende del tipo de lado: un lado de equipo se guarda como equipo
(no importa quien jugo, representa al equipo), y un lado mixto o abierto se
guarda con los apuntados uno a uno. Las fotos son opcionales y solo sirven
como prueba.

Comandos: /scrims team ...

By Killerbite95
"""

from __future__ import annotations

import asyncio
import datetime
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import discord
from discord import app_commands
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n

from .dashboard_integration import DashboardIntegration

_ = Translator("ScrimsLoL", __file__)

MAX_TEAM_NAME = 32
MAX_TEAM_TAG = 8
MAX_MEMBERS = 15
STARTER_SLOTS = 5
MEMBERSHIP_ROLES = ("player", "sub")
ROLE_LABELS = {"player": "Player", "sub": "Sub"}

COLOR_TEAM = discord.Color.from_rgb(0xC8, 0xAA, 0x6E)
COLOR_DANGER = discord.Color.from_rgb(0xE8, 0x4A, 0x4A)


def _bar(filled: int, total: int = STARTER_SLOTS) -> str:
    filled = max(0, min(filled, total))
    return "▰" * filled + "▱" * (total - filled)


def _role_label(role: str) -> str:
    return _(ROLE_LABELS.get(role, "Player"))


def _clean(value: str) -> str:
    return " ".join(str(value).split())


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


def _command_path(ctx: commands.Context, *parts: str) -> str:
    base = f"{ctx.clean_prefix}scrims team"
    return " ".join([base, *parts])


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


@cog_i18n(_)
class ScrimsLoL(DashboardIntegration, commands.Cog):
    """Scrim board for League of Legends: teams, sign-ups and match records."""

    __author__ = "Killerbite95"
    __version__ = "0.2.0"

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0x5C21A0B1, force_registration=True)
        self.config.register_guild(
            teams={},
            next_team_id=1,
        )
        self._locks: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre = super().format_help_for_context(ctx)
        return _("{pre}\n\nVersion: {version}").format(pre=pre, version=self.__version__)

    async def red_delete_data_for_user(self, *, requester: str, user_id: int) -> None:
        uid = str(user_id)
        for guild_id in await self.config.all_guilds():
            async with self.config.guild_from_id(guild_id).teams() as teams:
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

    # ------------------------------------------------------------------ helpers

    async def _require_guild(self, ctx: commands.Context) -> Optional[discord.Guild]:
        if ctx.guild is None:
            await ctx.reply(_("This command only works in a server."))
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
            await ctx.reply(
                _("You do not belong to any team. Create one with `{cmd}`.").format(cmd=_command_path(ctx, "create"))
            )
            return None
        if found[1].get("captain_id") != ctx.author.id:
            await ctx.reply(_("Only the captain can do this."))
            return None
        return found

    # --------------------------------------------------------------- commands

    @commands.hybrid_group(name="scrims")
    async def scrims(self, ctx: commands.Context) -> None:
        """Scrims of League of Legends."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @scrims.group(name="team")
    async def scrims_team(self, ctx: commands.Context) -> None:
        """Manage scrim teams."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

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
            await ctx.reply(_("The team name must be between 2 and 32 characters."))
            return
        clean_tag = _clean(tag or "").replace(" ", "")[:MAX_TEAM_TAG].upper()

        async with self._locks[guild.id]:
            teams = await self.config.guild(guild).teams()
            existing = self._find_by_user(teams, ctx.author.id)
            if existing is not None:
                await ctx.reply(
                    _("You are already in the team **{team}**. Leave it before creating another one.").format(
                        team=existing[1]["name"]
                    )
                )
                return
            if self._find_by_name(teams, clean_name) is not None:
                await ctx.reply(_("There is already a team named **{name}**.").format(name=clean_name))
                return
            if clean_tag and self._find_by_tag(teams, clean_tag) is not None:
                await ctx.reply(_("There is already a team with the tag **{tag}**.").format(tag=clean_tag))
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

        await ctx.reply(_("✅ Team **{name}** created. You are the captain.").format(name=clean_name), embed=card)

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
                await ctx.reply(
                    _("You do not belong to any team. Create one with `{cmd}`.").format(
                        cmd=_command_path(ctx, "create")
                    )
                )
            else:
                await ctx.reply(_("{member} does not belong to any team.").format(member=target.mention))
            return
        await ctx.reply(embed=self._team_card(ctx, guild, found[1]))

    @scrims_team.command(name="list")
    async def scrims_team_list(self, ctx: commands.Context) -> None:
        """List the teams of this server."""
        guild = await self._require_guild(ctx)
        if guild is None:
            return
        teams = await self.config.guild(guild).teams()
        if not teams:
            await ctx.reply(
                _("This server has no teams yet. Create the first one with `{cmd}`.").format(
                    cmd=_command_path(ctx, "create")
                )
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
        await ctx.reply(embed=embed)

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
            await ctx.reply(_("Role must be `player` or `sub`."))
            return
        if member.bot:
            await ctx.reply(_("That user cannot be added to a team."))
            return

        async with self._locks[guild.id]:
            teams = await self.config.guild(guild).teams()
            current = teams.get(team_id)
            if current is None:
                await ctx.reply(_("This team no longer exists."))
                return
            other = self._find_by_user(teams, member.id)
            if other is not None:
                await ctx.reply(
                    _("{member} is already in the team **{team}**.").format(member=member.mention, team=other[1]["name"])
                )
                return
            if len(current.get("members", {})) >= MAX_MEMBERS:
                await ctx.reply(_("The roster is full (15 members)."))
                return
            current.setdefault("members", {})[str(member.id)] = role
            await self.config.guild(guild).teams.set(teams)

        await ctx.reply(_("✅ {member} joined the team as {role}.").format(member=member.mention, role=_role_label(role)))

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
                await ctx.reply(_("This team no longer exists."))
                return
            members = current.get("members", {})
            if str(member.id) not in members:
                await ctx.reply(_("{member} is not in your team.").format(member=member.mention))
                return
            if current.get("captain_id") == member.id:
                await ctx.reply(_("The captain cannot be removed. Transfer the captaincy first."))
                return
            members.pop(str(member.id), None)
            await self.config.guild(guild).teams.set(teams)

        await ctx.reply(_("✅ {member} was removed from the team.").format(member=member.mention))

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
                await ctx.reply(
                    _("You do not belong to any team. Create one with `{cmd}`.").format(
                        cmd=_command_path(ctx, "create")
                    )
                )
                return
            team_id, team = found
            if team.get("captain_id") == ctx.author.id:
                await ctx.reply(_("You cannot leave a team you captain. Transfer the captaincy or delete the team."))
                return
            team.get("members", {}).pop(str(ctx.author.id), None)
            await self.config.guild(guild).teams.set(teams)
            name = team.get("name", "?")

        await ctx.reply(_("✅ You left the team **{name}**.").format(name=name))

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
                await ctx.reply(_("This team no longer exists."))
                return
            members = current.get("members", {})
            if str(member.id) not in members:
                await ctx.reply(_("{member} is not in your team.").format(member=member.mention))
                return
            if current.get("captain_id") == member.id:
                await ctx.reply(_("That member is already the captain."))
                return
            members[str(ctx.author.id)] = "player"
            members[str(member.id)] = "captain"
            current["captain_id"] = member.id
            await self.config.guild(guild).teams.set(teams)
            name = current.get("name", "?")

        await ctx.reply(_("✅ {member} is now the captain of **{name}**.").format(member=member.mention, name=name))

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
        message = await ctx.reply(embed=embed, view=view)
        await view.wait()
        try:
            await message.edit(view=None)
        except discord.HTTPException:
            pass
        if not view.value:
            await ctx.reply(_("Cancelled."))
            return

        async with self._locks[guild.id]:
            teams = await self.config.guild(guild).teams()
            teams.pop(team_id, None)
            await self.config.guild(guild).teams.set(teams)

        await ctx.reply(_("✅ Team **{name}** deleted.").format(name=team.get("name", "?")))
