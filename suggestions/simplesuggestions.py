import discord
from redbot.core import commands, Config, checks

class SimpleSuggestions(commands.Cog):
    """Cog simplificado para gestionar sugerencias."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567891, force_registration=True)
        
        default_guild = {
            "suggestions_channel": None,
            "log_channel": None,
            "dm_responses": True,
            "suggestion_threads": True,
            "keep_logs": True,
            "anonymous_suggestions": True,
            "auto_archive_threads": False,
            "images_in_suggestions": True,
            "ping_in_threads": True,
            "queue_channel": None,
            "queue_rejection_channel": None,
        }
        
        self.config.register_guild(**default_guild)

    @commands.command(name="setchannel")
    @checks.admin_or_permissions(administrator=True)
    async def set_channel(self, ctx, channel: discord.TextChannel):
        """Establece el canal de sugerencias."""
        await self.config.guild(ctx.guild).suggestions_channel.set(channel.id)
        await ctx.send(f"Canal de sugerencias establecido en {channel.mention}")

    @commands.command(name="setlogchannel")
    @checks.admin_or_permissions(administrator=True)
    async def set_log_channel(self, ctx, channel: discord.TextChannel):
        """Establece el canal de logs."""
        await self.config.guild(ctx.guild).log_channel.set(channel.id)
        await ctx.send(f"Canal de logs establecido en {channel.mention}")

    @commands.command(name="suggest")
    async def suggest(self, ctx, *, suggestion: str):
        """Envía una sugerencia al canal configurado."""
        guild_settings = await self.config.guild(ctx.guild).all()
        channel_id = guild_settings["suggestions_channel"]

        if not channel_id:
            return await ctx.send("No se ha configurado un canal de sugerencias.")

        channel = self.bot.get_channel(channel_id)
        if not channel:
            return await ctx.send("No se encontró el canal de sugerencias.")

        embed = discord.Embed(
            title="Nueva Sugerencia",
            description=suggestion,
            color=discord.Color.blue()
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url)

        if guild_settings["anonymous_suggestions"]:
            embed.set_author(name="Anónimo")

        if guild_settings["images_in_suggestions"] and ctx.message.attachments:
            embed.set_image(url=ctx.message.attachments[0].url)

        message = await channel.send(embed=embed)

        if guild_settings["suggestion_threads"]:
            await message.create_thread(name=f"Sugerencia de {ctx.author.display_name}")

        if guild_settings["dm_responses"]:
            await ctx.author.send(f"Tu sugerencia ha sido enviada a {channel.mention}")

    @commands.command(name="setdmresponses")
    @checks.admin_or_permissions(administrator=True)
    async def set_dm_responses(self, ctx, status: bool):
        """Activa o desactiva las respuestas por DM."""
        await self.config.guild(ctx.guild).dm_responses.set(status)
        status_str = "activadas" if status else "desactivadas"
        await ctx.send(f"Respuestas por DM {status_str}")

    @commands.command(name="setanonymous")
    @checks.admin_or_permissions(administrator=True)
    async def set_anonymous_suggestions(self, ctx, status: bool):
        """Activa o desactiva las sugerencias anónimas."""
        await self.config.guild(ctx.guild).anonymous_suggestions.set(status)
        status_str = "activadas" if status else "desactivadas"
        await ctx.send(f"Sugerencias anónimas {status_str}")
