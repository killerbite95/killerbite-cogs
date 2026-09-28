"""PruneBans: limpia automaticamente los creditos de los usuarios baneados.

Cuando alguien es baneado se apunta la fecha. Pasados ``delay_days`` dias,
si sigue baneado, se borra su cuenta del banco de Red en ese servidor. No
publica nada al banear o desbanear (de eso ya se encarga el modlog); solo deja
un resumen en el canal de logs cuando borra creditos.
"""
import datetime
import logging
from typing import Any, Dict, List, Optional, Tuple

import discord
from discord.ext import tasks
from redbot.core import Config, bank, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_number, pagify

from .dashboard_integration import DashboardIntegration

log = logging.getLogger("red.killerbite.autoprune")

DEFAULT_DELAY_DAYS = 7
MAX_DELAY_DAYS = 365
COLOR = 0xE67E22


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _parse_dt(value: Any) -> Optional[datetime.datetime]:
    """Fechas guardadas en ISO. Las antiguas no tienen zona: se asumen UTC."""
    try:
        dt = datetime.datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt


class PruneBans(DashboardIntegration, commands.Cog):
    """Borra automaticamente los creditos de los usuarios que siguen baneados pasados unos dias."""

    __author__ = "Killerbite95"
    __version__ = "2.0.0"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        self.config.register_guild(
            enabled=False,
            delay_days=DEFAULT_DELAY_DAYS,
            log_channel=None,
            # {user_id: {"ban_date": iso, "unban_date": iso (fecha de limpieza), "balance": int|str}}
            # (``unban_date`` conserva su nombre antiguo: AdvCheck lo lee).
            ban_track={},
            # Solo para migrar la version 1 (se registraban los bans en un canal).
            ban_log_channel=None,
        )
        self.config.register_global(schema=1, prune_global_bank=False)
        self.prune_loop.start()

    def format_help_for_context(self, ctx: commands.Context) -> str:
        return f"{super().format_help_for_context(ctx)}\n\nVersion: {self.__version__}"

    async def cog_load(self) -> None:
        await super().cog_load()
        await self._migrate()

    def cog_unload(self):
        self.prune_loop.cancel()

    async def _migrate(self) -> None:
        """v1 -> v2: quien tenia canal de registro de bans pasa a tener la limpieza activada."""
        if await self.config.schema() >= 2:
            return
        for guild_id, data in (await self.config.all_guilds()).items():
            group = self.config.guild_from_id(guild_id)
            if data.get("ban_log_channel"):
                await group.enabled.set(True)
                if not data.get("log_channel"):
                    await group.log_channel.set(data["ban_log_channel"])
            await group.ban_log_channel.clear()
        await self.config.schema.set(2)

    # ------------------------------------------------------------------
    # Protocolo de La Trini: TriniProfiles (export/import) y TriniBackups
    # ------------------------------------------------------------------

    # Datos de funcionamiento (no son configuracion): ni se exportan ni se pisan.
    _TRINI_RUNTIME_KEYS = ("ban_track", "ban_log_channel")
    # Configuracion que solo tiene sentido en el mismo servidor.
    _TRINI_LOCAL_KEYS = ()

    async def trini_export(self, guild):
        conf = await self.config.guild(guild).all()
        return {k: v for k, v in conf.items() if k not in self._TRINI_RUNTIME_KEYS}

    async def trini_import(self, guild, data, *, same_guild):
        skip = set(self._TRINI_RUNTIME_KEYS)
        if not same_guild:
            skip |= set(self._TRINI_LOCAL_KEYS)
        data = {k: v for k, v in data.items() if k not in skip}
        group = self.config.guild(guild)
        current = await group.all()
        for key, value in data.items():
            if key in current:
                await group.set_raw(key, value=value)
        return []

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        for guild_id in await self.config.all_guilds():
            async with self.config.guild_from_id(guild_id).ban_track() as ban_track:
                ban_track.pop(str(user_id), None)

    # ------------------------------------------------------------------
    # Banco
    # ------------------------------------------------------------------

    async def _balance(self, guild: discord.Guild, user_id: int) -> Optional[int]:
        """Saldo sin necesitar un Member (un baneado ya no esta en el servidor)."""
        try:
            if await bank.is_global():
                return await bank._config.user_from_id(user_id).balance()
            return await bank._config.member_from_ids(guild.id, user_id).balance()
        except Exception:
            return None

    async def _can_prune_bank(self) -> bool:
        """Con banco global, borrar la cuenta afecta a todos los servidores:
        solo se hace si el owner lo ha permitido."""
        if not await bank.is_global():
            return True
        return await self.config.prune_global_bank()

    # ------------------------------------------------------------------
    # Seguimiento
    # ------------------------------------------------------------------

    async def track(self, guild: discord.Guild, user_id: int, when: Optional[datetime.datetime] = None) -> Dict[str, Any]:
        when = when or _utcnow()
        days = await self.config.guild(guild).delay_days()
        balance = await self._balance(guild, user_id)
        entry = {
            "ban_date": when.isoformat(),
            "unban_date": (when + datetime.timedelta(days=days)).isoformat(),
            "balance": balance if balance is not None else "Desconocido",
        }
        async with self.config.guild(guild).ban_track() as ban_track:
            ban_track[str(user_id)] = entry
        return entry

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.abc.User):
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        if not await self.config.guild(guild).enabled():
            return
        await self.track(guild, user.id)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.abc.User):
        async with self.config.guild(guild).ban_track() as ban_track:
            ban_track.pop(str(user.id), None)

    async def process_guild(self, guild: discord.Guild, *, force: bool = False) -> List[Tuple[int, Any]]:
        """Limpia los baneos vencidos (o todos con ``force``). Devuelve ``[(user_id, saldo)]``."""
        ban_track = await self.config.guild(guild).ban_track()
        if not ban_track:
            return []
        if not await self._can_prune_bank():
            return []  # Se conserva el seguimiento por si el owner lo permite luego.
        now = _utcnow()
        pruned: List[Tuple[int, Any]] = []
        done: List[str] = []
        for uid_str, info in ban_track.items():
            due = _parse_dt(info.get("unban_date")) if isinstance(info, dict) else None
            if not force and (due is None or due > now):
                continue
            user_id = int(uid_str)
            try:
                await guild.fetch_ban(discord.Object(id=user_id))
            except discord.NotFound:
                done.append(uid_str)  # Ya no esta baneado: se deja de seguir.
                continue
            except discord.HTTPException:
                continue  # Sin permiso de ver bans o error temporal: se reintenta luego.
            balance = await self._balance(guild, user_id)
            await bank.bank_prune(self.bot, guild=guild, user_id=user_id)
            pruned.append((user_id, balance if balance is not None else info.get("balance")))
            done.append(uid_str)
        if done:
            async with self.config.guild(guild).ban_track() as current:
                for uid_str in done:
                    current.pop(uid_str, None)
        if pruned:
            await self._log_pruned(guild, pruned)
        return pruned

    async def _log_pruned(self, guild: discord.Guild, pruned: List[Tuple[int, Any]]) -> None:
        channel_id = await self.config.guild(guild).log_channel()
        channel = guild.get_channel(channel_id) if channel_id else None
        if channel is None or not channel.permissions_for(guild.me).embed_links:
            return
        lines = []
        for user_id, balance in pruned:
            amount = humanize_number(balance) if isinstance(balance, int) else "?"
            lines.append(f"<@{user_id}> (`{user_id}`) · {amount} {await bank.get_currency_name(guild)}")
        for page in pagify("\n".join(lines), page_length=3900):
            embed = discord.Embed(
                title="🧹 Creditos de usuarios baneados eliminados",
                description=page,
                color=COLOR,
                timestamp=_utcnow(),
            )
            try:
                await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                return

    @tasks.loop(hours=1)
    async def prune_loop(self):
        for guild_id, data in (await self.config.all_guilds()).items():
            if not data.get("enabled") or not data.get("ban_track"):
                continue
            guild = self.bot.get_guild(guild_id)
            if guild is None or guild.unavailable:
                continue
            try:
                if await self.bot.cog_disabled_in_guild(self, guild):
                    continue
                await self.process_guild(guild)
            except Exception:
                log.exception("Error limpiando los baneos de %s", guild_id)

    @prune_loop.before_loop
    async def before_prune_loop(self):
        await self.bot.wait_until_red_ready()

    # ------------------------------------------------------------------
    # Comandos
    # ------------------------------------------------------------------

    async def cog_check(self, ctx: commands.Context) -> bool:
        # Los subcomandos slash no heredan los checks del grupo: se exigen aqui.
        if ctx.guild is None:
            return False
        if await self.bot.is_owner(ctx.author):
            return True
        return ctx.author.guild_permissions.manage_guild or await self.bot.is_admin(ctx.author)

    async def _status_embed(self, guild: discord.Guild) -> discord.Embed:
        conf = await self.config.guild(guild).all()
        channel = guild.get_channel(conf["log_channel"]) if conf["log_channel"] else None
        global_bank = await bank.is_global()
        embed = discord.Embed(title="🧹 AutoPrune", color=COLOR)
        embed.description = (
            "Borra los creditos de los usuarios que siguen baneados pasados unos dias.\n"
            "Los baneos y desbaneos los registra el modlog; aqui solo se avisa al limpiar."
        )
        embed.add_field(name="Estado", value="🟢 Activado" if conf["enabled"] else "🔴 Desactivado")
        embed.add_field(name="Espera", value=f"{conf['delay_days']} dias")
        embed.add_field(name="Canal de logs", value=channel.mention if channel else "Ninguno")
        embed.add_field(name="En seguimiento", value=str(len(conf["ban_track"])))
        if global_bank:
            allowed = await self.config.prune_global_bank()
            embed.add_field(
                name="Banco",
                value="Global · " + ("se borran las cuentas" if allowed else "⚠️ no se borra nada (el owner puede activarlo con `autoprune globalbank true`)"),
                inline=False,
            )
        else:
            embed.add_field(name="Banco", value="Local (por servidor)", inline=False)
        return embed

    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    @commands.hybrid_group(name="autoprune", aliases=["prunebans"], invoke_without_command=True)
    async def autoprune(self, ctx: commands.Context):
        """Limpieza automatica de creditos de usuarios baneados."""
        await ctx.send(embed=await self._status_embed(ctx.guild))

    @autoprune.command(name="enable")
    async def autoprune_enable(self, ctx: commands.Context):
        """Activar la limpieza automatica en este servidor."""
        await self.config.guild(ctx.guild).enabled.set(True)
        days = await self.config.guild(ctx.guild).delay_days()
        await ctx.send(
            f"✅ Activado. Los creditos de quien siga baneado se borraran a los **{days}** dias.\n"
            f"Para seguir tambien a los que ya estaban baneados: `{ctx.clean_prefix}autoprune sync`."
        )

    @autoprune.command(name="disable")
    async def autoprune_disable(self, ctx: commands.Context):
        """Desactivar la limpieza automatica (no borra el seguimiento)."""
        await self.config.guild(ctx.guild).enabled.set(False)
        await ctx.send("⏸️ Desactivado. No se borrara nada hasta que lo vuelvas a activar.")

    @autoprune.command(name="days")
    async def autoprune_days(self, ctx: commands.Context, days: commands.Range[int, 0, MAX_DELAY_DAYS]):
        """Dias que tiene que seguir baneado antes de borrar sus creditos (0 = en la siguiente revision)."""
        await self.config.guild(ctx.guild).delay_days.set(days)
        # Recalcula la fecha de limpieza de los que ya estan en seguimiento.
        async with self.config.guild(ctx.guild).ban_track() as ban_track:
            for info in ban_track.values():
                start = _parse_dt(info.get("ban_date"))
                if start is not None:
                    info["unban_date"] = (start + datetime.timedelta(days=days)).isoformat()
        await ctx.send(f"✅ Espera fijada en **{days}** dias (aplicado tambien a los baneos pendientes).")

    @autoprune.command(name="logchannel")
    async def autoprune_logchannel(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Canal donde avisar cuando se borran creditos. Sin canal lo quita."""
        await self.config.guild(ctx.guild).log_channel.set(channel.id if channel else None)
        await ctx.send(f"✅ Canal de logs: {channel.mention}." if channel else "✅ Canal de logs quitado.")

    @autoprune.command(name="pending")
    async def autoprune_pending(self, ctx: commands.Context):
        """Baneos en seguimiento y cuando se limpiaran."""
        ban_track = await self.config.guild(ctx.guild).ban_track()
        if not ban_track:
            return await ctx.send("No hay baneos en seguimiento.")
        rows = []
        for uid_str, info in sorted(ban_track.items(), key=lambda kv: str(kv[1].get("unban_date", ""))):
            due = _parse_dt(info.get("unban_date"))
            when = discord.utils.format_dt(due, "R") if due else "?"
            balance = info.get("balance")
            amount = humanize_number(balance) if isinstance(balance, int) else "?"
            rows.append(f"<@{uid_str}> (`{uid_str}`) · {amount} · limpieza {when}")
        for page in pagify("\n".join(rows), page_length=3900):
            embed = discord.Embed(title=f"⏳ Baneos en seguimiento ({len(ban_track)})", description=page, color=COLOR)
            await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @autoprune.command(name="sync")
    @commands.bot_has_permissions(ban_members=True)
    async def autoprune_sync(self, ctx: commands.Context):
        """Empieza a seguir a los usuarios que ya estaban baneados (la cuenta atras empieza hoy)."""
        async with ctx.typing():
            tracked = await self.config.guild(ctx.guild).ban_track()
            added = 0
            async for entry in ctx.guild.bans(limit=None):
                if str(entry.user.id) not in tracked:
                    await self.track(ctx.guild, entry.user.id)
                    added += 1
        await ctx.send(f"✅ {added} baneos añadidos al seguimiento.")

    @autoprune.command(name="run")
    async def autoprune_run(self, ctx: commands.Context, now: bool = False):
        """Revisar ya los baneos vencidos. Con `true` limpia todos los pendientes sin esperar."""
        if not await self._can_prune_bank():
            return await ctx.send("⚠️ El banco es global y el owner no ha permitido borrar cuentas globales.")
        async with ctx.typing():
            pruned = await self.process_guild(ctx.guild, force=now)
        await ctx.send(f"🧹 Creditos eliminados de {len(pruned)} usuario(s).")

    @autoprune.command(name="forget")
    async def autoprune_forget(self, ctx: commands.Context, user_id: int):
        """Dejar de seguir a un usuario (no se le borraran los creditos)."""
        async with self.config.guild(ctx.guild).ban_track() as ban_track:
            removed = ban_track.pop(str(user_id), None)
        await ctx.send("✅ Quitado del seguimiento." if removed else "No estaba en seguimiento.")

    @commands.is_owner()
    @autoprune.command(name="globalbank")
    async def autoprune_globalbank(self, ctx: commands.Context, allow: bool):
        """(Owner) Permitir borrar cuentas cuando el banco de Red es global.

        Con banco global la cuenta es la misma en todos los servidores: un ban en
        un servidor le quitaria los creditos en todos.
        """
        await self.config.prune_global_bank.set(allow)
        await ctx.send("✅ Se borraran cuentas del banco global." if allow else "✅ No se tocaran cuentas del banco global.")
