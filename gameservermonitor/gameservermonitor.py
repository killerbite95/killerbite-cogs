import discord
from discord.ext import tasks
from redbot.core import commands, Config, checks
from opengsq.protocols import Source, Minecraft, FiveM

class GameServerMonitor(commands.Cog):
    """Monitorea el estado de servidores de juegos y actualiza el canal correspondiente."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_guild = {
            "servers": {},
            "timezone": "UTC"
        }
        self.config.register_guild(**default_guild)
        self.server_check.start()

    @commands.command(name="addserver")
    @checks.admin_or_permissions(administrator=True)
    async def add_server(self, ctx, server_ip: str, game: str, channel: discord.TextChannel = None):
        """Añade un servidor para monitorear."""
        channel = channel or ctx.channel
        async with self.config.guild(ctx.guild).servers() as servers:
            servers[server_ip] = {
                "game": game,
                "channel_id": channel.id,
                "message_id": None
            }
        await ctx.send(f"Servidor añadido para monitoreo: {server_ip} en {channel.mention}")

    @commands.command(name="removeserver")
    @checks.admin_or_permissions(administrator=True)
    async def remove_server(self, ctx, server_ip: str):
        """Elimina un servidor del monitoreo."""
        async with self.config.guild(ctx.guild).servers() as servers:
            if server_ip in servers:
                del servers[server_ip]
                await ctx.send(f"Servidor {server_ip} eliminado del monitoreo.")
            else:
                await ctx.send(f"Servidor {server_ip} no encontrado en el monitoreo.")

    @commands.command(name="settimezone")
    @checks.admin_or_permissions(administrator=True)
    async def set_timezone(self, ctx, timezone: str):
        """Establece la zona horaria para mostrar en los mensajes."""
        await self.config.guild(ctx.guild).timezone.set(timezone)
        await ctx.send(f"Zona horaria establecida a {timezone}")

    @commands.command(name="forzarstatus")
    async def force_status(self, ctx):
        """Fuerza una actualización de estado en el canal actual."""
        servers = await self.config.guild(ctx.guild).servers()
        for server_ip, data in servers.items():
            if data["channel_id"] == ctx.channel.id:
                await self.update_server_status(ctx.guild, server_ip, force=True)
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

    @tasks.loop(minutes=1)
    async def server_check(self):
        """Verifica el estado de los servidores cada minuto."""
        for guild in self.bot.guilds:
            servers = await self.config.guild(guild).servers()
            for server_ip in servers.keys():
                await self.update_server_status(guild, server_ip)

    async def update_server_status(self, guild, server_ip, force=False):
        """Actualiza el estado del servidor en el canal correspondiente."""
        async with self.config.guild(guild).servers() as servers:
            data = servers[server_ip]
            channel_id = data["channel_id"]
            channel = self.bot.get_channel(channel_id)
            if not channel:
                return

            try:
                game = data["game"].lower()
                if game in ["cs2", "css", "gmod", "rust"]:
                    protocol = Source(host=server_ip.split(":")[0], port=int(server_ip.split(":")[1]))
                elif game == "minecraft":
                    protocol = Minecraft(host=server_ip.split(":")[0], port=int(server_ip.split(":")[1]))
                elif game == "fivem":
                    protocol = FiveM(host=server_ip.split(":")[0], port=int(server_ip.split(":")[1]))
                else:
                    await channel.send(f"Juego no soportado: {data['game']}")
                    return

                info = await protocol.get_info()
                players = info.players
                max_players = info.max_players
                map_name = info.get("map", "Desconocido")
                hostname = info.get("name", "Servidor")
                game_name = {
                    "cs2": "Counter-Strike 2",
                    "css": "Counter-Strike: Source",
                    "gmod": "Garry's Mod",
                    "rust": "Rust",
                    "minecraft": "Minecraft",
                    "fivem": "FiveM"
                }.get(game, "Juego desconocido")

                timezone = await self.config.guild(guild).timezone()
                local_time = discord.utils.utcnow().astimezone(discord.utils.timezone(timezone)).strftime('%Y-%m-%d %H:%M:%S %Z')

                public_ip = server_ip.replace("10.0.0.", "178.33.160.187")
                connect_url = f"https://vauff.com/connect.php?ip={public_ip}"

                embed = discord.Embed(
                    title=hostname,
                    color=discord.Color.green()
                )
                embed.add_field(name="Game", value=game_name, inline=True)
                embed.add_field(name="Connect", value=f"[Connect]({connect_url})", inline=False)
                embed.add_field(name="Status", value=":green_circle: Online", inline=True)
                embed.add_field(name="Address:Port", value=f"{public_ip}", inline=True)
                embed.add_field(name="Current Map", value=map_name, inline=True)
                embed.add_field(name="Players", value=f"{players}/{max_players} ({int(players/max_players*100)}%)", inline=True)
                embed.set_footer(text=f"Game Server Monitor | Last update: {local_time}")

                if data["message_id"]:
                    message = await channel.fetch_message(data["message_id"])
                    await message.edit(embed=embed)
                else:
                    message = await channel.send(embed=embed)
                    servers[server_ip]["message_id"] = message.id

            except Exception as e:
                await channel.send(f"Error al obtener información del servidor {server_ip}: {e}")

    def cog_unload(self):
        self.server_check.cancel()

def setup(bot):
    bot.add_cog(GameServerMonitor(bot))
