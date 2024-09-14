import discord
from discord.ext import tasks
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core import bank

class AutoPrune(commands.Cog):
    """Detecta nuevos baneos y ejecuta prune automáticamente."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890123, force_registration=True)
        default_guild = {
            "prune_channel": None,
            "log_channel": None,
            "last_bans": []
        }
        self.config.register_guild(**default_guild)
        self.check_bans.start()

    def cog_unload(self):
        self.check_bans.cancel()

    @commands.command(name="setprunechannel")
    @commands.admin_or_permissions(administrator=True)
    async def set_prune_channel(self, ctx, channel: discord.TextChannel):
        """Establece el canal donde se ejecutará el comando de prune."""
        await self.config.guild(ctx.guild).prune_channel.set(channel.id)
        await ctx.send(f"Canal establecido para ejecutar el prune: {channel.mention}")

    @commands.command(name="setlogprune")
    @commands.admin_or_permissions(administrator=True)
    async def set_log_prune(self, ctx, channel: discord.TextChannel):
        """Establece el canal donde se enviarán los logs de prune."""
        await self.config.guild(ctx.guild).log_channel.set(channel.id)
        await ctx.send(f"Canal de logs establecido: {channel.mention}")

    @commands.command(name="forceprune")
    @commands.admin_or_permissions(administrator=True)
    async def force_prune(self, ctx):
        """Fuerza la ejecución de prune manualmente."""
        guild = ctx.guild
        log_channel_id = await self.config.guild(guild).log_channel()
        log_channel = guild.get_channel(log_channel_id) if log_channel_id else None

        try:
            await bank.prune_accounts(guild, local=True)
            await ctx.send("Prune forzado ejecutado correctamente.")
            if log_channel:
                await log_channel.send("Prune forzado ejecutado sin errores.")
        except Exception as e:
            await ctx.send(f"Error al ejecutar prune: {e}")
            if log_channel:
                await log_channel.send(f"Error al ejecutar prune: {e}")

    @tasks.loop(minutes=10)
    async def check_bans(self):
        for guild in self.bot.guilds:
            prune_channel_id = await self.config.guild(guild).prune_channel()
            log_channel_id = await self.config.guild(guild).log_channel()
            last_bans = await self.config.guild(guild).last_bans()

            if not prune_channel_id:
                continue

            prune_channel = guild.get_channel(prune_channel_id)
            log_channel = guild.get_channel(log_channel_id) if log_channel_id else None

            if not prune_channel:
                continue

            # Obtener lista de usuarios baneados
            try:
                current_bans = await guild.bans()
                current_banned_ids = [ban_entry.user.id for ban_entry in current_bans]

                # Comparar la lista actual de baneos con la última guardada
                new_bans = set(current_banned_ids) - set(last_bans)
                if new_bans:
                    # Llamar a la función de prune directamente
                    await bank.prune_accounts(guild, local=True)

                    # Guardar la lista actual como la nueva lista de baneos
                    await self.config.guild(guild).last_bans.set(current_banned_ids)

                    # Enviar logs al canal configurado si existe
                    if log_channel:
                        await log_channel.send(f"Se ha ejecutado prune debido a {len(new_bans)} nuevos baneos detectados.")

            except Exception as e:
                if log_channel:
                    await log_channel.send(f"Error al comprobar baneos: {e}")

    @check_bans.before_loop
    async def before_check_bans(self):
        await self.bot.wait_until_ready()
