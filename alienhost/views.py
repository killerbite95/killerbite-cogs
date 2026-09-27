from __future__ import annotations

from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, List, Optional

import discord

if TYPE_CHECKING:
    from .alienhost import AlienHost

ALERT_KINDS = {
    "offline": "Servidor offline",
    "ram": "RAM > 90 % (10 min)",
    "cpu": "CPU > 95 % (10 min)",
    "backup_failed": "Backup fallido",
    "restarted": "Servidor reiniciado",
}


class LinkModal(discord.ui.Modal):
    """Pide URL del panel y clave API sin que queden en el chat."""

    def __init__(self, on_submit: Callable[[discord.Interaction, str, str], Awaitable[None]], *, default_panel: str, title: str = "Vincular AlienHost", key_label: str = "Clave API del area cliente (pacc_…)"):
        super().__init__(title=title, timeout=600)
        self._cb = on_submit
        self.panel = discord.ui.TextInput(label="URL del panel", default=default_panel, max_length=200)
        self.key = discord.ui.TextInput(
            label=key_label,
            placeholder="Perfil → Claves API → Crear",
            min_length=20,
            max_length=200,
        )
        self.add_item(self.panel)
        self.add_item(self.key)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self._cb(interaction, self.panel.value.strip(), self.key.value.strip())


class OpenModalView(discord.ui.View):
    def __init__(self, author: discord.abc.User, factory: Callable[[], discord.ui.Modal], label: str = "Conectar cuenta"):
        super().__init__(timeout=300)
        self.author = author
        self.factory = factory
        self.open.label = label

    @discord.ui.button(label="Conectar cuenta", emoji="🔗", style=discord.ButtonStyle.blurple)
    async def open(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            return await interaction.response.send_message("Este boton no es para ti. Usa el comando `alienhost link`.", ephemeral=True)
        await interaction.response.send_modal(self.factory())


class OwnerView(discord.ui.View):
    def __init__(self, owner_id: int, *, timeout: float = 600):
        super().__init__(timeout=timeout)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Este panel no es tuyo.", ephemeral=True)
            return False
        return True


class ConfirmView(OwnerView):
    def __init__(self, owner_id: int, label: str):
        super().__init__(owner_id, timeout=60)
        self.value: Optional[bool] = None
        self.yes.label = label

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.red)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.stop()
        await interaction.response.edit_message(content="⏳ Enviando…", view=None)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.grey)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.stop()
        await interaction.response.edit_message(content="Cancelado.", view=None)


POWER_BUTTONS = [
    ("start", "Iniciar", "▶️", discord.ButtonStyle.green, "control.start"),
    ("restart", "Reiniciar", "🔄", discord.ButtonStyle.blurple, "control.restart"),
    ("stop", "Detener", "⏹", discord.ButtonStyle.grey, "control.stop"),
    ("kill", "Kill", "💀", discord.ButtonStyle.red, "control.stop"),
]


def has_perm(perms: List[str], needed: str) -> bool:
    return "*" in perms or needed in perms or needed.split(".")[0] + ".*" in perms


