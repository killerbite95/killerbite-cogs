"""
AlienHost Integration - gestiona tus servidores de AlienHost (Pelican) desde Discord.

Cada usuario vincula su cuenta con la URL del panel y una clave API de su
area cliente. Ambas se piden SIEMPRE en un modal (nunca en el chat), la clave
se valida contra el panel y se guarda cifrada.

By Killerbite95
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import defaultdict, deque
from typing import Any, Deque, Dict, List, Optional, Tuple

import aiohttp
import discord
from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path
from redbot.core.utils.chat_formatting import humanize_list

from .api import PelicanClient, PelicanError, normalize_panel
from .vault import Vault
from .views import (
    ALERT_KINDS,
    AdminServerBrowseView,
    AlertsView,
    BackupsView,
    ConfirmView,
    LinkModal,
    OpenModalView,
    ServerPanel,
    ServerSelectView,
    PrivateReplyView,
    has_perm,
)

log = logging.getLogger("red.killerbite95.alienhost")

DEFAULT_PANEL = "https://pelican.alienhost.es"
COLOR = discord.Color.from_rgb(124, 92, 255)
STATE = {
    "running": "🟢 Online",
    "starting": "🟡 Iniciando",
    "stopping": "🟠 Deteniendo",
    "offline": "🔴 Offline",
}
SERVER_STATUS = {
    "installing": "🔧 Instalando",
    "install_failed": "❌ Instalacion fallida",
    "reinstall_failed": "❌ Reinstalacion fallida",
    "restoring_backup": "⏪ Restaurando backup",
}
SIGNAL_LABEL = {"start": "iniciado", "restart": "reiniciado", "stop": "detenido", "kill": "forzado (kill)"}
CONFIRM_SIGNALS = {"restart", "stop", "kill"}
POWER_COOLDOWN = 10
POWER_PER_HOUR = 20
SUSTAIN = 600  # 10 minutos
KEY_LEAK_RE = re.compile(r"\b(pacc|papp|ptlc|ptla)_[A-Za-z0-9]{20,}")


def fmt_bytes(value: Optional[float]) -> str:
    if value is None:
        return "?"
    value = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit in ("GB", "TB") else f"{value:.0f} {unit}"
        value /= 1024
    return "?"


def fmt_uptime(ms: Optional[int]) -> str:
    if not ms:
        return "—"
    s = int(ms // 1000)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m = s // 60
    return f"{d}d {h}h" if d else (f"{h}h {m}m" if h else f"{m}m")


class AlienHost(commands.Cog):
    """Integracion con AlienHost: vincula tu clave API de Pelican y controla tus servidores desde Discord."""

    __author__ = "Killerbite95"
    __version__ = "1.0.0"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0x7121A11E, force_registration=True)
        self.config.register_global(
            allowed_panels=[DEFAULT_PANEL],
            default_panel=DEFAULT_PANEL,
            admin={"panel": None, "key": None},
            poll_interval=120,
            audit=[],
        )
        self.config.register_user(
            panel=None,
            api_key=None,
            account={},
            linked_at=None,
            alerts={},
        )
        self.config.register_guild(
            log_channel=None,
            admin_role=None,
            require_trusted=True,
        )
        self.vault = Vault(cog_data_path(self) / "vault.key")
        self.session: Optional[aiohttp.ClientSession] = None
        self._power_log: Dict[int, Deque[float]] = defaultdict(deque)
        self._server_cache: Dict[int, Tuple[float, List[Dict[str, Any]]]] = {}
        # Listado completo del panel (``type=admin-all``) por administrador.
        self._admin_servers_cache: Dict[int, Tuple[float, List[Dict[str, Any]]]] = {}
        self._alert_state: Dict[Tuple[int, str], Dict[str, Any]] = {}
        self._polls = 0
        self.p = "!"

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre = super().format_help_for_context(ctx)
        return f"{pre}\n\nVersion: {self.__version__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int) -> None:
        await self.config.user_from_id(user_id).clear()
        self._server_cache.pop(user_id, None)
        self._admin_servers_cache.pop(user_id, None)

    async def cog_load(self) -> None:
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        self.alert_loop.start()
        try:
            prefixes = await self.bot.get_valid_prefixes()
            self.p = next((x for x in prefixes if not x.startswith("<@")), self.p)
        except Exception:
            pass

    async def _private(self, ctx: commands.Context, **kwargs: Any) -> None:
        """Envia datos de la cuenta solo al autor.

        Con slash es un mensaje efimero; con prefijo en un servidor se publica un
        boton que muestra el contenido en privado (asi nada queda en el canal).
        """
        if ctx.interaction is not None:
            await ctx.send(ephemeral=True, **kwargs)
        elif ctx.guild is None:
            await ctx.send(**kwargs)
        else:
            view = PrivateReplyView(ctx.author.id, kwargs)
            view.message = await ctx.send(
                f"🔒 {ctx.author.mention}, pulsa para verlo en privado.",
                view=view,
                allowed_mentions=discord.AllowedMentions(users=[ctx.author]),
            )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Red de seguridad: si alguien pega una clave de Pelican en un canal, se borra."""
        if message.guild is None or message.author.bot or not KEY_LEAK_RE.search(message.content or ""):
            return
        await self._handle_leak(message)

    async def _handle_leak(self, message: discord.Message) -> None:
        deleted = False
        try:
            await message.delete()
            deleted = True
        except discord.HTTPException:
            pass
        text = (
            f"⚠️ {message.author.mention}, has pegado una clave API de Pelican en el chat"
            + (" y la he borrado." if deleted else " y **no he podido borrarla**.")
            + f" Por seguridad **eliminala en el panel** (Perfil → Claves API), crea otra y vinculala con `{self.p}alienhost link` (formulario privado)."
        )
        try:
            await message.channel.send(text, delete_after=30, allowed_mentions=discord.AllowedMentions(users=[message.author]))
        except discord.HTTPException:
            pass
        await self._audit(message.guild, message.author, "key_leak", f"en #{getattr(message.channel, 'name', '?')} · borrado={deleted}")

    async def cog_unload(self) -> None:
        self.alert_loop.cancel()
        if self.session is not None:
            await self.session.close()

    # ------------------------------------------------------------------
    # Clientes
    # ------------------------------------------------------------------

    async def client_for(self, user: discord.abc.User) -> Optional[PelicanClient]:
        data = await self.config.user(user).all()
        key = self.vault.decrypt(data["api_key"])
        if not data["panel"] or not key:
            return None
        return PelicanClient(self.session, data["panel"], key)

    async def admin_client(self) -> Optional[PelicanClient]:
        admin = await self.config.admin()
        key = self.vault.decrypt(admin.get("key"))
        if not admin.get("panel") or not key:
            return None
        return PelicanClient(self.session, admin["panel"], key)

    async def _panel_allowed(self, panel: str) -> bool:
        allowed = [normalize_panel(p) for p in await self.config.allowed_panels()]
        return panel in allowed

    # ------------------------------------------------------------------
    # Vinculacion
    # ------------------------------------------------------------------

    async def _on_link(self, interaction: discord.Interaction, panel_raw: str, key: str) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        panel = normalize_panel(panel_raw)
        if panel is None:
            return await interaction.followup.send("❌ URL del panel no valida.", ephemeral=True)
        if not await self._panel_allowed(panel):
            allowed = humanize_list([f"`{p}`" for p in await self.config.allowed_panels()])
            return await interaction.followup.send(f"❌ Ese panel no esta permitido. Paneles admitidos: {allowed}.", ephemeral=True)
        if key.startswith("papp_"):
            return await interaction.followup.send(
                "❌ Esa es una clave de **aplicacion** (`papp_`). Crea una clave en tu **area cliente**: Perfil → Claves API.",
                ephemeral=True,
            )
        if not key.startswith(("pacc_", "ptlc_")):
            return await interaction.followup.send("❌ Formato de clave no reconocido. Debe empezar por `pacc_`.", ephemeral=True)
        client = PelicanClient(self.session, panel, key)
        try:
            account = await client.account()
        except PelicanError as exc:
            return await interaction.followup.send(f"❌ No se pudo validar la clave: {exc.friendly}", ephemeral=True)
        async with self.config.user(interaction.user).all() as data:
            data["panel"] = panel
            data["api_key"] = self.vault.encrypt(key)
            data["account"] = {"uuid": account.get("uuid"), "username": account.get("username"), "2fa": bool(account.get("2fa_enabled"))}
            data["linked_at"] = int(time.time())
        self._server_cache.pop(interaction.user.id, None)
        self._admin_servers_cache.pop(interaction.user.id, None)
        await self._audit(interaction.guild, interaction.user, "link", panel)
        embed = discord.Embed(
            title="✅ Cuenta de AlienHost vinculada",
            color=discord.Color.green(),
            description=(
                f"Usuario del panel: **{account.get('username', '?')}**\nPanel: `{panel}`\n\n"
                "La clave se ha guardado **cifrada** y no aparecera en ningun mensaje.\n"
                f"Prueba ahora `{self.p}alienhost servers`."
            ),
        )
        if not account.get("2fa_enabled"):
            embed.add_field(name="⚠️ 2FA desactivado", value="Te recomendamos activar 2FA en tu cuenta del panel.", inline=False)
        embed.set_footer(text="Consejo: en el panel puedes limitar la clave a la IP del bot (IPs permitidas).")
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _on_admin_key(self, interaction: discord.Interaction, panel_raw: str, key: str) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        panel = normalize_panel(panel_raw)
        if panel is None or not await self._panel_allowed(panel):
            return await interaction.followup.send("❌ Panel no valido o no permitido.", ephemeral=True)
        if not key.startswith(("papp_", "ptla_")):
            return await interaction.followup.send("❌ Para administracion hace falta una clave de aplicacion (`papp_`).", ephemeral=True)
        client = PelicanClient(self.session, panel, key)
        try:
            await client.app_list("nodes", {"per_page": 1})
        except PelicanError as exc:
            return await interaction.followup.send(f"❌ No se pudo validar la clave: {exc.friendly}", ephemeral=True)
        await self.config.admin.set({"panel": panel, "key": self.vault.encrypt(key)})
        await self._audit(interaction.guild, interaction.user, "admin_key_set", panel)
        await interaction.followup.send("✅ Clave de administracion guardada (cifrada).", ephemeral=True)

    async def _open_modal(self, ctx: commands.Context, modal_factory, label: str) -> None:
        if ctx.interaction is not None:
            await ctx.interaction.response.send_modal(modal_factory())
        else:
            await ctx.send(
                "🔐 Por seguridad, los datos se introducen en un formulario privado. **Nunca pegues tu clave en el chat.**",
                view=OpenModalView(ctx.author, modal_factory, label),
            )

    # ------------------------------------------------------------------
    # Auditoria / logs
    # ------------------------------------------------------------------

    async def _audit(self, guild: Optional[discord.Guild], user: discord.abc.User, action: str, detail: str) -> None:
        async with self.config.audit() as audit:
            audit.append({"ts": int(time.time()), "user": user.id, "guild": guild.id if guild else None, "action": action, "detail": detail[:200]})
            del audit[:-500]
        if guild is None:
            return
        channel_id = await self.config.guild(guild).log_channel()
        channel = guild.get_channel_or_thread(channel_id) if channel_id else None
        if channel is None:
            return
        embed = discord.Embed(description=f"{user.mention} · `{action}` · {detail}", color=COLOR, timestamp=discord.utils.utcnow())
        embed.set_author(name="🖥 AlienHost")
        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass
        self.bot.dispatch("trini_alienhost_action", guild, user, action, detail)

    # ------------------------------------------------------------------
    # Servidores
    # ------------------------------------------------------------------

    async def _servers(self, user: discord.abc.User, *, fresh: bool = False) -> List[Dict[str, Any]]:
        cached = self._server_cache.get(user.id)
        if cached and not fresh and time.time() - cached[0] < 60:
            return cached[1]
        client = await self.client_for(user)
        if client is None:
            raise PelicanError(0, f"No tienes cuenta vinculada. Usa `{self.p}alienhost link`.")
        servers = await client.servers()
        self._server_cache[user.id] = (time.time(), servers)
        return servers

    async def fetch_states(self, user: discord.abc.User, uuids: List[str]) -> Dict[str, Optional[str]]:
        """Estado actual (running/offline/...) de varios servidores, 5 en paralelo."""
        client = await self.client_for(user)
        if client is None:
            return {u: None for u in uuids}
        sem = asyncio.Semaphore(5)

        async def one(uuid: str) -> Tuple[str, Optional[str]]:
            async with sem:
                try:
                    return uuid, (await client.resources(uuid)).get("current_state")
                except PelicanError:
                    return uuid, None

        return dict(await asyncio.gather(*(one(u) for u in uuids)))

    def _cached_name(self, user_id: int, uuid: str) -> str:
        """Nombre de un servidor ya listado (propio o via `admin servers`), o su UUID."""
        for cache in (self._server_cache, self._admin_servers_cache):
            for s in (cache.get(user_id) or (0, []))[1]:
                if s.get("uuid") == uuid:
                    return s.get("name", uuid)
        return uuid

    async def server_embed(self, user: discord.abc.User, identifier: str) -> Tuple[discord.Embed, Optional[List[str]]]:
        client = await self.client_for(user)
        if client is None:
            return discord.Embed(description=f"No tienes cuenta vinculada. Usa `{self.p}alienhost link`.", color=discord.Color.red()), None
        try:
            server, res = await asyncio.gather(client.server(identifier), client.resources(identifier))
        except PelicanError as exc:
            return discord.Embed(description=f"❌ {exc.friendly}", color=discord.Color.red()), None
        meta = server.get("_meta", {})
        perms = ["*"] if meta.get("is_server_owner") else list(meta.get("user_permissions", []))
        limits = server.get("limits", {})
        r = res.get("resources", {})
        status = server.get("status")
        if res.get("is_suspended") or status == "suspended":
            state = "⛔ Suspendido"
        elif status in SERVER_STATUS:
            state = SERVER_STATUS[status]
        else:
            state = STATE.get(res.get("current_state"), res.get("current_state", "?"))
        cpu_limit = limits.get("cpu") or 0
        mem_limit = (limits.get("memory") or 0) * 1024 * 1024
        disk_limit = (limits.get("disk") or 0) * 1024 * 1024
        rows = [
            ("Estado", state),
            ("Nodo", server.get("node", "?")),
            ("CPU", f"{r.get('cpu_absolute', 0):.0f} %" + (f" / {cpu_limit} %" if cpu_limit else "")),
            ("RAM", f"{fmt_bytes(r.get('memory_bytes'))} / {fmt_bytes(mem_limit) if mem_limit else '∞'}"),
            ("Disco", f"{fmt_bytes(r.get('disk_bytes'))} / {fmt_bytes(disk_limit) if disk_limit else '∞'}"),
            ("Uptime", fmt_uptime(r.get("uptime"))),
        ]
        if server.get("is_node_under_maintenance"):
            rows.append(("Aviso", "Nodo en mantenimiento"))
        body = "\n".join(f"{k:<12} {v}" for k, v in rows)
        embed = discord.Embed(title=f"🖥 {server.get('name', identifier)}", description=f"```\n{body}\n```", color=COLOR)
        embed.set_footer(text=f"{server.get('identifier', identifier)} · {client.panel}")
        return embed, perms

    async def _check_power_rate(self, user_id: int) -> Optional[str]:
        now = time.time()
        log_ = self._power_log[user_id]
        while log_ and now - log_[0] > 3600:
            log_.popleft()
        if log_ and now - log_[-1] < POWER_COOLDOWN:
            return f"Espera {POWER_COOLDOWN - int(now - log_[-1])}s antes de otra accion."
        if len(log_) >= POWER_PER_HOUR:
            return "Has alcanzado el limite de acciones por hora."
        log_.append(now)
        return None

    async def power_flow(self, interaction: discord.Interaction, identifier: str, signal: str) -> None:
        name = self._cached_name(interaction.user.id, identifier)
        if signal in CONFIRM_SIGNALS:
            view = ConfirmView(interaction.user.id, {"restart": "Reiniciar", "stop": "Detener", "kill": "Forzar kill"}[signal])
            warn = " Puede provocar perdida de datos no guardados." if signal == "kill" else ""
            await interaction.response.send_message(f"¿Seguro que quieres enviar **{signal}** a **{name}**?{warn}", view=view, ephemeral=True)
            await view.wait()
            if not view.value:
                return
            send = interaction.followup.send
        else:
            await interaction.response.defer(ephemeral=True, thinking=True)
            send = interaction.followup.send
        msg = await self.do_power(interaction.user, interaction.guild, identifier, name, signal)
        await send(msg, ephemeral=True)

    async def do_power(self, user: discord.abc.User, guild: Optional[discord.Guild], identifier: str, name: str, signal: str) -> str:
        limited = await self._check_power_rate(user.id)
        if limited:
            return f"⏳ {limited}"
        client = await self.client_for(user)
        if client is None:
            return f"No tienes cuenta vinculada. Usa `{self.p}alienhost link`."
        try:
            await client.power(identifier, signal)
        except PelicanError as exc:
            return f"❌ {exc.friendly}"
        await self._audit(guild, user, f"power:{signal}", f"{name} (`{identifier}`)")
        return f"✅ **{name}** {SIGNAL_LABEL[signal]}."

    async def backups_panel(self, user: discord.abc.User, identifier: str, guild_id: Optional[int]) -> Tuple[discord.Embed, Optional[discord.ui.View]]:
        client = await self.client_for(user)
        if client is None:
            return discord.Embed(description="No tienes cuenta vinculada.", color=discord.Color.red()), None
        try:
            server, data = await asyncio.gather(client.server(identifier), client.backups(identifier))
        except PelicanError as exc:
            return discord.Embed(description=f"❌ {exc.friendly}", color=discord.Color.red()), None
        backups = sorted(data["backups"], key=lambda b: b.get("created_at") or "", reverse=True)
        lines = []
        for b in backups[:10]:
            date = (b.get("created_at") or "")[:16].replace("T", " ")
            if not b.get("completed_at"):
                lines.append(f"⏳ {date}    en curso")
            elif b.get("is_successful"):
                lines.append(f"✅ {date}    {fmt_bytes(b.get('bytes'))}" + ("  🔒" if b.get("is_locked") else ""))
            else:
                lines.append(f"❌ {date}    Fallido")
        limit = server.get("feature_limits", {}).get("backups") or 0
        embed = discord.Embed(
            title=f"💾 Backups · {server.get('name', identifier)}",
            description="```\n" + ("\n".join(lines) or "Sin backups") + "\n```",
            color=COLOR,
        )
        embed.set_footer(text=f"{len(backups)} / {limit or '∞'} backups · Las descargas se hacen desde el panel.")
        meta = server.get("_meta", {})
        perms = ["*"] if meta.get("is_server_owner") else list(meta.get("user_permissions", []))
        can_create = has_perm(perms, "backup.create") and (not limit or len(backups) < limit)
        return embed, BackupsView(self, user.id, identifier, guild_id, can_create)

    async def create_backup_action(self, user: discord.abc.User, identifier: str, guild_id: Optional[int]) -> str:
        limited = await self._check_power_rate(user.id)
        if limited:
            return f"⏳ {limited}"
        client = await self.client_for(user)
        if client is None:
            return "No tienes cuenta vinculada."
        try:
            backup = await client.create_backup(identifier)
        except PelicanError as exc:
            return f"❌ {exc.friendly}"
        guild = self.bot.get_guild(guild_id) if guild_id else None
        await self._audit(guild, user, "backup:create", f"`{identifier}` {backup.get('name', '')}")
        return "💾 Backup solicitado. Aparecera en la lista cuando termine."

    # ------------------------------------------------------------------
    # Alertas
    # ------------------------------------------------------------------

    async def alerts_flow(self, interaction: discord.Interaction, identifier: str) -> None:
        alerts = await self.config.user(interaction.user).alerts()
        current = alerts.get(identifier, {})
        name = current.get("name") or self._cached_name(interaction.user.id, identifier)
        view = AlertsView(self, interaction.user.id, identifier, name, current)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)

    async def save_alerts(self, user: discord.abc.User, identifier: str, name: str, state: Dict[str, bool]) -> None:
        async with self.config.user(user).alerts() as alerts:
            if any(state.values()):
                alerts[identifier] = {"name": name, **state}
            else:
                alerts.pop(identifier, None)

    async def _notify(self, user_id: int, server_name: str, text: str, detail: str = "") -> None:
        user = self.bot.get_user(user_id)
        if user is None:
            return
        embed = discord.Embed(title="⚠️ AlienHost", description=f"**{server_name}**\n\n{text}" + (f"\n\n{detail}" if detail else ""), color=discord.Color.orange(), timestamp=discord.utils.utcnow())
        try:
            await user.send(embed=embed)
        except discord.HTTPException:
            pass

    @tasks.loop(seconds=60)
    async def alert_loop(self) -> None:
        interval = max(60, await self.config.poll_interval())
        self._polls += 1
        if (self._polls * 60) % interval >= 60:
            return
        check_backups = self._polls % 10 == 0
        users = await self.config.all_users()
        sem = asyncio.Semaphore(5)

        async def run(uid: int, data: Dict[str, Any]) -> None:
            async with sem:
                try:
                    await self._check_user_alerts(uid, data, check_backups)
                except Exception:
                    log.exception("Error comprobando alertas de %s", uid)

        await asyncio.gather(*(run(uid, d) for uid, d in users.items() if d.get("alerts") and d.get("api_key")))

    @alert_loop.before_loop
    async def _before_alerts(self) -> None:
        await self.bot.wait_until_red_ready()

    async def _check_user_alerts(self, uid: int, data: Dict[str, Any], check_backups: bool) -> None:
        key = self.vault.decrypt(data["api_key"])
        if not key or not data.get("panel"):
            return
        client = PelicanClient(self.session, data["panel"], key)
        now = time.time()
        for identifier, prefs in data["alerts"].items():
            st = self._alert_state.setdefault((uid, identifier), {"limits_at": 0})
            name = prefs.get("name", identifier)
            try:
                if now - st["limits_at"] > 3600:
                    srv = await client.server(identifier)
                    st["limits"] = srv.get("limits", {})
                    st["limits_at"] = now
                res = await client.resources(identifier)
            except PelicanError as exc:
                if exc.status == 401:
                    return
                continue
            state = res.get("current_state")
            r = res.get("resources", {})
            prev_state, prev_uptime = st.get("state"), st.get("uptime")
            uptime = r.get("uptime") or 0
            if prev_state is not None:
                if prefs.get("offline") and prev_state == "running" and state == "offline":
                    await self._notify(uid, name, "🔴 El servidor se ha detenido (offline).")
                if prefs.get("restarted") and state == "running" and (
                    prev_state in ("offline", "starting", "stopping") or (prev_uptime and uptime < prev_uptime)
                ):
                    await self._notify(uid, name, "🔄 El servidor se ha reiniciado.")
            st["state"], st["uptime"] = state, uptime
            limits = st.get("limits", {})
            mem_limit = (limits.get("memory") or 0) * 1024 * 1024
            cpu_limit = limits.get("cpu") or 0
            if prefs.get("ram") and mem_limit and state == "running":
                await self._sustained(st, "ram", r.get("memory_bytes", 0) / mem_limit >= 0.9, now, uid, name,
                                      "RAM superior al 90 % durante 10 minutos.", f"{fmt_bytes(r.get('memory_bytes'))} / {fmt_bytes(mem_limit)}")
            if prefs.get("cpu") and cpu_limit and state == "running":
                await self._sustained(st, "cpu", r.get("cpu_absolute", 0) / cpu_limit >= 0.95, now, uid, name,
                                      "CPU superior al 95 % durante 10 minutos.", f"{r.get('cpu_absolute', 0):.0f} % / {cpu_limit} %")
            if prefs.get("backup_failed") and check_backups:
                try:
                    backups = (await client.backups(identifier))["backups"]
                except PelicanError:
                    continue
                failed = {b["uuid"] for b in backups if b.get("completed_at") and not b.get("is_successful")}
                known = st.get("failed_backups")
                if known is not None:
                    for _ in failed - known:
                        await self._notify(uid, name, "❌ Un backup ha fallado.", "Revisa el panel para mas detalles.")
                st["failed_backups"] = failed

    async def _sustained(self, st: Dict[str, Any], kind: str, high: bool, now: float, uid: int, name: str, text: str, detail: str) -> None:
        since_key, sent_key = f"{kind}_since", f"{kind}_sent"
        if not high:
            st[since_key] = None
            st[sent_key] = False
            return
        if st.get(since_key) is None:
            st[since_key] = now
        if now - st[since_key] >= SUSTAIN and not st.get(sent_key):
            st[sent_key] = True
            await self._notify(uid, name, text, detail)

    # ------------------------------------------------------------------
    # Integracion con Trini Security
    # ------------------------------------------------------------------

    async def trini_security_findings(self, guild: discord.Guild) -> List[Dict[str, Any]]:
        findings = []
        data = await self.config.guild(guild).all()
        role = guild.get_role(data["admin_role"]) if data["admin_role"] else None
        admin_configured = bool((await self.config.admin()).get("key"))
        if role is not None and admin_configured:
            findings.append({
                "severity": "info",
                "title": f"AlienHost: {len(role.members)} miembro(s) con acceso a comandos de infraestructura",
                "detail": f"Rol {role.mention}" + ("" if data["require_trusted"] else " · no se exige Trusted Admin"),
                "penalty": 0 if data["require_trusted"] else 3,
                "category": "alienhost",
            })
            if not data["require_trusted"]:
                findings[-1]["severity"] = "warning"
        if admin_configured and not data["log_channel"]:
            findings.append({"severity": "info", "title": "AlienHost sin canal de auditoria", "detail": f"`{self.p}alienhost set logchannel #canal`", "penalty": 1, "category": "alienhost"})
        return findings

    async def trini_export(self, guild: discord.Guild) -> Dict[str, Any]:
        return await self.config.guild(guild).all()

    async def trini_import(self, guild: discord.Guild, data: Dict[str, Any], *, same_guild: bool) -> List[str]:
        for key in ("log_channel", "admin_role", "require_trusted"):
            if key in data:
                await self.config.guild(guild).set_raw(key, value=data[key])
        return []

    async def _is_infra_admin(self, ctx: commands.Context) -> bool:
        if await self.bot.is_owner(ctx.author):
            return True
        if ctx.guild is None:
            return False
        data = await self.config.guild(ctx.guild).all()
        role = ctx.guild.get_role(data["admin_role"]) if data["admin_role"] else None
        if role is None or role not in ctx.author.roles:
            return False
        if data["require_trusted"]:
            security = self.bot.get_cog("TriniSecurity")
            if security is None or not await security.is_trusted(ctx.author):
                return False
        return True

    # ------------------------------------------------------------------
    # Comandos de usuario
    # ------------------------------------------------------------------

    async def _server_autocomplete(self, interaction: discord.Interaction, current: str):
        try:
            servers = await self._servers(interaction.user)
        except PelicanError:
            return []
        current = current.lower()
        return [
            discord.app_commands.Choice(name=f"{s.get('name', '?')} ({s['identifier']})"[:100], value=s["uuid"])
            for s in servers
            if current in s.get("name", "").lower() or current in s["identifier"]
        ][:25]

    async def _resolve_server(self, ctx: commands.Context, query: str) -> Optional[Dict[str, Any]]:
        try:
            servers = await self._servers(ctx.author)
        except PelicanError as exc:
            await ctx.send(f"❌ {exc.friendly if exc.status else exc.message}", ephemeral=True)
            return None
        q = query.lower().strip()
        exact = [s for s in servers if s["identifier"] == q or s.get("uuid") == q or s.get("name", "").lower() == q]
        partial = [s for s in servers if q in s.get("name", "").lower()]
        found = exact or partial
        if len(found) != 1:
            await ctx.send(f"Servidor no encontrado o ambiguo. Usa `{self.p}alienhost servers`.", ephemeral=True)
            return None
        return found[0]

    @commands.hybrid_group(name="alienhost", aliases=["ah"])
    async def alienhost(self, ctx: commands.Context):
        """AlienHost: tus servidores de juego desde Discord."""

    @alienhost.command(name="link")
    async def ah_link(self, ctx: commands.Context):
        """Vincular tu cuenta con la URL del panel y una clave API de tu area cliente."""
        default = await self.config.default_panel()

        def factory() -> LinkModal:
            return LinkModal(self._on_link, default_panel=default)

        await self._open_modal(ctx, factory, "Conectar cuenta")

    @alienhost.command(name="unlink")
    async def ah_unlink(self, ctx: commands.Context):
        """Desvincular tu cuenta y borrar la clave guardada."""
        panel = await self.config.user(ctx.author).panel()
        await self.config.user(ctx.author).clear()
        self._server_cache.pop(ctx.author.id, None)
        self._admin_servers_cache.pop(ctx.author.id, None)
        for key in [k for k in self._alert_state if k[0] == ctx.author.id]:
            self._alert_state.pop(key, None)
        await self._audit(ctx.guild, ctx.author, "unlink", panel or "-")
        await ctx.send(
            "🔓 Cuenta desvinculada y clave eliminada del bot."
            + (f"\nRecuerda borrar tambien la clave en {panel} (Perfil → Claves API)." if panel else ""),
            ephemeral=True,
        )

    @alienhost.command(name="account")
    async def ah_account(self, ctx: commands.Context):
        """Ver el estado de tu vinculacion."""
        data = await self.config.user(ctx.author).all()
        if not data["api_key"]:
            return await ctx.send(f"No tienes cuenta vinculada. Usa `{self.p}alienhost link`.", ephemeral=True)
        client = await self.client_for(ctx.author)
        status = "🟢 clave valida"
        if client is None:
            status = "🔴 no se pudo descifrar la clave, vuelve a vincular"
        else:
            try:
                await client.account()
            except PelicanError as exc:
                status = f"🔴 {exc.friendly}"
        embed = discord.Embed(title="🔗 Cuenta de AlienHost", color=COLOR)
        embed.add_field(name="Usuario", value=data["account"].get("username", "?"), inline=True)
        embed.add_field(name="Panel", value=data["panel"], inline=True)
        embed.add_field(name="Estado", value=status, inline=False)
        embed.add_field(name="Vinculada", value=f"<t:{data['linked_at']}:R>" if data["linked_at"] else "?", inline=True)
        embed.add_field(name="Alertas activas", value=str(len(data["alerts"])), inline=True)
        await self._private(ctx, embed=embed)

    @alienhost.command(name="servers")
    async def ah_servers(self, ctx: commands.Context):
        """Listar tus servidores."""
        await ctx.defer(ephemeral=True)
        try:
            servers = await self._servers(ctx.author, fresh=True)
        except PelicanError as exc:
            return await ctx.send(f"❌ {exc.friendly if exc.status else exc.message}", ephemeral=True)
        if not servers:
            return await ctx.send("No tienes servidores en este panel.", ephemeral=True)
        client = await self.client_for(ctx.author)
        sem = asyncio.Semaphore(5)

        async def state(s):
            async with sem:
                try:
                    return (await client.resources(s["uuid"])).get("current_state")
                except PelicanError:
                    return None

        states = await asyncio.gather(*(state(s) for s in servers[:25]))
        lines = [
            f"{STATE.get(st, '⚪ ?').split(' ')[0]} **{s.get('name', '?')}** · {s.get('node', '?')} · `{s['identifier']}`"
            + (" · ⛔ suspendido" if s.get("status") == "suspended" or s.get("is_suspended") else "")
            + (f" · {SERVER_STATUS[s['status']]}" if s.get("status") in SERVER_STATUS else "")
            for s, st in zip(servers, states)
        ]
        embed = discord.Embed(title="🖥 Tus servidores de AlienHost", description="\n".join(lines), color=COLOR)
        if len(servers) > 25:
            embed.set_footer(text=f"Mostrando 25 de {len(servers)}")
        await self._private(ctx, embed=embed, view=ServerSelectView(self, ctx.author.id, servers, ctx.guild.id if ctx.guild else None))

    @alienhost.command(name="server")
    async def ah_server(self, ctx: commands.Context, *, server: str):
        """Detalles de un servidor con acciones rapidas."""
        await ctx.defer(ephemeral=True)
        s = await self._resolve_server(ctx, server)
        if s is None:
            return
        embed, perms = await self.server_embed(ctx.author, s["uuid"])
        kwargs: Dict[str, Any] = {"embed": embed}
        if perms is not None:
            kwargs["view"] = ServerPanel(self, ctx.author.id, s["uuid"], perms, ctx.guild.id if ctx.guild else None)
        await self._private(ctx, **kwargs)

    @alienhost.command(name="power")
    async def ah_power(self, ctx: commands.Context, server: str, signal: str):
        """Enviar start, stop, restart o kill a un servidor."""
        signal = signal.lower()
        if signal not in SIGNAL_LABEL:
            return await ctx.send("Señales: `start`, `stop`, `restart`, `kill`.", ephemeral=True)
        s = await self._resolve_server(ctx, server)
        if s is None:
            return
        if signal in CONFIRM_SIGNALS:
            view = ConfirmView(ctx.author.id, {"restart": "Reiniciar", "stop": "Detener", "kill": "Forzar kill"}[signal])
            await ctx.send(f"¿Seguro que quieres enviar **{signal}** a **{s.get('name')}**?", view=view, ephemeral=True)
            await view.wait()
            if not view.value:
                return
        text = await self.do_power(ctx.author, ctx.guild, s["uuid"], s.get("name", s["identifier"]), signal)
        await ctx.send(text, ephemeral=True)

    @ah_power.autocomplete("signal")
    async def _ac_signal(self, interaction: discord.Interaction, current: str):
        return [discord.app_commands.Choice(name=s, value=s) for s in SIGNAL_LABEL if current.lower() in s]

    @alienhost.command(name="backups")
    async def ah_backups(self, ctx: commands.Context, *, server: str):
        """Ver los ultimos backups de un servidor (y crear uno)."""
        await ctx.defer(ephemeral=True)
        s = await self._resolve_server(ctx, server)
        if s is None:
            return
        embed, view = await self.backups_panel(ctx.author, s["uuid"], ctx.guild.id if ctx.guild else None)
        kwargs: Dict[str, Any] = {"embed": embed}
        if view is not None:
            kwargs["view"] = view
        await self._private(ctx, **kwargs)

    @alienhost.command(name="alerts")
    async def ah_alerts(self, ctx: commands.Context, *, server: Optional[str] = None):
        """Configurar alertas por DM de un servidor (o ver las activas)."""
        if server is None:
            alerts = await self.config.user(ctx.author).alerts()
            if not alerts:
                return await ctx.send(f"No tienes alertas. Usa `{self.p}alienhost alerts <servidor>`.", ephemeral=True)
            lines = [
                f"**{a.get('name', ident)}** · " + ", ".join(ALERT_KINDS[k] for k in ALERT_KINDS if a.get(k))
                for ident, a in alerts.items()
            ]
            return await self._private(ctx, embed=discord.Embed(title="🔔 Tus alertas", description="\n".join(lines), color=COLOR))
        s = await self._resolve_server(ctx, server)
        if s is None:
            return
        current = (await self.config.user(ctx.author).alerts()).get(s["uuid"], {})
        view = AlertsView(self, ctx.author.id, s["uuid"], s.get("name", s["identifier"]), current)
        await self._private(ctx, embed=view.embed(), view=view)

    @ah_server.autocomplete("server")
    @ah_power.autocomplete("server")
    @ah_backups.autocomplete("server")
    @ah_alerts.autocomplete("server")
    async def _ac_server(self, interaction: discord.Interaction, current: str):
        return await self._server_autocomplete(interaction, current)

    # ------------------------------------------------------------------
    # Administracion
    # ------------------------------------------------------------------

    @alienhost.group(name="admin")
    async def ah_admin(self, ctx: commands.Context):
        """Administracion interna de AlienHost."""

    async def _require_infra_admin(self, ctx: commands.Context) -> bool:
        if not await self._is_infra_admin(ctx):
            await ctx.send("🔒 Solo administradores de AlienHost (rol configurado + Trusted Admin en Trini Security).", ephemeral=True)
            return False
        return True

    async def _admin_ctx(self, ctx: commands.Context) -> Optional[PelicanClient]:
        """Cliente con la clave de APLICACION (`papp_`): nodos, incidencias, buscar clientes."""
        if not await self._require_infra_admin(ctx):
            return None
        client = await self.admin_client()
        if client is None:
            await ctx.send(f"No hay clave de administracion. El owner debe usar `{self.p}alienhost admin setkey`.", ephemeral=True)
        return client

    async def _admin_servers(self, user: discord.abc.User, *, fresh: bool = False) -> List[Dict[str, Any]]:
        """Todos los servidores del panel, vistos con la clave de CLIENTE del propio ``user``.

        Requiere que la cuenta vinculada de ``user`` (`alienhost link`) sea
        ``root_admin`` en el panel: solo entonces Pelican permite pedir
        ``type=admin-all``. No usa la clave de aplicacion.
        """
        cached = self._admin_servers_cache.get(user.id)
        if cached and not fresh and time.time() - cached[0] < 60:
            return cached[1]
        client = await self.client_for(user)
        if client is None:
            raise PelicanError(0, f"No tienes cuenta vinculada. Usa `{self.p}alienhost link` con una cuenta de administrador del panel.")
        try:
            servers = await client.servers(admin_all=True)
        except PelicanError as exc:
            if exc.status == 403:
                raise PelicanError(403, "Tu cuenta vinculada en AlienHost no es administradora (root admin) del panel, asi que no puede ver todos los servidores.") from exc
            raise
        self._admin_servers_cache[user.id] = (time.time(), servers)
        return servers

    @ah_admin.command(name="setkey")
    @commands.is_owner()
    async def ah_admin_setkey(self, ctx: commands.Context):
        """(Owner) Guardar la clave de aplicacion (papp_) mediante formulario privado."""
        default = await self.config.default_panel()

        def factory() -> LinkModal:
            return LinkModal(self._on_admin_key, default_panel=default, title="Clave de administracion", key_label="Clave de aplicacion (papp_…)")

        await self._open_modal(ctx, factory, "Introducir clave")

    @ah_admin.command(name="nodes")
    async def ah_admin_nodes(self, ctx: commands.Context):
        """Estado de los nodos."""
        client = await self._admin_ctx(ctx)
        if client is None:
            return
        await ctx.defer(ephemeral=True)
        try:
            nodes, servers = await asyncio.gather(client.app_list("nodes"), client.app_list("servers"))
        except PelicanError as exc:
            return await ctx.send(f"❌ {exc.friendly}", ephemeral=True)
        per_node: Dict[Any, int] = defaultdict(int)
        for s in servers:
            per_node[s.get("node")] += 1
        lines = []
        for n in nodes:
            alloc = n.get("allocated_resources") or {}
            mem, disk = n.get("memory") or 0, n.get("disk") or 0
            mem_pct = (alloc.get("memory", 0) / mem * 100) if mem else 0
            icon = "🟠" if n.get("maintenance_mode") else ("🟡" if mem_pct >= 90 else "🟢")
            lines.append(
                f"{icon} **{n.get('name')}** · {n.get('fqdn')}\n"
                f"   RAM asignada {mem_pct:.0f}% · Disco {(alloc.get('disk', 0) / disk * 100) if disk else 0:.0f}% · Servers {per_node.get(n.get('id'), 0)}"
                + (" · mantenimiento" if n.get("maintenance_mode") else "")
            )
        embed = discord.Embed(title="🛰 Nodos de AlienHost", description="\n".join(lines)[:4000] or "Sin nodos", color=COLOR)
        embed.set_footer(text=f"{len(nodes)} nodos · {len(servers)} servidores (primeros 100)")
        await self._private(ctx, embed=embed)

    @ah_admin.command(name="incidents")
    async def ah_admin_incidents(self, ctx: commands.Context):
        """Servidores suspendidos, con instalacion fallida o nodos en mantenimiento."""
        client = await self._admin_ctx(ctx)
        if client is None:
            return
        await ctx.defer(ephemeral=True)
        try:
            nodes, servers = await asyncio.gather(client.app_list("nodes"), client.app_list("servers"))
        except PelicanError as exc:
            return await ctx.send(f"❌ {exc.friendly}", ephemeral=True)
        lines = [f"🟠 Nodo **{n.get('name')}** en mantenimiento" for n in nodes if n.get("maintenance_mode")]
        for s in servers:
            status = s.get("status")
            if s.get("suspended") or status == "suspended":
                lines.append(f"⛔ **{s.get('name')}** (`{s.get('identifier')}`) suspendido")
            elif status in ("install_failed", "reinstall_failed", "restoring_backup"):
                lines.append(f"🔧 **{s.get('name')}** (`{s.get('identifier')}`) · {status}")
        await self._private(ctx, embed=discord.Embed(title="🚧 Incidencias", description="\n".join(lines)[:4000] or "🟢 Sin incidencias", color=COLOR))

    @ah_admin.command(name="servers")
    async def ah_admin_servers(self, ctx: commands.Context, *, query: Optional[str] = None):
        """Ver y administrar TODOS los servidores del panel (25 por pagina, con buscador).

        Usa tu propia cuenta vinculada con `alienhost link`, que debe ser
        administradora (root admin) del panel. Opcionalmente filtra por nombre,
        identificador, UUID o nodo.
        """
        if not await self._require_infra_admin(ctx):
            return
        await ctx.defer(ephemeral=True)
        try:
            servers = await self._admin_servers(ctx.author, fresh=True)
        except PelicanError as exc:
            return await ctx.send(f"❌ {exc.friendly if exc.status not in (0, 403) else exc.message}", ephemeral=True)
        if not servers:
            return await ctx.send("El panel no tiene servidores.", ephemeral=True)
        view = AdminServerBrowseView(self, ctx.author.id, servers, ctx.guild.id if ctx.guild else None, query=(query or "").strip())
        embed = await view.render(ctx.author)
        await self._audit(ctx.guild, ctx.author, "admin:servers", f"{len(servers)} servidores" + (f" · filtro {query}" if query else ""))
        await self._private(ctx, embed=embed, view=view)

    @ah_admin.command(name="user")
    async def ah_admin_user(self, ctx: commands.Context, *, query: str):
        """Buscar un cliente por email o usuario (o mencion de Discord vinculada)."""
        client = await self._admin_ctx(ctx)
        if client is None:
            return
        await ctx.defer(ephemeral=True)
        try:
            member = await commands.UserConverter().convert(ctx, query)
            linked = (await self.config.user(member).account()).get("username")
            if linked:
                query = linked
        except commands.BadArgument:
            pass
        try:
            key = "filter[email]" if "@" in query else "filter[username]"
            users = await client.app_list("users", {key: query, "include": "servers"})
        except PelicanError as exc:
            return await ctx.send(f"❌ {exc.friendly}", ephemeral=True)
        if not users:
            return await ctx.send("Usuario no encontrado.", ephemeral=True)
        u = users[0]
        servers = [s.get("attributes", {}) for s in u.get("relationships", {}).get("servers", {}).get("data", [])]
        embed = discord.Embed(title=f"👤 {u.get('username')}", color=COLOR)
        embed.add_field(name="Email", value=u.get("email", "?"), inline=True)
        embed.add_field(name="2FA", value="✅" if u.get("2fa") or u.get("2fa_enabled") else "❌", inline=True)
        embed.add_field(name="Admin", value="✅" if u.get("root_admin") else "❌", inline=True)
        embed.add_field(name=f"Servidores ({len(servers)})", value="\n".join(f"• {s.get('name')} (`{s.get('identifier')}`)" for s in servers[:15]) or "—", inline=False)
        await self._private(ctx, embed=embed)

    # ------------------------------------------------------------------
    # Ajustes
    # ------------------------------------------------------------------

    @alienhost.group(name="set")
    async def ah_set(self, ctx: commands.Context):
        """Configuracion de la integracion."""

    @ah_set.command(name="panels")
    @commands.is_owner()
    async def ah_set_panels(self, ctx: commands.Context, action: str, url: Optional[str] = None):
        """(Owner) Paneles permitidos: `add <url>`, `remove <url>`, `list`, `default <url>`."""
        action = action.lower()
        panels = await self.config.allowed_panels()
        if action == "list":
            default = await self.config.default_panel()
            return await ctx.send("\n".join(f"• `{p}`{' (por defecto)' if p == default else ''}" for p in panels) or "Ninguno")
        norm = normalize_panel(url or "")
        if norm is None:
            return await ctx.send("URL no valida.")
        if action == "add":
            if norm not in panels:
                panels.append(norm)
                await self.config.allowed_panels.set(panels)
            await ctx.send(f"Panel permitido: `{norm}`.")
        elif action == "remove":
            await self.config.allowed_panels.set([p for p in panels if p != norm])
            await ctx.send(f"Panel eliminado: `{norm}`. Las cuentas vinculadas a el dejaran de funcionar.")
        elif action == "default":
            if norm not in panels:
                return await ctx.send("Primero añadelo con `add`.")
            await self.config.default_panel.set(norm)
            await ctx.send(f"Panel por defecto: `{norm}`.")
        else:
            await ctx.send("Acciones: `add`, `remove`, `list`, `default`.")

    @ah_set.command(name="pollinterval")
    @commands.is_owner()
    async def ah_set_poll(self, ctx: commands.Context, seconds: int):
        """(Owner) Cada cuanto se comprueban las alertas (minimo 60s)."""
        await self.config.poll_interval.set(max(60, seconds))
        await ctx.send(f"Intervalo de alertas: {max(60, seconds)}s.")

    @ah_set.command(name="logchannel")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def ah_set_logchannel(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Canal donde se registran las acciones (power, backups, vinculaciones)."""
        await self.config.guild(ctx.guild).log_channel.set(channel.id if channel else None)
        self.bot.dispatch("trini_settings_change", ctx.guild, "AlienHost", ctx.author, "log_channel", str(channel))
        await ctx.send(f"Canal de auditoria de AlienHost: {channel.mention if channel else 'ninguno'}.")

    @ah_set.command(name="adminrole")
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    async def ah_set_adminrole(self, ctx: commands.Context, role: Optional[discord.Role] = None, require_trusted: bool = True):
        """Rol con acceso a `alienhost admin` y si ademas se exige Trusted Admin de Trini Security."""
        await self.config.guild(ctx.guild).admin_role.set(role.id if role else None)
        await self.config.guild(ctx.guild).require_trusted.set(require_trusted)
        self.bot.dispatch("trini_settings_change", ctx.guild, "AlienHost", ctx.author, "admin_role", f"{role} trusted={require_trusted}")
        await ctx.send(
            f"Rol de administracion: {role.mention if role else 'ninguno'} · exigir Trusted Admin: {'si' if require_trusted else 'no'}.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @ah_set.command(name="show")
    async def ah_set_show(self, ctx: commands.Context):
        """Ver la configuracion."""
        g = await self.config.guild(ctx.guild).all() if ctx.guild else {}
        admin = await self.config.admin()
        embed = discord.Embed(title="⚙️ AlienHost", color=COLOR)
        embed.add_field(name="Paneles permitidos", value="\n".join(await self.config.allowed_panels()) or "—", inline=False)
        embed.add_field(name="Clave admin", value=f"✅ {admin['panel']}" if admin.get("key") else "❌", inline=True)
        embed.add_field(name="Alertas cada", value=f"{await self.config.poll_interval()}s", inline=True)
        if g:
            embed.add_field(name="Canal de auditoria", value=f"<#{g['log_channel']}>" if g["log_channel"] else "—", inline=True)
            embed.add_field(name="Rol admin", value=(f"<@&{g['admin_role']}>" if g["admin_role"] else "—") + (" (+Trusted)" if g["require_trusted"] else ""), inline=True)
        linked = sum(1 for d in (await self.config.all_users()).values() if d.get("api_key"))
        embed.add_field(name="Cuentas vinculadas", value=str(linked), inline=True)
        await self._private(ctx, embed=embed, allowed_mentions=discord.AllowedMentions.none())
