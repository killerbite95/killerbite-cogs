"""
EquiposRoles - team role requests confirmed by the team itself.

A player presses the panel button, picks a team and the bot posts a request
card in that team's private channel. A member who already has the team role
confirms or rejects it. Only on confirmation does the bot assign the role,
so nobody has to wait for staff and no role is handed out blindly.

Models::

    team = {
        "id": int,
        "name": str,
        "role_id": int,
        "channel_id": int,
        "created_at": int,
    }

    request = {
        "id": int,
        "user_id": int,
        "team_id": int,
        "status": "pending" | "approved" | "rejected" | "expired" | "cancelled",
        "created_at": int,
        "expires_at": int,
        "resolved_at": int | None,
        "resolved_by": int | None,
        "channel_id": int,
        "message_id": int | None,
    }

Settings per guild: request panel channel, audit log channel, per-user
cooldown in seconds (60 minutes by default) and request expiry in seconds
(48 hours by default).

By Killerbite95
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import logging
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n

from .dashboard_integration import DashboardIntegration

_ = Translator("EquiposRoles", __file__)
log = logging.getLogger("red.killerbite-cogs.equipos_roles")

MAX_TEAMS = 125
MAX_SELECTS = 5
MAX_OPTIONS = 25
MAX_NAME = 64
PRIVATE_DELETE_AFTER = 20.0
SWEEP_MINUTES = 5
PRUNE_AFTER = 30 * 86400

MIN_COOLDOWN_MINUTES = 1
MAX_COOLDOWN_MINUTES = 7 * 24 * 60
MIN_EXPIRY_HOURS = 1
MAX_EXPIRY_HOURS = 30 * 24

COLOR_PENDING = discord.Color.from_rgb(0xE8, 0xB3, 0x4A)
COLOR_APPROVED = discord.Color.from_rgb(0x4A, 0xE8, 0x8A)
COLOR_REJECTED = discord.Color.from_rgb(0xE8, 0x4A, 0x4A)
COLOR_MUTED = discord.Color.from_rgb(0x9A, 0x9A, 0x9A)

STATUS_COLORS = {
    "pending": COLOR_PENDING,
    "approved": COLOR_APPROVED,
    "rejected": COLOR_REJECTED,
    "expired": COLOR_MUTED,
    "cancelled": COLOR_MUTED,
}
STATUS_CHOICES = (
    ("pending", "Pending"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
    ("expired", "Expired"),
    ("cancelled", "Cancelled"),
    ("all", "All"),
)
STATUS_EMOJI = {
    "pending": "🕓",
    "approved": "✅",
    "rejected": "❌",
    "expired": "⏰",
    "cancelled": "🚫",
}

PANEL_ID = "equipos_roles:panel"
CONFIRM_ID = "equipos_roles:confirm"
REJECT_ID = "equipos_roles:reject"


def _clean(value: str) -> str:
    return " ".join(str(value).split())


def _status_label(status: str) -> str:
    labels = {
        "pending": _("Pending"),
        "approved": _("Approved"),
        "rejected": _("Rejected"),
        "expired": _("Expired"),
        "cancelled": _("Cancelled"),
    }
    return labels.get(status, status)


def _action_label(action: str) -> str:
    labels = {
        "created": _("Created"),
        "approved": _("Approved"),
        "rejected": _("Rejected"),
        "expired": _("Expired"),
        "cancelled": _("Cancelled"),
    }
    return labels.get(action, action)


def _fmt_cooldown(seconds: int) -> str:
    minutes = max(1, int(round(int(seconds) / 60)))
    if minutes % 60 == 0:
        return _("{hours} h").format(hours=minutes // 60)
    return _("{minutes} min").format(minutes=minutes)


def _fmt_expiry(seconds: int) -> str:
    hours = max(1, int(round(int(seconds) / 3600)))
    return _("{hours} h").format(hours=hours)


def _command_path(ctx: commands.Context, *parts: str) -> str:
    return " ".join([f"{ctx.clean_prefix}teamroles", *parts])


class TeamSelect(discord.ui.Select):
    """Picks one of the registered teams."""

    def __init__(self, cog: "EquiposRoles", teams: List[dict], index: int, total: int) -> None:
        self.cog = cog
        options = []
        for team in teams:
            options.append(
                discord.SelectOption(
                    label=str(team.get("name", "?"))[:100],
                    value=str(team.get("id")),
                )
            )
        placeholder = _("Teams {start}-{end} of {total}").format(
            start=index + 1, end=index + len(teams), total=total
        )
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(_("This only works in a server."), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        ok, message = await self.cog.apply_request(interaction.guild, int(self.values[0]), interaction.user)
        await interaction.followup.send(message, ephemeral=True)


class TeamSelectView(discord.ui.View):
    """Dropdown (or dropdowns) listing every registered team."""

    def __init__(self, cog: "EquiposRoles", teams: Dict[str, dict]) -> None:
        super().__init__(timeout=180.0)
        ordered = sorted(teams.values(), key=lambda item: str(item.get("name", "")).casefold())
        total = len(ordered)
        limit = min(total, MAX_SELECTS * MAX_OPTIONS)
        for start in range(0, limit, MAX_OPTIONS):
            chunk = ordered[start : start + MAX_OPTIONS]
            self.add_item(TeamSelect(cog, chunk, start, total))


class PanelView(discord.ui.View):
    """Persistent panel with the request button."""

    def __init__(self, cog: "EquiposRoles") -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.request_button.label = _("Request team role")

    @discord.ui.button(label="Request team role", emoji="🎟️", style=discord.ButtonStyle.primary, custom_id=PANEL_ID)
    async def request_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(_("This only works in a server."), ephemeral=True)
            return
        teams = await self.cog.config.guild(interaction.guild).teams()
        if not teams:
            await interaction.response.send_message(
                _("There are no teams registered yet. Tell an admin."), ephemeral=True
            )
            return
        await interaction.response.send_message(
            _("Pick your team."), view=TeamSelectView(self.cog, teams), ephemeral=True
        )


class RequestView(discord.ui.View):
    """Persistent confirm/reject buttons of a request card."""

    def __init__(self, cog: "EquiposRoles") -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.confirm_button.label = _("Confirm")
        self.reject_button.label = _("Reject")

    async def _request(self, interaction: discord.Interaction) -> Optional[dict]:
        if interaction.guild is None:
            await interaction.response.send_message(_("This only works in a server."), ephemeral=True)
            return None
        request = await self.cog.request_by_message(interaction.guild, interaction.message.id)
        if request is None:
            await interaction.response.send_message(_("That request no longer exists."), ephemeral=True)
            return None
        if request.get("status") != "pending":
            await interaction.response.send_message(_("That request is already resolved."), ephemeral=True)
            return None
        if not await self.cog.can_resolve(interaction.guild, interaction.user, request):
            await interaction.response.send_message(
                _("Only members with the team role or bot staff can resolve this request."), ephemeral=True
            )
            return None
        return request

    @discord.ui.button(label="Confirm", emoji="✅", style=discord.ButtonStyle.success, custom_id=CONFIRM_ID)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        request = await self._request(interaction)
        if request is None:
            return
        await interaction.response.defer()
        ok, message = await self.cog.resolve_request(
            interaction.guild, request["id"], interaction.user, True, message=interaction.message
        )
        await interaction.followup.send(message, ephemeral=True)

    @discord.ui.button(label="Reject", emoji="✖️", style=discord.ButtonStyle.danger, custom_id=REJECT_ID)
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        request = await self._request(interaction)
        if request is None:
            return
        await interaction.response.defer()
        ok, message = await self.cog.resolve_request(
            interaction.guild, request["id"], interaction.user, False, message=interaction.message
        )
        await interaction.followup.send(message, ephemeral=True)


class StatusSelect(discord.ui.Select):
    """Picks a request status to list them."""

    def __init__(self, cog: "EquiposRoles") -> None:
        self.cog = cog
        options = []
        for value, label in STATUS_CHOICES:
            options.append(
                discord.SelectOption(
                    label=_status_label(value) if value != "all" else _("All"),
                    value=value,
                )
            )
        super().__init__(placeholder=_("Pick a status"), min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(_("This only works in a server."), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        embed = await self.cog.requests_embed(interaction.guild, self.values[0])
        if embed is None:
            await interaction.followup.send(_("There are no requests with that status."), ephemeral=True)
            return
        await interaction.followup.send(embed=embed, ephemeral=True)


class RequestsView(discord.ui.View):
    """Board listing requests by status."""

    def __init__(self, cog: "EquiposRoles") -> None:
        super().__init__(timeout=300.0)
        self.add_item(StatusSelect(cog))


class TeamNameModal(discord.ui.Modal):
    """Asks for the team name before picking its role and channel."""

    def __init__(self, cog: "EquiposRoles") -> None:
        super().__init__(title=_("Register team"))
        self.cog = cog
        self.name = discord.ui.TextInput(
            label=_("Team name"),
            placeholder=_("Team name (2-64 characters)"),
            min_length=2,
            max_length=64,
        )
        self.add_item(self.name)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(_("This only works in a server."), ephemeral=True)
            return
        await interaction.response.send_message(
            _("Now pick the role and the channel."),
            view=RoleChannelView(self.cog, self.name.value.strip()),
            ephemeral=True,
        )


class TeamRoleSelect(discord.ui.RoleSelect):
    """Picks the role of the team being registered."""

    def __init__(self, view: "RoleChannelView") -> None:
        super().__init__(placeholder=_("Pick the role"), min_values=1, max_values=1)
        self.parent_view = view

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.values:
            self.parent_view.selected_role = self.values[0]
        await interaction.response.defer()


class TeamChannelSelect(discord.ui.ChannelSelect):
    """Picks the private channel of the team being registered."""

    def __init__(self, view: "RoleChannelView") -> None:
        super().__init__(
            placeholder=_("Pick the channel"),
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1,
        )
        self.parent_view = view

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.values:
            self.parent_view.selected_channel = self.values[0]
        await interaction.response.defer()


class RoleChannelView(discord.ui.View):
    """Picks the role and the channel, then registers the team."""

    def __init__(self, cog: "EquiposRoles", name: str) -> None:
        super().__init__(timeout=300.0)
        self.cog = cog
        self.name = name
        self.selected_role: Optional[discord.Role] = None
        self.selected_channel: Optional[discord.TextChannel] = None
        self.role_select = TeamRoleSelect(self)
        self.channel_select = TeamChannelSelect(self)
        self.add_item(self.role_select)
        self.add_item(self.channel_select)
        self.register_button.label = _("Register")

    @discord.ui.button(label="Register", emoji="✅", style=discord.ButtonStyle.success)
    async def register_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(_("This only works in a server."), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        if self.selected_role is None:
            await interaction.followup.send(_("Pick the role first."), ephemeral=True)
            return
        if self.selected_channel is None:
            await interaction.followup.send(_("Pick the channel first."), ephemeral=True)
            return
        channel = interaction.guild.get_channel(self.selected_channel.id)
        if channel is None:
            await interaction.followup.send(_("Pick the channel first."), ephemeral=True)
            return
        ok, message = await self.cog.add_team(interaction.guild, self.name, self.selected_role, channel)
        await interaction.followup.send(message, ephemeral=True)


class CooldownModal(discord.ui.Modal):
    """Asks for the cooldown in minutes."""

    def __init__(self, cog: "EquiposRoles") -> None:
        super().__init__(title=_("Set cooldown"))
        self.cog = cog
        self.minutes = discord.ui.TextInput(
            label=_("Cooldown in minutes"),
            placeholder="60",
            min_length=1,
            max_length=5,
        )
        self.add_item(self.minutes)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(_("This only works in a server."), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            minutes = int(self.minutes.value)
        except ValueError:
            await interaction.followup.send(_("The cooldown must be a number of minutes."), ephemeral=True)
            return
        if not (MIN_COOLDOWN_MINUTES <= minutes <= MAX_COOLDOWN_MINUTES):
            await interaction.followup.send(
                _("The cooldown must be between {min} and {max} minutes.").format(
                    min=MIN_COOLDOWN_MINUTES, max=MAX_COOLDOWN_MINUTES
                ),
                ephemeral=True,
            )
            return
        await self.cog.config.guild(interaction.guild).cooldown_seconds.set(minutes * 60)
        await interaction.followup.send(embed=await self.cog.config_embed(interaction.guild), ephemeral=True)


class ExpiryModal(discord.ui.Modal):
    """Asks for the expiry in hours."""

    def __init__(self, cog: "EquiposRoles") -> None:
        super().__init__(title=_("Set expiry"))
        self.cog = cog
        self.hours = discord.ui.TextInput(
            label=_("Expiry in hours"),
            placeholder="48",
            min_length=1,
            max_length=5,
        )
        self.add_item(self.hours)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(_("This only works in a server."), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            hours = int(self.hours.value)
        except ValueError:
            await interaction.followup.send(_("The expiry must be a number of hours."), ephemeral=True)
            return
        if not (MIN_EXPIRY_HOURS <= hours <= MAX_EXPIRY_HOURS):
            await interaction.followup.send(
                _("The expiry must be between {min} and {max} hours.").format(
                    min=MIN_EXPIRY_HOURS, max=MAX_EXPIRY_HOURS
                ),
                ephemeral=True,
            )
            return
        await self.cog.config.guild(interaction.guild).expiry_seconds.set(hours * 3600)
        await interaction.followup.send(embed=await self.cog.config_embed(interaction.guild), ephemeral=True)


class LogChannelSelect(discord.ui.ChannelSelect):
    """Picks the audit log channel."""

    def __init__(self, cog: "EquiposRoles") -> None:
        self.cog = cog
        super().__init__(
            placeholder=_("Pick the log channel"),
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(_("This only works in a server."), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        # ChannelSelect yields AppCommandChannel, so resolve the real channel first.
        channel = interaction.guild.get_channel(self.values[0].id) if self.values else None
        if channel is None:
            await interaction.followup.send(
                _("That channel is not a text channel."), ephemeral=True
            )
            return
        if not self.cog._channel_ready(interaction.guild, channel):
            await interaction.followup.send(
                _("I cannot post in that channel. Check my permissions there."), ephemeral=True
            )
            return
        await self.cog.config.guild(interaction.guild).log_channel_id.set(channel.id)
        await interaction.followup.send(
            _("✅ Audit log set to {channel}.").format(channel=channel.mention), ephemeral=True
        )


class LogChannelView(discord.ui.View):
    """Board to pick the audit log channel."""

    def __init__(self, cog: "EquiposRoles") -> None:
        super().__init__(timeout=300.0)
        self.add_item(LogChannelSelect(cog))


class PanelChannelSelect(discord.ui.ChannelSelect):
    """Picks the channel where the panel is published."""

    def __init__(self, cog: "EquiposRoles") -> None:
        self.cog = cog
        super().__init__(
            placeholder=_("Pick the panel channel"),
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(_("This only works in a server."), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        # ChannelSelect yields AppCommandChannel, so resolve the real channel first.
        channel = interaction.guild.get_channel(self.values[0].id) if self.values else None
        if channel is None:
            await interaction.followup.send(
                _("That channel is not a text channel."), ephemeral=True
            )
            return
        ok, message = await self.cog.publish_panel(interaction.guild, channel)
        await interaction.followup.send(message, ephemeral=True)


class PanelChannelView(discord.ui.View):
    """Board to pick where the panel is published."""

    def __init__(self, cog: "EquiposRoles") -> None:
        super().__init__(timeout=300.0)
        self.add_item(PanelChannelSelect(cog))


class DeleteTeamSelect(discord.ui.Select):
    """Picks the team to delete."""

    def __init__(self, cog: "EquiposRoles", teams: Dict[str, dict]) -> None:
        self.cog = cog
        options = [
            discord.SelectOption(label=str(team.get("name", "?"))[:100], value=str(team.get("id")))
            for team in sorted(teams.values(), key=lambda item: str(item.get("name", "")).casefold())
        ]
        super().__init__(
            placeholder=_("Pick the team to delete."),
            min_values=1,
            max_values=1,
            options=options[:MAX_OPTIONS],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(_("This only works in a server."), ephemeral=True)
            return
        await interaction.response.send_message(
            _("Delete this team?"),
            view=ConfirmDeleteView(self.cog, int(self.values[0])),
            ephemeral=True,
        )


class DeleteTeamView(discord.ui.View):
    """Board to pick the team to delete."""

    def __init__(self, cog: "EquiposRoles", teams: Dict[str, dict]) -> None:
        super().__init__(timeout=300.0)
        if teams:
            self.add_item(DeleteTeamSelect(cog, teams))


class ConfirmDeleteView(discord.ui.View):
    """Confirms a team deletion."""

    def __init__(self, cog: "EquiposRoles", team_id: int) -> None:
        super().__init__(timeout=120.0)
        self.cog = cog
        self.team_id = team_id
        self.delete_button.label = _("Delete")
        self.cancel_button.label = _("Cancel")

    @discord.ui.button(label="Delete", emoji="🗑️", style=discord.ButtonStyle.danger)
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(_("This only works in a server."), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        ok, message = await self.cog.remove_team_by_id(interaction.guild, self.team_id, interaction.user)
        await interaction.followup.send(message, ephemeral=True)

    @discord.ui.button(label="Cancel", emoji="↩️", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(content=_("Cancelled."), view=None)


class SettingsView(discord.ui.View):
    """Board with the admin settings actions."""

    def __init__(self, cog: "EquiposRoles") -> None:
        super().__init__(timeout=300.0)
        self.cog = cog
        self.cooldown_button.label = _("Set cooldown")
        self.expiry_button.label = _("Set expiry")
        self.log_button.label = _("Set log channel")
        self.show_button.label = _("Show settings")

    @discord.ui.button(label="Set cooldown", emoji="⏱️", style=discord.ButtonStyle.primary)
    async def cooldown_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(CooldownModal(self.cog))

    @discord.ui.button(label="Set expiry", emoji="⏳", style=discord.ButtonStyle.primary)
    async def expiry_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(ExpiryModal(self.cog))

    @discord.ui.button(label="Set log channel", emoji="📜", style=discord.ButtonStyle.primary)
    async def log_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message(_("Pick the log channel."), view=LogChannelView(self.cog), ephemeral=True)

    @discord.ui.button(label="Show settings", emoji="📊", style=discord.ButtonStyle.secondary)
    async def show_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(_("This only works in a server."), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(embed=await self.cog.config_embed(interaction.guild), ephemeral=True)


class AdminView(discord.ui.View):
    """Main admin board: everything through buttons."""

    def __init__(self, cog: "EquiposRoles") -> None:
        super().__init__(timeout=600.0)
        self.cog = cog
        self.panel_button.label = _("Publish panel")
        self.delete_panel_button.label = _("Delete panel")
        self.add_button.label = _("Register team")
        self.delete_button.label = _("Delete team")
        self.requests_button.label = _("Requests")
        self.settings_button.label = _("Settings")

    @discord.ui.button(label="Publish panel", emoji="🎟️", style=discord.ButtonStyle.primary)
    async def panel_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message(
            _("Pick the panel channel."), view=PanelChannelView(self.cog), ephemeral=True
        )

    @discord.ui.button(label="Delete panel", emoji="🗑️", style=discord.ButtonStyle.danger)
    async def delete_panel_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(_("This only works in a server."), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        ok, message = await self.cog.unpublish_panel(interaction.guild)
        await interaction.followup.send(message, ephemeral=True)

    @discord.ui.button(label="Register team", emoji="➕", style=discord.ButtonStyle.success)
    async def add_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(TeamNameModal(self.cog))

    @discord.ui.button(label="Delete team", emoji="➖", style=discord.ButtonStyle.danger)
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(_("This only works in a server."), ephemeral=True)
            return
        teams = await self.cog.config.guild(interaction.guild).teams()
        if not teams:
            await interaction.response.send_message(
                _("There are no teams registered yet. Tell an admin."), ephemeral=True
            )
            return
        await interaction.response.send_message(
            _("Pick the team to delete."), view=DeleteTeamView(self.cog, teams), ephemeral=True
        )

    @discord.ui.button(label="Requests", emoji="📋", style=discord.ButtonStyle.primary)
    async def requests_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message(
            _("Pick a status."), view=RequestsView(self.cog), ephemeral=True
        )

    @discord.ui.button(label="Settings", emoji="⚙️", style=discord.ButtonStyle.secondary, row=1)
    async def settings_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message(
            _("Team role settings."), view=SettingsView(self.cog), ephemeral=True
        )


@cog_i18n(_)
class EquiposRoles(DashboardIntegration, commands.Cog):
    """Team role requests confirmed by the team itself."""

    __author__ = "Killerbite95"
    __version__ = "0.1.0"

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0x5C21A0B2, force_registration=True)
        self.config.register_guild(
            teams={},
            next_team_id=1,
            requests={},
            next_request_id=1,
            cooldowns={},
            cooldown_seconds=3600,
            expiry_seconds=48 * 3600,
            panel_channel_id=None,
            panel_message_id=None,
            log_channel_id=None,
        )
        self._locks: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._panel_view: Optional[PanelView] = None
        self._request_view: Optional[RequestView] = None

    async def cog_load(self) -> None:
        await super().cog_load()
        self._panel_view = PanelView(self)
        self._request_view = RequestView(self)
        self.bot.add_view(self._panel_view)
        self.bot.add_view(self._request_view)
        if not self.expire_loop.is_running():
            self.expire_loop.start()
        await self._sweep_all()

    def cog_unload(self) -> None:
        self.expire_loop.cancel()
        for view in (self._panel_view, self._request_view):
            if view is not None:
                try:
                    self.bot.remove_view(view)
                except Exception:
                    pass
        self._panel_view = None
        self._request_view = None

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre = super().format_help_for_context(ctx)
        return _("{pre}\n\nVersion: {version}").format(pre=pre, version=self.__version__)

    async def red_delete_data_for_user(self, *, requester: str, user_id: int) -> None:
        uid = int(user_id)
        for guild_id in await self.config.all_guilds():
            async with self._locks[guild_id]:
                guild_conf = self.config.guild_from_id(guild_id)
                requests = await guild_conf.requests()
                changed = False
                for request_id in list(requests):
                    request = requests[request_id]
                    if request.get("user_id") == uid or request.get("resolved_by") == uid:
                        del requests[request_id]
                        changed = True
                if changed:
                    await guild_conf.requests.set(requests)
                cooldowns = await guild_conf.cooldowns()
                if str(uid) in cooldowns:
                    del cooldowns[str(uid)]
                    await guild_conf.cooldowns.set(cooldowns)

    # ------------------------------------------------------------------ helpers

    async def _reply(
        self,
        ctx: commands.Context,
        content: Optional[str] = None,
        *,
        embed: Optional[discord.Embed] = None,
        view: Optional[discord.ui.View] = None,
        keep: bool = False,
        delete_after: Optional[float] = None,
    ) -> Optional[discord.Message]:
        """Respond privately: ephemeral in slash, auto-deleted in prefix."""
        if ctx.interaction is not None:
            return await ctx.send(content, embed=embed, view=view, ephemeral=True)
        return await ctx.send(
            content,
            embed=embed,
            view=view,
            delete_after=None if keep else (delete_after or PRIVATE_DELETE_AFTER),
        )

    async def _require_guild(self, ctx: commands.Context) -> Optional[discord.Guild]:
        if ctx.guild is None:
            await self._reply(ctx, _("This command only works in a server."))
            return None
        return ctx.guild

    @staticmethod
    def _find_team_by_name(teams: Dict[str, dict], name: str) -> Optional[Tuple[str, dict]]:
        wanted = _clean(name).casefold()
        for team_id, team in teams.items():
            if str(team.get("name", "")).casefold() == wanted:
                return team_id, team
        return None

    @staticmethod
    def _channel_ready(guild: discord.Guild, channel: discord.TextChannel) -> bool:
        if guild.me is None:
            return False
        perms = channel.permissions_for(guild.me)
        return bool(perms.send_messages and perms.embed_links)

    def _is_team_member(self, guild: discord.Guild, user: discord.abc.User, team: dict) -> bool:
        member = guild.get_member(user.id)
        if member is None:
            return False
        role = guild.get_role(int(team.get("role_id", 0)))
        return role is not None and role in member.roles

    async def _log_action(
        self,
        guild: discord.Guild,
        action: str,
        request: dict,
        team: Optional[dict],
        actor: Optional[discord.abc.User] = None,
    ) -> None:
        channel_id = await self.config.guild(guild).log_channel_id()
        if not channel_id:
            return
        channel = guild.get_channel(int(channel_id))
        if not isinstance(channel, discord.TextChannel):
            return
        colours = {"created": COLOR_PENDING, "approved": COLOR_APPROVED, "rejected": COLOR_REJECTED}
        embed = discord.Embed(
            title=_("Team role request · {action}").format(action=_action_label(action)),
            colour=colours.get(action, COLOR_MUTED),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name=_("Request"), value=f"#{request.get('id')}", inline=True)
        embed.add_field(name=_("Player"), value=f"<@{request.get('user_id')}>", inline=True)
        embed.add_field(name=_("Team"), value=(team or {}).get("name", "—"), inline=True)
        if actor is not None:
            embed.add_field(name=_("By"), value=actor.mention, inline=True)
        with contextlib.suppress(discord.HTTPException):
            await channel.send(embed=embed)

    def _request_embed(self, guild: discord.Guild, request: dict, team: dict) -> discord.Embed:
        status = request.get("status", "pending")
        embed = discord.Embed(
            title=_("Team role request · {team}").format(team=team.get("name", "?")),
            colour=STATUS_COLORS.get(status, COLOR_MUTED),
        )
        target = guild.get_member(int(request.get("user_id", 0)))
        who = target.mention if target is not None else f"<@{request.get('user_id')}>"
        if target is not None:
            who = f"{who}\n{target}"
        embed.add_field(name=_("Player"), value=who, inline=True)
        role = guild.get_role(int(team.get("role_id", 0)))
        embed.add_field(name=_("Team"), value=role.mention if role is not None else team.get("name", "?"), inline=True)
        embed.add_field(name=_("Status"), value=_status_label(status), inline=True)

        created = int(request.get("created_at", 0))
        embed.add_field(
            name=_("Requested"),
            value=_("<t:{ts}:F> (<t:{ts}:R>)").format(ts=created),
            inline=False,
        )
        if status == "pending":
            expires = int(request.get("expires_at", 0))
            embed.add_field(name=_("Expires"), value=_("<t:{ts}:R>").format(ts=expires), inline=False)
        else:
            resolved = int(request.get("resolved_at") or created)
            embed.add_field(name=_("Resolved"), value=_("<t:{ts}:R>").format(ts=resolved), inline=False)
            if request.get("resolved_by"):
                embed.add_field(
                    name=_("Resolved by"),
                    value=f"<@{request.get('resolved_by')}>",
                    inline=True,
                )
        embed.set_footer(text=_("EquiposRoles · Request #{id}").format(id=request.get("id", "?")))
        if self.bot.user is not None:
            embed.set_author(name=_("EquiposRoles"), icon_url=self.bot.user.display_avatar.url)
        return embed

    async def _edit_card(
        self,
        guild: discord.Guild,
        request: dict,
        team: Optional[dict],
        *,
        message: Optional[discord.Message] = None,
    ) -> None:
        if team is None:
            return
        if message is None:
            channel = guild.get_channel(int(request.get("channel_id") or 0))
            if not isinstance(channel, discord.TextChannel):
                return
            try:
                message = await channel.fetch_message(int(request.get("message_id") or 0))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return
        view = self._request_view if request.get("status") == "pending" else discord.ui.View()
        try:
            await message.edit(embed=self._request_embed(guild, request, team), view=view)
        except discord.HTTPException:
            log.warning("Could not edit team role request card #%s in guild %s", request.get("id"), guild.id)

    async def request_by_message(self, guild: discord.Guild, message_id: int) -> Optional[dict]:
        requests = await self.config.guild(guild).requests()
        for request in requests.values():
            if request.get("message_id") == message_id:
                return request
        return None

    async def can_resolve(self, guild: discord.Guild, user: discord.abc.User, request: dict) -> bool:
        member = guild.get_member(user.id)
        if member is None:
            return False
        if await self.bot.is_mod(member) or await self.bot.is_admin(member):
            return True
        teams = await self.config.guild(guild).teams()
        team = teams.get(str(request.get("team_id")))
        if team is None:
            return False
        return self._is_team_member(guild, user, team)

    async def requests_embed(self, guild: discord.Guild, estado: str) -> Optional[discord.Embed]:
        estado = str(estado).casefold()
        requests = await self.config.guild(guild).requests()
        teams = await self.config.guild(guild).teams()
        selected = [
            request
            for request in requests.values()
            if estado == "all" or request.get("status") == estado
        ]
        selected.sort(key=lambda item: int(item.get("created_at", 0)), reverse=True)
        if not selected:
            return None
        embed = discord.Embed(
            title=_("🎟️ Requests · {status} ({count})").format(
                status=_status_label(estado) if estado != "all" else _("All"),
                count=len(selected),
            ),
            colour=STATUS_COLORS.get(estado, COLOR_MUTED),
        )
        for request in selected[:20]:
            team = teams.get(str(request.get("team_id")))
            team_name = team.get("name", "?") if team else "?"
            status = request.get("status", "pending")
            embed.add_field(
                name=_("{emoji} #{id} · {status}").format(
                    emoji=STATUS_EMOJI.get(status, "•"),
                    id=request.get("id"),
                    status=_status_label(status),
                ),
                value=_("{user} · {team} · {when}").format(
                    user=f"<@{request.get('user_id')}>",
                    team=team_name,
                    when=_("<t:{ts}:R>").format(ts=int(request.get("created_at", 0))),
                ),
                inline=False,
            )
        if len(selected) > 20:
            embed.set_footer(text=_("… and {n} more.").format(n=len(selected) - 20))
        return embed

    async def config_embed(self, guild: discord.Guild) -> discord.Embed:
        config = self.config.guild(guild)
        teams = await config.teams()
        requests = await config.requests()
        pending = sum(1 for request in requests.values() if request.get("status") == "pending")
        panel_channel = await config.panel_channel_id()
        log_channel = await config.log_channel_id()
        embed = discord.Embed(title=_("⚙️ Team role settings"), colour=COLOR_PENDING)
        embed.add_field(
            name=_("Panel channel"),
            value=f"<#{panel_channel}>" if panel_channel else _("not set"),
            inline=True,
        )
        embed.add_field(
            name=_("Audit log"),
            value=f"<#{log_channel}>" if log_channel else _("not set"),
            inline=True,
        )
        embed.add_field(
            name=_("Cooldown"),
            value=_fmt_cooldown(int(await config.cooldown_seconds())),
            inline=True,
        )
        embed.add_field(
            name=_("Expiry"),
            value=_fmt_expiry(int(await config.expiry_seconds())),
            inline=True,
        )
        embed.add_field(name=_("Teams"), value=str(len(teams)), inline=True)
        embed.add_field(name=_("Pending requests"), value=str(pending), inline=True)
        return embed

    async def _panel_embed(self, guild: discord.Guild) -> discord.Embed:
        teams = await self.config.guild(guild).teams()
        cooldown = int(await self.config.guild(guild).cooldown_seconds())
        expiry = int(await self.config.guild(guild).expiry_seconds())
        embed = discord.Embed(
            title=_("🎟️ Team role request"),
            description=_(
                "Press the button, pick your team and wait for its members to confirm you. "
                "You can request again after {cooldown}."
            ).format(cooldown=_fmt_cooldown(cooldown)),
            colour=COLOR_PENDING,
        )
        embed.add_field(
            name=_("How it works"),
            value=_(
                "1. Press **Request team role**.\n"
                "2. Pick your team.\n"
                "3. The team confirms or rejects it in its private channel."
            ),
            inline=False,
        )
        ordered = sorted(teams.values(), key=lambda item: str(item.get("name", "")).casefold())
        preview = "\n".join(f"🛡️ {team.get('name', '?')}" for team in ordered[:10])
        if len(ordered) > 10:
            preview += "\n" + _("… and {n} more.").format(n=len(ordered) - 10)
        embed.add_field(name=_("Registered teams"), value=preview or "—", inline=False)
        embed.add_field(name=_("Cooldown"), value=_fmt_cooldown(cooldown), inline=True)
        embed.add_field(name=_("Expiry"), value=_fmt_expiry(expiry), inline=True)
        embed.set_footer(text=_("EquiposRoles · {count} teams").format(count=len(teams)))
        if self.bot.user is not None:
            embed.set_author(name=_("EquiposRoles"), icon_url=self.bot.user.display_avatar.url)
        return embed

    async def publish_panel(
        self, guild: discord.Guild, channel: discord.TextChannel
    ) -> Tuple[bool, str]:
        teams = await self.config.guild(guild).teams()
        if not teams:
            return False, _("There are no teams registered yet. Tell an admin.")
        if not self._channel_ready(guild, channel):
            return False, _("I cannot post in that channel. Check my permissions there.")

        previous_channel = await self.config.guild(guild).panel_channel_id()
        previous_message = await self.config.guild(guild).panel_message_id()
        if previous_channel and previous_message:
            old_channel = guild.get_channel(int(previous_channel))
            if isinstance(old_channel, discord.TextChannel):
                with contextlib.suppress(discord.HTTPException):
                    old_message = await old_channel.fetch_message(int(previous_message))
                    await old_message.delete()

        message = await channel.send(embed=await self._panel_embed(guild), view=self._panel_view)
        await self.config.guild(guild).panel_channel_id.set(channel.id)
        await self.config.guild(guild).panel_message_id.set(message.id)
        return True, _("✅ Panel published in {channel}.").format(channel=channel.mention)

    async def unpublish_panel(self, guild: discord.Guild) -> Tuple[bool, str]:
        channel_id = await self.config.guild(guild).panel_channel_id()
        message_id = await self.config.guild(guild).panel_message_id()
        if not channel_id or not message_id:
            return False, _("There is no published panel.")
        channel = guild.get_channel(int(channel_id))
        if isinstance(channel, discord.TextChannel):
            with contextlib.suppress(discord.HTTPException):
                message = await channel.fetch_message(int(message_id))
                await message.delete()
        await self.config.guild(guild).panel_channel_id.set(None)
        await self.config.guild(guild).panel_message_id.set(None)
        return True, _("✅ Panel deleted.")

    # ------------------------------------------------------------------- teams

    async def add_team(
        self,
        guild: discord.Guild,
        name: str,
        role: discord.Role,
        channel: discord.TextChannel,
    ) -> Tuple[bool, str]:
        name = _clean(name)
        if len(name) < 2 or len(name) > MAX_NAME:
            return False, _("The team name must be between 2 and 64 characters.")
        if role.is_default() or role.managed:
            return False, _("That role cannot be assigned by the bot.")
        if guild.me is None or role >= guild.me.top_role:
            return False, _("That role is above my highest role. Move my role higher.")
        if not self._channel_ready(guild, channel):
            return False, _("I cannot post in that channel. Check my permissions there.")

        async with self._locks[guild.id]:
            teams = await self.config.guild(guild).teams()
            for team in teams.values():
                if str(team.get("name", "")).casefold() == name.casefold():
                    return False, _("There is already a team named **{name}**.").format(name=name)
                if int(team.get("role_id", 0)) == role.id:
                    return False, _("That role is already linked to **{team}**.").format(team=team.get("name", "?"))
            if len(teams) >= MAX_TEAMS:
                return False, _("The maximum of {max} teams is reached.").format(max=MAX_TEAMS)
            team_id = int(await self.config.guild(guild).next_team_id())
            teams[str(team_id)] = {
                "id": team_id,
                "name": name,
                "role_id": role.id,
                "channel_id": channel.id,
                "created_at": int(time.time()),
            }
            await self.config.guild(guild).teams.set(teams)
            await self.config.guild(guild).next_team_id.set(team_id + 1)
        return True, _("✅ Team **{name}** registered with role {role} in {channel}.").format(
            name=name, role=role.mention, channel=channel.mention
        )

    async def remove_team(self, guild: discord.Guild, name: str) -> Tuple[bool, str]:
        async with self._locks[guild.id]:
            teams = await self.config.guild(guild).teams()
            found = self._find_team_by_name(teams, name)
            if found is None:
                return False, _("There is no team named **{name}**.").format(name=_clean(name))
            team_id = int(found[0])
        return await self.remove_team_by_id(guild, team_id, None)

    async def remove_team_by_id(
        self, guild: discord.Guild, team_id: int, actor: Optional[discord.abc.User] = None
    ) -> Tuple[bool, str]:
        async with self._locks[guild.id]:
            teams = await self.config.guild(guild).teams()
            team = teams.pop(str(team_id), None)
            if team is None:
                return False, _("There is no team with that id.")
            requests = await self.config.guild(guild).requests()
            cancelled: List[dict] = []
            now = int(time.time())
            for request in requests.values():
                if request.get("team_id") == team.get("id") and request.get("status") == "pending":
                    request["status"] = "cancelled"
                    request["resolved_at"] = now
                    request["resolved_by"] = actor.id if actor is not None else None
                    cancelled.append(request)
            await self.config.guild(guild).teams.set(teams)
            await self.config.guild(guild).requests.set(requests)
        for request in cancelled:
            await self._edit_card(guild, request, team)
            await self._log_action(guild, "cancelled", request, team, actor=actor)
        return True, _("✅ Team **{name}** deleted.").format(name=team.get("name", "?"))

    # ---------------------------------------------------------------- requests

    async def apply_request(
        self, guild: discord.Guild, team_id: int, user: discord.abc.User
    ) -> Tuple[bool, str]:
        async with self._locks[guild.id]:
            teams = await self.config.guild(guild).teams()
            team = teams.get(str(team_id))
            if team is None:
                return False, _("That team no longer exists.")
            member = guild.get_member(user.id)
            if member is None:
                return False, _("I cannot find you in this server.")
            role = guild.get_role(int(team.get("role_id", 0)))
            if role is None:
                return False, _("The role of **{team}** no longer exists.").format(team=team.get("name", "?"))
            if role in member.roles:
                return False, _("You already have the role of **{team}**.").format(team=team.get("name", "?"))

            requests = await self.config.guild(guild).requests()
            for existing in requests.values():
                if existing.get("user_id") == user.id and existing.get("status") == "pending":
                    pending_team = teams.get(str(existing.get("team_id")))
                    label = pending_team.get("name", "?") if pending_team else "?"
                    return False, _("You already have a pending request for **{team}**.").format(team=label)

            cooldowns = await self.config.guild(guild).cooldowns()
            cooldown = int(await self.config.guild(guild).cooldown_seconds())
            last = int(cooldowns.get(str(user.id), 0))
            if last and int(time.time()) - last < cooldown:
                return False, _("You can request again <t:{ts}:R>.").format(ts=last + cooldown)

            channel = guild.get_channel(int(team.get("channel_id", 0)))
            if not isinstance(channel, discord.TextChannel):
                return False, _("The channel of **{team}** no longer exists.").format(team=team.get("name", "?"))
            if not self._channel_ready(guild, channel):
                return False, _("I cannot post in the channel of **{team}**. Tell an admin.").format(
                    team=team.get("name", "?")
                )

            request_id = int(await self.config.guild(guild).next_request_id())
            now = int(time.time())
            expiry = int(await self.config.guild(guild).expiry_seconds())
            request = {
                "id": request_id,
                "user_id": user.id,
                "team_id": int(team_id),
                "status": "pending",
                "created_at": now,
                "expires_at": now + expiry,
                "resolved_at": None,
                "resolved_by": None,
                "channel_id": channel.id,
                "message_id": None,
            }
            try:
                message = await channel.send(
                    embed=self._request_embed(guild, request, team),
                    view=self._request_view,
                )
            except discord.HTTPException:
                log.exception("Could not post a team role request in guild %s", guild.id)
                return False, _("I could not post the request. Tell an admin.")
            request["message_id"] = message.id
            requests[str(request_id)] = request
            cooldowns[str(user.id)] = now
            await self.config.guild(guild).requests.set(requests)
            await self.config.guild(guild).next_request_id.set(request_id + 1)
            await self.config.guild(guild).cooldowns.set(cooldowns)

        await self._log_action(guild, "created", request, team, actor=user)
        return True, _("✅ Request sent to **{team}**. Its members will confirm or reject it.").format(
            team=team.get("name", "?")
        )

    async def resolve_request(
        self,
        guild: discord.Guild,
        request_id: int,
        actor: discord.abc.User,
        approved: bool,
        *,
        message: Optional[discord.Message] = None,
    ) -> Tuple[bool, str]:
        async with self._locks[guild.id]:
            requests = await self.config.guild(guild).requests()
            request = requests.get(str(request_id))
            if request is None:
                return False, _("That request no longer exists.")
            if request.get("status") != "pending":
                return False, _("That request is already resolved.")
            teams = await self.config.guild(guild).teams()
            team = teams.get(str(request.get("team_id")))
            if team is None:
                return False, _("That team no longer exists.")
            if not self._is_team_member(guild, actor, team):
                return False, _("Only members with the team role or bot staff can resolve this request.")

            target = guild.get_member(int(request.get("user_id", 0)))
            role = guild.get_role(int(team.get("role_id", 0)))
            if approved:
                if role is None:
                    return False, _("The role of **{team}** no longer exists.").format(team=team.get("name", "?"))
                if guild.me is None or role >= guild.me.top_role:
                    return False, _("I cannot assign **{role}**: it is above my role.").format(role=role.name)
                if target is not None and role not in target.roles:
                    try:
                        await target.add_roles(
                            role,
                            reason=_("Team role request #{id} approved by {user}").format(
                                id=request_id, user=str(actor)
                            ),
                        )
                    except discord.Forbidden:
                        return False, _("I do not have permission to assign that role. Tell an admin.")
                    except discord.HTTPException:
                        log.exception("Could not assign a team role in guild %s", guild.id)
                        return False, _("Discord rejected the role assignment. Tell an admin.")

            now = int(time.time())
            request["status"] = "approved" if approved else "rejected"
            request["resolved_at"] = now
            request["resolved_by"] = actor.id
            requests[str(request_id)] = request
            await self.config.guild(guild).requests.set(requests)
            await self._edit_card(guild, request, team, message=message)

        if target is not None:
            with contextlib.suppress(discord.HTTPException):
                if approved:
                    await target.send(
                        _("✅ Your request for **{team}** was approved. You now have the role.").format(
                            team=team.get("name", "?")
                        )
                    )
                else:
                    await target.send(
                        _("❌ Your request for **{team}** was rejected.").format(team=team.get("name", "?"))
                    )
        await self._log_action(guild, "approved" if approved else "rejected", request, team, actor=actor)
        if approved:
            return True, _("✅ Request #{id} approved.").format(id=request_id)
        return True, _("✅ Request #{id} rejected.").format(id=request_id)

    async def cancel_request(
        self, guild: discord.Guild, request_id: int, actor: discord.abc.User
    ) -> Tuple[bool, str]:
        async with self._locks[guild.id]:
            requests = await self.config.guild(guild).requests()
            request = requests.get(str(request_id))
            if request is None:
                return False, _("That request no longer exists.")
            if request.get("status") != "pending":
                return False, _("That request is already resolved.")
            teams = await self.config.guild(guild).teams()
            team = teams.get(str(request.get("team_id")))
            request["status"] = "cancelled"
            request["resolved_at"] = int(time.time())
            request["resolved_by"] = actor.id
            requests[str(request_id)] = request
            await self.config.guild(guild).requests.set(requests)
            if team is not None:
                await self._edit_card(guild, request, team)
        target = guild.get_member(int(request.get("user_id", 0)))
        if target is not None:
            with contextlib.suppress(discord.HTTPException):
                await target.send(
                    _("ℹ️ Your request for **{team}** was cancelled.").format(
                        team=(team or {}).get("name", "?")
                    )
                )
        await self._log_action(guild, "cancelled", request, team, actor=actor)
        return True, _("✅ Request #{id} cancelled.").format(id=request_id)

    # ------------------------------------------------------------------- sweep

    @tasks.loop(minutes=SWEEP_MINUTES)
    async def expire_loop(self) -> None:
        try:
            await self._sweep_all()
        except Exception:
            log.exception("Team role request sweep failed")

    async def _sweep_all(self) -> None:
        for guild in list(self.bot.guilds):
            try:
                await self._sweep_guild(guild)
            except Exception:
                log.exception("Team role request sweep failed in guild %s", guild.id)

    async def _sweep_guild(self, guild: discord.Guild) -> None:
        async with self._locks[guild.id]:
            requests = await self.config.guild(guild).requests()
            teams = await self.config.guild(guild).teams()
            now = int(time.time())
            changed = False
            to_edit: List[dict] = []
            for request_id in list(requests):
                request = requests[request_id]
                if request.get("status") == "pending" and now >= int(request.get("expires_at", 0)):
                    request["status"] = "expired"
                    request["resolved_at"] = now
                    changed = True
                    to_edit.append(request)
                elif request.get("status") != "pending":
                    reference = int(request.get("resolved_at") or request.get("created_at") or now)
                    if now - reference > PRUNE_AFTER:
                        del requests[request_id]
                        changed = True
            cooldowns = await self.config.guild(guild).cooldowns()
            cooldown_changed = False
            for uid, timestamp in list(cooldowns.items()):
                if now - int(timestamp) > PRUNE_AFTER:
                    del cooldowns[uid]
                    cooldown_changed = True
            if changed:
                await self.config.guild(guild).requests.set(requests)
            if cooldown_changed:
                await self.config.guild(guild).cooldowns.set(cooldowns)
            for request in to_edit:
                team = teams.get(str(request.get("team_id")))
                await self._edit_card(guild, request, team)
            for request in to_edit:
                team = teams.get(str(request.get("team_id")))
                await self._log_action(guild, "expired", request, team)

    # ---------------------------------------------------------------- commands

    @commands.hybrid_group(name="teamroles")
    async def teamroles(self, ctx: commands.Context) -> None:
        """Team role requests confirmed by the team itself."""
        if ctx.invoked_subcommand is None:
            await self._reply(ctx, self._help_text(ctx))

    def _help_text(self, ctx: commands.Context) -> str:
        return _(
            "**Team roles**\n"
            "`{pedir}` — request a team role.\n"
            "`{lista}` — see the registered teams.\n"
            "`{admin}` — open the admin board (admin).\n"
            "`{panel}` — publish the request panel (admin).\n"
            "`{config}` — show or change the settings (admin).\n"
            "`{solicitudes}` — list requests (admin)."
        ).format(
            pedir=_command_path(ctx, "pedir"),
            lista=_command_path(ctx, "lista"),
            admin=_command_path(ctx, "admin"),
            panel=_command_path(ctx, "panel"),
            config=_command_path(ctx, "config"),
            solicitudes=_command_path(ctx, "solicitudes"),
        )

    @teamroles.command(name="pedir")
    @app_commands.describe(equipo="Nombre del equipo. Si lo omites, eliges en un desplegable.")
    async def equipos_pedir(self, ctx: commands.Context, *, equipo: Optional[str] = None) -> None:
        """Request the role of a team."""
        guild = await self._require_guild(ctx)
        if guild is None:
            return
        teams = await self.config.guild(guild).teams()
        if not teams:
            await self._reply(ctx, _("There are no teams registered yet. Tell an admin."))
            return
        if equipo is None:
            await self._reply(
                ctx,
                _("Pick your team."),
                view=TeamSelectView(self, teams),
                delete_after=180.0,
            )
            return
        found = self._find_team_by_name(teams, equipo)
        if found is None:
            await self._reply(ctx, _("There is no team named **{name}**.").format(name=_clean(equipo)))
            return
        team_id, _team = found
        ok, message = await self.apply_request(guild, int(team_id), ctx.author)
        await self._reply(ctx, message)

    @teamroles.command(name="lista")
    async def equipos_lista(self, ctx: commands.Context) -> None:
        """List the registered teams."""
        guild = await self._require_guild(ctx)
        if guild is None:
            return
        teams = await self.config.guild(guild).teams()
        if not teams:
            await self._reply(ctx, _("There are no teams registered yet. Tell an admin."))
            return
        embed = discord.Embed(
            title=_("🎟️ Teams ({count})").format(count=len(teams)),
            colour=COLOR_PENDING,
        )
        ordered = sorted(teams.values(), key=lambda item: str(item.get("name", "")).casefold())
        for team in ordered[:25]:
            role = guild.get_role(int(team.get("role_id", 0)))
            channel = guild.get_channel(int(team.get("channel_id", 0)))
            embed.add_field(
                name=team.get("name", "?"),
                value=_("{role} · {channel}").format(
                    role=role.mention if role is not None else _("role missing"),
                    channel=channel.mention if isinstance(channel, discord.TextChannel) else _("channel missing"),
                ),
                inline=False,
            )
        if len(ordered) > 25:
            embed.set_footer(text=_("… and {n} more.").format(n=len(ordered) - 25))
        if self.bot.user is not None:
            embed.set_author(name=_("EquiposRoles"), icon_url=self.bot.user.display_avatar.url)
        await self._reply(ctx, embed=embed)

    @teamroles.command(name="panel")
    @commands.admin_or_permissions(manage_guild=True)
    @app_commands.describe(canal="Canal donde se publica el panel. Por defecto, el configurado o este.")
    async def equipos_panel(
        self, ctx: commands.Context, canal: Optional[discord.TextChannel] = None
    ) -> None:
        """Publish the request panel."""
        guild = await self._require_guild(ctx)
        if guild is None:
            return
        configured = await self.config.guild(guild).panel_channel_id()
        channel = canal
        if channel is None and configured:
            channel = guild.get_channel(int(configured))
        if channel is None:
            channel = ctx.channel
        if not isinstance(channel, discord.TextChannel):
            await self._reply(ctx, _("That channel is not a text channel."))
            return
        ok, message = await self.publish_panel(guild, channel)
        await self._reply(ctx, message)

    @teamroles.command(name="add")
    @commands.admin_or_permissions(manage_guild=True)
    @app_commands.describe(
        nombre="Nombre visible del equipo.",
        rol="Rol de Discord que entregará el bot.",
        canal="Canal privado donde el equipo confirma o rechaza.",
    )
    async def equipos_add(
        self,
        ctx: commands.Context,
        nombre: str,
        rol: discord.Role,
        canal: discord.TextChannel,
    ) -> None:
        """Register a team with its role and confirmation channel."""
        guild = await self._require_guild(ctx)
        if guild is None:
            return
        ok, message = await self.add_team(guild, nombre, rol, canal)
        await self._reply(ctx, message)

    @teamroles.command(name="remove")
    @commands.admin_or_permissions(manage_guild=True)
    @app_commands.describe(nombre="Nombre del equipo a eliminar.")
    async def equipos_remove(self, ctx: commands.Context, *, nombre: str) -> None:
        """Delete a team."""
        guild = await self._require_guild(ctx)
        if guild is None:
            return
        ok, message = await self.remove_team(guild, nombre)
        await self._reply(ctx, message)

    @teamroles.command(name="config")
    @commands.admin_or_permissions(manage_guild=True)
    @app_commands.describe(
        canal_panel="Canal del panel de solicitudes.",
        canal_log="Canal de auditoría.",
        cooldown="Minutos de espera entre solicitudes por usuario.",
        caducidad="Horas antes de que caduque una solicitud.",
        quitar_log="Quitar el canal de auditoría.",
    )
    async def equipos_config(
        self,
        ctx: commands.Context,
        canal_panel: Optional[discord.TextChannel] = None,
        canal_log: Optional[discord.TextChannel] = None,
        cooldown: Optional[int] = None,
        caducidad: Optional[int] = None,
        quitar_log: bool = False,
    ) -> None:
        """Show or change the settings."""
        guild = await self._require_guild(ctx)
        if guild is None:
            return
        if canal_log is not None and quitar_log:
            await self._reply(ctx, _("You cannot set and remove the log channel at the same time."))
            return
        if cooldown is not None and not (MIN_COOLDOWN_MINUTES <= cooldown <= MAX_COOLDOWN_MINUTES):
            await self._reply(
                ctx,
                _("The cooldown must be between {min} and {max} minutes.").format(
                    min=MIN_COOLDOWN_MINUTES, max=MAX_COOLDOWN_MINUTES
                ),
            )
            return
        if caducidad is not None and not (MIN_EXPIRY_HOURS <= caducidad <= MAX_EXPIRY_HOURS):
            await self._reply(
                ctx,
                _("The expiry must be between {min} and {max} hours.").format(
                    min=MIN_EXPIRY_HOURS, max=MAX_EXPIRY_HOURS
                ),
            )
            return
        if canal_log is not None and not self._channel_ready(guild, canal_log):
            await self._reply(ctx, _("I cannot post in that channel. Check my permissions there."))
            return
        if canal_panel is not None and not self._channel_ready(guild, canal_panel):
            await self._reply(ctx, _("I cannot post in that channel. Check my permissions there."))
            return

        config = self.config.guild(guild)
        if canal_panel is not None:
            await config.panel_channel_id.set(canal_panel.id)
        if canal_log is not None:
            await config.log_channel_id.set(canal_log.id)
        if quitar_log:
            await config.log_channel_id.set(None)
        if cooldown is not None:
            await config.cooldown_seconds.set(int(cooldown) * 60)
        if caducidad is not None:
            await config.expiry_seconds.set(int(caducidad) * 3600)

        await self._reply(ctx, embed=await self.config_embed(guild))

    @teamroles.command(name="solicitudes")
    @commands.admin_or_permissions(manage_guild=True)
    @app_commands.describe(estado="Qué solicitudes listar.")
    @app_commands.choices(
        estado=[
            app_commands.Choice(name="Pendientes", value="pending"),
            app_commands.Choice(name="Aprobadas", value="approved"),
            app_commands.Choice(name="Rechazadas", value="rejected"),
            app_commands.Choice(name="Caducadas", value="expired"),
            app_commands.Choice(name="Canceladas", value="cancelled"),
            app_commands.Choice(name="Todas", value="all"),
        ]
    )
    async def equipos_solicitudes(self, ctx: commands.Context, estado: str = "pending") -> None:
        """List requests by status."""
        guild = await self._require_guild(ctx)
        if guild is None:
            return
        estado = str(estado).casefold()
        valid = {value for value, _label in STATUS_CHOICES}
        if estado not in valid:
            await self._reply(ctx, _("Status must be one of: {values}.").format(values=", ".join(sorted(valid))))
            return
        embed = await self.requests_embed(guild, estado)
        if embed is None:
            await self._reply(ctx, _("There are no requests with that status."))
            return
        await self._reply(ctx, embed=embed)

    @teamroles.command(name="cancelar")
    @commands.admin_or_permissions(manage_guild=True)
    @app_commands.describe(solicitud="ID de la solicitud a cancelar.")
    async def equipos_cancelar(self, ctx: commands.Context, solicitud: int) -> None:
        """Cancel a pending request."""
        guild = await self._require_guild(ctx)
        if guild is None:
            return
        ok, message = await self.cancel_request(guild, int(solicitud), ctx.author)
        await self._reply(ctx, message)

    @teamroles.command(name="admin")
    @commands.admin_or_permissions(manage_guild=True)
    async def teamroles_admin(self, ctx: commands.Context) -> None:
        """Manage teams and settings from a board."""
        guild = await self._require_guild(ctx)
        if guild is None:
            return
        embed = discord.Embed(
            title=_("🛠️ Team role admin"),
            description=_(
                "Everything from here: publish the panel, register or delete teams, "
                "review requests and change the settings."
            ),
            colour=COLOR_PENDING,
        )
        if self.bot.user is not None:
            embed.set_author(name=_("EquiposRoles"), icon_url=self.bot.user.display_avatar.url)
        await self._reply(ctx, embed=embed, view=AdminView(self), delete_after=600.0)
