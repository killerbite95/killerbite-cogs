from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

import discord

if TYPE_CHECKING:
    from .events import TriniEvents


def _cog(interaction: discord.Interaction) -> Optional["TriniEvents"]:
    return interaction.client.get_cog("TriniEvents")  # type: ignore[attr-defined]


class EventButton(discord.ui.DynamicItem[discord.ui.Button], template=r"trinievt:(?P<action>join|leave|remind|checkin):(?P<eid>\d+)"):
    STYLES = {
        "join": ("Participar", "✅", discord.ButtonStyle.green),
        "leave": ("Cancelar plaza", "❌", discord.ButtonStyle.red),
        "remind": ("Recordarme", "🔔", discord.ButtonStyle.grey),
        "checkin": ("Check-in", "✋", discord.ButtonStyle.blurple),
    }

    def __init__(self, action: str, event_id: int):
        label, emoji, style = self.STYLES[action]
        super().__init__(
            discord.ui.Button(label=label, emoji=emoji, style=style, custom_id=f"trinievt:{action}:{event_id}")
        )
        self.action = action
        self.event_id = event_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str], /):
        return cls(match["action"], int(match["eid"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        cog = _cog(interaction)
        if cog is None or interaction.guild is None:
            return await interaction.response.send_message("Trini Events no esta disponible.", ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        text = await cog.handle_button(interaction, self.action, self.event_id)
        await interaction.followup.send(text, ephemeral=True)


def event_view(event: Dict[str, Any], *, checkin_open: bool) -> Optional[discord.ui.View]:
    view = discord.ui.View(timeout=None)
    active = event["status"] in ("scheduled", "ongoing")
    if active:
        if event["kind"] == "arencup":
            view.add_item(EventButton("remind", event["id"]))
        else:
            view.add_item(EventButton("join", event["id"]))
            view.add_item(EventButton("leave", event["id"]))
            view.add_item(EventButton("remind", event["id"]))
            if checkin_open:
                view.add_item(EventButton("checkin", event["id"]))
    url = (event.get("arencup") or {}).get("url")
    if url and url.startswith(("http://", "https://")):
        view.add_item(discord.ui.Button(label="Ver torneo", emoji="🏆", url=url))
    return view if view.children else None


class EventModal(discord.ui.Modal):
    def __init__(self, on_submit: Callable, *, title: str = "Crear evento", defaults: Optional[Dict[str, str]] = None):
        super().__init__(title=title, timeout=600)
        d = defaults or {}
        self._on_submit = on_submit
        self.name = discord.ui.TextInput(label="Nombre", placeholder="Noche de Minecraft", max_length=100, default=d.get("name"))
        self.date = discord.ui.TextInput(label="Fecha", placeholder="02/10/2026 22:00 · viernes 22:00 · +2h", max_length=40, default=d.get("date"))
        self.slots = discord.ui.TextInput(label="Plazas (0 = sin limite)", placeholder="20", max_length=4, required=False, default=d.get("slots"))
        self.duration = discord.ui.TextInput(label="Duracion (minutos)", placeholder="120", max_length=4, required=False, default=d.get("duration"))
        self.description = discord.ui.TextInput(
            label="Descripcion", style=discord.TextStyle.paragraph, max_length=2000, required=False, default=d.get("description")
        )
        for item in (self.name, self.date, self.slots, self.duration, self.description):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self._on_submit(
            interaction,
            {
                "name": self.name.value.strip(),
                "date": self.date.value.strip(),
                "slots": (self.slots.value or "0").strip(),
                "duration": (self.duration.value or "").strip(),
                "description": (self.description.value or "").strip(),
            },
        )


class ArenCupModal(discord.ui.Modal):
    def __init__(self, on_submit: Callable, *, defaults: Optional[Dict[str, str]] = None):
        super().__init__(title="Evento ArenCup", timeout=600)
        d = defaults or {}
        self._on_submit = on_submit
        self.name = discord.ui.TextInput(label="Nombre", placeholder="ArenCup Friday Cup #14", max_length=100, default=d.get("name"))
        self.start = discord.ui.TextInput(label="Inicio", placeholder="02/10/2026 19:00", max_length=40, default=d.get("start"))
        self.checkin = discord.ui.TextInput(label="Check-in", placeholder="02/10/2026 18:30", max_length=40, required=False, default=d.get("checkin"))
        self.url = discord.ui.TextInput(label="URL del torneo", placeholder="https://arencup.com/...", max_length=300, required=False, default=d.get("url"))
        self.teams = discord.ui.TextInput(label="Equipos", placeholder="16", max_length=4, required=False, default=d.get("teams"))
        for item in (self.name, self.start, self.checkin, self.url, self.teams):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self._on_submit(
            interaction,
            {
                "name": self.name.value.strip(),
                "start": self.start.value.strip(),
                "checkin": (self.checkin.value or "").strip(),
                "url": (self.url.value or "").strip(),
                "teams": (self.teams.value or "").strip(),
            },
        )


class OpenModalView(discord.ui.View):
    """Para comandos con prefijo: un boton que abre el modal (los modales requieren interaccion)."""

    def __init__(self, author: discord.abc.User, modal_factory: Callable[[], discord.ui.Modal]):
        super().__init__(timeout=300)
        self.author = author
        self.modal_factory = modal_factory

    @discord.ui.button(label="Abrir formulario", emoji="📝", style=discord.ButtonStyle.blurple)
    async def open(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            return await interaction.response.send_message("Este formulario no es tuyo.", ephemeral=True)
        await interaction.response.send_modal(self.modal_factory())
