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
from redbot.core.i18n import Translator, cog_i18n, set_contextual_locales_from_guild

_ = Translator("PruneBans", __file__)

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


@cog_i18n(_)
class PruneBans(DashboardIntegration, commands.Cog):
    """Automatically deletes the credits of users who are still banned after some days."""

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
        return _("{format_help_for_context}\n\nVersion: {version}").format(format_help_for_context=super().format_help_for_context(ctx), version=self.__version__)

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
                title=_("🧹 Banned users' credits deleted"),
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
                await set_contextual_locales_from_guild(self.bot, guild)
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
        embed = discord.Embed(title=_("🧹 AutoPrune"), color=COLOR)
        embed.description = _("Deletes the credits of users who are still banned after some days.\nBans and unbans are logged by modlog; this only reports cleanups.")
        embed.add_field(name=_("Status"), value=_("🟢 Enabled") if conf["enabled"] else _("🔴 Disabled"))
        embed.add_field(name=_("Wait"), value=_("{delay_days} days").format(delay_days=conf['delay_days']))
        embed.add_field(name=_("Log channel"), value=channel.mention if channel else "Ninguno")
        embed.add_field(name=_("Tracked"), value=str(len(conf["ban_track"])))
        if global_bank:
            allowed = await self.config.prune_global_bank()
            embed.add_field(
                name=_("Bank"),
                value=_("Global · ") + (_("accounts are deleted") if allowed else _("⚠️ nothing is deleted (the owner can enable it with `autoprune globalbank true`)")),
                inline=False,
            )
        else:
            embed.add_field(name=_("Bank"), value=_("Local (per server)"), inline=False)
        return embed

    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    @commands.hybrid_group(name="autoprune", aliases=["prunebans"], invoke_without_command=True)
    async def autoprune(self, ctx: commands.Context):
        """Automatic cleanup of banned users' credits."""
        await ctx.send(embed=await self._status_embed(ctx.guild))

    @autoprune.command(name="enable")
    async def autoprune_enable(self, ctx: commands.Context):
        """Enable automatic cleanup in this server."""
        await self.config.guild(ctx.guild).enabled.set(True)
        days = await self.config.guild(ctx.guild).delay_days()
        await ctx.send(
            _("✅ Enabled. Credits of users who are still banned will be deleted after **{days}** days.\nTo also track users who were already banned: `{clean_prefix}autoprune sync`.").format(days=days, clean_prefix=ctx.clean_prefix)
        )

    @autoprune.command(name="disable")
    async def autoprune_disable(self, ctx: commands.Context):
        """Disable automatic cleanup (tracking is kept)."""
        await self.config.guild(ctx.guild).enabled.set(False)
        await ctx.send(_("⏸️ Disabled. Nothing will be deleted until you enable it again."))

    @autoprune.command(name="days")
    async def autoprune_days(self, ctx: commands.Context, days: commands.Range[int, 0, MAX_DELAY_DAYS]):
        """Days a user must stay banned before their credits are deleted (0 = next check)."""
        await self.config.guild(ctx.guild).delay_days.set(days)
        # Recalcula la fecha de limpieza de los que ya estan en seguimiento.
        async with self.config.guild(ctx.guild).ban_track() as ban_track:
            for info in ban_track.values():
                start = _parse_dt(info.get("ban_date"))
                if start is not None:
                    info["unban_date"] = (start + datetime.timedelta(days=days)).isoformat()
        await ctx.send(_("✅ Wait set to **{days}** days (also applied to pending bans).").format(days=days))

    @autoprune.command(name="logchannel")
    async def autoprune_logchannel(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Channel to report deleted credits. Without a channel it is removed."""
        await self.config.guild(ctx.guild).log_channel.set(channel.id if channel else None)
        await ctx.send(_("✅ Log channel: {channel}.").format(channel=channel.mention) if channel else _("✅ Log channel removed."))

    @autoprune.command(name="pending")
    async def autoprune_pending(self, ctx: commands.Context):
        """Tracked bans and when they will be cleaned up."""
        ban_track = await self.config.guild(ctx.guild).ban_track()
        if not ban_track:
            return await ctx.send(_("There are no tracked bans."))
        rows = []
        for uid_str, info in sorted(ban_track.items(), key=lambda kv: str(kv[1].get("unban_date", ""))):
            due = _parse_dt(info.get("unban_date"))
            when = discord.utils.format_dt(due, "R") if due else "?"
            balance = info.get("balance")
            amount = humanize_number(balance) if isinstance(balance, int) else "?"
            rows.append(_("<@{uid_str}> (`{uid_str}`) · {amount} · cleanup {when}").format(uid_str=uid_str, amount=amount, when=when))
        for page in pagify("\n".join(rows), page_length=3900):
            embed = discord.Embed(title=_("⏳ Tracked bans ({count})").format(count=len(ban_track)), description=page, color=COLOR)
            await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @autoprune.command(name="sync")
    @commands.bot_has_permissions(ban_members=True)
    async def autoprune_sync(self, ctx: commands.Context):
        """Start tracking users who were already banned (the countdown starts today)."""
        async with ctx.typing():
            tracked = await self.config.guild(ctx.guild).ban_track()
            added = 0
            async for entry in ctx.guild.bans(limit=None):
                if str(entry.user.id) not in tracked:
                    await self.track(ctx.guild, entry.user.id)
                    added += 1
        await ctx.send(_("✅ {added} bans added to tracking.").format(added=added))

    @autoprune.command(name="run")
    async def autoprune_run(self, ctx: commands.Context, now: bool = False):
        """Check expired bans now. With `true` it cleans every pending one without waiting."""
        if not await self._can_prune_bank():
            return await ctx.send(_("⚠️ The bank is global and the owner has not allowed deleting global accounts."))
        async with ctx.typing():
            pruned = await self.process_guild(ctx.guild, force=now)
        await ctx.send(_("🧹 Credits deleted from {count} user(s).").format(count=len(pruned)))

    @autoprune.command(name="forget")
    async def autoprune_forget(self, ctx: commands.Context, user_id: int):
        """Stop tracking a user (their credits will not be deleted)."""
        async with self.config.guild(ctx.guild).ban_track() as ban_track:
            removed = ban_track.pop(str(user_id), None)
        await ctx.send(_("✅ Removed from tracking.") if removed else _("It was not tracked."))

    @commands.is_owner()
    @autoprune.command(name="globalbank")
    async def autoprune_globalbank(self, ctx: commands.Context, allow: bool):
        """(Owner) Allow deleting accounts when Red's bank is global.

        With a global bank the account is the same in every server: a ban in
        one server would remove their credits everywhere.
        """
        await self.config.prune_global_bank.set(allow)
        await ctx.send(_("✅ Global bank accounts will be deleted.") if allow else _("✅ Global bank accounts will not be touched."))
