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
            raise commands.BadArgument(f"The channel or thread '{argument}' is not a valid ID.")

        # Intentar obtener el canal o hilo
        channel = ctx.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await ctx.bot.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden):
                raise commands.BadArgument(f"Could not find a channel or thread with ID {channel_id}.")
        # Verificar que sea un canal de texto o un hilo
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            raise commands.BadArgument("The provided ID does not correspond to a text channel or thread.")
        return channel

class MapTrack(commands.Cog):
    """Cog para rastrear cambios de mapa en servidores de juegos. By Killerbite95"""
    __author__ = "Killerbite95"  # Aquí se declara el autor

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

    @commands.command(name="addmaptrack", aliases=["añadirmaptrack"])
    @checks.admin_or_permissions(administrator=True)
    async def add_map_track(self, ctx, server_ip: str, channel: ChannelOrThreadConverter = None):
        """Adds a server to track map changes.

        Uso: !addmaptrack <server_ip> [channel_id]
        """
        channel = channel or ctx.channel
        async with self.config.guild(ctx.guild).map_track_channels() as map_track_channels:
            map_track_channels[server_ip] = channel.id
        await ctx.send(f"Map track added for server `{server_ip}` in {channel.mention}")
        # Enviar un primer mensaje con el estado actual
        await self.send_map_update(ctx.guild, server_ip, first_time=True)

    @commands.command(name="removemaptrack", aliases=["borrarmaptrack"])
    @checks.admin_or_permissions(administrator=True)
    async def remove_map_track(self, ctx, channel: ChannelOrThreadConverter):
        """Removes all map tracks from a channel or thread.

        Uso: !removemaptrack <channel_id>
        """
        async with self.config.guild(ctx.guild).map_track_channels() as map_track_channels:
            to_remove = [ip for ip, ch_id in map_track_channels.items() if ch_id == channel.id]
            for ip in to_remove:
                del map_track_channels[ip]
        await ctx.send(f"All map tracks removed from channel/thread {channel.mention}")

    @commands.command(name="maptracks", aliases=["listarmaptracks"])
    async def list_map_tracks(self, ctx):
        """Lists all servers with active map tracking."""
        map_track_channels = await self.config.guild(ctx.guild).map_track_channels()
        if not map_track_channels:
            await ctx.send("There are no active map tracks.")
            return

        # Limpiar map tracks con canales eliminados antes de mostrar
        map_track_channels = await self.cleanup_map_tracks(ctx.guild)

        message = "**Active Map Tracks:**\n"
        for server_ip, channel_id in map_track_channels.items():
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except (discord.NotFound, discord.Forbidden):
                    continue  # Ya ha sido limpiado
            if channel:
                message += f"• **{server_ip}** - Channel/Thread: {channel.mention}\n"
        await ctx.send(message)

    @commands.command(name="forcemaptrack", aliases=["forzarmaptrack"])
    async def force_map_track(self, ctx):
        """Forces a map tracking update in the current channel or thread."""
        map_track_channels = await self.config.guild(ctx.guild).map_track_channels()
        server_ip = None
        for ip, channel_id in map_track_channels.items():
            if channel_id == ctx.channel.id:
                server_ip = ip
                break
        if server_ip:
            await self.send_map_update(ctx.guild, server_ip, force=True)
            await ctx.send(f"Map track forced for server `{server_ip}`.")
        else:
            await ctx.send("There is no active map track in this channel or thread.")

    @tasks.loop(seconds=30)
    async def map_check(self):
        """Verifica periódicamente si hay un cambio de mapa en los servidores rastreados."""
        for guild in self.bot.guilds:
            # Limpiar map tracks con canales eliminados
            await self.cleanup_map_tracks(guild)
            map_track_channels = await self.config.guild(guild).map_track_channels()
            tasks_list = []
            for server_ip in list(map_track_channels.keys()):
                tasks_list.append(self.send_map_update(guild, server_ip))
            if tasks_list:
                await asyncio.gather(*tasks_list)

    async def cleanup_map_tracks(self, guild):
        """Elimina map tracks asociados con canales o hilos eliminados."""
        async with self.config.guild(guild).map_track_channels() as map_track_channels:
            to_remove = []
            for server_ip, channel_id in map_track_channels.items():
                channel = self.bot.get_channel(channel_id)
                if channel is None:
                    try:
                        channel = await self.bot.fetch_channel(channel_id)
                    except (discord.NotFound, discord.Forbidden):
                        to_remove.append(server_ip)
                        self.logger.warning(f"Channel with ID {channel_id} not found. Map track for {server_ip} removed.")
                elif not isinstance(channel, (discord.TextChannel, discord.Thread)):
                    # Si el canal no es un canal de texto o hilo, eliminar el map track
                    to_remove.append(server_ip)
                    self.logger.warning(f"Channel with ID {channel_id} is not a text channel or thread. Map track for {server_ip} removed.")
            for server_ip in to_remove:
                del map_track_channels[server_ip]
        return map_track_channels

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
                self.logger.info(f"Server {server_ip} is back online.")

            if first_time or force or last_map != map_name:
                channel_id = await self.config.guild(guild).map_track_channels.get_raw(server_ip)
                channel = self.bot.get_channel(channel_id)
                if channel is None:
                    try:
                        channel = await self.bot.fetch_channel(channel_id)
                    except (discord.NotFound, discord.Forbidden):
                        # Eliminar el map track si el canal no existe
                        async with self.config.guild(guild).map_track_channels() as map_track_channels:
                            del map_track_channels[server_ip]
                        self.logger.warning(f"Channel with ID {channel_id} not found. Map track for {server_ip} removed.")
                        return

                if channel:
                    # Verificar permisos antes de enviar el mensaje
                    if not channel.permissions_for(guild.me).send_messages:
                        self.logger.warning(f"No permission to send messages in {channel} (ID: {channel_id})")
                        return

                    # Reemplazar la IP interna con la IP pública
                    internal_ip, port = server_ip.split(":")
                    if internal_ip.startswith("10.0.0."):
                        public_ip = "178.33.160.187"
                    else:
                        public_ip = internal_ip
                    connect_url = f"https://alienhost.ovh/connect.php?ip={public_ip}:{port}"

                    embed = discord.Embed(
                        title="📢 Map Change Detected!" if not first_time else "📋 Initial Map State",
                        color=discord.Color.green(),
                        timestamp=discord.utils.utcnow()
                    )
                    embed.add_field(name="🗺️ Map", value=map_name, inline=False)
                    embed.add_field(name="👥 Players", value=f"{players}/{max_players}", inline=False)
                    embed.add_field(name="🔗 Connect to server", value=f"[Connect]({connect_url})", inline=False)
                    embed.set_footer(text="MapTrack Monitor by Killerbite95")
                    
                    await channel.send(embed=embed)
                    self.logger.info(f"Sent map update for {server_ip} in {channel}.")
                    
                else:
                    # Eliminar el map track si el canal no existe
                    async with self.config.guild(guild).map_track_channels() as map_track_channels:
                        del map_track_channels[server_ip]
                    self.logger.warning(f"Channel with ID {channel_id} not found. Map track for {server_ip} removed.")
                
                # Almacenar el nuevo mapa como el último mapa
                async with self.config.guild(guild).last_maps() as last_maps:
                    last_maps[server_ip] = map_name
        
        except Exception as e:
            self.logger.error(f"Error getting info from server {server_ip}: {e}")
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
                            # Eliminar el map track si el canal no existe
                            async with self.config.guild(guild).map_track_channels() as map_track_channels:
                                del map_track_channels[server_ip]
                            self.logger.warning(f"Channel with ID {channel_id} not found. Map track for {server_ip} removed.")
                            return
                    if channel:
                        # Verificar permisos antes de enviar el mensaje
                        if not channel.permissions_for(guild.me).send_messages:
                            self.logger.warning(f"No permission to send messages in {channel} (ID: {channel_id})")
                            return

                        embed = discord.Embed(
                            title="❌ Server Offline",
                            color=discord.Color.red(),
                            timestamp=discord.utils.utcnow()
                        )
                        embed.add_field(name="Status", value=":red_circle: Offline", inline=False)
                        embed.set_footer(text="MapTrack Monitor by Killerbite95")

                        await channel.send(embed=embed)
                        self.logger.info(f"Sent offline notification for {server_ip} in {channel}.")
                    else:
                        # Eliminar el map track si el canal no existe
                        async with self.config.guild(guild).map_track_channels() as map_track_channels:
                            del map_track_channels[server_ip]
                        self.logger.warning(f"Channel with ID {channel_id} not found. Map track for {server_ip} removed.")
                    offline_status[server_ip] = True

    def cog_unload(self):
        self.map_check.cancel()

    def __unload(self):
        self.map_check.cancel()

def setup(bot):
    bot.add_cog(MapTrack(bot))
