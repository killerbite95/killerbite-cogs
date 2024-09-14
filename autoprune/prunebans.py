import discord
from discord.ext import tasks, commands
from redbot.core import commands, Config, checks
from redbot.core.bot import Red

class PruneBans(commands.Cog):
    """Cog para manejar la eliminación de créditos de usuarios baneados automáticamente."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        self.config.register_guild(log_channel=None, last_bans=[])
        self.check_bans.start()

    def cog_unload(self):
        self.check_bans.cancel()

    @commands.command(name="setlogprune")
    @checks.admin_or_permissions(administrator=True)
    async def set_log_prune(self, ctx, channel: discord.TextChannel):
        """Establece el canal donde se enviarán los logs de prune."""
        await self.config.guild(ctx.guild).log_channel.set(channel.id)
        await ctx.send(f"Canal de logs establecido en: {channel.mention}")

    @commands.command(name="forceprune")
    @checks.admin_or_permissions(administrator=True)
    async def force_prune(self, ctx):
        """Fuerza la ejecución de prune sin comprobar los baneos."""
        await self.execute_prune(ctx.guild)
        await ctx.send("Función de prune forzada ejecutada.")

    @tasks.loop(minutes=10)
    async def check_bans(self):
        """Comprueba cada 10 minutos si hay nuevos baneados y ejecuta la función de prune si es necesario."""
        for guild in self.bot.guilds:
            await self.check_new_bans(guild)

    async def check_new_bans(self, guild: discord.Guild):
        """Comprueba los nuevos baneos en el servidor."""
        try:
            last_bans = await self.config.guild(guild).last_bans()
            current_bans = [ban async for ban in guild.bans()]
            current_ban_ids = [ban_entry.user.id for ban_entry in current_bans]

            new_bans = [ban for ban in current_ban_ids if ban not in last_bans]

            if new_bans:
                await self.execute_prune(guild)
                await self.config.guild(guild).last_bans.set(current_ban_ids)
        except Exception as e:
            log_channel_id = await self.config.guild(guild).log_channel()
            if log_channel_id:
                channel = guild.get_channel(log_channel_id)
                if channel:
                    await channel.send(f"Error al comprobar los baneos: {str(e)}")

    async def execute_prune(self, guild: discord.Guild):
        """Ejecuta el comando prune en el canal de logs configurado."""
        log_channel_id = await self.config.guild(guild).log_channel()
        if log_channel_id:
            log_channel = guild.get_channel(log_channel_id)
            if log_channel:
                try:
                    # Enviar el comando prune al canal de logs
                    await log_channel.send("!bankset prune local yes")
                    await log_channel.send("Función prune ejecutada correctamente.")
                except Exception as e:
                    await log_channel.send(f"Error al ejecutar prune: {str(e)}")
