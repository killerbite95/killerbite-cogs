import discord
from discord.ext import tasks
from redbot.core import commands, Config, checks
from opengsq.protocols import Source
from typing import Union
import asyncio
import logging

class ChannelOrThreadConverter(commands.Converter):
    async def convert(self, ctx, argument):
        # Intentar convertir el argumento a un entero (ID)
        try:
            channel_id = int(argument)
        except ValueError:
            raise commands.BadArgument(f"El canal o hilo '{argument}' no es un ID válido.")

        # Intentar obtener el canal o hilo
        channel = ctx.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await ctx.bot.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden):
                raise commands.BadArgument(f"No se pudo encontrar un canal o hilo con el ID {channel_id}.")
        # Verificar que sea un canal de texto o un hilo
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            raise commands.BadArgument("El ID proporcionado no corresponde a un canal de texto o hilo.")
        return channel

class MapTrack(commands.Cog):
    """Cog para rastrear cambios de mapa en servidores de juegos. By Killerbite95"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_guild = {
            "map_track_channels": {},
            "last_maps": {},
            "offline_status": {}  # Para rastrear si un servidor está offline
        }
        self.config.register_guild(**default_guild)
        self.logger = logging.getLogger("red.MapTrack")
        if not self.logger.hasHandlers():
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
        self.map_check.start()

    @commands.command(name="añadirmaptrack")
    @checks.admin_or_permissions(administrator=True)
    async def add_map_track(self, ctx, server_ip: str, channel: ChannelOrThreadConverter = None):
        """Añade un servidor para rastrear cambios de mapa.

        Uso: !añadirmaptrack <server_ip> [channel_id]
        """
        channel = channel or ctx.channel
        async with self.config.guild(ctx.guild).map_track_channels() as map_track_channels:
            map_track_channels[server_ip] = channel.id
        await ctx.send(f"Map track añadido para el servidor `{server_ip}` en {channel.mention}")
        # Enviar un primer mensaje con el estado actual
        await self.send_map_update(ctx.guild, server_ip, first_time=True)

    @commands.command(name="borrarmaptrack")
    @checks.admin_or_permissions(administrator=True)
    async def remove_map_track(self, ctx, channel: ChannelOrThreadConverter):
        """Elimina todos los map tracks de un canal o hilo.

        Uso: !borrarmaptrack <channel_id>
        """
        async with self.config.guild(ctx.guild).map_track_channels() as map_track_channels:
            to_remove = [ip for ip, ch_id in map_track_channels.items() if ch_id == channel.id]
            for ip in to_remove:
                del map_track_channels[ip]
        await ctx.send(f"Todos los map tracks eliminados del canal/hilo {channel.mention}")

    @commands.command(name="maptracks")
    async def list_map_tracks(self, ctx):
        """Lista todos los servidores con map track activo."""
        map_track_channels = await self.config.guild(ctx.guild).map_track_channels()
        if not map_track_channels:
            await ctx.send("No hay map tracks activos.")
            return
        message = "**MapTracks Activos:**\n"
        for server_ip, channel_id in map_track_channels.items():
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except (discord.NotFound, discord.Forbidden):
                    channel = None
            if channel:
                message += f"• **{server_ip}** - Canal/Hilo: {channel.mention}\n"
            else:
                message += f"• **{server_ip}** - Canal/Hilo: No encontrado (ID: {channel_id})\n"
        await ctx.send(message)

    @commands.command(name="forzarmaptrack")
    async def force_map_track(self, ctx):
        """Fuerza un rastreo de mapa en el canal o hilo actual."""
        map_track_channels = await self.config.guild(ctx.guild).map_track_channels()
        server_ip = None
        for ip, channel_id in map_track_channels.items():
            if channel_id == ctx.channel.id:
                server_ip = ip
                break
        if server_ip:
            await self.send_map_update(ctx.guild, server_ip, force=True)
            await ctx.send(f"Map track forzado para el servidor `{server_ip}`.")
        else:
            await ctx.send("No hay map track activo en este canal o hilo.")

    @tasks.loop(seconds=30)
    async def map_check(self):
        """Verifica periódicamente si hay un cambio de mapa en los servidores rastreados."""
        for guild in self.bot.guilds:
            map_track_channels = await self.config.guild(guild).map_track_channels()
            tasks = []
            for server_ip in list(map_track_channels.keys()):
                tasks.append(self.send_map_update(guild, server_ip))
            if tasks:
                await asyncio.gather(*tasks)

    async def send_map_update(self, guild, server_ip, first_time=False, force=False):
        """Envía una actualización de mapa si hay un cambio."""
        host, port = server_ip.split(":")
        source = Source(host=host, port=int(port))
        
        try:
            info = await source.get_info()
            map_name = info.map
            players = info.players
            max_players = info.max_players
            
            last_maps = await self.config.guild(guild).last_maps()
            last_map = last_maps.get(server_ip)

            # Obtener el estado de offline actual
            offline_status = await self.config.guild(guild).offline_status()
            is_offline = offline_status.get(server_ip, False)
            
            if is_offline:
                # El servidor está online nuevamente, actualizar el estado
                async with self.config.guild(guild).offline_status() as offline_status:
                    offline_status[server_ip] = False
                self.logger.info(f"Servidor {server_ip} volvió en línea.")

            if first_time or force or last_map != map_name:
                channel_id = await self.config.guild(guild).map_track_channels.get_raw(server_ip)
                channel = self.bot.get_channel(channel_id)
                if channel is None:
                    try:
                        channel = await self.bot.fetch_channel(channel_id)
                    except (discord.NotFound, discord.Forbidden):
                        channel = None

                if channel:
                    # Verificar permisos antes de enviar el mensaje
                    if not channel.permissions_for(guild.me).send_messages:
                        self.logger.warning(f"Sin permiso para enviar mensajes en {channel} (ID: {channel_id})")
                        return

                    # Reemplazar la IP interna con la IP pública
                    internal_ip, port = server_ip.split(":")
                    if internal_ip.startswith("10.0.0."):
                        public_ip = "178.33.160.187"
                    else:
                        public_ip = internal_ip
                    connect_url = f"https://vauff.com/connect.php?ip={public_ip}:{port}"

                    embed = discord.Embed(
                        title="📢 ¡Cambio de mapa detectado!" if not first_time else "📋 Estado inicial del mapa",
                        color=discord.Color.green(),
                        timestamp=discord.utils.utcnow()
                    )
                    embed.add_field(name="🗺️ Mapa", value=map_name, inline=False)
                    embed.add_field(name="👥 Jugadores", value=f"{players}/{max_players}", inline=False)
                    embed.add_field(name="🔗 Conectar al servidor", value=f"[Conectar]({connect_url})", inline=False)
                    embed.set_footer(text="MapTrack Monitor by Killerbite95")
                    
                    await channel.send(embed=embed)
                    self.logger.info(f"Enviada actualización de mapa para {server_ip} en {channel}.")
                    
                else:
                    # Si el canal no se encuentra, eliminarlo de la configuración
                    async with self.config.guild(guild).map_track_channels() as map_track_channels:
                        del map_track_channels[server_ip]
                    self.logger.warning(f"Canal con ID {channel_id} no encontrado. Map track para {server_ip} eliminado.")
                
                # Almacenar el nuevo mapa como el último mapa
                async with self.config.guild(guild).last_maps() as last_maps:
                    last_maps[server_ip] = map_name
        
        except Exception as e:
            self.logger.error(f"Error al obtener información del servidor {server_ip}: {e}")
            # Si ocurre un error, asumimos que el servidor está offline
            async with self.config.guild(guild).offline_status() as offline_status:
                if not offline_status.get(server_ip, False):
                    # El servidor no estaba marcado como offline, enviar un mensaje
                    channel_id = await self.config.guild(guild).map_track_channels.get_raw(server_ip)
                    channel = self.bot.get_channel(channel_id)
                    if channel is None:
                        try:
                            channel = await self.bot.fetch_channel(channel_id)
                        except (discord.NotFound, discord.Forbidden):
                            channel = None
                    if channel:
                        # Verificar permisos antes de enviar el mensaje
                        if not channel.permissions_for(guild.me).send_messages:
                            self.logger.warning(f"Sin permiso para enviar mensajes en {channel} (ID: {channel_id})")
                            return

                        embed = discord.Embed(
                            title="❌ Servidor Offline",
                            color=discord.Color.red(),
                            timestamp=discord.utils.utcnow()
                        )
                        embed.add_field(name="Estado", value=":red_circle: Offline", inline=False)
                        embed.set_footer(text="MapTrack Monitor by Killerbite95")

                        await channel.send(embed=embed)
                        self.logger.info(f"Enviada notificación de servidor offline para {server_ip} en {channel}.")
                    else:
                        # Si el canal no se encuentra, eliminarlo de la configuración
                        async with self.config.guild(guild).map_track_channels() as map_track_channels:
                            del map_track_channels[server_ip]
                        self.logger.warning(f"Canal con ID {channel_id} no encontrado. Map track para {server_ip} eliminado.")
                    offline_status[server_ip] = True

    def cog_unload(self):
        self.map_check.cancel()

    def __unload(self):
        self.map_check.cancel()

def setup(bot):
    bot.add_cog(MapTrack(bot))