class ServerPanel(OwnerView):
    def __init__(self, cog: "AlienHost", owner_id: int, identifier: str, perms: List[str], guild_id: Optional[int]):
        super().__init__(owner_id)
        self.cog = cog
        self.identifier = identifier
        self.guild_id = guild_id
        for signal, label, emoji, style, perm in POWER_BUTTONS:
            btn = discord.ui.Button(label=label, emoji=emoji, style=style, disabled=not has_perm(perms, perm), row=0)
            btn.callback = self._power(signal)
            self.add_item(btn)
        backups = discord.ui.Button(label="Backups", emoji="💾", style=discord.ButtonStyle.grey, disabled=not has_perm(perms, "backup.read"), row=1)
        backups.callback = self._backups
        self.add_item(backups)
        refresh = discord.ui.Button(label="Actualizar", emoji="🔃", style=discord.ButtonStyle.grey, row=1)
        refresh.callback = self._refresh
        self.add_item(refresh)
        alerts = discord.ui.Button(label="Alertas", emoji="🔔", style=discord.ButtonStyle.grey, row=1)
        alerts.callback = self._alerts
        self.add_item(alerts)

    def _power(self, signal: str):
        async def callback(interaction: discord.Interaction):
            await self.cog.power_flow(interaction, self.identifier, signal)
        return callback

    async def _backups(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        embed, view = await self.cog.backups_panel(interaction.user, self.identifier, self.guild_id)
        kwargs: Dict[str, Any] = {"embed": embed, "ephemeral": True}
        if view is not None:
            kwargs["view"] = view
        await interaction.followup.send(**kwargs)

    async def _refresh(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed, _ = await self.cog.server_embed(interaction.user, self.identifier)
        await interaction.edit_original_response(embed=embed, view=self)

    async def _alerts(self, interaction: discord.Interaction):
        await self.cog.alerts_flow(interaction, self.identifier)


class ServerSelectView(OwnerView):
    def __init__(self, cog: "AlienHost", owner_id: int, servers: List[Dict[str, Any]], guild_id: Optional[int]):
        super().__init__(owner_id)
        self.cog = cog
        self.guild_id = guild_id
        select = discord.ui.Select(
            placeholder="Elige un servidor",
            options=[
                discord.SelectOption(label=s.get("name", s["identifier"])[:100], value=s["uuid"], description=f"{s.get('node', '')} · {s['identifier']}"[:100])
                for s in servers[:25]
            ],
        )
        select.callback = self._select
        self.select = select
        self.add_item(select)

    async def _select(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        identifier = self.select.values[0]
        embed, perms = await self.cog.server_embed(interaction.user, identifier)
        view = ServerPanel(self.cog, interaction.user.id, identifier, perms, self.guild_id) if perms is not None else None
        kwargs: Dict[str, Any] = {"embed": embed, "ephemeral": True}
        if view is not None:
            kwargs["view"] = view
        await interaction.followup.send(**kwargs)


class BackupsView(OwnerView):
    def __init__(self, cog: "AlienHost", owner_id: int, identifier: str, guild_id: Optional[int], can_create: bool):
        super().__init__(owner_id)
        self.cog = cog
        self.identifier = identifier
        self.guild_id = guild_id
        self.create.disabled = not can_create

    @discord.ui.button(label="Crear backup", emoji="💾", style=discord.ButtonStyle.green)
    async def create(self, interaction: discord.Interaction, button: discord.ui.Button):
        button.disabled = True
        await interaction.response.edit_message(view=self)
        msg = await self.cog.create_backup_action(interaction.user, self.identifier, self.guild_id)
        await interaction.followup.send(msg, ephemeral=True)


class AlertsView(OwnerView):
    def __init__(self, cog: "AlienHost", owner_id: int, identifier: str, name: str, current: Dict[str, bool]):
        super().__init__(owner_id, timeout=300)
        self.cog = cog
        self.identifier = identifier
        self.name = name
        self.state = {k: bool(current.get(k, False)) for k in ALERT_KINDS}
        for key in ALERT_KINDS:
            btn = discord.ui.Button(label=ALERT_KINDS[key], row=0 if key in ("offline", "ram", "cpu") else 1)
            btn.callback = self._toggle(key)
            btn.custom_id = f"alert:{key}"
            self.add_item(btn)
        self._style()

    def _style(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.custom_id and item.custom_id.startswith("alert:"):
                key = item.custom_id.split(":", 1)[1]
                item.style = discord.ButtonStyle.green if self.state[key] else discord.ButtonStyle.grey
                item.emoji = "✅" if self.state[key] else "❌"

    def embed(self) -> discord.Embed:
        lines = [f"{ALERT_KINDS[k]:<24} {'✅' if v else '❌'}" for k, v in self.state.items()]
        e = discord.Embed(title=f"🔔 Alertas · {self.name}", description="```\n" + "\n".join(lines) + "\n```", color=discord.Color.blurple())
        e.set_footer(text="Las alertas llegan por mensaje privado. Pulsa para activar/desactivar.")
        return e

    def _toggle(self, key: str):
        async def callback(interaction: discord.Interaction):
            self.state[key] = not self.state[key]
            self._style()
            await self.cog.save_alerts(interaction.user, self.identifier, self.name, self.state)
            await interaction.response.edit_message(embed=self.embed(), view=self)
        return callback


class PrivateReplyView(discord.ui.View):
    """Con comandos de prefijo: muestra la respuesta como mensaje efimero solo al autor."""

    def __init__(self, owner_id: int, payload: Dict[str, Any]):
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.payload = payload
        self.message: Optional[discord.Message] = None

    @discord.ui.button(label="Ver en privado", emoji="🔒", style=discord.ButtonStyle.blurple)
    async def show(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("Esto no es para ti.", ephemeral=True)
        await interaction.response.send_message(ephemeral=True, **self.payload)
        self.stop()
        try:
            await interaction.message.delete()
        except discord.HTTPException:
            pass

    async def on_timeout(self) -> None:
        if self.message is not None:
            try:
                await self.message.delete()
            except discord.HTTPException:
                pass


class SearchModal(discord.ui.Modal):
    def __init__(self, on_submit: Callable[[discord.Interaction, str], Awaitable[None]], current: str = ""):
        super().__init__(title="Buscar servidor", timeout=300)
        self._cb = on_submit
        self.query = discord.ui.TextInput(
            label="Nombre, identificador, UUID o nodo",
            placeholder="Vacio = quitar filtro",
            default=current or None,
            required=False,
            max_length=100,
        )
        self.add_item(self.query)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self._cb(interaction, (self.query.value or "").strip())


class AdminServerBrowseView(OwnerView):
    """Navegador paginado de TODOS los servidores del panel (`alienhost admin servers`).

    Muestra 25 por pagina (el maximo de un desplegable de Discord), con
    anterior/siguiente y un buscador. Al elegir uno se abre el mismo panel que
    `alienhost servers` (power, backups, alertas), usando la clave del admin.
    """

    PAGE_SIZE = 25
    STATE_ICON = {"running": "🟢", "starting": "🟡", "stopping": "🟠", "offline": "🔴"}

    def __init__(self, cog: "AlienHost", owner_id: int, servers: List[Dict[str, Any]], guild_id: Optional[int], query: str = ""):
        super().__init__(owner_id, timeout=600)
        self.cog = cog
        self.guild_id = guild_id
        self.all_servers = sorted(servers, key=lambda s: (s.get("node") or "", (s.get("name") or "").lower()))
        self.page = 0
        self._states: Dict[str, Optional[str]] = {}
        self.apply_filter(query)

    # ---- datos ----

    def apply_filter(self, query: str) -> None:
        self.query = query
        q = query.lower()
        if not q:
            self.filtered = self.all_servers
        else:
            self.filtered = [
                s for s in self.all_servers
                if any(q in str(s.get(k) or "").lower() for k in ("name", "identifier", "uuid", "node"))
            ]
        self.page = 0

    @property
    def total_pages(self) -> int:
        return max(1, -(-len(self.filtered) // self.PAGE_SIZE))

    def current_chunk(self) -> List[Dict[str, Any]]:
        start = self.page * self.PAGE_SIZE
        return self.filtered[start:start + self.PAGE_SIZE]

    # ---- render ----

    async def render(self, user: discord.abc.User) -> discord.Embed:
        chunk = self.current_chunk()
        missing = [s["uuid"] for s in chunk if s["uuid"] not in self._states]
        if missing:
            self._states.update(await self.cog.fetch_states(user, missing))
        lines = []
        for s in chunk:
            status = s.get("status")
            if status == "suspended" or s.get("is_suspended"):
                icon = "⛔"
            elif status in ("installing", "install_failed", "reinstall_failed", "restoring_backup"):
                icon = "🔧"
            else:
                icon = self.STATE_ICON.get(self._states.get(s["uuid"]), "⚪")
            lines.append(f"{icon} **{s.get('name', '?')}** · {s.get('node', '?')} · `{s.get('identifier', '?')}`")
        embed = discord.Embed(
            title="🖥 Todos los servidores del panel",
            description="\n".join(lines) or "Ningun servidor coincide con la busqueda.",
            color=discord.Color.from_rgb(124, 92, 255),
        )
        footer = f"{len(self.filtered)} servidor(es)"
        if self.query:
            footer += f" de {len(self.all_servers)} · filtro: {self.query}"
        footer += f" · pagina {self.page + 1}/{self.total_pages}"
        embed.set_footer(text=footer)
        self._build_items()
        return embed

    def _build_items(self) -> None:
        self.clear_items()
        chunk = self.current_chunk()
        start = self.page * self.PAGE_SIZE
        select = discord.ui.Select(
            placeholder=f"Administrar servidor ({start + 1}-{start + len(chunk)})" if chunk else "Sin resultados",
            options=[
                discord.SelectOption(
                    label=(s.get("name") or s.get("identifier") or "?")[:100],
                    value=s["uuid"],
                    description=f"{s.get('node', '')} · {s.get('identifier', '')}"[:100],
                )
                for s in chunk
            ] or [discord.SelectOption(label="—", value="none")],
            disabled=not chunk,
            row=0,
        )
        select.callback = self._select
        self.add_item(select)
        for label, cb, disabled in (
            ("◀ Anterior", self._prev, self.page <= 0),
            ("Siguiente ▶", self._next, self.page >= self.total_pages - 1),
        ):
            btn = discord.ui.Button(label=label, style=discord.ButtonStyle.grey, disabled=disabled, row=1)
            btn.callback = cb
            self.add_item(btn)
        search = discord.ui.Button(label="Buscar", emoji="🔍", style=discord.ButtonStyle.blurple, row=1)
        search.callback = self._open_search
        self.add_item(search)
        refresh = discord.ui.Button(label="Actualizar", emoji="🔃", style=discord.ButtonStyle.grey, row=1)
        refresh.callback = self._refresh
        self.add_item(refresh)

    async def _rerender(self, interaction: discord.Interaction) -> None:
        if not interaction.response.is_done():
            await interaction.response.defer()
        embed = await self.render(interaction.user)
        await interaction.edit_original_response(embed=embed, view=self)

    # ---- callbacks ----

    async def _select(self, interaction: discord.Interaction) -> None:
        uuid = interaction.data["values"][0]
        if uuid == "none":
            return await interaction.response.defer()
        await interaction.response.defer(ephemeral=True, thinking=True)
        embed, perms = await self.cog.server_embed(interaction.user, uuid)
        kwargs: Dict[str, Any] = {"embed": embed, "ephemeral": True}
        if perms is not None:
            kwargs["view"] = ServerPanel(self.cog, interaction.user.id, uuid, perms, self.guild_id)
        await interaction.followup.send(**kwargs)

    async def _prev(self, interaction: discord.Interaction) -> None:
        self.page = max(0, self.page - 1)
        await self._rerender(interaction)

    async def _next(self, interaction: discord.Interaction) -> None:
        self.page = min(self.total_pages - 1, self.page + 1)
        await self._rerender(interaction)

    async def _open_search(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(SearchModal(self._on_search, self.query))

    async def _on_search(self, interaction: discord.Interaction, query: str) -> None:
        self.apply_filter(query)
        await self._rerender(interaction)

    async def _refresh(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        try:
            servers = await self.cog._admin_servers(interaction.user, fresh=True)
        except Exception as exc:  # PelicanError u otros: se informa sin romper la vista
            return await interaction.followup.send(f"❌ {getattr(exc, 'message', exc)}", ephemeral=True)
        self.all_servers = sorted(servers, key=lambda s: (s.get("node") or "", (s.get("name") or "").lower()))
        self._states.clear()
        page = self.page
        self.apply_filter(self.query)
        self.page = min(page, self.total_pages - 1)
        await self._rerender(interaction)
