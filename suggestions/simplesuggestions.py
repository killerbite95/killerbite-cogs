import discord
from discord.ext import commands
from redbot.core import Config, checks

class SimpleSuggestions(commands.Cog):
    """Simple Suggestions System"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210, force_registration=True)
        default_guild = {
            "suggestions_channel": None,
            "log_channel": None,
            "dm_responses": True,
            "anonymous_suggestions": False,
            "create_threads": True,
            "keep_logs": True
        }
        self.config.register_guild(**default_guild)

    @commands.command(name="setsuggestionschannel")
    @checks.admin_or_permissions(administrator=True)
    async def set_suggestions_channel(self, ctx, channel: discord.TextChannel):
        """Establece el canal de sugerencias."""
        await self.config.guild(ctx.guild).suggestions_channel.set(channel.id)
        await ctx.send(f"Canal de sugerencias establecido en {channel.mention}")

    @commands.command(name="setlogchannel")
    @checks.admin_or_permissions(administrator=True)
    async def set_log_channel(self, ctx, channel: discord.TextChannel):
        """Establece el canal de registro."""
        await self.config.guild(ctx.guild).log_channel.set(channel.id)
        await ctx.send(f"Canal de registro establecido en {channel.mention}")

    @commands.command(name="setsuggestion")
    async def set_suggestion(self, ctx, *, suggestion: str):
        """Envía una sugerencia."""
        guild_settings = await self.config.guild(ctx.guild).all()
        channel_id = guild_settings["suggestions_channel"]
        if not channel_id:
            await ctx.send("No se ha establecido un canal de sugerencias.")
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            await ctx.send("El canal de sugerencias no es válido.")
            return

        embed = discord.Embed(
            title="Nueva Sugerencia",
            description=suggestion,
            color=discord.Color.blue()
        )
        if guild_settings["anonymous_suggestions"]:
            embed.set_footer(text="Enviado de forma anónima")
        else:
            embed.set_footer(text=f"Sugerido por {ctx.author.name}")

        suggestion_message = await channel.send(embed=embed)

        if guild_settings["create_threads"]:
            await suggestion_message.create_thread(name=f"Sugerencia de {ctx.author.name}")

        if guild_settings["dm_responses"]:
            try:
                await ctx.author.send("Tu sugerencia ha sido enviada.")
            except discord.Forbidden:
                pass

        if guild_settings["log_channel"]:
            log_channel = self.bot.get_channel(guild_settings["log_channel"])
            if log_channel:
                await log_channel.send(f"Sugerencia enviada por {ctx.author.mention}: {suggestion}")

    @commands.command(name="approvesuggestion")
    @checks.admin_or_permissions(administrator=True)
    async def approve_suggestion(self, ctx, message_id: int):
        """Aprueba una sugerencia."""
        guild_settings = await self.config.guild(ctx.guild).all()
        channel_id = guild_settings["suggestions_channel"]
        channel = self.bot.get_channel(channel_id)
        if not channel:
            await ctx.send("No se ha establecido un canal de sugerencias.")
            return

        try:
            message = await channel.fetch_message(message_id)
            embed = message.embeds[0]
            embed.color = discord.Color.green()
            embed.add_field(name="Estado", value="Aprobado")
            await message.edit(embed=embed)

            if guild_settings["log_channel"]:
                log_channel = self.bot.get_channel(guild_settings["log_channel"])
                if log_channel:
                    await log_channel.send(f"La sugerencia {message_id} ha sido aprobada.")

        except discord.NotFound:
            await ctx.send("No se encontró la sugerencia especificada.")

    @commands.command(name="denysuggestion")
    @checks.admin_or_permissions(administrator=True)
    async def deny_suggestion(self, ctx, message_id: int):
        """Rechaza una sugerencia."""
        guild_settings = await self.config.guild(ctx.guild).all()
        channel_id = guild_settings["suggestions_channel"]
        channel = self.bot.get_channel(channel_id)
        if not channel:
            await ctx.send("No se ha establecido un canal de sugerencias.")
            return

        try:
            message = await channel.fetch_message(message_id)
            embed = message.embeds[0]
            embed.color = discord.Color.red()
            embed.add_field(name="Estado", value="Rechazado")
            await message.edit(embed=embed)

            if guild_settings["log_channel"]:
                log_channel = self.bot.get_channel(guild_settings["log_channel"])
                if log_channel:
                    await log_channel.send(f"La sugerencia {message_id} ha sido rechazada.")

        except discord.NotFound:
            await ctx.send("No se encontró la sugerencia especificada.")

def setup(bot):
    bot.add_cog(SimpleSuggestions(bot))
