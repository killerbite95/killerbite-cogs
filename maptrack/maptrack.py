import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
import asyncio
from opengsq import SourceQuery

class MapTrack(commands.Cog):
    """
    Cog para realizar queries a servidores de CS2 y notificar cambios de mapa en un canal de Discord.
    """

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_guild = {
            "tracked_servers": {}  # Almacena servidores en formato {"channel_id": {"ip:port": {"last_map": "", "interval": 30}}}
        }
        self.config.register_guild(**default_guild)
        self.bg_task = self.bot.loop.create_task(self.maptrack_loop())

    async def maptrack_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            guilds_data = await self.config.all_guilds()
            for guild_id, data in guilds_data.items():
                for channel_id, servers in data["tracked_servers"].items():
                    channel = self.bot.get_channel(int(channel_id))
                    if not channel:
                        continue

                    for server, info in servers.items():
                        ip, port = server.split(":")
                        query = SourceQuery(ip, int(port))

                        try:
                            server_info = await query.info()
                            current_map = server_info.get('map')
                            player_count = server_info.get('players')
                            max_players = server_info.get('max_players')

                            if current_map != info["last_map"]:
                                await channel.send(
                                    f"Now Playing: **{current_map}**\n"
                                    f"Players Online: **{player_count}/{max_players}**\n"
                                    f"Quick Join: **connect {ip}:{port}**"
                                )
                                async with self.config.guild_from_id(guild_id).tracked_servers() as servers:
                                    servers[server]["last_map"] = current_map

                        except Exception as e:
                            await channel.send(f"Error querying server {server}: {str(e)}")

            await asyncio.sleep(30)

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def añadirmaptrack(self, ctx, ip_port: str):
        """Añadir un servidor para monitorizar en el canal actual."""
        channel_id = str(ctx.channel.id)
        async with self.config.guild(ctx.guild).tracked_servers() as servers:
            if channel_id not in servers:
                servers[channel_id] = {}

            if ip_port not in servers[channel_id]:
                servers[channel_id][ip_port] = {"last_map": "", "interval": 30}
                await ctx.send(f"Server {ip_port} added for map tracking in this channel.")
            else:
                await ctx.send(f"Server {ip_port} is already being tracked in this channel.")

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def borrarmaptrack(self, ctx, channel: discord.TextChannel = None):
        """Eliminar todos los servidores monitorizados en un canal específico."""
        if not channel:
            channel = ctx.channel

        channel_id = str(channel.id)
        async with self.config.guild(ctx.guild).tracked_servers() as servers:
            if channel_id in servers:
                del servers[channel_id]
                await ctx.send(f"All map tracking stopped for {channel.mention}.")
            else:
                await ctx.send(f"No map tracking is currently active for {channel.mention}.")

def setup(bot: Red):
    bot.add_cog(MapTrack(bot))
