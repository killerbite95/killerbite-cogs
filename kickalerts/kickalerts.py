# cogs/kickalerts/kickalerts.py

import discord
from discord.ext import commands, tasks
from redbot.core import Config, checks, commands
import aiohttp
import asyncio
import logging

# Configuración del logger para el cog
log = logging.getLogger("red.kickalerts")

class KickAlerts(commands.Cog):
    """Cog para alertar cuando los canales comienzan a transmitir en Kick.com."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        
        # Configuración predeterminada por guild
        default_guild = {
            "alert_channel": None,     # ID del canal donde se enviarán las alertas
            "alerted_streams": [],     # Lista de IDs de transmisiones ya alertadas
            "api_token": None          # Token de acceso a la API de Kick.com (si es necesario)
        }
        self.config.register_guild(**default_guild)
        
        self.session = aiohttp.ClientSession()
        self.check_live_streams.start()

    def cog_unload(self):
        self.check_live_streams.cancel()
        asyncio.create_task(self.session.close())

    @commands.command(name="setkickalertchannel")
    @checks.admin_or_permissions(administrator=True)
    async def set_kick_alert_channel(self, ctx, channel: discord.TextChannel):
        """Establece el canal donde se enviarán las alertas de Kick.com."""
        await self.config.guild(ctx.guild).alert_channel.set(channel.id)
        await ctx.send(f"Canal de alertas de Kick.com establecido en: {channel.mention}")

    @commands.command(name="resetalertedstreams")
    @checks.admin_or_permissions(administrator=True)
    async def reset_alerted_streams(self, ctx):
        """Reinicia la lista de transmisiones alertadas."""
        await self.config.guild(ctx.guild).alerted_streams.set([])
        await ctx.send("Lista de transmisiones alertadas reiniciada.")

    @commands.command(name="setkickt_token")
    @checks.admin_or_permissions(administrator=True)
    async def set_kick_token(self, ctx, token: str):
        """Establece el token de acceso a la API de Kick.com."""
        await self.config.guild(ctx.guild).api_token.set(token)
        await ctx.send("Token de acceso a la API de Kick.com establecido correctamente.")

    async def fetch_live_streams(self, guild_id):
        """Obtiene las transmisiones en vivo desde la API de Kick.com."""
        url = "https://api.kick.com/private/v1/livestreams"
        
        # Obtener el token de acceso desde la configuración (si es necesario)
        api_token = await self.config.guild_from_id(guild_id).api_token()
        headers = {}
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"

        try:
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    log.debug(f"Respuesta de la API: {data}")  # Añadir esta línea para depuración
                    # Asegúrate de ajustar la clave según la estructura real de la respuesta
                    live_streams = data.get("livestreams", [])
                    log.debug(f"Transmisiones obtenidas: {live_streams}")
                    return live_streams
                else:
                    log.error(f"Error al obtener transmisiones de Kick.com: {response.status}")
                    return []
        except Exception as e:
            log.exception(f"Excepción al obtener transmisiones de Kick.com: {e}")
            return []

    @tasks.loop(minutes=5)
    async def check_live_streams(self):
        """Tarea que verifica las transmisiones en vivo y envía alertas."""
        log.debug("Iniciando verificación de transmisiones en vivo.")
        for guild in self.bot.guilds:
            alert_channel_id = await self.config.guild(guild).alert_channel()
            if not alert_channel_id:
                log.debug(f"No se ha configurado un canal de alertas para {guild.name}.")
                continue  # No se ha configurado un canal de alertas para este servidor

            alert_channel = guild.get_channel(alert_channel_id)
            if not alert_channel:
                log.warning(f"El canal de alertas ID {alert_channel_id} no se encontró en {guild.name}.")
                continue

            live_streams = await self.fetch_live_streams(guild.id)
            if not live_streams:
                log.debug("No hay transmisiones en vivo actualmente.")
                continue  # No hay transmisiones en vivo actualmente

            async with self.config.guild(guild).alerted_streams() as alerted_streams:
                for stream in live_streams:
                    stream_id = stream.get("id")
                    streamer_name = stream.get("streamer_name")
                    title = stream.get("title")
                    thumbnail_url = stream.get("thumbnail_url")
                    stream_url = stream.get("url")

                    if stream_id not in alerted_streams:
                        # Crear embed de alerta
                        embed = discord.Embed(
                            title="🔴 Nueva Transmisión en Vivo en Kick.com",
                            description=f"**Streamer:** {streamer_name}\n**Título:** {title}",
                            color=discord.Color.red(),
                            url=stream_url
                        )
                        embed.set_thumbnail(url=thumbnail_url)
                        embed.set_footer(text="KickAlerts - Monitoreando transmisiones en vivo.")

                        # Enviar mensaje de alerta
                        try:
                            await alert_channel.send(embed=embed)
                            log.info(f"Alerta enviada para la transmisión ID {stream_id} en {guild.name}.")
                        except Exception as e:
                            log.exception(f"No se pudo enviar la alerta en {guild.name}: {e}")
                            continue

                        # Añadir a la lista de transmisiones alertadas
                        alerted_streams.append(stream_id)
                        log.debug(f"Transmisión ID {stream_id} añadida a 'alerted_streams'.")

    @check_live_streams.before_loop
    async def before_check_live_streams(self):
        """Espera hasta que el bot esté listo antes de iniciar la tarea."""
        log.debug("Esperando hasta que el bot esté listo para iniciar la tarea de verificación.")
        await self.bot.wait_until_ready()

    @commands.command(name="checkkickstreams")
    @checks.admin_or_permissions(administrator=True)
    async def check_kick_streams_manual(self, ctx):
        """Forzar una verificación manual de transmisiones en vivo."""
        await ctx.trigger_typing()
        await self.check_live_streams()
        await ctx.send("Verificación manual de transmisiones en vivo completada.")
