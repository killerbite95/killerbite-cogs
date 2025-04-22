# arenaqueue/seasons.py
# coding: utf-8

from redbot.core import commands, Config
from redbot.core.utils.chat_formatting import pagify, box
import discord
from datetime import datetime, timedelta

class SeasonsCog(commands.Cog):
    """🎮 Gestión de temporadas y leaderboards."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=3456789012)
        default_guild = {
            "season": None,  # almacena dict con info de temporada activa
        }
        self.config.register_guild(**default_guild)

    @commands.group(name="season", invoke_without_command=True)
    @commands.guild_only()
    async def season(self, ctx: commands.Context):
        """Grupo de comandos para gestionar temporadas."""
        await ctx.send_help(ctx.command)

    @season.command(name="start")
    @commands.admin_or_permissions(manage_guild=True)
    async def season_start(
        self,
        ctx: commands.Context,
        days: int,
        game: str,
        updates_channel: discord.TextChannel,
        season_name: str = None,
        notify_role: discord.Role = None,
    ):
        """
        Inicia una nueva temporada.
        days: duración en días (1-90)
        game: juego (LoL, Valorant, Overwatch, Custom)
        updates_channel: canal para anuncios
        season_name: nombre opcional
        notify_role: rol opcional a notificar
        """
        if days < 1 or days > 90:
            await ctx.send("❌ La duración debe estar entre 1 y 90 días.")
            return
        now = datetime.utcnow()
        end = now + timedelta(days=days)
        season = {
            "name": season_name or f"Season {now.year}-{now.month}",
            "game": game,
            "start_ts": now.timestamp(),
            "end_ts": end.timestamp(),
            "channel_id": updates_channel.id,
            "role_id": notify_role.id if notify_role else None,
            "stats": {
                "games_played": 0,
                "unique_players": set(),
            },
        }
        # Guardar (convertir set a lista para serializar)
        season["stats"]["unique_players"] = []
        await self.config.guild(ctx.guild).season.set(season)
        # Notificar inicio
        mention = notify_role.mention if notify_role else ""
        await updates_channel.send(
            f"🏁 **{season['name']}** de **{game}** ha comenzado! {mention}\n"
            f"Duración: {days} días (hasta {end.date()})."
        )
        # Programar recordatorio un día antes
        # (Requiere task externo o evento on_ready que compruebe fechas)

    @season.command(name="extend")
    @commands.admin_or_permissions(manage_guild=True)
    async def season_extend(
        self,
        ctx: commands.Context,
        game: str,
        days: int,
    ):
        """
        Extiende la temporada activa.
        game: juego de la temporada a extender
        days: días a sumar
        """
        season = await self.config.guild(ctx.guild).season()
        if not season or season["game"].lower() != game.lower():
            await ctx.send("❌ No hay temporada activa para ese juego.")
            return
        if days < 1 or days > 90:
            await ctx.send("❌ Días de extensión deben estar entre 1 y 90.")
            return
        end = datetime.utcfromtimestamp(season["end_ts"]) + timedelta(days=days)
        season["end_ts"] = end.timestamp()
        await self.config.guild(ctx.guild).season.set(season)
        ch = ctx.guild.get_channel(season["channel_id"])
        await ch.send(f"➕ La temporada **{season['name']}** se extiende {days} días, hasta {end.date()}.")

    @season.command(name="shorten")
    @commands.admin_or_permissions(manage_guild=True)
    async def season_shorten(
        self,
        ctx: commands.Context,
        game: str,
        days: int,
    ):
        """
        Acorta la temporada activa.
        game: juego de la temporada a acortar
        days: días a restar
        """
        season = await self.config.guild(ctx.guild).season()
        if not season or season["game"].lower() != game.lower():
            await ctx.send("❌ No hay temporada activa para ese juego.")
            return
        if days < 1 or days > 90:
            await ctx.send("❌ Días de acortamiento deben estar entre 1 y 90.")
            return
        end_dt = datetime.utcfromtimestamp(season["end_ts"]) - timedelta(days=days)
        if end_dt <= datetime.utcfromtimestamp(season["start_ts"]):
            await ctx.send("❌ La nueva fecha de fin sería anterior al inicio.")
            return
        season["end_ts"] = end_dt.timestamp()
        await self.config.guild(ctx.guild).season.set(season)
        ch = ctx.guild.get_channel(season["channel_id"])
        await ch.send(f"➖ La temporada **{season['name']}** se acorta {days} días, hasta {end_dt.date()}.")

    @season.command(name="end")
    @commands.admin_or_permissions(manage_guild=True)
    async def season_end(
        self,
        ctx: commands.Context,
        game: str,
    ):
        """
        Termina la temporada activa antes de tiempo.
        game: juego de la temporada a terminar
        """
        season = await self.config.guild(ctx.guild).season()
        if not season or season["game"].lower() != game.lower():
            await ctx.send("❌ No hay temporada activa para ese juego.")
            return
        ch = ctx.guild.get_channel(season["channel_id"])
        await ch.send(f"🏁 La temporada **{season['name']}** ha finalizado antes de tiempo.")
        # Aquí podrías enviar standings finales...
        await self.config.guild(ctx.guild).season.clear()

    @season.command(name="stats")
    @commands.guild_only()
    async def season_stats(
        self,
        ctx: commands.Context,
        game: str,
    ):
        """
        Muestra estadísticas de la temporada activa.
        game: juego de la temporada
        """
        season = await self.config.guild(ctx.guild).season()
        if not season or season["game"].lower() != game.lower():
            await ctx.send("❌ No hay temporada activa para ese juego.")
            return
        start = datetime.utcfromtimestamp(season["start_ts"]).date()
        end = datetime.utcfromtimestamp(season["end_ts"]).date()
        stats = season.get("stats", {})
        games = stats.get("games_played", 0)
        unique = len(stats.get("unique_players", []))
        lines = [
            f"**{season['name']}** ({season['game']})",
            f"Inicio: {start}",
            f"Fin: {end}",
            f"Partidas jugadas: {games}",
            f"Jugadores únicos: {unique}",
        ]
        # Top 3 placeholder (requiere implementar leaderboard real)
        lines.append("Top 3 jugadores: (pendiente de implementar)")
        message = "\n".join(lines)
        for page in pagify(message):
            await ctx.send(box(page, lang="ini"))
