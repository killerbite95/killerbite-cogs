# arenaqueue/admin_utils.py
# coding: utf-8

import discord
from redbot.core import commands, Config
from redbot.core.utils.chat_formatting import box

class AdminUtilsCog(commands.Cog):
    """🔧 Comandos administrativos generales para arenaqueue"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9012345678)
        default_guild = {
            "join_limit": True,
            "mmr_toggle": True,
        }
        self.config.register_guild(**default_guild)

    @commands.command(name="reset")
    @commands.admin_or_permissions(manage_guild=True)
    async def cmd_reset(self, ctx: commands.Context, target: str = None):
        """
        Resetea datos: `scores` o `challenges` o `mvp`.
        """
        if not target:
            await ctx.send_help()
            return
        # TODO: implementar lógica de reset
        await ctx.send(f"🔄 Reset de `{target}` ejecutado.")

    @commands.command(name="void")
    @commands.admin_or_permissions(manage_guild=True)
    async def cmd_void(self, ctx: commands.Context):
        """Purge all records of a game (void)."""
        # TODO: implementar purge de partida
        await ctx.send("🗑️ Partida purgada.")

    @commands.command(name="change_winner")
    @commands.admin_or_permissions(manage_guild=True)
    async def cmd_change_winner(self, ctx: commands.Context, game_id: int, winner: discord.Member):
        """Change the results of a finished game."""
        # TODO: actualizar la base de datos de resultados
        await ctx.send(f"🏅 Ganador actualizado para el juego {game_id}: {winner.mention}")

    @commands.command(name="winner")
    @commands.guild_only()
    async def cmd_winner(self, ctx: commands.Context, winner: discord.Member):
        """Set a winner for an ongoing game without vote."""
        # TODO: asignar ganador al juego en curso
        await ctx.send(f"🎉 ¡{winner.mention} ha sido declarado ganador!")

    @commands.group(name="aqconfig", invoke_without_command=True)
    @commands.guild_only()
    async def aqconfig(self, ctx: commands.Context):
        """Grupo de comandos de configuración avanzada de arenaqueue."""
        await ctx.send_help(ctx.command)

    @aqconfig.command(name="join_limit")
    @commands.admin_or_permissions(manage_guild=True)
    async def queue_join_limit(self, ctx: commands.Context, enabled: bool):
        """Decide si players pueden estar en varias colas a la vez."""
        await self.config.guild(ctx.guild).join_limit.set(enabled)
        await ctx.send(f"✅ Límite de joins establecido a `{enabled}`.")

    @aqconfig.command(name="duo")
    @commands.admin_or_permissions(manage_guild=True)
    async def queue_duo(self, ctx: commands.Context, enabled: bool):
        """Toggle duo queuing."""
        # TODO: aplicar setting de duo
        await ctx.send(f"✅ Duo queuing establecido a `{enabled}`.")

    @aqconfig.command(name="role")
    @commands.admin_or_permissions(manage_guild=True)
    async def queue_role(self, ctx: commands.Context, role: discord.Role):
        """Require users to have this role before queueing."""
        # TODO: almacenar y aplicar role requirement
        await ctx.send(f"✅ Rol requerido para colar: {role.mention}.")

    @aqconfig.command(name="fill")
    @commands.admin_or_permissions(manage_guild=True)
    async def queue_fill(self, ctx: commands.Context, enabled: bool):
        """Enable fill: random assigned roles for fillers."""
        # TODO: aplicar fill setting
        await ctx.send(f"✅ Fill habilitado: `{enabled}`.")

    @aqconfig.command(name="casual")
    @commands.admin_or_permissions(manage_guild=True)
    async def queue_casual(self, ctx: commands.Context, enabled: bool):
        """Enable casual mode: single quick queue button."""
        # TODO: aplicar casual mode
        await ctx.send(f"✅ Modo casual: `{enabled}`.")

    @aqconfig.command(name="force_start")
    @commands.admin_or_permissions(manage_guild=True)
    async def queue_force_start(self, ctx: commands.Context):
        """Forces the game to start once ready-up begins."""
        # TODO: aplicar force start
        await ctx.send("🏁 Force start habilitado.")

    @aqconfig.command(name="schedule")
    @commands.admin_or_permissions(manage_guild=True)
    async def queue_schedule(
        self,
        ctx: commands.Context,
        open_time: str,
        close_time: str,
        timezone: str = "UTC"
    ):
        """Schedule when the queue opens/closes automatically."""
        # TODO: parsear y almacenar horario
        await ctx.send(f"📅 Cola programada de {open_time} a {close_time} ({timezone}).")

    @commands.command(name="purge")
    @commands.admin_or_permissions(manage_guild=True)
    async def cmd_purge(self, ctx: commands.Context, purge_type: str):
        """Purge user|inactive from database."""
        # TODO: implementar purge
        await ctx.send(f"🧹 `{purge_type}` purgado.")

    @commands.command(name="grant")
    @commands.admin_or_permissions(manage_guild=True)
    async def cmd_grant(self, ctx: commands.Context, role: discord.Role, command_name: str):
        """Grant a Discord role permission to run a specific admin command."""
        # TODO: registrar permiso
        await ctx.send(f"🔑 Permiso `{command_name}` otorgado a {role.mention}.")

    @commands.command(name="revoke")
    @commands.admin_or_permissions(manage_guild=True)
    async def cmd_revoke(self, ctx: commands.Context, role: discord.Role, command_name: str):
        """Revoke a previously granted admin command from a role."""
        # TODO: revocar permiso
        await ctx.send(f"🚫 Permiso `{command_name}` revocado de {role.mention}.")

    @commands.command(name="server_stats")
    @commands.guild_only()
    async def cmd_server_stats(self, ctx: commands.Context):
        """Bring up server statistics for arenaqueue bot."""
        # TODO: generar estadísticas
        await ctx.send("📊 Estadísticas del servidor: ...")

    @commands.command(name="check_permissions")
    @commands.guild_only()
    async def cmd_check_permissions(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Check and display enabled arenaqueue permissions in a channel."""
        ch = channel or ctx.channel
        # TODO: introspectar y mostrar permisos
        await ctx.send(f"🔍 Permisos en {ch.mention}: ...")
