import discord
from discord.ext import tasks, commands
from redbot.core import Config, checks
from opengsq.protocols import Source, Minecraft
import datetime
import pytz
import logging

logger = logging.getLogger("red.trini.gameservermonitor")

class GameServerMonitor(commands.Cog):
    """Monitoriza servidores de juegos y actualiza su estado en Discord. By Killerbite95"""

    def __init__(self, bot):
        self.bot = bot
        self.debug = False  # Modo debug desactivado por defecto
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_guild = {
            "servers": {},
            "timezone": "UTC",
            "refresh_time": 60  # Actualización cada 60 segundos por defecto
        }
        self.config.register_guild(**default_guild)
        self.server_monitor.start()

    @commands.command(name="gamservermonitordebug")
    @checks.admin_or_permissions(administrator=True)
    async def gamservermonitordebug(self, ctx, enabled: bool):
        """Activa o desactiva el modo debug. Ejemplo: !gamservermonitordebug true"""
        self.debug = enabled
        await ctx.send(f"Modo debug {'activado' if enabled else 'desactivado'}.")

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
        
        Ejemplo:
          !addserver 194.69.160.51:25575 minecraft #canal mc.dominio.com
        """
        channel = channel or ctx.channel
        game = game.lower()
        parsed = self.parse_server_ip(server_ip, game)
        if not parsed:
            await ctx.send(f"Formato inválido para server_ip '{server_ip}'.")
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
            await ctx.send(f"Formato inválido para server_ip '{server_ip}'.")
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
        updated = False
        for server_ip, data in servers.items():
            if data["channel_id"] == ctx.channel.id:
                await self.update_server_status(ctx.guild, server_ip, first_time=True)
                updated = True
        await ctx.send("Actualización forzada." if updated else "No hay servidores en este canal.")

    @commands.command(name="listaserver")
    async def list_servers(self, ctx):
        """Lista todos los servidores monitoreados."""
        servers = await self.config.guild(ctx.guild).servers()
        if not servers:
            await ctx.send("No hay servidores monitoreados.")
            return
        msg = "Servidores monitoreados:\n"
        for server_ip, data in servers.items():
            channel = self.bot.get_channel(data["channel_id"])
            msg += f"**{server_ip}** - Juego: **{data['game'].upper()}** - Canal: {channel.mention if channel else 'Desconocido'}\n"
        await ctx.send(msg)

    @commands.command(name="refreshtime")
    @checks.admin_or_permissions(administrator=True)
    async def refresh_time(self, ctx, seconds: int):
        """Establece el tiempo de actualización en segundos (mínimo 10)."""
        if seconds < 10:
            await ctx.send("El tiempo debe ser al menos 10 segundos.")
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
            rt = await self.config.guild(guild).refresh_time()
            self.server_monitor.change_interval(seconds=rt)

    def parse_server_ip(self, server_ip: str, game: str = None):
        """Analiza y valida server_ip; retorna (ip, port, formatted) o None."""
        default_ports = {"cs2": 27015, "css": 27015, "gmod": 27015, "rust": 28015, "minecraft": 25565}
        if ":" in server_ip:
            parts = server_ip.split(":")
            if len(parts) != 2:
                logger.error(f"server_ip '{server_ip}' tiene más de un ':'")
                return None
            ip_part, port_str = parts
            try:
                port = int(port_str)
            except ValueError:
                logger.error(f"Puerto inválido '{port_str}' en {server_ip}")
                return None
        else:
            if not game:
                logger.error(f"server_ip '{server_ip}' sin puerto y sin juego para asignar uno.")
                return None
            port = default_ports.get(game.lower())
            if not port:
                logger.error(f"No hay puerto predeterminado para {game}")
                return None
            ip_part = server_ip
        return ip_part, port, f"{ip_part}:{port}"

    def convert_motd(self, motd):
        """Convierte el MOTD (JSON o string) a texto plano y normalizado."""
        if isinstance(motd, str):
            result = motd
        elif isinstance(motd, dict):
            result = motd.get("text", "")
            if "extra" in motd and isinstance(motd["extra"], list):
                for extra in motd["extra"]:
                    result += self.convert_motd(extra)
        elif isinstance(motd, list):
            result = "".join(self.convert_motd(item) for item in motd)
        else:
            result = ""
        return " ".join(result.strip().split())

    def truncate_title(self, title: str, suffix: str) -> str:
        """
        Trunca el título (hostname + sufijo) para no superar 256 caracteres.
        Si aún excede, se usa "Server Status" como título.
        """
        max_total = 256
        allowed = max_total - len(suffix)
        truncated = title if len(title) <= allowed else title[: max(allowed - 3, 0)] + "..."
        final_title = truncated + suffix
        if len(final_title) > max_total:
            final_title = "Server Status"
        return final_title

    async def update_server_status(self, guild, server_ip, first_time=False):
        """Actualiza el estado del servidor y edita el mensaje en Discord."""
        async with self.config.guild(guild).servers() as servers:
            info_cfg = servers.get(server_ip)
            if not info_cfg:
                logger.warning(f"Servidor {server_ip} no encontrado en {guild.name}.")
                return
            game = info_cfg.get("game")
            channel_id = info_cfg.get("channel_id")
            message_id = info_cfg.get("message_id")
            domain = info_cfg.get("domain")
            channel = self.bot.get_channel(channel_id)
            if not channel:
                logger.error(f"Canal ID {channel_id} no encontrado en {guild.name}.")
                return
            parsed = self.parse_server_ip(server_ip, game)
            if not parsed:
                logger.error(f"Formato inválido para {server_ip} en {guild.name}.")
                return
            ip_part, port, _ = parsed

            # Crear objeto de consulta según el juego
            if game in ["cs2", "css", "gmod", "rust"]:
                try:
                    source = Source(host=ip_part, port=port)
                except Exception as e:
                    logger.error(f"Error creando Source para {server_ip}: {e}")
                    return
                game_name = {"cs2": "Counter-Strike 2", "css": "Counter-Strike: Source",
                             "gmod": "Garry's Mod", "rust": "Rust"}.get(game, "Unknown Game")
            elif game == "minecraft":
                try:
                    source = Minecraft(host=ip_part, port=port)
                except Exception as e:
                    logger.error(f"Error creando Minecraft para {server_ip}: {e}")
                    return
                game_name = "Minecraft"
            else:
                logger.warning(f"Juego {game} no soportado en {server_ip}.")
                await channel.send(f"Juego {game} no soportado.")
                return

            try:
                if game == "minecraft":
                    status = await source.get_status()
                    is_passworded = False
                    online = status["players"]["online"]
                    maxp = status["players"]["max"]
                    motd_raw = status.get("description", "Minecraft Server")
                    if self.debug:
                        logger.debug(f"Raw MOTD: {motd_raw}")
                    hostname = self.convert_motd(motd_raw)
                    if self.debug:
                        logger.debug(f"MOTD convertido: {hostname}")
                    version = status.get("version", {}).get("name", "???")
                    map_name = version
                else:
                    info = await source.get_info()
                    online = info.players
                    maxp = info.max_players
                    map_name = getattr(info, "map", "N/A")
                    hostname = getattr(info, "name", "Unknown Server")
                    is_passworded = hasattr(info, "visibility") and info.visibility == 1

                if not hostname:
                    hostname = "Minecraft Server"

                public_ip = "178.33.160.187" if ip_part.startswith("10.0.0.") else ip_part
                ip_to_show = domain if (game == "minecraft" and domain) else f"{public_ip}:{port}"

                timezone = await self.config.guild(guild).timezone()
                try:
                    tz = pytz.timezone(timezone)
                except pytz.UnknownTimeZoneError:
                    logger.error(f"Zona '{timezone}' inválida en {guild.name}, usando UTC.")
                    tz = pytz.UTC
                now = datetime.datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

                suffix = " - Server Status"
                title = self.truncate_title(hostname, suffix)
                if self.debug:
                    logger.debug(f"Título final: {title} (longitud {len(title)})")

                if is_passworded:
                    embed = discord.Embed(title=title, color=discord.Color.orange())
                    embed.add_field(name="🔐 Status", value="Maintenance", inline=True)
                else:
                    embed = discord.Embed(title=title, color=discord.Color.green())
                    embed.add_field(name="✅ Status", value="Online", inline=True)

                embed.add_field(name="🎮 Game", value=game_name, inline=True)
                if game != "minecraft":
                    url = f"https://alienhost.ovh/connect.php?ip={public_ip}:{port}"
                    embed.add_field(name="\n\u200b\n🔗 Connect", value=f"[Connect]({url})\n\u200b\n", inline=False)
                embed.add_field(name="📌 IP", value=ip_to_show, inline=True)
                if game == "minecraft":
                    embed.add_field(name="💎 Version", value=map_name, inline=True)
                else:
                    embed.add_field(name="🗺️ Current Map", value=map_name, inline=True)
                percent = int(online / maxp * 100) if maxp > 0 else 0
                embed.add_field(name="👥 Players", value=f"{online}/{maxp} ({percent}%)", inline=True)
                embed.set_footer(text=f"Game Server Monitor by Killerbite95 | Last update: {now}")

                if first_time or not message_id:
                    msg = await channel.send(embed=embed)
                    servers[server_ip]["message_id"] = msg.id
                    if self.debug:
                        logger.debug(f"Mensaje enviado (ID: {msg.id}).")
                else:
                    try:
                        msg = await channel.fetch_message(message_id)
                        await msg.edit(embed=embed)
                        if self.debug:
                            logger.debug(f"Mensaje editado (ID: {msg.id}).")
                    except discord.NotFound:
                        msg = await channel.send(embed=embed)
                        servers[server_ip]["message_id"] = msg.id
                        if self.debug:
                            logger.debug(f"Mensaje no encontrado; se envió uno nuevo (ID: {msg.id}).")
            except Exception as e:
                logger.error(f"Error al actualizar {server_ip}: {e}")
                if self.debug:
                    logger.exception("Error en update_server_status:")
                fallback_title = self.truncate_title(f"{game_name if game != 'minecraft' else 'Minecraft'} Server", " - ❌ Offline")
                embed = discord.Embed(title=fallback_title, color=discord.Color.red())
                embed.add_field(name="Status", value="🔴 Offline", inline=True)
                embed.add_field(name="🎮 Game", value=game_name, inline=True)
                ip_to_show = domain if (game == "minecraft" and domain) else f"{public_ip}:{port}"
                embed.add_field(name="📌 IP", value=ip_to_show, inline=True)
                if game != "minecraft":
                    url = f"https://alienhost.ovh/connect.php?ip={public_ip}:{port}"
                    embed.add_field(name="\n\u200b\n🔗 Connect", value=f"[Connect]({url})\n\u200b\n", inline=False)
                embed.set_footer(text="Game Server Monitor by Killerbite95")
                if first_time or not message_id:
                    try:
                        msg = await channel.send(embed=embed)
                        servers[server_ip]["message_id"] = msg.id
                        if self.debug:
                            logger.debug(f"Mensaje offline enviado (ID: {msg.id}).")
                    except Exception as send_err:
                        logger.error(f"Error al enviar mensaje offline para {server_ip}: {send_err}")
                else:
                    try:
                        msg = await channel.fetch_message(message_id)
                        await msg.edit(embed=embed)
                    except discord.NotFound:
                        try:
                            msg = await channel.send(embed=embed)
                            servers[server_ip]["message_id"] = msg.id
                        except Exception as send_err:
                            logger.error(f"Error al enviar mensaje offline para {server_ip}: {send_err}")

async def setup(bot):
    await bot.add_cog(GameServerMonitor(bot))
