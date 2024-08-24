import discord
from discord.ext import tasks
from redbot.core import commands, Config, checks
from opengsq.protocols import Source, Minecraft, FiveM, DayZ

class GameServerMonitor(commands.Cog):
    """Cog para monitorear servidores de juegos y mostrar el estado en Discord."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_guild = {
            "server_channels": {},
            "last_status": {},
            "timezone": "UTC"
        }
        self.config.register_guild(**default_guild)
        self.server_check.start()

    @commands.command(name="añadirservidor")
    @checks.admin_or_permissions(administrator=True)
    async def add_server(self, ctx, server_ip: str, channel: discord.TextChannel = None):
        """Añade un servidor para monitorear."""
        channel = channel or ctx.channel
        async with self.config.guild(ctx.guild).server_channels() as server_channels:
            server_channels[server_ip] = channel.id
        await ctx.send(f"Servidor añadido para el monitoreo: {server_ip} en {channel.mention}")
        await self.send_server_status(ctx.guild, server_ip, first_time=True)

    @commands.command(name="borrarservidor")
    @checks.admin_or_permissions(administrator=True)
    async def remove_server(self, ctx, channel: discord.TextChannel):
        """Elimina todos los servidores monitoreados de un canal."""
        async with self.config.guild(ctx.guild).server_channels() as server_channels:
            to_remove = [ip for ip, ch_id in server_channels.items() if ch_id == channel.id]
            for ip in to_remove:
                del server_channels[ip]
        await ctx.send(f"Todos los servidores eliminados del canal {channel.mention}")

    @commands.command(name="listaserver")
    async def list_servers(self, ctx):
        """Lista todos los servidores monitoreados."""
        server_channels = await self.config.guild(ctx.guild).server_channels()
        if not server_channels:
            await ctx.send("No hay servidores monitoreados.")
            return
        message = "Servidores Monitoreados:\n"
        for server_ip, channel_id in server_channels.items():
            channel = self.bot.get_channel(channel_id)
            if channel:
                message += f"**{server_ip}** - Canal: {channel.mention}\n"
        await ctx.send(message)

    @commands.command(name="forzarstatus")
    async def force_status_update(self, ctx):
        """Fuerza una actualización de estado en el canal actual."""
        server_channels = await self.config.guild(ctx.guild).server_channels()
        server_ip = None
        for ip, channel_id in server_channels.items():
            if channel_id == ctx.channel.id:
                server_ip = ip
                break
        if server_ip:
            await self.send_server_status(ctx.guild, server_ip, force=True)
        else:
            await ctx.send("No hay servidores monitoreados en este canal.")

    @commands.command(name="settimezone")
    @checks.admin_or_permissions(administrator=True)
    async def set_timezone(self, ctx, timezone: str):
        """Establece la zona horaria del mensaje del servidor."""
        await self.config.guild(ctx.guild).timezone.set(timezone)
        await ctx.send(f"Zona horaria establecida a {timezone}.")

    @tasks.loop(minutes=1)
    async def server_check(self):
        """Verifica cada minuto si hay un cambio de estado en los servidores monitoreados."""
        for guild in self.bot.guilds:
            server_channels = await self.config.guild(guild).server_channels()
            for server_ip in server_channels.keys():
                await self.send_server_status(guild, server_ip)

    async def send_server_status(self, guild, server_ip, first_time=False, force=False):
        """Envía una actualización de estado del servidor si hay un cambio."""
        host, port = server_ip.split(":")
        source = Source(host=host, port=int(port))

        try:
            info = await source.get_info()
            map_name = info.map
            players = info.players
            max_players = info.max_players

            last_status = await self.config.guild(guild).last_status()
            last_map = last_status.get(server_ip)

            if first_time or force or last_map != map_name:
                channel_id = await self.config.guild(guild).server_channels.get_raw(server_ip)
                channel = self.bot.get_channel(channel_id)

                if channel:
                    public_ip = server_ip.replace("10.0.0.", "178.33.160.187")
                    connect_url = f"https://vauff.com/connect.php?ip={public_ip}"

                    embed = discord.Embed(
                        title="Server Status Update" if not first_time else "Initial Server Status",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="Map", value=map_name, inline=False)
                    embed.add_field(name="Players", value=f"{players}/{max_players}", inline=False)
                    embed.add_field(name="Connect", value=f"[Connect]({connect_url})", inline=False)

                    await channel.send(embed=embed)

                async with self.config.guild(guild).last_status() as last_status:
                    last_status[server_ip] = map_name

        except Exception as e:
            channel_id = await self.config.guild(guild).server_channels.get_raw(server_ip)
            channel = self.bot.get_channel(channel_id)
            if channel:
                await channel.send(f"Error al obtener información del servidor {server_ip}: {e}")

    def cog_unload(self):
        self.server_check.cancel()

def setup(bot):
    bot.add_cog(GameServerMonitor(bot))
