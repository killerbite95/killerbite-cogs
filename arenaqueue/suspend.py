# arenaqueue/suspend.py
# coding: utf-8

import re
from datetime import datetime, timedelta

import discord
from redbot.core import commands, Config
from redbot.core.utils.chat_formatting import box

# Unidades de tiempo para parsear duraciones (e.g., "1d", "5h", "30m")
_TIME_UNITS = {"d": "days", "h": "hours", "m": "minutes"}


def _parse_duration(duration: str) -> timedelta:
    """Parsea una cadena de duración tipo '1d', '5h', '30m' en timedelta."""
    match = re.fullmatch(r"(\d+)([dhm])", duration)
    if not match:
        return None
    amount, unit = match.groups()
    return timedelta(**{_TIME_UNITS[unit]: int(amount)})


class SuspendCog(commands.Cog):
    """🔒 Suspender y levantar suspensión de jugadores en arenaqueue."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=6789012345)
        default_guild = {
            # guild_id -> { user_id: { "start": ts, "end": ts_or_None, "reason": str } }
            "suspensions": {},
        }
        self.config.register_guild(**default_guild)

    async def is_suspended(self, guild: discord.Guild, user: discord.Member):
        """Devuelve (suspended: bool, info: dict) para un usuario."""
        susp = await self.config.guild(guild).suspensions()
        info = susp.get(str(user.id))
        if not info:
            return False, None
        now = datetime.utcnow().timestamp()
        # Si tiene end y ya pasó, levantamos la suspensión automáticamente
        if info["end"] and now >= info["end"]:
            # limpiar
            susp.pop(str(user.id))
            await self.config.guild(guild).suspensions.set(susp)
            return False, None
        return True, info

    @commands.group(name="queue", invoke_without_command=True)
    @commands.guild_only()
    async def queue_base(self, ctx: commands.Context):
        """Grupo base /queue (incluye suspend)."""
        await ctx.send_help(ctx.command)

    @queue_base.group(name="suspend", invoke_without_command=True)
    @commands.admin_or_permissions(manage_guild=True)
    async def suspend_group(self, ctx: commands.Context):
        """Gestiona suspensiones de arenaqueue."""
        await ctx.send_help(ctx.command)

    @suspend_group.command(name="add")
    @commands.admin_or_permissions(manage_guild=True)
    async def suspend_add(
        self,
        ctx: commands.Context,
        member: discord.Member,
        duration: str = None,
        *,
        reason: str = "Sin motivo especificado",
    ):
        """
        Suspende a un miembro de todas las colas.
        duration: opcional, e.g. '1d', '5h', '30m'. Si no se indica, es indefinido.
        """
        susp = await self.config.guild(ctx.guild).suspensions()
        start_ts = datetime.utcnow().timestamp()
        end_ts = None
        if duration:
            delta = _parse_duration(duration)
            if not delta:
                await ctx.send("❌ Formato de duración inválido. Usa e.g. `1d`, `5h` o `30m`.")
                return
            end_ts = (datetime.utcnow() + delta).timestamp()
        susp[str(member.id)] = {
            "start": start_ts,
            "end": end_ts,
            "reason": reason,
        }
        await self.config.guild(ctx.guild).suspensions.set(susp)
        msg = f"🔇 {member.mention} ha sido suspendido"
        if duration:
            msg += f" por {duration}"
        msg += f".\nRazón: {reason}"
        await ctx.send(msg)
        try:
            await member.send(
                f"Has sido suspendido de todas las colas en **{ctx.guild.name}**"
                + (f" por {duration}" if duration else "")
                + f".\nRazón: {reason}"
            )
        except discord.Forbidden:
            pass

    @suspend_group.command(name="remove")
    @commands.admin_or_permissions(manage_guild=True)
    async def suspend_remove(self, ctx: commands.Context, member: discord.Member):
        """
        Levanta la suspensión de un miembro.
        """
        susp = await self.config.guild(ctx.guild).suspensions()
        if str(member.id) not in susp:
            await ctx.send("❌ Este miembro no está suspendido.")
            return
        susp.pop(str(member.id))
        await self.config.guild(ctx.guild).suspensions.set(susp)
        await ctx.send(f"✅ {member.mention} ya no está suspendido.")
        try:
            await member.send(f"Tu suspensión en **{ctx.guild.name}** ha sido levantada.")
        except discord.Forbidden:
            pass

    @queue_base.command(name="suspensions")
    @commands.admin_or_permissions(manage_guild=True)
    async def list_suspensions(self, ctx: commands.Context):
        """
        Muestra todas las suspensiones activas en el servidor.
        """
        susp = await self.config.guild(ctx.guild).suspensions()
        lines = []
        now = datetime.utcnow().timestamp()
        for uid, info in susp.items():
            end = info["end"]
            if end and now >= end:
                continue  # se levantará en next check
            member = ctx.guild.get_member(int(uid))
            name = member.display_name if member else f"<Usuario {uid}>"
            if end:
                end_dt = datetime.utcfromtimestamp(end)
                timestr = f"hasta {end_dt.date()} {end_dt.time():.0f} UTC"
            else:
                timestr = "indefinido"
            lines.append(f"• **{name}** — {timestr}\n  Razón: {info['reason']}")
        if not lines:
            await ctx.send("ℹ️ No hay suspensiones activas.")
            return
        await ctx.send(box("\n".join(lines), lang="yaml"))

    @commands.Cog.listener()
    async def on_command(self, ctx: commands.Context):
        """
        Impide que usuarios suspendidos usen comandos de cola (join/leave/start).
        """
        # Solo interferimos con comandos que empiecen por 'queue '
        if not ctx.command or not ctx.command.full_parent_name == "queue":
            return
        # Check suspensión
        suspended, info = await self.is_suspended(ctx.guild, ctx.author)
        if suspended:
            await ctx.send(
                f"🚫 Estás suspendido de las colas"
                + (f" hasta {datetime.utcfromtimestamp(info['end']).date()}" if info["end"] else " de forma indefinida")
                + f".\nRazón: {info['reason']}"
            )
            raise commands.CheckFailure("Usuario suspendido.")

# Para cargar el cog:
# def setup(bot):
#     bot.add_cog(SuspendCog(bot))
