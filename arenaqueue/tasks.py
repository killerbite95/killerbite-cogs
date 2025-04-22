# arenaqueue/tasks.py
# coding: utf-8

import discord
from redbot.core import commands, Config
from redbot.core.utils import schedules
from redbot.core.utils.chat_formatting import box
from redbot.core.utils.schedules import crontab
from redbot.core.bot import Red
from datetime import datetime, timedelta

class SeasonTasks(commands.Cog):
    """Tareas programadas para gestionar recordatorios y cierre automático de temporadas."""

    def __init__(self, bot: Red):
        self.bot = bot
        # Usamos el mismo identifier que en seasons.py para compartir configuración
        self.config = Config.get_conf(self, identifier=3456789012)
        # No volvemos a register_guild aquí: ya lo hace SeasonsCog
        self.check_seasons.start()

    def cog_unload(self):
        self.check_seasons.cancel()

    @schedules.loop(schedule=crontab(hour=0, minute=0))
    async def check_seasons(self):
        """Revisa cada día a medianoche UTC el estado de las temporadas activas."""
        now = datetime.utcnow()
        for guild in self.bot.guilds:
            season = await self.config.guild(guild).season()
            if not season:
                continue

            start = datetime.utcfromtimestamp(season["start_ts"])
            end = datetime.utcfromtimestamp(season["end_ts"])
            channel = guild.get_channel(season["channel_id"])
            role = guild.get_role(season["role_id"]) if season.get("role_id") else None

            # Recordatorio 1 día antes
            if timedelta(days=1) >= (end - now) > timedelta(hours=23):
                mention = role.mention if role else ""
                await channel.send(
                    f"⏰ **Recordatorio:** la temporada **{season['name']}** finaliza mañana ({end.date()}). {mention}"
                )

            # Cierre automático de temporada
            if now >= end:
                await channel.send(f"🏆 **{season['name']}** ha finalizado. ¡Aquí los resultados finales!")
                # TODO: Formatear y enviar standings reales
                await self.config.guild(guild).season.clear()

    @check_seasons.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()
