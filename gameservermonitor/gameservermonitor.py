import discord
from discord.ext import tasks
from redbot.core import commands, Config, checks
from opengsq.protocols import Source, Minecraft
import datetime
import pytz
import logging

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
            "refresh_time": 60  # Tiempo de actualización en segundos
        }
        self.config.register_guild(**default_guild)
        self.debug = False  # Modo debug desactivado por defecto
        self.server_monitor.start()

    @commands.command(name="settimezone")
    @checks.admin_or_permissions(administrator=True)
    async def set_timezone(self, ctx, timezone: str):
        """Establece la zona horaria para las actualizaciones."""
        try:
            pytz.timezone(timezone)
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
        await ctx.send(f"Servidor {server_ip_formatted} añadido para el juego **{game.upper()}** en {channel.mention}." +
                       (f"\nDominio asignado: {domain}" if domain else ""))
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
                await ctx.send(f"No se encontró un servidor con IP {server_ip_formatted}.")

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
            message += f"**{server_ip}** - Juego: **{data['game'].upper()}** - Canal: {channel.mention if channel else 'Desconocido'}"
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

    @commands.command(name="gameservermonitordebug")
    @checks.admin_or_permissions(administrator=True)
    async def gameservermonitordebug(self, ctx, state: bool):
        """Activa o desactiva el modo debug."""
        self.debug = state
        await ctx.send(f"Modo debug {'activado' if state else 'desactivado'}.")

    @tasks.loop(seconds=60)
    async def server_monitor(self):
        """Actualiza el estado de los servidores periódicamente."""
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
            ip_part, port_str = parts
            try:
                port_part = int(port_str)
            except ValueError:
                logger.error(f"Puerto inválido '{port_str}' en server_ip '{server_ip}'.")
                return None
        else:
            if not game:
                logger.error(f"server_ip '{server_ip}' no incluye puerto y no se proporcionó el juego.")
                return None
            port_part = default_ports.get(game.lower())
            if not port_part:
                logger.error(f"No hay puerto predeterminado para el juego '{game}'.")
                return None
            ip_part = server_ip
        return ip_part, port_part, f"{ip_part}:{port_part}"

    def convert_motd(self, motd):
        """
        Convierte el MOTD (que puede venir en formato JSON) a un string plano y colapsa espacios.
        """
        if isinstance(motd, str):
            text = motd.strip()
        elif isinstance(motd, dict):
            text = motd.get("text", "")
            if "extra" in motd and isinstance(motd["extra"], list):
                for extra in motd["extra"]:
                    text += " " + self.convert_motd(extra)
            text = text.strip()
        elif isinstance(motd, list):
            text = " ".join([self.convert_motd(item) for item in motd]).strip()
        else:
            text = ""
        return " ".join(text.split())

    def truncate_title(self, title: str, suffix: str) -> str:
        """
        Trunca el título para que (título + sufijo) no supere 256 caracteres.
        """
        max_total = 256
        allowed = max_total - len(suffix)
        if len(title) > allowed:
            title = title[: max(allowed - 3, 0)] + "..."
        return title + suffix

    async def update_server_status(self, guild, server_ip, first_time=False):
        async with self.config.guild(guild).servers() as servers:
            server_info = servers.get(server_ip)
            if not server_info:
                logger.warning(f"Servidor {server_ip} no encontrado en {guild.name}.")
                return

            game = server_info.get("game")
            channel = self.bot.get_channel(server_info.get("channel_id"))
            message_id = server_info.get("message_id")
            domain = server_info.get("domain")

            if not channel:
                logger.error(f"Canal no encontrado en {guild.name} (ID {server_info.get('channel_id')}).")
                return

            parsed = self.parse_server_ip(server_ip, game)
            if not parsed:
                logger.error(f"Formato inválido para server_ip '{server_ip}' en {guild.name}.")
                return
            ip_part, port_part, server_ip_formatted = parsed

            # Definir public_ip de forma anticipada para usarla en cualquier bloque
            public_ip = "178.33.160.187" if ip_part.startswith("10.0.0.") else ip_part

            # Crear el objeto del protocolo
            if game in ["cs2", "css", "gmod", "rust"]:
                try:
                    source = Source(host=ip_part, port=port_part)
                except Exception as e:
                    logger.error(f"Error creando Source para {server_ip_formatted}: {e}")
                    source = None
                game_name = {"cs2": "Counter-Strike 2",
                             "css": "Counter-Strike: Source",
                             "gmod": "Garry's Mod",
                             "rust": "Rust"}.get(game, "Unknown Game")
            elif game == "minecraft":
                try:
                    source = Minecraft(host=ip_part, port=port_part)
                except Exception as e:
                    logger.error(f"Error creando Minecraft para {server_ip_formatted}: {e}")
                    source = None
                game_name = "Minecraft"
            else:
                logger.warning(f"Juego '{game}' no soportado en {server_ip_formatted}.")
                await channel.send(f"Juego {game} no soportado.")
                return

            try:
                if game == "minecraft":
                    info = await source.get_status()
                    if self.debug:
                        logger.debug(f"Raw get_status para {server_ip_formatted}: {info}")
                    is_passworded = False
                    players = info["players"]["online"]
                    max_players = info["players"]["max"]
                    raw_motd = info.get("description", "Minecraft Server")
                    if self.debug:
                        logger.debug(f"Raw MOTD para {server_ip_formatted}: {raw_motd}")
                    hostname = self.convert_motd(raw_motd)
                    if self.debug:
                        logger.debug(f"Hostname convertido: {hostname} (longitud {len(hostname)})")
                    version_str = info.get("version", {}).get("name", "???")
                    map_name = version_str
                else:
                    info = await source.get_info()
                    if self.debug:
                        logger.debug(f"Raw get_info para {server_ip_formatted}: {info}")
                    players = info.players
                    max_players = info.max_players
                    map_name = getattr(info, "map", "N/A")
                    hostname = getattr(info, "name", "Unknown Server")
                    is_passworded = hasattr(info, "visibility") and info.visibility == 1

                if not hostname:
                    hostname = "Minecraft Server"

                ip_to_show = domain if (game == "minecraft" and domain) else f"{public_ip}:{port_part}"

                timezone = await self.config.guild(guild).timezone()
                try:
                    tz = pytz.timezone(timezone)
                except pytz.UnknownTimeZoneError:
                    logger.error(f"Zona horaria '{timezone}' inválida en {guild.name}, usando UTC.")
                    tz = pytz.UTC
                local_time = datetime.datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

                suffix = " - Server Status"
                title = self.truncate_title(hostname, suffix)
                if self.debug:
                    logger.debug(f"Título final: '{title}' (longitud {len(title)})")
                if is_passworded:
                    embed = discord.Embed(title=title, color=discord.Color.orange())
                    embed.add_field(name="🔐 Status", value="Maintenance", inline=True)
                else:
                    embed = discord.Embed(title=title, color=discord.Color.green())
                    embed.add_field(name="✅ Status", value="Online", inline=True)

                embed.add_field(name="🎮 Game", value=game_name, inline=True)
                if game != "minecraft":
                    connect_url = f"https://alienhost.ovh/connect.php?ip={public_ip}:{port_part}"
                    embed.add_field(name="\n\u200b\n🔗 Connect", value=f"[Connect]({connect_url})\n\u200b\n", inline=False)
                embed.add_field(name="📌 IP", value=ip_to_show, inline=True)
                if game == "minecraft":
                    embed.add_field(name="💎 Version", value=map_name, inline=True)
                else:
                    embed.add_field(name="🗺️ Current Map", value=map_name, inline=True)
                percent = int(players / max_players * 100) if max_players > 0 else 0
                embed.add_field(name="👥 Players", value=f"{players}/{max_players} ({percent}%)", inline=True)
                embed.set_footer(text=f"Game Server Monitor by Killerbite95 | Last update: {local_time}")

                try:
                    if first_time or not message_id:
                        msg = await channel.send(embed=embed)
                        servers[server_ip]["message_id"] = msg.id
                    else:
                        msg = await channel.fetch_message(message_id)
                        await msg.edit(embed=embed)
                except Exception as send_error:
                    if "embeds.0.title" in str(send_error):
                        logger.error(f"Error título largo en {server_ip_formatted}: {send_error}. Usando fallback.")
                        embed.title = "Server Status"
                        try:
                            if first_time or not message_id:
                                msg = await channel.send(embed=embed)
                                servers[server_ip]["message_id"] = msg.id
                            else:
                                msg = await channel.fetch_message(message_id)
                                await msg.edit(embed=embed)
                        except Exception as fallback_error:
                            logger.error(f"Error fallback en {server_ip_formatted}: {fallback_error}")
                    else:
                        logger.error(f"Error enviando mensaje en {server_ip_formatted}: {send_error}")

            except Exception as e:
                logger.error(f"Error actualizando {server_ip_formatted}: {e}")
                fallback_title = self.truncate_title(game_name + " Server", " - ❌ Offline")
                embed = discord.Embed(title=fallback_title, color=discord.Color.red())
                embed.add_field(name="Status", value="🔴 Offline", inline=True)
                embed.add_field(name="🎮 Game", value=game_name, inline=True)
                ip_to_show = domain if (game == "minecraft" and domain) else f"{public_ip}:{port_part}"
                embed.add_field(name="📌 IP", value=ip_to_show, inline=True)
                if game != "minecraft":
                    connect_url = f"https://alienhost.ovh/connect.php?ip={public_ip}:{port_part}"
                    embed.add_field(name="\n\u200b\n🔗 Connect", value=f"[Connect]({connect_url})\n\u200b\n", inline=False)
                embed.set_footer(text="Game Server Monitor by Killerbite95")
                try:
                    if first_time or not message_id:
                        msg = await channel.send(embed=embed)
                        servers[server_ip]["message_id"] = msg.id
                    else:
                        msg = await channel.fetch_message(message_id)
                        await msg.edit(embed=embed)
                except Exception as offline_error:
                    logger.error(f"Error enviando embed offline para {server_ip_formatted}: {offline_error}")

def setup(bot):
    bot.add_cog(GameServerMonitor(bot))
