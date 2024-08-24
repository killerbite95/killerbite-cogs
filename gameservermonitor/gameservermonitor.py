import discord
from discord.ext import tasks
from redbot.core import commands, Config, checks
from opengsq.protocols import Source, GoldSource, Minecraft, FiveM, DayZ
from pytz import timezone, all_timezones
from datetime import datetime

class GameServerStatus(commands.Cog):
    """Cog para monitorear el estado de servidores de juegos múltiples."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_guild = {
            "servers": {},
            "last_messages": {},
            "timezone": "UTC"
        }
        self.config.register_guild(**default_guild)
        self.status_check.start()

    @commands.command(name="addserver")
    @checks.admin_or_permissions(administrator=True)
    async def add_server(self, ctx, game_type: str, server_ip: str, channel: discord.TextChannel = None):
        """Añade un servidor para monitorear su estado."""
        channel = channel or ctx.channel
        async with self.config.guild(ctx.guild).servers() as servers:
            servers[server_ip] = {"channel": channel.id, "game_type": game_type.lower()}
        await ctx.send(f"Monitoreo añadido para el servidor {server_ip} ({game_type}) en {channel.mention}")
        await self.send_status_update(ctx.guild, server_ip, first_time=True)

    @commands.command(name="removeserver")
    @checks.admin_or_permissions(administrator=True)
    async def remove_server(self, ctx, server_ip: str):
        """Elimina el monitoreo de un servidor."""
        async with self.config.guild(ctx.guild).servers() as servers:
            if server_ip in servers:
                del servers[server_ip]
                await ctx.send(f"Monitoreo eliminado para el servidor {server_ip}")
            else:
                await ctx.send(f"No se encontró el servidor {server_ip} en el monitoreo.")

    @commands.command(name="settimezone")
    @checks.admin_or_permissions(administrator=True)
    async def set_timezone(self, ctx, tz: str):
        """Establece la zona horaria para los mensajes de actualización."""
        if tz in all_timezones:
            await self.config.guild(ctx.guild).timezone.set(tz)
            await ctx.send(f"Zona horaria establecida a {tz}")
        else:
            await ctx.send("Zona horaria no válida. Consulta la lista de zonas horarias soportadas.")

    @tasks.loop(minutes=1)
    async def status_check(self):
        """Verifica cada minuto el estado de los servidores monitoreados."""
        for guild in self.bot.guilds:
            servers = await self.config.guild(guild).servers()
            for server_ip in servers.keys():
                await self.send_status_update(guild, server_ip)

    async def send_status_update(self, guild, server_ip, first_time=False):
        """Envía una actualización del estado del servidor o edita el mensaje anterior."""
        async with self.config.guild(guild).servers() as servers:
            server_info = servers.get(server_ip)
            if not server_info:
                return
            
            game_type = server_info["game_type"]
            channel_id = server_info["channel"]
            channel = self.bot.get_channel(channel_id)

            # Definir el protocolo según el tipo de juego
            if game_type == "source":
                protocol = Source
            elif game_type == "goldsource":
                protocol = GoldSource
            elif game_type == "minecraft":
                protocol = Minecraft
            elif game_type == "fivem":
                protocol = FiveM
            elif game_type == "dayz":
                protocol = DayZ
            elif game_type == "rust":
                protocol = Source  # Rust usa el mismo protocolo que Source para las queries
            else:
                if channel:
                    await channel.send(f"Tipo de juego '{game_type}' no soportado para el servidor {server_ip}.")
                return
            
            host, port = server_ip.split(":")
            server = protocol(host=host, port=int(port))
        
            try:
                info = await server.get_info()
                map_name = info.map if hasattr(info, 'map') else "Desconocido"
                players = info.players
                max_players = info.max_players
                
                # Reemplazar la IP interna con la IP pública si es necesario
                public_ip = server_ip.replace("10.0.0.", "178.33.160.187")
                connect_url = f"steam://connect/{public_ip}"

                # Obtener la zona horaria configurada
                tz = await self.config.guild(guild).timezone()
                local_time = datetime.now(timezone(tz)).strftime('%Y-%m-%d %I:%M:%S%p %Z')

                embed = discord.Embed(
                    title="Server Status",
                    color=discord.Color.green()
                )
                embed.add_field(name="Connect", value=f"[Connect]({connect_url})", inline=False)
                embed.add_field(name="Status", value=":green_circle: Online", inline=True)
                embed.add_field(name="Address:Port", value=f"{public_ip}", inline=True)
                embed.add_field(name="Current Map", value=map_name, inline=True)
                embed.add_field(name="Players", value=f"{players}/{max_players} ({int(players/max_players*100)}%)", inline=True)
                embed.set_footer(text=f"Game Server Monitor | Last update: {local_time}")

                async with self.config.guild(guild).last_messages() as last_messages:
                    last_msg_id = last_messages.get(server_ip)
                    if last_msg_id:
                        try:
                            last_msg = await channel.fetch_message(last_msg_id)
                            await last_msg.edit(embed=embed)
                        except discord.NotFound:
                            last_msg = await channel.send(embed=embed)
                            last_messages[server_ip] = last_msg.id
                    else:
                        last_msg = await channel.send(embed=embed)
                        last_messages[server_ip] = last_msg.id
        
            except Exception as e:
                if channel:
                    await channel.send(f"Error al obtener información del servidor {server_ip}: {e}")

    def cog_unload(self):
        self.status_check.cancel()

def setup(bot):
    bot.add_cog(GameServerStatus(bot))
