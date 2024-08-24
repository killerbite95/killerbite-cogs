import discord
from discord.ext import tasks
from redbot.core import commands, Config, checks
from opengsq.protocols import Source

class MapTrack(commands.Cog):
    """Cog para rastrear cambios de mapa en servidores de juegos."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_guild = {
            "map_track_channels": {},
            "last_maps": {}
        }
        self.config.register_guild(**default_guild)
        self.map_check.start()

    @commands.command(name="añadirmaptrack")
    @checks.admin_or_permissions(administrator=True)
    async def add_map_track(self, ctx, server_ip: str, channel: discord.TextChannel = None):
        """Añade un servidor para rastrear cambios de mapa."""
        channel = channel or ctx.channel
        async with self.config.guild(ctx.guild).map_track_channels() as map_track_channels:
            map_track_channels[server_ip] = channel.id
        await ctx.send(f"Map track añadido para el servidor {server_ip} en {channel.mention}")
        # Enviar un primer mensaje con el estado actual
        await self.send_map_update(ctx.guild, server_ip, first_time=True)

    @commands.command(name="borrarmaptrack")
    @checks.admin_or_permissions(administrator=True)
    async def remove_map_track(self, ctx, channel: discord.TextChannel):
        """Elimina todos los map track de un canal."""
        async with self.config.guild(ctx.guild).map_track_channels() as map_track_channels:
            to_remove = [ip for ip, ch_id in map_track_channels.items() if ch_id == channel.id]
            for ip in to_remove:
                del map_track_channels[ip]
        await ctx.send(f"Todos los map tracks eliminados del canal {channel.mention}")

    @commands.command(name="maptracks")
    async def list_map_tracks(self, ctx):
        """Lista todos los servidores con map track activo."""
        map_track_channels = await self.config.guild(ctx.guild).map_track_channels()
        if not map_track_channels:
            await ctx.send("No hay map tracks activos.")
            return
        message = "MapTracks Activos:\n"
        for server_ip, channel_id in map_track_channels.items():
            channel = self.bot.get_channel(channel_id)
            if channel:
                message += f"**{server_ip}** - Canal: {channel.mention}\n"
        await ctx.send(message)

    @commands.command(name="forzarmaptrack")
    async def force_map_track(self, ctx):
        """Fuerza un rastreo de mapa en el canal actual."""
        map_track_channels = await self.config.guild(ctx.guild).map_track_channels()
        server_ip = None
        for ip, channel_id in map_track_channels.items():
            if channel_id == ctx.channel.id:
                server_ip = ip
                break
        if server_ip:
            await self.send_map_update(ctx.guild, server_ip, force=True)
        else:
            await ctx.send("No hay map track activo en este canal.")

    @tasks.loop(seconds=30)
    async def map_check(self):
        """Verifica cada 30 segundos si hay un cambio de mapa en los servidores rastreados."""
        for guild in self.bot.guilds:
            map_track_channels = await self.config.guild(guild).map_track_channels()
            for server_ip in map_track_channels.keys():
                await self.send_map_update(guild, server_ip)

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
            
            if first_time or force or last_map != map_name:
                channel_id = await self.config.guild(guild).map_track_channels.get_raw(server_ip)
                channel = self.bot.get_channel(channel_id)
                
                if channel:
                    embed = discord.Embed(
                        title="Map Change Detected!" if not first_time else "Initial Map State",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="Map", value=map_name, inline=False)
                    embed.add_field(name="Players", value=f"{players}/{max_players}", inline=False)
                    embed.add_field(name="Connect", value=f"steam://connect/{server_ip}", inline=False)
                    
                    await channel.send(embed=embed)
                    
                # Almacenar el nuevo mapa como el último mapa
                async with self.config.guild(guild).last_maps() as last_maps:
                    last_maps[server_ip] = map_name
        
        except Exception as e:
            channel_id = await self.config.guild(guild).map_track_channels.get_raw(server_ip)
            channel = self.bot.get_channel(channel_id)
            if channel:
                await channel.send(f"Error al obtener información del servidor {server_ip}: {e}")

    def cog_unload(self):
        self.map_check.cancel()

def setup(bot):
    bot.add_cog(MapTrack(bot))
