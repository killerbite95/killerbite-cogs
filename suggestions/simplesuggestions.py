import discord
from redbot.core import commands, Config, checks

class SimpleSuggestions(commands.Cog):
    """Cog para gestionar sugerencias en un canal de Discord."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_guild = {
            "suggestion_channel": None,
            "log_channel": None,
            "suggestion_threads": False,
            "thread_auto_archive": False,
            "suggestion_id": 1
        }
        self.config.register_guild(**default_guild)

    @commands.command(name="setsuggestionchannel")
    @checks.admin_or_permissions(administrator=True)
    async def set_suggestion_channel(self, ctx, channel: discord.TextChannel):
        """Establece el canal de sugerencias."""
        await self.config.guild(ctx.guild).suggestion_channel.set(channel.id)
        await ctx.send(f"Canal de sugerencias establecido en {channel.mention}.")

    @commands.command(name="setlogchannel")
    @checks.admin_or_permissions(administrator=True)
    async def set_log_channel(self, ctx, channel: discord.TextChannel):
        """Establece el canal de logs de sugerencias."""
        await self.config.guild(ctx.guild).log_channel.set(channel.id)
        await ctx.send(f"Canal de logs de sugerencias establecido en {channel.mention}.")

    @commands.command(name="suggest")
    async def suggest(self, ctx, *, suggestion: str):
        """Envía una sugerencia al canal designado."""
        suggestion_channel_id = await self.config.guild(ctx.guild).suggestion_channel()
        if suggestion_channel_id is None:
            await ctx.send("El canal de sugerencias no ha sido configurado.")
            return

        suggestion_channel = self.bot.get_channel(suggestion_channel_id)
        if suggestion_channel is None:
            await ctx.send("El canal de sugerencias configurado no es válido.")
            return

        suggestion_id = await self.config.guild(ctx.guild).suggestion_id()
        embed = discord.Embed(
            title=f"Sugerencia #{suggestion_id}",
            description=suggestion,
            color=discord.Color.blue()
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        message = await suggestion_channel.send(embed=embed)
        
        # Añadir reacciones 👍 y 👎
        await message.add_reaction("👍")
        await message.add_reaction("👎")
        
        await self.config.guild(ctx.guild).suggestion_id.set(suggestion_id + 1)

        if await self.config.guild(ctx.guild).suggestion_threads():
            await message.create_thread(name=f"Sugerencia #{suggestion_id}", auto_archive_duration=1440)

        await ctx.send("Tu sugerencia ha sido enviada.")

    @commands.command(name="approve")
    @checks.admin_or_permissions(administrator=True)
    async def approve_suggestion(self, ctx, message_id: int):
        """Aprueba una sugerencia."""
        suggestion_channel_id = await self.config.guild(ctx.guild).suggestion_channel()
        suggestion_channel = self.bot.get_channel(suggestion_channel_id)
        if suggestion_channel is None:
            await ctx.send("El canal de sugerencias configurado no es válido.")
            return

        try:
            message = await suggestion_channel.fetch_message(message_id)
            embed = message.embeds[0]
            embed.color = discord.Color.green()
            embed.set_footer(text="Aprobado")
            await message.edit(embed=embed)

            # Archivar el hilo si existe
            if message.thread and await self.config.guild(ctx.guild).thread_auto_archive():
                await message.thread.edit(archived=True, locked=True)

            await ctx.send("Sugerencia aprobada.")
        except discord.NotFound:
            await ctx.send("No se encontró un mensaje con ese ID en el canal de sugerencias.")

    @commands.command(name="deny")
    @checks.admin_or_permissions(administrator=True)
    async def deny_suggestion(self, ctx, message_id: int):
        """Rechaza una sugerencia."""
        suggestion_channel_id = await self.config.guild(ctx.guild).suggestion_channel()
        suggestion_channel = self.bot.get_channel(suggestion_channel_id)
        if suggestion_channel is None:
            await ctx.send("El canal de sugerencias configurado no es válido.")
            return

        try:
            message = await suggestion_channel.fetch_message(message_id)
            embed = message.embeds[0]
            embed.color = discord.Color.red()
            embed.set_footer(text="Rechazado")
            await message.edit(embed=embed)

            # Archivar el hilo si existe
            if message.thread and await self.config.guild(ctx.guild).thread_auto_archive():
                await message.thread.edit(archived=True, locked=True)

            await ctx.send("Sugerencia rechazada.")
        except discord.NotFound:
            await ctx.send("No se encontró un mensaje con ese ID en el canal de sugerencias.")

    @commands.command(name="togglesuggestionthreads")
    @checks.admin_or_permissions(administrator=True)
    async def toggle_suggestion_threads(self, ctx):
        """Activa o desactiva la creación de hilos para nuevas sugerencias."""
        current = await self.config.guild(ctx.guild).suggestion_threads()
        await self.config.guild(ctx.guild).suggestion_threads.set(not current)
        state = "activado" if not current else "desactivado"
        await ctx.send(f"La creación de hilos para nuevas sugerencias ha sido {state}.")

    @commands.command(name="togglethreadarchive")
    @checks.admin_or_permissions(administrator=True)
    async def toggle_thread_archive(self, ctx):
        """Activa o desactiva el archivado automático de hilos creados para sugerencias."""
        current = await self.config.guild(ctx.guild).thread_auto_archive()
        await self.config.guild(ctx.guild).thread_auto_archive.set(not current)
        state = "activado" if not current else "desactivado"
        await ctx.send(f"El archivado automático de hilos ha sido {state}.")

def setup(bot):
    bot.add_cog(SimpleSuggestions(bot))
