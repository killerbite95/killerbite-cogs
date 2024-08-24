import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from opengsq.protocols import Source
import asyncio

class MapTrack(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        self.tracked_servers = {}
        self.task = self.bot.loop.create_task(self.track_servers())

    async def track_servers(self):
        await self.bot.wait_until_red_ready()
        while True:
            for channel_id, servers in self.tracked_servers.items():
                channel = self.bot.get_channel(channel_id)
                for server_info in servers:
                    ip, port, last_map = server_info
                    query = Source(ip, port)
                    try:
                        info = await query.get_info()
                        if info['map'] != last_map:
                            await channel.send(f"Map changed to {info['map']} with {info['players']} players. [Join](steam://connect/{ip}:{port})")
                            server_info[2] = info['map']
                    except Exception as e:
                        await channel.send(f"Failed to query server {ip}:{port}: {e}")
            await asyncio.sleep(30)

    @commands.command(name="añadirmaptrack")
    @commands.admin_or_permissions(administrator=True)
    async def add_maptrack(self, ctx: commands.Context, ip: str, port: int):
        """Añade un servidor para hacer seguimiento de los cambios de mapa en este canal."""
        channel_id = ctx.channel.id
        if channel_id not in self.tracked_servers:
            self.tracked_servers[channel_id] = []
        self.tracked_servers[channel_id].append([ip, port, None])
        await ctx.send(f"Added map tracking for {ip}:{port} in this channel.")

    @commands.command(name="borrarmaptrack")
    @commands.admin_or_permissions(administrator=True)
    async def remove_maptrack(self, ctx: commands.Context):
        """Borra el seguimiento de mapas para este canal."""
        channel_id = ctx.channel.id
        if channel_id in self.tracked_servers:
            del self.tracked_servers[channel_id]
            await ctx.send("Removed all map tracking for this channel.")
        else:
            await ctx.send("No map tracking found for this channel.")

    def cog_unload(self):
        self.task.cancel()
