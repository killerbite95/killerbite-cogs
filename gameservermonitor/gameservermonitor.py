import discord
from discord.ext import tasks
from redbot.core import commands, Config, checks
from opengsq.protocols import Source, Minecraft, FiveM

class GameServerMonitor(commands.Cog):
    """Monitoriza el estado de servidores de juegos como CS:Source, Garry's Mod, Rust, Minecraft, FiveM y CS2."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_guild = {
            "servers": {},
            "timezone": "UTC",
        }
        self.config.register_guild(**default_guild)
        self.server_check.start()

    def cog_unload(self):
        self.server_check.cancel()

    @commands.command(name="settimezone")
    @checks.admin_or_permissions(administrator=True)
    async def set_timezone(self, ctx, timezone: str):
        """Establece la zona horaria para los mensajes de actualización del servidor."""
        await self.config.guild(ctx.guild).timezone.set(timezone)
        await ctx.send(f"Zona horaria establecida en {timezone}.")

    @commands.command(name="addserver")
    @checks.admin_or_permissions(administrator=True)
    async def add_server(self, ctx, server_ip: str, game: str, channel: discord.TextChannel = None):
        """Añade un servidor para monitorear su estado."""
        channel = channel or ctx.channel
        async with self.config.guild(ctx.guild).servers() as servers:
            servers[server_ip] = {"game": game, "channel_id": channel.id}
        await ctx.send(f"Servidor {server_ip} añadido para monitoreo en {channel.mention}.")
        # Enviar un primer mensaje con el estado actual
        await self.send_server_update(ctx.guild, server_ip, game, first_time=True)

    @commands.command(name="removeserver")
    @checks.admin_or_permissions(administrator=True)
    async def remove_server(self, ctx, server_ip: str):
        """Elimina el monitoreo de un servidor."""
        async with self.config.guild(ctx.guild).servers() as servers:
            if server_ip in servers:
                del servers[server_ip]
                await ctx.send(f"Servidor {server_ip} eliminado del monitoreo.")
            else:
                await ctx.send(f"No se encontró el servidor {server_ip}.")

    @tasks.loop(minutes=1)
    async def server_check(self):
        """Verifica cada minuto el estado de los servidores monitoreados."""
        for guild in self.bot.guilds:
            servers = await self.config.guild(guild).servers()
            for server_ip, details in servers.items():
                game = details["game"]
                await self.send_server_update(guild, server_ip, game)

    async def send_server_update(self, guild, server_ip, game, first_time=False, force=False):
        """Envía una actualización del estado del servidor."""
        host, port = server_ip.split(":")
        port = int(port)

        try:
            if game.lower() == "cs:source" or game.lower() == "cs2":
                protocol = Source(host=host, port=port)
            elif game.lower() == "minecraft":
                protocol = Minecraft(host=host, port=port)
            elif game.lower() == "fivem":
                protocol = FiveM(host=host, port=port)
            else:
                await self.bot.get_channel(servers[server_ip]["channel_id"]).send(f"Juego {game} no soportado.")
                return

            info = await protocol.get_info()
            map_name = getattr(info, "map", "Desconocido")
            players = info.players
            max_players = info.max_players

            last_servers = await self.config.guild(guild).servers()
            last_map = last_servers[server_ip].get("last_map")

            if first_time or force or last_map != map_name:
                channel_id = last_servers[server_ip]["channel_id"]
                channel = self.bot.get_channel(channel_id)

                if channel:
                    # Reemplazar la IP interna con la IP pública
                    public_ip = server_ip.replace("10.0.0.", "178.33.160.187")
                    connect_url = f"https://vauff.com/connect.php?ip={public_ip}"
                    timezone = await self.config.guild(guild).timezone()

                    embed = discord.Embed(
                        title="Server Status Update" if not first_time else "Initial Server Status",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="Connect", value=f"[Connect]({connect_url})", inline=False)
                    embed.add_field(name="Status", value=":green_circle: Online", inline=True)
                    embed.add_field(name="Address:Port", value=f"{public_ip}", inline=True)
                    embed.add_field(name="Current Map", value=map_name, inline=True)
                    embed.add_field(name="Players", value=f"{players}/{max_players} ({int(players/max_players*100)}%)", inline=True)
                    embed.set_footer(text=f"Game Server Monitor | Last update: {timezone}")

                    # Editar o enviar el mensaje
                    if first_time or force:
                        last_servers[server_ip]["message_id"] = (await channel.send(embed=embed)).id
                    else:
                        message = await channel.fetch_message(last_servers[server_ip]["message_id"])
                        await message.edit(embed=embed)

                    last_servers[server_ip]["last_map"] = map_name

        except Exception as e:
            channel_id = await self.config.guild(guild).servers.get_raw(server_ip, "channel_id")
            channel = self.bot.get_channel(channel_id)
            if channel:
                await channel.send(f"Error al obtener información del servidor {server_ip}: {e}")

def setup(bot):
    bot.add_cog(GameServerMonitor(bot))
