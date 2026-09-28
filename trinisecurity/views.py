from __future__ import annotations

import io
import re
from typing import TYPE_CHECKING, Optional

import discord
from redbot.core.i18n import Translator, set_contextual_locales_from_guild

_ = Translator("TriniSecurity", __file__)

if TYPE_CHECKING:
    from .security import TriniSecurity


def _cog(interaction: discord.Interaction) -> Optional["TriniSecurity"]:
    return interaction.client.get_cog("TriniSecurity")  # type: ignore[attr-defined]


async def _check_staff(interaction: discord.Interaction, cog: "TriniSecurity") -> bool:
    if interaction.guild is None or not isinstance(interaction.user, discord.Member):
        return False
    level = await cog.get_authority_level(interaction.user)
    if level in ("owner", "extra_owner", "trusted_admin", "admin"):
        return True
    await interaction.response.send_message(_("You don't have permission for this."), ephemeral=True)
    return False


class CompareButton(discord.ui.DynamicItem[discord.ui.Button], template=r"trinisec:cmp:(?P<ts>\d+)"):
    """Compara el estado actual con el ultimo backup anterior a ``ts`` (0 = ultimo)."""

    def __init__(self, ts: int = 0):
        super().__init__(
            discord.ui.Button(
                label=_("Compare with backup"),
                emoji="📦",
                style=discord.ButtonStyle.grey,
                custom_id=f"trinisec:cmp:{ts}",
            )
        )
        self.ts = ts
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Los callbacks no pasan por un comando: se usa el idioma del servidor.
        await set_contextual_locales_from_guild(interaction.client, interaction.guild)
        return await super().interaction_check(interaction)

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str], /):
        return cls(int(match["ts"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        cog = _cog(interaction)
        if cog is None or not await _check_staff(interaction, cog):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        embeds, error = await cog.compare_with_backup(interaction.guild, self.ts or None)
        if error:
            return await interaction.followup.send(error, ephemeral=True)
        await interaction.followup.send(embeds=embeds[:10], ephemeral=True)


class IncidentReportButton(discord.ui.DynamicItem[discord.ui.Button], template=r"trinisec:rep:(?P<id>\d+)"):
    def __init__(self, incident_id: int):
        super().__init__(
            discord.ui.Button(
                label=_("Generate report"),
                emoji="📝",
                style=discord.ButtonStyle.blurple,
                custom_id=f"trinisec:rep:{incident_id}",
            )
        )
        self.incident_id = incident_id
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Los callbacks no pasan por un comando: se usa el idioma del servidor.
        await set_contextual_locales_from_guild(interaction.client, interaction.guild)
        return await super().interaction_check(interaction)

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str], /):
        return cls(int(match["id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        cog = _cog(interaction)
        if cog is None or not await _check_staff(interaction, cog):
            return
        text = await cog.build_incident_report(interaction.guild, self.incident_id)
        if text is None:
            return await interaction.response.send_message(_("Incident not found."), ephemeral=True)
        fp = io.BytesIO(text.encode("utf-8"))
        await interaction.response.send_message(
            file=discord.File(fp, filename=f"incident-{self.incident_id}.txt"), ephemeral=True
        )


class IncidentCompareButton(discord.ui.DynamicItem[discord.ui.Button], template=r"trinisec:icmp:(?P<id>\d+)"):
    def __init__(self, incident_id: int):
        super().__init__(
            discord.ui.Button(
                label=_("Compare previous state"),
                emoji="📦",
                style=discord.ButtonStyle.grey,
                custom_id=f"trinisec:icmp:{incident_id}",
            )
        )
        self.incident_id = incident_id
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Los callbacks no pasan por un comando: se usa el idioma del servidor.
        await set_contextual_locales_from_guild(interaction.client, interaction.guild)
        return await super().interaction_check(interaction)

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str], /):
        return cls(int(match["id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        cog = _cog(interaction)
        if cog is None or not await _check_staff(interaction, cog):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        incident = (await cog.config.guild(interaction.guild).incidents()).get(str(self.incident_id))
        if incident is None:
            return await interaction.followup.send(_("Incident not found."), ephemeral=True)
        embeds, error = await cog.compare_with_backup(interaction.guild, incident["start"])
        if error:
            return await interaction.followup.send(error, ephemeral=True)
        await interaction.followup.send(embeds=embeds[:10], ephemeral=True)


class ReleaseButton(discord.ui.DynamicItem[discord.ui.Button], template=r"trinisec:rel:(?P<uid>\d+)"):
    def __init__(self, user_id: int):
        super().__init__(
            discord.ui.Button(
                label=_("Release quarantine"),
                emoji="🔓",
                style=discord.ButtonStyle.red,
                custom_id=f"trinisec:rel:{user_id}",
            )
        )
        self.user_id = user_id
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Los callbacks no pasan por un comando: se usa el idioma del servidor.
        await set_contextual_locales_from_guild(interaction.client, interaction.guild)
        return await super().interaction_check(interaction)

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str], /):
        return cls(int(match["uid"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        cog = _cog(interaction)
        if cog is None or interaction.guild is None:
            return
        level = await cog.get_authority_level(interaction.user)
        if level not in ("owner", "extra_owner", "trusted_admin") or interaction.user.id == self.user_id:
            return await interaction.response.send_message(
                _("Only the Owner, Extra Owners or Trusted Admins can release a quarantine."), ephemeral=True
            )
        await interaction.response.defer(ephemeral=True)
        ok, msg = await cog.release_quarantine(interaction.guild, self.user_id, interaction.user)
        await interaction.followup.send(msg, ephemeral=True)


DYNAMIC_ITEMS = (CompareButton, IncidentReportButton, IncidentCompareButton, ReleaseButton)


def incident_view(incident_id: int, quarantined_user: Optional[int] = None, has_backups: bool = True) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    if has_backups:
        view.add_item(IncidentCompareButton(incident_id))
    view.add_item(IncidentReportButton(incident_id))
    if quarantined_user:
        view.add_item(ReleaseButton(quarantined_user))
    return view


def compare_view(ts: int = 0) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(CompareButton(ts))
    return view


class ConfirmView(discord.ui.View):
    def __init__(self, author: discord.abc.User, *, label: str = "Continuar", style=discord.ButtonStyle.green):
        super().__init__(timeout=60)
        self.author = author
        self.value: Optional[bool] = None
        self.confirm.label = label
        self.confirm.style = style

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        await set_contextual_locales_from_guild(interaction.client, interaction.guild)
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(_("Only whoever ran the command can confirm."), ephemeral=True)
            return False
        return True

    @discord.ui.button(label=_("Continue"), style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label=_("Cancel"), style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.stop()
        await interaction.response.defer()
