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
            "alert_channel": None,         # ID del canal donde se enviarán las alertas
            "alerted_streams": [],         # Lista de IDs de transmisiones ya alertadas
            "api_token": None,             # Token de acceso a la API de Kick.com (si es necesario)
            "monitored_channels": []       # Lista de canales de Kick a monitorear (por slug)
        }
        self.config.register_guild(**default_guild)
        
        self.session = aiohttp.ClientSession()
        self.check_live_streams_task.start()

    def cog_unload(self):
        self.check_live_streams_task.cancel()
        asyncio.create_task(self.session.close())

    @commands.command(name="setkickalertchannel")
    @checks.admin_or_permissions(administrator=True)
    async def set_kick_alert_channel(self, ctx, channel: discord.TextChannel):
        """Establece el canal donde se enviarán las alertas de Kick.com."""
        await self.config.guild(ctx.guild).alert_channel.set(channel.id)
        await ctx.send(f"Canal de alertas de Kick.com establecido en: {channel.mention}")
        log.info(f"Guild {ctx.guild.name} ha establecido el canal de alertas en {channel.name}.")

    @commands.command(name="resetalertedstreams")
    @checks.admin_or_permissions(administrator=True)
    async def reset_alerted_streams(self, ctx):
        """Reinicia la lista de transmisiones alertadas."""
        await self.config.guild(ctx.guild).alerted_streams.set([])
        await ctx.send("Lista de transmisiones alertadas reiniciada.")
        log.info(f"Guild {ctx.guild.name} ha reiniciado la lista de transmisiones alertadas.")

    @commands.command(name="setkickt_token")
    @checks.admin_or_permissions(administrator=True)
    async def set_kick_token(self, ctx, token: str):
        """Establece el token de acceso a la API de Kick.com."""
        await self.config.guild(ctx.guild).api_token.set(token)
        await ctx.send("Token de acceso a la API de Kick.com establecido correctamente.")
        log.info(f"Guild {ctx.guild.name} ha establecido el token de la API de Kick.com.")

    @commands.command(name="addkickchannel")
    @checks.admin_or_permissions(administrator=True)
    async def add_kick_channel(self, ctx, *, channel_slug: str):
        """Añade un canal de Kick.com para monitorear si está en directo."""
        async with self.config.guild(ctx.guild).monitored_channels() as channels:
            if channel_slug in channels:
                await ctx.send(f"El canal de Kick.com `{channel_slug}` ya está siendo monitoreado.")
                return
            channels.append(channel_slug)
        await ctx.send(f"El canal de Kick.com `{channel_slug}` ha sido añadido a la lista de monitoreo.")
        log.info(f"Guild {ctx.guild.name} ha añadido el canal de Kick.com `{channel_slug}` para monitoreo.")

    @commands.command(name="removekickchannel")
    @checks.admin_or_permissions(administrator=True)
    async def remove_kick_channel(self, ctx, *, channel_slug: str):
        """Elimina un canal de Kick.com de la lista de monitoreo."""
        async with self.config.guild(ctx.guild).monitored_channels() as channels:
            if channel_slug not in channels:
                await ctx.send(f"El canal de Kick.com `{channel_slug}` no está siendo monitoreado.")
                return
            channels.remove(channel_slug)
        await ctx.send(f"El canal de Kick.com `{channel_slug}` ha sido eliminado de la lista de monitoreo.")
        log.info(f"Guild {ctx.guild.name} ha eliminado el canal de Kick.com `{channel_slug}` del monitoreo.")

    @commands.command(name="listkickchannels")
    @checks.admin_or_permissions(administrator=True)
    async def list_kick_channels(self, ctx):
        """Lista todos los canales de Kick.com que están siendo monitoreados."""
        channels = await self.config.guild(ctx.guild).monitored_channels()
        if not channels:
            await ctx.send("No hay canales de Kick.com siendo monitoreados actualmente.")
            return
        channel_list = "\n".join(f"- {channel}" for channel in channels)
        embed = discord.Embed(
            title="📺 Canales de Kick.com Monitoreados",
            description=channel_list,
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

    async def fetch_live_streams(self, guild_id):
        """Obtiene las transmisiones en vivo desde la API de Kick.com para los canales monitoreados."""
        url = "https://api.kick.com/private/v1/livestreams"
        
        # Obtener el token de acceso desde la configuración (si es necesario)
        api_token = await self.config.guild_from_id(guild_id).api_token()
        headers = {}
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"

        # Obtener los canales monitoreados
        monitored_channels = await self.config.guild_from_id(guild_id).monitored_channels()
        if not monitored_channels:
            log.debug(f"Guild ID {guild_id} no tiene canales de Kick.com monitoreados.")
            return []

        try:
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    log.debug(f"Respuesta de la API: {data}")  # Línea para depuración
                    
                    # Asumiendo que las transmisiones están bajo 'livestreams'
                    all_live_streams = data.get("livestreams", [])
                    log.debug(f"Transmisiones obtenidas: {all_live_streams}")
                    
                    # Filtrar transmisiones por los canales monitoreados
                    live_streams = []
                    for stream in all_live_streams:
                        # Suponiendo que 'streamer_name' representa el slug del canal de Kick
                        channel_slug = stream.get("streamer_name")
                        if channel_slug in monitored_channels:
                            live_streams.append({
                                "id": stream.get("id"),
                                "streamer_name": channel_slug,
                                "title": stream.get("title"),
                                "thumbnail_url": stream.get("thumbnail_url"),
                                "url": stream.get("url")
                            })
                    
                    log.debug(f"Transmisiones filtradas para monitoreo: {live_streams}")
                    return live_streams
                else:
                    log.error(f"Error al obtener transmisiones de Kick.com: {response.status}")
                    return []
        except Exception as e:
            log.exception(f"Excepción al obtener transmisiones de Kick.com: {e}")
            return []

    async def check_live_streams(self):
        """Función principal para verificar transmisiones en vivo y enviar alertas."""
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

    @tasks.loop(minutes=5)
    async def check_live_streams_task(self):
        """Tarea programada que verifica transmisiones en vivo cada 5 minutos."""
        await self.check_live_streams()

    @check_live_streams_task.before_loop
    async def before_check_live_streams_task(self):
        """Espera hasta que el bot esté listo antes de iniciar la tarea."""
        log.debug("Esperando hasta que el bot esté listo para iniciar la tarea de verificación.")
        await self.bot.wait_until_ready()

    @commands.command(name="checkkickstreams")
    @checks.admin_or_permissions(administrator=True)
    async def check_kick_streams_manual(self, ctx):
        """Forzar una verificación manual de transmisiones en vivo."""
        async with ctx.typing():
            await self.check_live_streams()
        await ctx.send("Verificación manual de transmisiones en vivo completada.")
        log.info(f"Guild {ctx.guild.name} ha ejecutado una verificación manual de transmisiones en vivo.")
