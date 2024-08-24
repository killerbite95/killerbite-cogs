import discord
from discord.ext import commands, tasks
from opengsq.protocols import Source
import asyncio

class MapTrack(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.servers = {}  # Diccionario para almacenar los servidores y sus datos
        self.check_maps.start()

    @tasks.loop(seconds=30)
    async def check_maps(self):
        for channel_id, server_info in self.servers.items():
            channel = self.bot.get_channel(channel_id)
            if not channel:
                continue

            ip, port, last_map = server_info
            query = Source(ip, port)
            try:
                server_info = await query.get_info()
                current_map = server_info.get('map')

                if current_map != last_map:
                    self.servers[channel_id][2] = current_map
                    players = server_info.get('players', 0)
                    max_players = server_info.get('max_players', 0)
                    await channel.send(f"**Map Change Detected!**\nNow Playing: `{current_map}`\nPlayers Online: `{players}/{max_players}`\n[Join the server!](steam://connect/{ip}:{port})")
            except Exception as e:
                await channel.send(f"Error querying the server {ip}:{port}: {str(e)}")

    @commands.command()
    async def añadirmaptrack(self, ctx, ip: str, port: int):
        """Añadir un servidor al canal actual para seguimiento de mapa."""
        self.servers[ctx.channel.id] = [ip, port, None]
        await ctx.send(f"El servidor `{ip}:{port}` ha sido añadido al seguimiento de mapa en este canal.")

    @commands.command()
    async def borrarmaptrack(self, ctx):
        """Eliminar el seguimiento de mapas en el canal actual."""
        if ctx.channel.id in self.servers:
            del self.servers[ctx.channel.id]
            await ctx.send("El seguimiento de mapas ha sido eliminado para este canal.")
        else:
            await ctx.send("No hay seguimiento de mapas configurado para este canal.")

    def cog_unload(self):
        self.check_maps.cancel()

def setup(bot):
    bot.add_cog(MapTrack(bot))
