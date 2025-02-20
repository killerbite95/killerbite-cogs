import discord
from discord.ext import tasks
from redbot.core import commands, Config, checks
from opengsq.protocols import Source, Minecraft
import datetime
import pytz
import logging
import ast

# Configuración de logging
logger = logging.getLogger("red.trini.gameservermonitor")

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
        try:
            pytz.timezone(timezone)  # Validar zona horaria
        except pytz.UnknownTimeZoneError:
            await ctx.send(f"La zona horaria '{timezone}' no es válida.")
            return
        await self.config.guild(ctx.guild).timezone.set(timezone)
        await ctx.send(f"Zona horaria establecida en {timezone}")

    @commands.command(name="addserver")
    @checks.admin_or_permissions(administrator=True)
    async def add_server(self, ctx, server_ip: str, game: str, channel: discord.TextChannel = None, domain: str = None):
        """
        Añade un servidor para monitorear su estado.
        
        Uso:
          !addserver <ip:puerto> <juego> [channel] [domain]

        Ejemplos:
          !addserver 194.69.160.51:25575 minecraft #canal mc.dominio.com
          !addserver 194.69.160.51:27015 cs2 #canal
          !addserver 51.255.126.200:27015 gmod #canal 1330136596573589551
        """
        channel = channel or ctx.channel
        game = game.lower()

        parsed = self.parse_server_ip(server_ip, game)
        if not parsed:
            await ctx.send(f"Formato inválido para server_ip '{server_ip}'. Debe ser 'ip:puerto' o solo 'ip'.")
            return
        ip_part, port_part, server_ip_formatted = parsed

        async with self.config.guild(ctx.guild).servers() as servers:
            if server_ip_formatted in servers:
                await ctx.send(f"El servidor {server_ip_formatted} ya está siendo monitoreado.")
                return
            servers[server_ip_formatted] = {
                "game": game,
                "channel_id": channel.id,
                "message_id": None,
                "domain": domain
            }
        await ctx.send(
            f"Servidor {server_ip_formatted} añadido para el juego **{game.upper()}** en {channel.mention}."
            + (f"\nDominio asignado: {domain}" if domain else "")
        )
        await self.update_server_status(ctx.guild, server_ip_formatted, first_time=True)

    @commands.command(name="removeserver")
    @checks.admin_or_permissions(administrator=True)
    async def remove_server(self, ctx, server_ip: str):
        """Elimina el monitoreo de un servidor."""
        parsed = self.parse_server_ip(server_ip)
        if not parsed:
            await ctx.send(f"Formato inválido para server_ip '{server_ip}'. Debe ser 'ip:puerto'.")
            return
        server_ip_formatted = f"{parsed[0]}:{parsed[1]}"

        async with self.config.guild(ctx.guild).servers() as servers:
            if server_ip_formatted in servers:
                del servers[server_ip_formatted]
                await ctx.send(f"Monitoreo del servidor {server_ip_formatted} eliminado.")
            else:
                await ctx.send(f"No se encontró un servidor con IP {server_ip_formatted} en la lista.")

    @commands.command(name="forzarstatus")
    async def force_status(self, ctx):
        """Fuerza una actualización de estado en el canal actual."""
        servers = await self.config.guild(ctx.guild).servers()
        actualizados = False
        for server_ip, data in servers.items():
            if data["channel_id"] == ctx.channel.id:
                await self.update_server_status(ctx.guild, server_ip, first_time=True)
                actualizados = True
        if actualizados:
            await ctx.send("Actualización de estado forzada para los servidores en este canal.")
        else:
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
            domain = data.get("domain")
            message += (
                f"**{server_ip}** - Juego: **{data['game'].upper()}** - "
                f"Canal: {channel.mention if channel else 'Desconocido'}"
            )
            if domain:
                message += f" - Dominio: {domain}"
            message += "\n"

        await ctx.send(message)

    @commands.command(name="refreshtime")
    @checks.admin_or_permissions(administrator=True)
    async def refresh_time(self, ctx, seconds: int):
        """Establece el tiempo de actualización en segundos."""
        if seconds < 10:
            await ctx.send("El tiempo de actualización debe ser al menos 10 segundos.")
            return
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

    def parse_server_ip(self, server_ip: str, game: str = None):
        """
        Analiza y valida server_ip.
        Retorna (ip, port, server_ip_formatted) o None si inválido.
        """
        default_ports = {
            "cs2": 27015,
            "css": 27015,
            "gmod": 27015,
            "rust": 28015,
            "minecraft": 25565
        }
        if ":" in server_ip:
            parts = server_ip.split(":")
            if len(parts) != 2:
                logger.error(f"server_ip '{server_ip}' tiene más de un ':'.")
                return None
            ip_part, port_part_str = parts
            try:
                port_part = int(port_part_str)
            except ValueError:
                logger.error(f"Puerto inválido '{port_part_str}' en server_ip '{server_ip}'.")
                return None
        else:
            if not game:
                logger.error(f"server_ip '{server_ip}' no incluye puerto y no se proporcionó el juego para asignar puerto predeterminado.")
                return None
            port_part = default_ports.get(game.lower())
            if not port_part:
                logger.error(f"No hay puerto predeterminado para el juego '{game}'.")
                return None
            ip_part = server_ip
        server_ip_formatted = f"{ip_part}:{port_part}"
        return ip_part, port_part, server_ip_formatted

    def parse_minecraft_description(self, description):
        """
        Convierte un "Chat Component" de Minecraft (dict o lista) a texto plano.
        """
        result = ""
        if isinstance(description, dict):
            result += description.get("text", "")
            if "extra" in description:
                for item in description["extra"]:
                    result += self.parse_minecraft_description(item)
        elif isinstance(description, list):
            for item in description:
                result += self.parse_minecraft_description(item)
        else:
            result += str(description)
        return result

    def get_plain_hostname(self, raw_hostname):
        """
        Procesa el hostname obtenido del servidor de Minecraft.
         - Si es dict o lista, lo convierte a texto plano.
         - Si es una cadena que luce como dict (comienza con '{' y termina con '}'),
           se intenta evaluar y extraer el texto.
         - Se trunca para que, al añadir " - Server Status", el total no supere 256 caracteres.
        """
        if isinstance(raw_hostname, (dict, list)):
            hostname = self.parse_minecraft_description(raw_hostname)
        elif isinstance(raw_hostname, str):
            # Intentar convertir la cadena a un objeto si luce como dict
            stripped = raw_hostname.strip()
            if stripped.startswith("{") and stripped.endswith("}"):
                try:
                    parsed_obj = ast.literal_eval(stripped)
                    if isinstance(parsed_obj, (dict, list)):
                        hostname = self.parse_minecraft_description(parsed_obj)
                    else:
                        hostname = raw_hostname
                except Exception as e:
                    logger.error(f"Error al evaluar la descripción: {e}")
                    hostname = raw_hostname
            else:
                hostname = raw_hostname
        else:
            hostname = str(raw_hostname)
        hostname = hostname.strip()
        sufijo = " - Server Status"
        max_hostname_length = 256 - len(sufijo)
        if len(hostname) > max_hostname_length:
            hostname = hostname[:max_hostname_length - 3] + "..."
        return hostname

    async def update_server_status(self, guild, server_ip, first_time=False):
        """Actualiza el estado del servidor y edita el mensaje en Discord."""
        async with self.config.guild(guild).servers() as servers:
            server_info = servers.get(server_ip)
            if not server_info:
                logger.warning(f"Servidor {server_ip} no encontrado en la configuración de {guild.name}.")
                return

            game = server_info.get("game")
            channel_id = server_info.get("channel_id")
            message_id = server_info.get("message_id")
            domain = server_info.get("domain")
            channel = self.bot.get_channel(channel_id)
            if not channel:
                logger.error(f"Canal con ID {channel_id} no encontrado en {guild.name}.")
                return

            parsed = self.parse_server_ip(server_ip, game)
            if not parsed:
                logger.error(f"Formato inválido para server_ip '{server_ip}' en {guild.name}.")
                return
            ip_part, port_part, server_ip_formatted = parsed

            if game in ["cs2", "css", "gmod", "rust"]:
                try:
                    source = Source(host=ip_part, port=port_part)
                except Exception as e:
                    logger.error(f"Error al crear objeto Source para {server_ip_formatted}: {e}")
                    source = None
                game_name = {
                    "cs2": "Counter-Strike 2",
                    "css": "Counter-Strike: Source",
                    "gmod": "Garry's Mod",
                    "rust": "Rust"
                }.get(game, "Unknown Game")
            elif game == "minecraft":
                try:
                    source = Minecraft(host=ip_part, port=port_part)
                except Exception as e:
                    logger.error(f"Error al crear objeto Minecraft para {server_ip_formatted}: {e}")
                    source = None
                game_name = "Minecraft"
            else:
                logger.warning(f"Juego '{game}' no soportado para {server_ip_formatted}.")
                await channel.send(f"Juego {game} no soportado.")
                return

            try:
                if game == "minecraft":
                    info = await source.get_status()
                    is_passworded = False
                    players = info["players"]["online"]
                    max_players = info["players"]["max"]
                    raw_hostname = info.get("description", "Minecraft Server")
                    hostname = self.get_plain_hostname(raw_hostname)
                    version_str = info.get("version", {}).get("name", "???")
                    map_name = version_str
                else:
                    info = await source.get_info()
                    players = info.players
                    max_players = info.max_players
                    map_name = getattr(info, "map", "N/A")
                    hostname = getattr(info, "name", "Unknown Server")
                    is_passworded = hasattr(info, "visibility") and info.visibility == 1

                if ip_part.startswith("10.0.0."):
                    public_ip = "178.33.160.187"
                else:
                    public_ip = ip_part

                if game == "minecraft" and domain:
                    ip_to_show = f"{domain}"
                else:
                    ip_to_show = f"{public_ip}:{port_part}"

                timezone = await self.config.guild(guild).timezone()
                try:
                    tz = pytz.timezone(timezone)
                except pytz.UnknownTimeZoneError:
                    logger.error(f"Zona horaria '{timezone}' inválida para {guild.name}. Usando UTC.")
                    tz = pytz.UTC
                now = datetime.datetime.now(tz)
                local_time = now.strftime("%Y-%m-%d %H:%M:%S")

                title_online = f"{hostname} - Server Status"

                if is_passworded:
                    embed = discord.Embed(
                        title=title_online,
                        color=discord.Color.orange()
                    )
                    embed.add_field(name="🔐 Status", value="Maintenance", inline=True)
                else:
                    embed = discord.Embed(
                        title=title_online,
                        color=discord.Color.green()
                    )
                    embed.add_field(name="✅ Status", value="Online", inline=True)

                embed.add_field(name="🎮 Game", value=game_name, inline=True)

                if game != "minecraft":
                    connect_url = f"https://alienhost.ovh/connect.php?ip={public_ip}:{port_part}"
                    embed.add_field(
                        name="\n\u200b\n🔗 Connect",
                        value=f"[Connect]({connect_url})\n\u200b\n",
                        inline=False
                    )

                embed.add_field(name="📌 IP", value=ip_to_show, inline=True)

                if game == "minecraft":
                    embed.add_field(name="💎 Version", value=map_name, inline=True)
                else:
                    embed.add_field(name="🗺️ Current Map", value=map_name, inline=True)

                if max_players > 0:
                    percent = int(players / max_players * 100)
                else:
                    percent = 0
                embed.add_field(
                    name="👥 Players",
                    value=f"{players}/{max_players} ({percent}%)",
                    inline=True
                )

                embed.set_footer(text=f"Game Server Monitor by Killerbite95 | Last update: {local_time}")

                if first_time or not message_id:
                    msg = await channel.send(embed=embed)
                    servers[server_ip]["message_id"] = msg.id
                else:
                    try:
                        msg = await channel.fetch_message(message_id)
                        await msg.edit(embed=embed)
                    except discord.NotFound:
                        msg = await channel.send(embed=embed)
                        servers[server_ip]["message_id"] = msg.id

            except Exception as e:
                logger.error(f"Error al actualizar el servidor {server_ip_formatted}: {e}")
                if ip_part.startswith("10.0.0."):
                    public_ip = "178.33.160.187"
                else:
                    public_ip = ip_part

                if game == "minecraft":
                    game_title = "Minecraft"
                elif game in ["cs2", "css", "gmod", "rust"]:
                    game_title = game_name
                else:
                    game_title = game

                title_offline = f"{game_title} Server - ❌ Offline"
                if len(title_offline) > 256:
                    title_offline = title_offline[:253] + "..."
                embed = discord.Embed(
                    title=title_offline,
                    color=discord.Color.red()
                )
                embed.add_field(name="Status", value="🔴 Offline", inline=True)
                embed.add_field(name="🎮 Game", value=game_title, inline=True)

                if game == "minecraft" and domain:
                    ip_to_show = f"{domain}"
                else:
                    ip_to_show = f"{public_ip}:{port_part}"

                embed.add_field(name="📌 IP", value=ip_to_show, inline=True)

                if game != "minecraft":
                    connect_url = f"https://alienhost.ovh/connect.php?ip={public_ip}:{port_part}"
                    embed.add_field(
                        name="\n\u200b\n🔗 Connect",
                        value=f"[Connect]({connect_url})\n\u200b\n",
                        inline=False
                    )

                embed.set_footer(text="Game Server Monitor by Killerbite95")

                if first_time or not message_id:
                    try:
                        msg = await channel.send(embed=embed)
                        servers[server_ip]["message_id"] = msg.id
                    except Exception as send_error:
                        logger.error(f"Error al enviar mensaje offline para {server_ip_formatted}: {send_error}")
                else:
                    try:
                        msg = await channel.fetch_message(message_id)
                        await msg.edit(embed=embed)
                    except discord.NotFound:
                        try:
                            msg = await channel.send(embed=embed)
                            servers[server_ip]["message_id"] = msg.id
                        except Exception as send_error:
                            logger.error(f"Error al enviar mensaje offline para {server_ip_formatted}: {send_error}")

    def setup(bot):
        bot.add_cog(GameServerMonitor(bot))
