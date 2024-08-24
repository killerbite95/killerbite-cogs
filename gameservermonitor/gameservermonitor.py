import discord
from discord.ext import tasks, commands
from redbot.core import Config, checks
from opengsq.protocols import Source, Minecraft, FiveM
import datetime
import pytz

class GameServerMonitor(commands.Cog):
    """Monitoreo de servidores de juegos en Discord."""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_guild = {
            "servers": {},
            "timezone": "UTC",
        }
        self.config.register_guild(**default_guild)
        self.server_check.start()

    @commands.command(name="settimezone")
    @checks.admin_or_permissions(administrator=True)
    async def set_timezone(self, ctx, timezone: str):
        """Establece la zona horaria para el servidor."""
        try:
            pytz.timezone(timezone)
            await self.config.guild(ctx.guild).timezone.set(timezone)
            await ctx.send(f"Zona horaria establecida en {timezone}.")
        except pytz.UnknownTimeZoneError:
            await ctx.send("Zona horaria inválida. Consulta https://en.wikipedia.org/wiki/List_of_tz_database_time_zones para una lista de zonas horarias válidas.")

    @commands.command(name="addserver")
    @checks.admin_or_permissions(administrator=True)
    async def add_server(self, ctx, server_ip: str, game: str, channel: discord.TextChannel = None):
        """Añade un servidor para monitorear su estado."""
        channel = channel or ctx.channel
        async with self.config.guild(ctx.guild).servers() as servers:
            servers[server_ip] = {"game": game, "channel_id": channel.id, "message_id": None}
        await ctx.send(f"Servidor {server_ip} añadido para monitoreo en {channel.mention}.")

    @commands.command(name="removeserver")
    @checks.admin_or_permissions(administrator=True)
    async def remove_server(self, ctx, server_ip: str):
        """Elimina un servidor del monitoreo."""
        async with self.config.guild(ctx.guild).servers() as servers:
            if server_ip in servers:
                del servers[server_ip]
                await ctx.send(f"Servidor {server_ip} eliminado del monitoreo.")
            else:
                await ctx.send(f"Servidor {server_ip} no encontrado en la lista de monitoreo.")

    @tasks.loop(minutes=1)
    async def server_check(self):
        """Verifica el estado de los servidores cada minuto."""
        for guild in self.bot.guilds:
            servers = await self.config.guild(guild).servers()
            timezone = await self.config.guild(guild).timezone()
            tz = pytz.timezone(timezone)
            for server_ip, details in servers.items():
                await self.update_server_status(guild, server_ip, details, tz)

    async def update_server_status(self, guild, server_ip, details, tz):
        """Actualiza el estado del servidor en el canal correspondiente."""
        host, port = server_ip.split(":")
        game = details["game"].lower()
        channel = self.bot.get_channel(details["channel_id"])
        message_id = details["message_id"]

        if game == "cs2":
            server = Source(host=host, port=int(port))
        elif game == "rust":
            server = Source(host=host, port=int(port))
        elif game == "fivem":
            server = FiveM(host=host, port=int(port))
        elif game == "minecraft":
            server = Minecraft(host=host, port=int(port))
        else:
            await channel.send(f"Juego no soportado: {game}")
            return

        try:
            info = await server.get_info()
            map_name = getattr(info, 'map', 'N/A')
            players = getattr(info, 'players', 0)
            max_players = getattr(info, 'max_players', 0)

            public_ip = server_ip.replace("10.0.0.", "178.33.160.187")
            connect_url = f"https://vauff.com/connect.php?ip={public_ip}"

            embed = discord.Embed(
                title="Game Server Status",
                color=discord.Color.green()
            )
            embed.add_field(name="Connect", value=f"[Connect]({connect_url})", inline=False)
            embed.add_field(name="Status", value=":green_circle: Online", inline=True)
            embed.add_field(name="Address:Port", value=f"{public_ip}", inline=True)
            embed.add_field(name="Current Map", value=map_name, inline=True)
            embed.add_field(name="Players", value=f"{players}/{max_players} ({int(players/max_players*100)}%)", inline=True)
            local_time = datetime.datetime.now(tz).strftime('%Y-%m-%d %I:%M:%S %p %Z')
            embed.set_footer(text=f"Game Server Monitor | Last update: {local_time}")

            if message_id:
                try:
                    message = await channel.fetch_message(message_id)
                    await message.edit(embed=embed)
                except discord.NotFound:
                    new_message = await channel.send(embed=embed)
                    details["message_id"] = new_message.id
            else:
                new_message = await channel.send(embed=embed)
                details["message_id"] = new_message.id

        except Exception as e:
            if channel:
                await channel.send(f"Error al obtener información del servidor {server_ip}: {e}")

    def cog_unload(self):
        self.server_check.cancel()

def setup(bot):
    bot.add_cog(GameServerMonitor(bot))
