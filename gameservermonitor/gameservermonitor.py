import discord
from discord.ext import tasks
from redbot.core import commands, Config, checks
from opengsq.protocols import Source, Minecraft, FiveM
import datetime
import pytz

class GameServerMonitor(commands.Cog):
    """Monitoriza servidores de juegos y actualiza su estado en Discord. By Killerbite95"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_guild = {
            "servers": {},
            "timezone": "UTC",
            "refresh_time": 60  # Tiempo de actualización por defecto en segundos
        }
        self.config.register_guild(**default_guild)
        self.server_monitor.start()

    @commands.command(name="settimezone")
    @checks.admin_or_permissions(administrator=True)
    async def set_timezone(self, ctx, timezone: str):
        """Establece la zona horaria para las actualizaciones."""
        await self.config.guild(ctx.guild).timezone.set(timezone)
        await ctx.send(f"Zona horaria establecida en {timezone}")

    @commands.command(name="addserver")
    @checks.admin_or_permissions(administrator=True)
    async def add_server(self, ctx, server_ip: str, game: str, channel: discord.TextChannel = None):
        """Añade un servidor para monitorear su estado."""
        channel = channel or ctx.channel
        async with self.config.guild(ctx.guild).servers() as servers:
            servers[server_ip] = {
                "game": game,
                "channel_id": channel.id,
                "message_id": None  # Inicialmente sin mensaje
            }
        await ctx.send(f"Servidor {server_ip} añadido para el juego {game} en {channel.mention}")
        await self.update_server_status(ctx.guild, server_ip, first_time=True)

    @commands.command(name="removeserver")
    @checks.admin_or_permissions(administrator=True)
    async def remove_server(self, ctx, server_ip: str):
        """Elimina el monitoreo de un servidor."""
        async with self.config.guild(ctx.guild).servers() as servers:
            if server_ip in servers:
                del servers[server_ip]
                await ctx.send(f"Monitoreo del servidor {server_ip} eliminado.")
            else:
                await ctx.send(f"No se encontró un servidor con IP {server_ip} en la lista.")

    @commands.command(name="forzarstatus")
    async def force_status(self, ctx):
        """Fuerza una actualización de estado en el canal actual."""
        servers = await self.config.guild(ctx.guild).servers()
        for server_ip, data in servers.items():
            if data["channel_id"] == ctx.channel.id:
                await self.update_server_status(ctx.guild, server_ip, first_time=True)
                return
        await ctx.send("No hay servidores monitoreados en este canal.")

    @commands.command(name="listaserver")
    async def list_servers(self, ctx):
        """Lista todos los servidores monitoreados."""
        servers = await self.config.guild(ctx.guild).servers()
        if not servers:
            await ctx.send("No hay servidores siendo monitoreados.")
            return

        message = "Servidores monitoreados:\n"
        for server_ip, data in servers.items():
            channel = self.bot.get_channel(data["channel_id"])
            message += f"**{server_ip}** - Juego: {data['game']} - Canal: {channel.mention if channel else 'Desconocido'}\n"

        await ctx.send(message)

    @commands.command(name="refreshtime")
    @checks.admin_or_permissions(administrator=True)
    async def refresh_time(self, ctx, seconds: int):
        """Establece el tiempo de actualización en segundos."""
        await self.config.guild(ctx.guild).refresh_time.set(seconds)
        self.server_monitor.change_interval(seconds=seconds)
        await ctx.send(f"Tiempo de actualización establecido en {seconds} segundos.")

    @tasks.loop(seconds=60)
    async def server_monitor(self):
        """Verifica el estado de los servidores monitoreados."""
        for guild in self.bot.guilds:
            servers = await self.config.guild(guild).servers()
            for server_ip in servers.keys():
                await self.update_server_status(guild, server_ip)

    @server_monitor.before_loop
    async def before_server_monitor(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            refresh_time = await self.config.guild(guild).refresh_time()
            self.server_monitor.change_interval(seconds=refresh_time)

    async def update_server_status(self, guild, server_ip, first_time=False):
        """Actualiza el estado del servidor y edita el mensaje en Discord."""
        async with self.config.guild(guild).servers() as servers:
            server_info = servers.get(server_ip)
            if not server_info:
                return

            game = server_info.get("game")
            channel_id = server_info.get("channel_id")
            message_id = server_info.get("message_id")
            channel = self.bot.get_channel(channel_id)

            if not channel:
                return

            # Determinamos el objeto "source"
            if game in ["cs2", "css", "gmod", "rust"]:
                source = Source(host=server_ip.split(":")[0], port=int(server_ip.split(":")[1]))
                game_name = {
                    "cs2": "Counter-Strike 2",
                    "css": "Counter-Strike: Source",
                    "gmod": "Garry's Mod",
                    "rust": "Rust"
                }[game]
            elif game == "minecraft":
                source = Minecraft(host=server_ip.split(":")[0], port=int(server_ip.split(":")[1]))
                game_name = "Minecraft"
            elif game == "fivem":
                source = FiveM(host=server_ip.split(":")[0], port=int(server_ip.split(":")[1]))
                game_name = "FiveM"
            else:
                await channel.send(f"Juego {game} no soportado.")
                return

            # Comprobamos el estado
            try:
                if game == "minecraft":
                    # Usamos get_status() en lugar de get_info()
                    info = await source.get_status()
                    # Estructura típica devuelta por get_status():
                    # {
                    #   "description": "A Minecraft Server",
                    #   "players": {"max": 20, "online": 0},
                    #   "version": {"name": "Paper 1.19.3", "protocol": 761},
                    #   ...
                    # }
                    players = info["players"]["online"]
                    max_players = info["players"]["max"]
                    # El 'hostname' podría venir de "description", "motd", etc.
                    hostname = info.get("description", "Minecraft Server")
                    # No hay "map" en Minecraft (podrías mostrar otra info)
                    map_name = "N/A"

                    # No hay contraseña tipo "is_passworded" en Minecraft
                    is_passworded = False

                else:
                    # Para Source, FiveM (y otros) usamos get_info()
                    info = await source.get_info()
                    players = info.players
                    max_players = info.max_players
                    map_name = info.map if hasattr(info, "map") else "N/A"
                    hostname = info.name if hasattr(info, "name") else "Unknown Server"

                    # Verificar si el servidor está protegido con contraseña (SOLO Source)
                    is_passworded = False
                    if game in ["cs2", "css", "gmod", "rust"]:
                        if hasattr(info, "visibility") and info.visibility == 1:
                            is_passworded = True

                # Reemplazar la IP interna si aplica
                internal_ip, port = server_ip.split(":")
                if internal_ip.startswith("10.0.0."):
                    public_ip = "178.33.160.187"
                else:
                    public_ip = internal_ip

                # Obtener la hora local
                timezone = await self.config.guild(guild).timezone()
                tz = pytz.timezone(timezone)
                now = datetime.datetime.now(tz)
                local_time = now.strftime("%Y-%m-%d %H:%M:%S")

                # Creamos el embed
                # Si es Source, marcar Mantenimiento si is_passworded
                if is_passworded:
                    embed = discord.Embed(
                        title=f"{hostname} - Server Status",
                        color=discord.Color.orange()
                    )
                    embed.add_field(name="🔐 Status", value="Maintenance", inline=True)
                else:
                    embed = discord.Embed(
                        title=f"{hostname} - Server Status",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="✅ Status", value="Online", inline=True)

                embed.add_field(name=":video_game: Game", value=game_name, inline=True)

                if game != "minecraft":
                    # Para juegos que tengan un link de conexión (Source, FiveM).
                    connect_url = f"https://vauff.com/connect.php?ip={public_ip}:{port}"
                    embed.add_field(
                        name=":link: Connect",
                        value=f"\n[Connect]({connect_url})\n",
                        inline=False
                    )

                # IP y mapa
                embed.add_field(name=":round_pushpin: IP", value=f"{public_ip}:{port}", inline=True)
                embed.add_field(name=":map: Current Map", value=map_name, inline=True)

                # Jugadores
                if max_players > 0:
                    percent = int(players / max_players * 100)
                else:
                    percent = 0
                embed.add_field(
                    name=":busts_in_silhouette: Players",
                    value=f"{players}/{max_players} ({percent}%)",
                    inline=True
                )

                embed.set_footer(text=f"Game Server Monitor by Killerbite95 | Last update: {local_time}")

                # Enviar o editar el mensaje
                if first_time or not message_id:
                    message = await channel.send(embed=embed)
                    servers[server_ip]["message_id"] = message.id
                else:
                    try:
                        message = await channel.fetch_message(message_id)
                        await message.edit(embed=embed)
                    except discord.NotFound:
                        message = await channel.send(embed=embed)
                        servers[server_ip]["message_id"] = message.id

            except Exception:
                # Si falla, marcamos como Offline
                internal_ip, port = server_ip.split(":")
                if internal_ip.startswith("10.0.0."):
                    public_ip = "178.33.160.187"
                else:
                    public_ip = internal_ip

                # Para que no dé error si no se llegó a game_name
                if game == "minecraft":
                    game_title = "Minecraft"
                elif game in ["cs2", "css", "gmod", "rust", "fivem"]:
                    game_title = game_name  # ya definido arriba
                else:
                    game_title = game

                embed = discord.Embed(
                    title=f"{game_title} Server - ❌ Offline",
                    color=discord.Color.red()
                )
                embed.add_field(name="Status", value=":red_circle: Offline", inline=True)
                embed.add_field(name=":video_game: Game", value=game_title, inline=True)
                embed.add_field(name=":round_pushpin: IP", value=f"{public_ip}:{port}", inline=True)
                embed.set_footer(text="Game Server Monitor by Killerbite95")

                # No mostramos "Connect" si es Minecraft
                if game not in ["minecraft"]:
                    connect_url = f"https://vauff.com/connect.php?ip={public_ip}:{port}"
                    embed.add_field(
                        name=":link: Connect",
                        value=f"\n[Connect]({connect_url})\n",
                        inline=False
                    )

                if first_time or not message_id:
                    message = await channel.send(embed=embed)
                    servers[server_ip]["message_id"] = message.id
                else:
                    try:
                        message = await channel.fetch_message(message_id)
                        await message.edit(embed=embed)
                    except discord.NotFound:
                        message = await channel.send(embed=embed)
                        servers[server_ip]["message_id"] = message.id

    def cog_unload(self):
        self.server_monitor.cancel()


def setup(bot):
    bot.add_cog(GameServerMonitor(bot))
