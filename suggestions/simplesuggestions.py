import discord
from discord.ext import commands
from redbot.core import Config, checks

class SimpleSuggestions(commands.Cog):
    """Cog para gestionar sugerencias con hilos y administración."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_guild = {
            "suggestion_channel": None,
            "log_channel": None,
            "dm_responses": True,
            "suggestion_threads": True,
            "thread_auto_archive": False,
        }
        self.config.register_guild(**default_guild)

    @commands.command(name="setsuggestionchannel")
    @checks.admin_or_permissions(administrator=True)
    async def set_suggestion_channel(self, ctx, channel: discord.TextChannel):
        """Establece el canal para las sugerencias."""
        await self.config.guild(ctx.guild).suggestion_channel.set(channel.id)
        await ctx.send(f"Canal de sugerencias establecido en {channel.mention}")

    @commands.command(name="setlogchannel")
    @checks.admin_or_permissions(administrator=True)
    async def set_log_channel(self, ctx, channel: discord.TextChannel):
        """Establece el canal de logs."""
        await self.config.guild(ctx.guild).log_channel.set(channel.id)
        await ctx.send(f"Canal de logs establecido en {channel.mention}")

    @commands.command(name="suggest")
    async def suggest(self, ctx, *, suggestion: str):
        """Envía una sugerencia."""
        suggestion_channel_id = await self.config.guild(ctx.guild).suggestion_channel()
        suggestion_channel = self.bot.get_channel(suggestion_channel_id)
        if not suggestion_channel:
            await ctx.send("El canal de sugerencias no está configurado.")
            return

        embed = discord.Embed(title="Nueva Sugerencia", description=suggestion, color=discord.Color.blue())
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        embed.set_footer(text=f"Sugerencia de {ctx.author.id}")

        message = await suggestion_channel.send(embed=embed)
        await message.add_reaction("👍")
        await message.add_reaction("👎")

        if await self.config.guild(ctx.guild).suggestion_threads():
            thread = await message.create_thread(name=f"Sugerencia de {ctx.author.display_name}", auto_archive_duration=10080)
            await thread.send(f"Discusión sobre la sugerencia: {suggestion}")

        if await self.config.guild(ctx.guild).dm_responses():
            try:
                await ctx.author.send(f"Tu sugerencia ha sido enviada: {suggestion}")
            except discord.Forbidden:
                pass

        await ctx.send("Sugerencia enviada.")

    @commands.command(name="approve")
    @checks.admin_or_permissions(administrator=True)
    async def approve_suggestion(self, ctx, message_id: int):
        """Aprueba una sugerencia."""
        suggestion_channel_id = await self.config.guild(ctx.guild).suggestion_channel()
        suggestion_channel = self.bot.get_channel(suggestion_channel_id)
        if not suggestion_channel:
            await ctx.send("El canal de sugerencias no está configurado.")
            return

        try:
            message = await suggestion_channel.fetch_message(message_id)
            embed = message.embeds[0]
            embed.color = discord.Color.green()
            embed.add_field(name="Estado", value="Aprobado", inline=False)
            await message.edit(embed=embed)

            if await self.config.guild(ctx.guild).log_channel():
                log_channel = self.bot.get_channel(await self.config.guild(ctx.guild).log_channel())
                if log_channel:
                    await log_channel.send(f"La sugerencia `{message_id}` ha sido aprobada por {ctx.author.mention}.")
        except discord.NotFound:
            await ctx.send("No se encontró el mensaje con esa ID.")

    @commands.command(name="deny")
    @checks.admin_or_permissions(administrator=True)
    async def deny_suggestion(self, ctx, message_id: int):
        """Rechaza una sugerencia."""
        suggestion_channel_id = await self.config.guild(ctx.guild).suggestion_channel()
        suggestion_channel = self.bot.get_channel(suggestion_channel_id)
        if not suggestion_channel:
            await ctx.send("El canal de sugerencias no está configurado.")
            return

        try:
            message = await suggestion_channel.fetch_message(message_id)
            embed = message.embeds[0]
            embed.color = discord.Color.red()
            embed.add_field(name="Estado", value="Rechazado", inline=False)
            await message.edit(embed=embed)

            if await self.config.guild(ctx.guild).log_channel():
                log_channel = self.bot.get_channel(await self.config.guild(ctx.guild).log_channel())
                if log_channel:
                    await log_channel.send(f"La sugerencia `{message_id}` ha sido rechazada por {ctx.author.mention}.")
        except discord.NotFound:
            await ctx.send("No se encontró el mensaje con esa ID.")

    @commands.command(name="togglesuggestionthreads")
    @checks.admin_or_permissions(administrator=True)
    async def toggle_suggestion_threads(self, ctx):
        """Activa o desactiva la creación de hilos para nuevas sugerencias."""
        current = await self.config.guild(ctx.guild).suggestion_threads()
        await self.config.guild(ctx.guild).suggestion_threads.set(not current)
        state = "activada" if not current else "desactivada"
        await ctx.send(f"La creación de hilos para sugerencias ha sido {state}.")

    @commands.command(name="togglethreadarchive")
    @checks.admin_or_permissions(administrator=True)
    async def toggle_thread_archive(self, ctx):
        """Activa o desactiva el archivado automático de hilos creados para sugerencias."""
        current = await self.config.guild(ctx.guild).thread_auto_archive()
        await self.config.guild(ctx.guild).thread_auto_archive.set(not current)
        state = "activado" si no current else "desactivado"
        await ctx.send(f"El archivado automático de hilos ha sido {state}.")

    def cog_unload(self):
        pass

def setup(bot):
    bot.add_cog(SimpleSuggestions(bot))
