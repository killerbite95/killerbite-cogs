import discord
from redbot.core import commands, Config
from opengsq.protocols import Source
import asyncio

class MapTrack(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        self.config.register_guild(tracked_servers={})
        self.loop = asyncio.create_task(self.track_maps())

    def cog_unload(self):
        self.loop.cancel()

    @commands.command(name="añadirmaptrack")
    @commands.admin_or_permissions(administrator=True)
    async def add_map_track(self, ctx, server_ip: str, channel: discord.TextChannel = None):
        """Añadir un servidor para hacerle seguimiento de cambios de mapa."""
        if channel is None:
            channel = ctx.channel

        async with self.config.guild(ctx.guild).tracked_servers() as tracked_servers:
            tracked_servers[server_ip] = {
                "channel_id": channel.id,
                "last_map": None
            }
        await ctx.send(f"Seguimiento de mapa añadido para el servidor {server_ip} en el canal {channel.mention}")

    @commands.command(name="borrarmaptrack")
    @commands.admin_or_permissions(administrator=True)
    async def remove_map_track(self, ctx, channel: discord.TextChannel = None):
        """Eliminar todos los servidores del seguimiento de cambios de mapa en un canal específico."""
        if channel is None:
            channel = ctx.channel

        async with self.config.guild(ctx.guild).tracked_servers() as tracked_servers:
            to_remove = [ip for ip, info in tracked_servers.items() if info["channel_id"] == channel.id]
            for ip in to_remove:
                del tracked_servers[ip]

        if to_remove:
            await ctx.send(f"Se han eliminado los seguimientos de mapa en el canal {channel.mention}")
        else:
            await ctx.send(f"No se encontraron seguimientos de mapa en el canal {channel.mention}")

    @commands.command(name="forzarmaptrack")
    @commands.admin_or_permissions(administrator=True)
    async def force_map_track(self, ctx):
        """Forzar el envío de un mensaje de cambio de mapa en el canal actual."""
        tracked_servers = await self.config.guild(ctx.guild).tracked_servers()
        for server_ip, info in tracked_servers.items():
            if info["channel_id"] == ctx.channel.id:
                await self.send_map_update(ctx.guild, server_ip)
                return
        await ctx.send("No se encontró ningún seguimiento de mapas activo en este canal.")

    @commands.command(name="maptracks")
    @commands.admin_or_permissions(administrator=True)
    async def list_map_tracks(self, ctx):
        """Listar todos los servidores que tienen seguimiento de mapas."""
        tracked_servers = await self.config.guild(ctx.guild).tracked_servers()
        if not tracked_servers:
            await ctx.send("No hay ningún seguimiento de mapas configurado.")
            return

        embed = discord.Embed(title="MapTracks Activos", color=discord.Color.blue())
        for server_ip, info in tracked_servers.items():
            channel = self.bot.get_channel(info["channel_id"])
            channel_name = channel.mention if channel else "Canal no encontrado"
            embed.add_field(name=server_ip, value=f"Canal: {channel_name}", inline=False)

        await ctx.send(embed=embed)

    async def track_maps(self):
        await self.bot.wait_until_ready()
        while True:
            guilds = await self.config.all_guilds()
            for guild_id, data in guilds.items():
                for server_ip, info in data["tracked_servers"].items():
                    await self.send_map_update(self.bot.get_guild(guild_id), server_ip)
            await asyncio.sleep(30)

    async def send_map_update(self, guild, server_ip):
        async with self.config.guild(guild).tracked_servers() as tracked_servers:
            channel_id = tracked_servers[server_ip]["channel_id"]
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                return

            source = Source(server_ip.split(":")[0], int(server_ip.split(":")[1]))
            try:
                info = await source.get_info()
                map_name = info.get('map') or "Desconocido"
                players = info.get('players', 0)
                max_players = info.get('max_players', 0)
            except Exception as e:
                await channel.send(f"Error al obtener información del servidor {server_ip}: {e}")
                return

            if map_name != tracked_servers[server_ip]["last_map"]:
                tracked_servers[server_ip]["last_map"] = map_name
                await channel.send(
                    f"¡Cambio de mapa detectado!\nServidor: {server_ip}\nMapa: {map_name}\nJugadores: {players}/{max_players}\n[Únete al servidor](steam://connect/{server_ip})"
                )

def setup(bot):
    bot.add_cog(MapTrack(bot))
