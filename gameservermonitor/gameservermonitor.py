"""
GameServerMonitor - Cog para Red Discord Bot
Monitoriza servidores de juegos y actualiza su estado en Discord.
By Killerbite95

Versión: 2.0.0
Compatible con: Red-DiscordBot 3.5.22+
"""

import discord
from discord.ext import tasks
from redbot.core import commands, Config, checks
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n
import datetime
import pytz
import logging
import typing
from typing import Optional, Dict, Any, List, Tuple

# Importaciones locales
from .dashboard_integration import DashboardIntegration, dashboard_page
from .models import (
    ServerStatus, GameType, QueryResult, ServerData, 
    EmbedConfig, ServerStats
)
from .query_handlers import QueryService
from .exceptions import (
    GameServerMonitorError, ServerNotFoundError, ServerAlreadyExistsError,
    InvalidPortError, UnsupportedGameError, ChannelNotFoundError,
    InsufficientPermissionsError, InvalidTimezoneError
)

# Configuración de logging
logger = logging.getLogger("red.killerbite95.gameservermonitor")

# Internacionalización
_ = Translator("GameServerMonitor", __file__)


@cog_i18n(_)
class GameServerMonitor(DashboardIntegration, commands.Cog):
    """Monitoriza servidores de juegos y actualiza su estado en Discord. By Killerbite95"""
    
    __author__ = "Killerbite95"
    __version__ = "2.0.0"
    
    def __init__(self, bot: Red) -> None:
        self.bot: Red = bot
        self.config: Config = Config.get_conf(
            self, 
            identifier=1234567890, 
            force_registration=True
        )
        
        # Configuración por defecto del guild
        default_guild: Dict[str, Any] = {
            "servers": {},
            "timezone": "UTC",
            "refresh_time": 60,
            "public_ip": None,  # IP pública para reemplazar IPs privadas
            "connect_url_template": "https://alienhost.ovh/connect.php?ip={ip}",  # URL configurable
            "embed_config": {
                "show_thumbnail": True,
                "show_connect_button": True,
                "color_online": None,
                "color_offline": None,
                "color_maintenance": None
            }
        }
        self.config.register_guild(**default_guild)
        
        # Servicio de queries con caché
        self.query_service: QueryService = QueryService(cache_max_age=5.0)
        
        # Iniciar tarea de monitoreo
        self.server_monitor.start()
    
    def cog_unload(self) -> None:
        """Limpieza al descargar el cog."""
        self.server_monitor.cancel()
        self.query_service.clear_cache()
    
    async def red_delete_data_for_user(self, **kwargs) -> None:
        """Requerido por Red para GDPR compliance."""
        pass
    
    # ==================== Utilidades ====================
    
    def _valid_port(self, port: int) -> bool:
        """Valida que un puerto esté en el rango válido."""
        return isinstance(port, int) and 1 <= port <= 65535
    
    def _parse_server_ip(
        self, 
        server_ip: str, 
        game: Optional[GameType] = None
    ) -> Optional[Tuple[str, int, str]]:
        """
        Parsea una IP de servidor.
        
        Args:
            server_ip: IP en formato 'ip:puerto' o solo 'ip'
            game: Tipo de juego para puerto por defecto
            
        Returns:
            Tupla (ip, puerto, formatted_key) o None si es inválido
        """
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
                logger.error(f"server_ip '{server_ip}' no incluye puerto y no se proporcionó juego.")
                return None
            port_part = game.default_port
            ip_part = server_ip
        
        if not self._valid_port(port_part):
            return None
            
        return ip_part, port_part, f"{ip_part}:{port_part}"
    
    async def _get_public_ip(
        self, 
        guild: discord.Guild, 
        original_ip: str
    ) -> str:
        """
        Obtiene la IP pública, reemplazando IPs privadas si está configurado.
        
        Args:
            guild: Guild de Discord
            original_ip: IP original del servidor
            
        Returns:
            IP pública o la original si no aplica
        """
        public_ip = await self.config.guild(guild).public_ip()
        
        # Solo reemplazar si hay IP pública configurada y la original es privada
        if public_ip and (
            original_ip.startswith("10.") or
            original_ip.startswith("192.168.") or
            original_ip.startswith("172.16.") or
            original_ip.startswith("172.17.") or
            original_ip.startswith("172.18.") or
            original_ip.startswith("172.19.") or
            original_ip.startswith("172.2") or
            original_ip.startswith("172.30.") or
            original_ip.startswith("172.31.")
        ):
            return public_ip
        return original_ip
    
    async def _check_channel_permissions(
        self, 
        channel: discord.TextChannel
    ) -> Tuple[bool, List[str]]:
        """
        Verifica que el bot tenga permisos necesarios en el canal.
        
        Returns:
            Tupla (tiene_permisos, lista_permisos_faltantes)
        """
        permissions = channel.permissions_for(channel.guild.me)
        missing = []
        
        if not permissions.send_messages:
            missing.append("send_messages")
        if not permissions.embed_links:
            missing.append("embed_links")
        if not permissions.read_message_history:
            missing.append("read_message_history")
        
        return len(missing) == 0, missing
    
    def _truncate_title(self, title: str, suffix: str) -> str:
        """Trunca el título del embed para cumplir con el límite de Discord."""
        max_total = 256
        allowed = max_total - len(suffix)
        if len(title) > allowed:
            title = title[:max(allowed - 3, 0)] + "..."
        return title + suffix
    
    async def _get_timezone(self, guild: discord.Guild) -> pytz.BaseTzInfo:
        """Obtiene la zona horaria configurada para el guild."""
        timezone_str = await self.config.guild(guild).timezone()
        try:
            return pytz.timezone(timezone_str)
        except pytz.UnknownTimeZoneError:
            logger.warning(f"Zona horaria '{timezone_str}' inválida, usando UTC.")
            return pytz.UTC
    
    # ==================== Generación de Embeds ====================
    
    async def _create_online_embed(
        self,
        guild: discord.Guild,
        server_data: ServerData,
        query_result: QueryResult,
        ip_to_show: str
    ) -> discord.Embed:
        """
        Crea un embed para servidor online/maintenance.
        
        Args:
            guild: Guild de Discord
            server_data: Datos del servidor
            query_result: Resultado de la query
            ip_to_show: IP formateada para mostrar
            
        Returns:
            Embed de Discord configurado
        """
        tz = await self._get_timezone(guild)
        local_time = datetime.datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        
        embed_config_data = await self.config.guild(guild).embed_config()
        embed_config = EmbedConfig(**embed_config_data)
        
        # Título y color
        suffix = " - Server Status"
        title = self._truncate_title(query_result.hostname, suffix)
        color = embed_config.get_color(query_result.status)
        
        embed = discord.Embed(title=title, color=color)
        
        # Thumbnail del juego
        if embed_config.show_thumbnail and server_data.game:
            thumbnail_url = server_data.game.thumbnail_url
            if thumbnail_url:
                embed.set_thumbnail(url=thumbnail_url)
        
        # Status
        status_emoji = query_result.status.emoji
        status_name = query_result.status.display_name
        embed.add_field(
            name=f"{status_emoji} Status",
            value=status_name,
            inline=True
        )
        
        # Juego
        game_name = server_data.game.display_name if server_data.game else "Unknown"
        embed.add_field(name="🎮 Game", value=game_name, inline=True)
        
        # Botón de conexión (no para Minecraft)
        if embed_config.show_connect_button and server_data.game != GameType.MINECRAFT:
            connect_template = await self.config.guild(guild).connect_url_template()
            connect_url = connect_template.format(ip=ip_to_show)
            embed.add_field(
                name="\n\u200b\n🔗 Connect", 
                value=f"[Connect]({connect_url})\n\u200b\n", 
                inline=False
            )
        
        # IP
        embed.add_field(name="📌 IP", value=ip_to_show, inline=True)
        
        # Mapa o Versión
        if server_data.game == GameType.MINECRAFT:
            embed.add_field(name="💎 Version", value=query_result.map_name, inline=True)
        else:
            embed.add_field(name="🗺️ Current Map", value=query_result.map_name, inline=True)
        
        # Jugadores
        embed.add_field(
            name="👥 Players", 
            value=query_result.player_display, 
            inline=True
        )
        
        # Latencia si está disponible
        if query_result.latency_ms:
            embed.add_field(
                name="📶 Ping", 
                value=f"{query_result.latency_ms:.0f}ms", 
                inline=True
            )
        
        embed.set_footer(
            text=f"Game Server Monitor by Killerbite95 | Last update: {local_time}"
        )
        
        return embed
    
    async def _create_offline_embed(
        self,
        guild: discord.Guild,
        server_data: ServerData,
        ip_to_show: str
    ) -> discord.Embed:
        """
        Crea un embed para servidor offline.
        
        Args:
            guild: Guild de Discord
            server_data: Datos del servidor
            ip_to_show: IP formateada para mostrar
            
        Returns:
            Embed de Discord configurado
        """
        embed_config_data = await self.config.guild(guild).embed_config()
        embed_config = EmbedConfig(**embed_config_data)
        
        game_name = server_data.game.display_name if server_data.game else "Game"
        title = self._truncate_title(f"{game_name} Server", " - ❌ Offline")
        color = embed_config.get_color(ServerStatus.OFFLINE)
        
        embed = discord.Embed(title=title, color=color)
        
        # Thumbnail
        if embed_config.show_thumbnail and server_data.game:
            thumbnail_url = server_data.game.thumbnail_url
            if thumbnail_url:
                embed.set_thumbnail(url=thumbnail_url)
        
        embed.add_field(name="Status", value="🔴 Offline", inline=True)
        embed.add_field(
            name="🎮 Game", 
            value=game_name,
            inline=True
        )
        embed.add_field(name="📌 IP", value=ip_to_show, inline=True)
        
        # Botón de conexión (no para Minecraft)
        if embed_config.show_connect_button and server_data.game != GameType.MINECRAFT:
            connect_template = await self.config.guild(guild).connect_url_template()
            connect_url = connect_template.format(ip=ip_to_show)
            embed.add_field(
                name="\n\u200b\n🔗 Connect", 
                value=f"[Connect]({connect_url})\n\u200b\n", 
                inline=False
            )
        
        embed.set_footer(text="Game Server Monitor by Killerbite95")
        
        return embed
    
    # ==================== Core: Actualización de Estado ====================
    
    async def _dispatch_status_event(
        self,
        guild: discord.Guild,
        server_key: str,
        old_status: Optional[ServerStatus],
        new_status: ServerStatus
    ) -> None:
        """
        Dispara eventos personalizados cuando cambia el estado de un servidor.
        
        Eventos:
            - on_gameserver_online: Cuando un servidor pasa a online
            - on_gameserver_offline: Cuando un servidor pasa a offline
            - on_gameserver_status_change: Cualquier cambio de estado
        """
        if old_status == new_status:
            return
        
        # Evento general de cambio
        self.bot.dispatch(
            "gameserver_status_change",
            guild=guild,
            server_key=server_key,
            old_status=old_status,
            new_status=new_status
        )
        
        # Eventos específicos
        if new_status == ServerStatus.ONLINE:
            self.bot.dispatch(
                "gameserver_online",
                guild=guild,
                server_key=server_key
            )
        elif new_status == ServerStatus.OFFLINE:
            self.bot.dispatch(
                "gameserver_offline",
                guild=guild,
                server_key=server_key
            )
    
    async def update_server_status(
        self, 
        guild: discord.Guild, 
        server_key: str, 
        first_time: bool = False
    ) -> None:
        """
        Actualiza el estado de un servidor específico.
        
        Args:
            guild: Guild de Discord
            server_key: Clave del servidor (ip:puerto)
            first_time: Si es la primera vez (crear mensaje nuevo)
        """
        async with self.config.guild(guild).servers() as servers:
            server_dict = servers.get(server_key)
            if not server_dict:
                logger.warning(f"Servidor {server_key} no encontrado en {guild.name}.")
                return
            
            # Convertir a dataclass
            server_data = ServerData.from_dict(server_key, server_dict)
            
            if not server_data.game:
                logger.error(f"Juego no válido para servidor {server_key}")
                return
            
            # Obtener canal
            channel = self.bot.get_channel(server_data.channel_id)
            if not channel:
                logger.error(
                    f"Canal {server_data.channel_id} no encontrado para {server_key}"
                )
                return
            
            # Verificar permisos
            has_perms, missing = await self._check_channel_permissions(channel)
            if not has_perms:
                logger.error(
                    f"Permisos insuficientes en {channel.name}: {missing}"
                )
                return
            
            # Obtener IP pública
            host = server_data.host
            port = server_data.port
            public_ip = await self._get_public_ip(guild, host)
            
            if server_data.game == GameType.DAYZ:
                game_port = server_data.game_port or port
                ip_to_show = f"{public_ip}:{game_port}"
            else:
                ip_to_show = f"{public_ip}:{port}"
            
            # Realizar query
            query_kwargs = {}
            if server_data.game == GameType.DAYZ:
                query_kwargs["query_port"] = server_data.query_port
            
            query_result = await self.query_service.query_server(
                host=host,
                port=server_data.game_port if server_data.game == GameType.DAYZ else port,
                game=server_data.game,
                **query_kwargs
            )
            
            # Actualizar estadísticas
            old_status = server_data.last_status
            server_data.total_queries += 1
            if query_result.success:
                server_data.successful_queries += 1
                server_data.last_online = datetime.datetime.utcnow()
            else:
                server_data.last_offline = datetime.datetime.utcnow()
            server_data.last_status = query_result.status
            
            # Disparar eventos de cambio de estado
            await self._dispatch_status_event(
                guild, server_key, old_status, query_result.status
            )
            
            # Crear embed
            if query_result.success:
                embed = await self._create_online_embed(
                    guild, server_data, query_result, ip_to_show
                )
            else:
                embed = await self._create_offline_embed(
                    guild, server_data, ip_to_show
                )
            
            # Enviar o editar mensaje
            try:
                if first_time or not server_data.message_id:
                    msg = await channel.send(embed=embed)
                    server_data.message_id = msg.id
                else:
                    try:
                        msg = await channel.fetch_message(server_data.message_id)
                        await msg.edit(embed=embed)
                    except discord.NotFound:
                        # Mensaje eliminado, crear uno nuevo
                        msg = await channel.send(embed=embed)
                        server_data.message_id = msg.id
            except discord.Forbidden:
                logger.error(f"Sin permisos para enviar mensaje en {channel.name}")
            except discord.HTTPException as e:
                logger.error(f"Error HTTP al enviar mensaje: {e}")
            
            # Guardar datos actualizados
            servers[server_key] = server_data.to_dict()
    
    # ==================== Tareas ====================
    
    @tasks.loop(seconds=60)
    async def server_monitor(self) -> None:
        """Tarea principal de monitoreo de servidores."""
        # Limpiar caché expirada
        self.query_service.cleanup_cache()
        
        for guild in self.bot.guilds:
            servers = await self.config.guild(guild).servers()
            for server_key in servers.keys():
                try:
                    await self.update_server_status(guild, server_key)
                except Exception as e:
                    logger.error(f"Error actualizando {server_key} en {guild.name}: {e!r}")
    
    @server_monitor.before_loop
    async def before_server_monitor(self) -> None:
        """Espera a que el bot esté listo antes de iniciar el monitoreo."""
        await self.bot.wait_until_ready()
        
        # Obtener refresh_time del primer guild (o usar default)
        for guild in self.bot.guilds:
            refresh_time = await self.config.guild(guild).refresh_time()
            self.server_monitor.change_interval(seconds=refresh_time)
            break
    
    # ==================== Comandos de Configuración ====================
    
    @commands.command(name="settimezone")
    @checks.admin_or_permissions(administrator=True)
    async def set_timezone(self, ctx: commands.Context, timezone: str) -> None:
        """
        Establece la zona horaria para las actualizaciones.
        
        Ejemplo: `[p]settimezone Europe/Madrid`
        """
        try:
            pytz.timezone(timezone)
        except pytz.UnknownTimeZoneError:
            await ctx.send(_("❌ La zona horaria '{}' no es válida.").format(timezone))
            return
        
        await self.config.guild(ctx.guild).timezone.set(timezone)
        await ctx.send(_("✅ Zona horaria establecida en **{}**").format(timezone))
    
    @commands.command(name="setpublicip")
    @checks.admin_or_permissions(administrator=True)
    async def set_public_ip(self, ctx: commands.Context, ip: Optional[str] = None) -> None:
        """
        Establece la IP pública para reemplazar IPs privadas.
        
        Usa sin argumentos para desactivar el reemplazo.
        
        Ejemplo: `[p]setpublicip 123.45.67.89`
        """
        if ip is None:
            await self.config.guild(ctx.guild).public_ip.set(None)
            await ctx.send(_("✅ Reemplazo de IP pública desactivado."))
        else:
            await self.config.guild(ctx.guild).public_ip.set(ip)
            await ctx.send(
                _("✅ IP pública establecida en **{}**. Las IPs privadas serán reemplazadas.").format(ip)
            )
    
    @commands.command(name="setconnecturl")
    @checks.admin_or_permissions(administrator=True)
    async def set_connect_url(self, ctx: commands.Context, *, url: str) -> None:
        """
        Establece la plantilla de URL de conexión.
        
        Usa `{ip}` como placeholder para la IP:puerto del servidor.
        
        Ejemplo: `[p]setconnecturl https://mysite.com/connect?server={ip}`
        """
        if "{ip}" not in url:
            await ctx.send(_("❌ La URL debe contener `{ip}` como placeholder."))
            return
        
        await self.config.guild(ctx.guild).connect_url_template.set(url)
        await ctx.send(_("✅ URL de conexión establecida: {}").format(url))
    
    @commands.command(name="refreshtime")
    @checks.admin_or_permissions(administrator=True)
    async def refresh_time(self, ctx: commands.Context, seconds: int) -> None:
        """
        Establece el tiempo de actualización en segundos.
        
        Mínimo: 10 segundos
        
        Ejemplo: `[p]refreshtime 120`
        """
        if seconds < 10:
            await ctx.send(_("❌ El tiempo debe ser al menos 10 segundos."))
            return
        
        await self.config.guild(ctx.guild).refresh_time.set(seconds)
        self.server_monitor.change_interval(seconds=seconds)
        await ctx.send(_("✅ Tiempo de actualización establecido en **{}** segundos.").format(seconds))
    
    @commands.command(name="gameservermonitordebug")
    @checks.admin_or_permissions(administrator=True)
    async def toggle_debug(self, ctx: commands.Context, state: bool) -> None:
        """
        Activa o desactiva el modo debug.
        
        Ejemplo: `[p]gameservermonitordebug true`
        """
        self.query_service.debug = state
        status = _("activado") if state else _("desactivado")
        await ctx.send(_("✅ Modo debug {}.").format(status))
    
    # ==================== Comandos de Servidores ====================
    
    @commands.command(name="addserver")
    @checks.admin_or_permissions(administrator=True)
    async def add_server(
        self,
        ctx: commands.Context,
        server_ip: str,
        game: str,
        game_port: typing.Optional[int] = None,
        query_port: typing.Optional[int] = None,
        channel: typing.Optional[discord.TextChannel] = None,
        domain: typing.Optional[str] = None,
    ) -> None:
        """
        Añade un servidor para monitorear su estado.

        **Uso general:**
        `[p]addserver <ip[:puerto]> <juego> [#canal] [dominio]`

        **Uso DayZ (puertos separados):**
        `[p]addserver <ip> dayz <game_port> <query_port> [#canal] [dominio]`

        **Juegos soportados:** cs2, css, gmod, rust, minecraft, dayz
        """
        channel = channel or ctx.channel
        game_type = GameType.from_string(game)
        
        if game_type is None:
            supported = ", ".join(GameType.supported_games())
            await ctx.send(
                _("❌ Juego '{}' no soportado. Disponibles: {}").format(game, supported)
            )
            return
        
        # Verificar permisos del canal
        has_perms, missing = await self._check_channel_permissions(channel)
        if not has_perms:
            await ctx.send(
                _("❌ Faltan permisos en {}: {}").format(channel.mention, ", ".join(missing))
            )
            return
        
        # Manejo especial para DayZ
        if game_type == GameType.DAYZ:
            host = server_ip.split(":")[0]
            
            if game_port is None:
                await ctx.send(
                    _("❌ Para **DayZ** indica al menos `game_port` (ej. 2302).\n"
                      "Ejemplo: `{}addserver 1.2.3.4 dayz 2302 27016 #canal`").format(ctx.prefix)
                )
                return
            
            if not self._valid_port(game_port):
                await ctx.send(_("❌ Puerto de juego inválido (1-65535)."))
                return
            
            if query_port is not None and not self._valid_port(query_port):
                await ctx.send(_("❌ Puerto de query inválido (1-65535)."))
                return
            
            key = f"{host}:{game_port}"
            
            async with self.config.guild(ctx.guild).servers() as servers:
                if key in servers:
                    await ctx.send(_("❌ El servidor **{}** ya está siendo monitoreado.").format(key))
                    return
                
                servers[key] = {
                    "game": "dayz",
                    "channel_id": channel.id,
                    "message_id": None,
                    "domain": domain,
                    "game_port": game_port,
                    "query_port": query_port,
                    "total_queries": 0,
                    "successful_queries": 0,
                    "last_online": None,
                    "last_offline": None,
                    "last_status": None
                }
            
            msg = _("✅ Servidor **{}** (DayZ) añadido en {}.\n"
                   "Puertos → juego: **{}**").format(key, channel.mention, game_port)
            if query_port:
                msg += _(", query: **{}**").format(query_port)
            if domain:
                msg += _("\nDominio: {}").format(domain)
            
            await ctx.send(msg)
            await self.update_server_status(ctx.guild, key, first_time=True)
            return
        
        # Resto de juegos
        parsed = self._parse_server_ip(server_ip, game_type)
        if not parsed:
            await ctx.send(
                _("❌ Formato inválido. Usa 'ip:puerto' o solo 'ip' (se usará puerto por defecto).")
            )
            return
        
        ip_part, port_part, server_key = parsed
        
        async with self.config.guild(ctx.guild).servers() as servers:
            if server_key in servers:
                await ctx.send(
                    _("❌ El servidor **{}** ya está siendo monitoreado.").format(server_key)
                )
                return
            
            servers[server_key] = {
                "game": game_type.value,
                "channel_id": channel.id,
                "message_id": None,
                "domain": domain,
                "total_queries": 0,
                "successful_queries": 0,
                "last_online": None,
                "last_offline": None,
                "last_status": None
            }
        
        msg = _("✅ Servidor **{}** ({}) añadido en {}.").format(
            server_key, game_type.display_name, channel.mention
        )
        if domain:
            msg += _("\nDominio: {}").format(domain)
        
        await ctx.send(msg)
        await self.update_server_status(ctx.guild, server_key, first_time=True)
    
    @commands.command(name="removeserver")
    @checks.admin_or_permissions(administrator=True)
    async def remove_server(self, ctx: commands.Context, server_key: str) -> None:
        """
        Elimina el monitoreo de un servidor.
        
        Pasa exactamente la clave listada (ej. `ip:puerto`).
        
        Ejemplo: `[p]removeserver 192.168.1.1:27015`
        """
        if ":" not in server_key:
            await ctx.send(_("❌ Formato: `ip:puerto`"))
            return
        
        async with self.config.guild(ctx.guild).servers() as servers:
            if server_key in servers:
                del servers[server_key]
                await ctx.send(_("✅ Servidor **{}** eliminado del monitoreo.").format(server_key))
            else:
                await ctx.send(_("❌ No se encontró servidor con clave **{}**.").format(server_key))
    
    @commands.command(name="forzarstatus")
    async def force_status(self, ctx: commands.Context) -> None:
        """Fuerza una actualización de estado en el canal actual."""
        servers = await self.config.guild(ctx.guild).servers()
        updated = False
        
        for server_key, data in servers.items():
            if data.get("channel_id") == ctx.channel.id:
                # Limpiar caché para este servidor
                game = GameType.from_string(data.get("game", ""))
                if game:
                    host, port = server_key.split(":")
                    self.query_service._cache.invalidate(host, int(port), game)
                
                await self.update_server_status(ctx.guild, server_key, first_time=True)
                updated = True
        
        if updated:
            await ctx.send(_("✅ Actualización forzada completada."))
        else:
            await ctx.send(_("❌ No hay servidores monitoreados en este canal."))
    
    @commands.command(name="listaserver")
    async def list_servers(self, ctx: commands.Context) -> None:
        """Lista todos los servidores monitoreados."""
        servers = await self.config.guild(ctx.guild).servers()
        
        if not servers:
            await ctx.send(_("📋 No hay servidores siendo monitoreados."))
            return
        
        embed = discord.Embed(
            title=_("📋 Servidores Monitoreados"),
            color=discord.Color.blue()
        )
        
        for server_key, data in servers.items():
            game_type = GameType.from_string(data.get("game", ""))
            game_name = game_type.display_name if game_type else data.get("game", "N/A").upper()
            
            channel = self.bot.get_channel(data.get("channel_id"))
            channel_mention = channel.mention if channel else "Desconocido"
            
            value = f"**Juego:** {game_name}\n**Canal:** {channel_mention}"
            
            if data.get("game", "").lower() == "dayz":
                value += f"\n**Puertos:** game:{data.get('game_port')} | query:{data.get('query_port')}"
            
            if data.get("domain"):
                value += f"\n**Dominio:** {data.get('domain')}"
            
            # Estadísticas básicas
            uptime = 0
            if data.get("total_queries", 0) > 0:
                uptime = (data.get("successful_queries", 0) / data.get("total_queries", 1)) * 100
            value += f"\n**Uptime:** {uptime:.1f}%"
            
            embed.add_field(name=f"📡 {server_key}", value=value, inline=False)
        
        await ctx.send(embed=embed)
    
    @commands.command(name="serverstats")
    async def server_stats(self, ctx: commands.Context, server_key: str) -> None:
        """
        Muestra estadísticas detalladas de un servidor.
        
        Ejemplo: `[p]serverstats 192.168.1.1:27015`
        """
        servers = await self.config.guild(ctx.guild).servers()
        
        if server_key not in servers:
            await ctx.send(_("❌ Servidor **{}** no encontrado.").format(server_key))
            return
        
        server_data = ServerData.from_dict(server_key, servers[server_key])
        
        if not server_data.game:
            await ctx.send(_("❌ Datos de juego no válidos para este servidor."))
            return
        
        # Obtener estado actual
        query_kwargs = {}
        if server_data.game == GameType.DAYZ:
            query_kwargs["query_port"] = server_data.query_port
            port = server_data.game_port or server_data.port
        else:
            port = server_data.port
        
        query_result = await self.query_service.query_server(
            host=server_data.host,
            port=port,
            game=server_data.game,
            use_cache=False,
            **query_kwargs
        )
        
        # Crear estadísticas
        stats = ServerStats(
            server_key=server_key,
            game=server_data.game,
            status=query_result.status,
            uptime_percentage=server_data.uptime_percentage,
            total_queries=server_data.total_queries,
            successful_queries=server_data.successful_queries,
            last_online=server_data.last_online,
            last_offline=server_data.last_offline,
            current_players=query_result.players,
            max_players=query_result.max_players,
            hostname=query_result.hostname,
            map_name=query_result.map_name
        )
        
        timezone = await self.config.guild(ctx.guild).timezone()
        embed = stats.to_embed(timezone)
        
        await ctx.send(embed=embed)
    
    # ==================== Dashboard ====================
    
    @dashboard_page(name="servers", description="Muestra los servidores monitorizados")
    async def rpc_callback_servers(
        self, 
        guild_id: int, 
        **kwargs
    ) -> typing.Dict[str, typing.Any]:
        """Página del dashboard que lista los servidores monitorizados."""
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return {"status": 1, "error": "Guild no encontrada."}
        
        servers = await self.config.guild(guild).servers()
        
        html_content = """
        <link rel="stylesheet"
              href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
        <div class="container mt-4">
          <h1 class="mb-4">🎮 Servidores Monitoreados</h1>
          <table class="table table-bordered table-striped table-hover">
            <thead class="table-dark">
              <tr>
                <th scope="col">IP (clave)</th>
                <th scope="col">Juego</th>
                <th scope="col">Canal ID</th>
                <th scope="col">Dominio</th>
                <th scope="col">Puertos</th>
                <th scope="col">Uptime</th>
              </tr>
            </thead>
            <tbody>
        """
        
        for server_key, data in servers.items():
            game_type = GameType.from_string(data.get("game", ""))
            game_name = game_type.display_name if game_type else data.get("game", "N/A").upper()
            channel_id = data.get("channel_id", "N/A")
            domain = data.get("domain") or "-"
            
            ports = "-"
            if data.get("game", "").lower() == "dayz":
                ports = f"game:{data.get('game_port')} | query:{data.get('query_port')}"
            
            uptime = 0
            if data.get("total_queries", 0) > 0:
                uptime = (data.get("successful_queries", 0) / data.get("total_queries", 1)) * 100
            
            html_content += f"""
              <tr>
                <td><code>{server_key}</code></td>
                <td>{game_name}</td>
                <td>{channel_id}</td>
                <td>{domain}</td>
                <td>{ports}</td>
                <td>{uptime:.1f}%</td>
              </tr>
            """
        
        html_content += """
            </tbody>
          </table>
        </div>
        """
        
        return {"status": 0, "web_content": {"source": html_content}}
    
    @dashboard_page(
        name="add_server", 
        description="Añade un servidor al monitor", 
        methods=("GET", "POST")
    )
    async def rpc_add_server(
        self, 
        guild_id: int, 
        **kwargs
    ) -> typing.Dict[str, typing.Any]:
        """Página del dashboard para añadir un servidor."""
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return {"status": 1, "error": "Guild no encontrada."}
        
        import wtforms
        
        class AddServerForm(kwargs["Form"]):
            server_ip = wtforms.StringField(
                "Server Host (IP o dominio)", 
                validators=[wtforms.validators.InputRequired()]
            )
            game = wtforms.SelectField(
                "Juego",
                choices=[(g.value, g.display_name) for g in GameType],
                validators=[wtforms.validators.InputRequired()]
            )
            game_port = wtforms.IntegerField("DayZ Game Port (ej. 2302)", default=None)
            query_port = wtforms.IntegerField("DayZ Query Port (opcional)", default=None)
            channel_id = wtforms.IntegerField(
                "Channel ID", 
                validators=[wtforms.validators.InputRequired()]
            )
            domain = wtforms.StringField("Dominio (opcional)")
            submit = wtforms.SubmitField("Añadir Servidor")
        
        form = AddServerForm()
        
        if form.validate_on_submit():
            server_ip = form.server_ip.data.strip()
            game_str = form.game.data.strip().lower()
            channel_id = form.channel_id.data
            domain = form.domain.data.strip() if form.domain.data else None
            game_type = GameType.from_string(game_str)
            
            if game_type is None:
                return {"status": 1, "error": f"Juego '{game_str}' no soportado."}
            
            if game_type == GameType.DAYZ:
                gp = form.game_port.data
                qp = form.query_port.data
                
                if not gp:
                    return {"status": 1, "error": "Para DayZ debes indicar game_port."}
                
                if not self._valid_port(int(gp)):
                    return {"status": 1, "error": "Puerto de juego inválido."}
                
                if qp and not self._valid_port(int(qp)):
                    return {"status": 1, "error": "Puerto de query inválido."}
                
                host = server_ip.split(":")[0]
                key = f"{host}:{int(gp)}"
                
                async with self.config.guild(guild).servers() as servers:
                    if key in servers:
                        return {
                            "status": 0,
                            "notifications": [{
                                "message": "El servidor ya está siendo monitoreado.",
                                "category": "warning"
                            }]
                        }
                    
                    servers[key] = {
                        "game": "dayz",
                        "channel_id": channel_id,
                        "message_id": None,
                        "domain": domain,
                        "game_port": int(gp),
                        "query_port": int(qp) if qp else None,
                        "total_queries": 0,
                        "successful_queries": 0,
                        "last_online": None,
                        "last_offline": None,
                        "last_status": None
                    }
                
                await self.update_server_status(guild, key, first_time=True)
                return {
                    "status": 0,
                    "notifications": [{
                        "message": f"Servidor {key} (DayZ) añadido.",
                        "category": "success"
                    }],
                    "redirect_url": kwargs["request_url"]
                }
            
            # Otros juegos
            parsed = self._parse_server_ip(server_ip, game_type)
            if not parsed:
                return {"status": 1, "error": "Formato de IP inválido."}
            
            ip_part, port_part, server_key = parsed
            
            async with self.config.guild(guild).servers() as servers:
                if server_key in servers:
                    return {
                        "status": 0,
                        "notifications": [{
                            "message": "El servidor ya está siendo monitoreado.",
                            "category": "warning"
                        }]
                    }
                
                servers[server_key] = {
                    "game": game_type.value,
                    "channel_id": channel_id,
                    "message_id": None,
                    "domain": domain,
                    "total_queries": 0,
                    "successful_queries": 0,
                    "last_online": None,
                    "last_offline": None,
                    "last_status": None
                }
            
            await self.update_server_status(guild, server_key, first_time=True)
            return {
                "status": 0,
                "notifications": [{
                    "message": f"Servidor {server_key} añadido.",
                    "category": "success"
                }],
                "redirect_url": kwargs["request_url"]
            }
        
        source = "{{ form|safe }}"
        return {"status": 0, "web_content": {"source": source, "form": form}}
    
    @dashboard_page(
        name="remove_server", 
        description="Elimina un servidor del monitor", 
        methods=("GET", "POST")
    )
    async def rpc_remove_server(
        self, 
        guild_id: int, 
        **kwargs
    ) -> typing.Dict[str, typing.Any]:
        """Página del dashboard para eliminar un servidor."""
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return {"status": 1, "error": "Guild no encontrada."}
        
        import wtforms
        
        class RemoveServerForm(kwargs["Form"]):
            server_key = wtforms.StringField(
                "Server Key (ip:puerto)", 
                validators=[wtforms.validators.InputRequired()]
            )
            submit = wtforms.SubmitField("Eliminar Servidor")
        
        form = RemoveServerForm()
        
        if form.validate_on_submit():
            key = form.server_key.data.strip()
            
            async with self.config.guild(guild).servers() as servers:
                if key not in servers:
                    return {
                        "status": 0,
                        "notifications": [{
                            "message": "El servidor no está siendo monitoreado.",
                            "category": "warning"
                        }]
                    }
                del servers[key]
            
            return {
                "status": 0,
                "notifications": [{
                    "message": f"Servidor {key} eliminado.",
                    "category": "success"
                }],
                "redirect_url": kwargs["request_url"]
            }
        
        source = "{{ form|safe }}"
        return {"status": 0, "web_content": {"source": source, "form": form}}
    
    @dashboard_page(name="config", description="Configuración del monitor", methods=("GET", "POST"))
    async def rpc_config(
        self, 
        guild_id: int, 
        **kwargs
    ) -> typing.Dict[str, typing.Any]:
        """Página del dashboard para configuración general."""
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return {"status": 1, "error": "Guild no encontrada."}
        
        import wtforms
        
        current_config = {
            "timezone": await self.config.guild(guild).timezone(),
            "refresh_time": await self.config.guild(guild).refresh_time(),
            "public_ip": await self.config.guild(guild).public_ip() or "",
            "connect_url": await self.config.guild(guild).connect_url_template()
        }
        
        class ConfigForm(kwargs["Form"]):
            timezone = wtforms.StringField("Zona Horaria", default=current_config["timezone"])
            refresh_time = wtforms.IntegerField(
                "Tiempo de actualización (segundos)", 
                default=current_config["refresh_time"]
            )
            public_ip = wtforms.StringField("IP Pública", default=current_config["public_ip"])
            connect_url = wtforms.StringField(
                "URL de Conexión (usar {ip})", 
                default=current_config["connect_url"]
            )
            submit = wtforms.SubmitField("Guardar Configuración")
        
        form = ConfigForm()
        
        if form.validate_on_submit():
            # Validar timezone
            try:
                pytz.timezone(form.timezone.data)
            except pytz.UnknownTimeZoneError:
                return {"status": 1, "error": f"Zona horaria '{form.timezone.data}' inválida."}
            
            # Validar refresh_time
            if form.refresh_time.data < 10:
                return {"status": 1, "error": "El tiempo de actualización debe ser al menos 10 segundos."}
            
            # Validar connect_url
            if form.connect_url.data and "{ip}" not in form.connect_url.data:
                return {"status": 1, "error": "La URL de conexión debe contener {ip}."}
            
            # Guardar configuración
            await self.config.guild(guild).timezone.set(form.timezone.data)
            await self.config.guild(guild).refresh_time.set(form.refresh_time.data)
            await self.config.guild(guild).public_ip.set(form.public_ip.data or None)
            await self.config.guild(guild).connect_url_template.set(form.connect_url.data)
            
            self.server_monitor.change_interval(seconds=form.refresh_time.data)
            
            return {
                "status": 0,
                "notifications": [{
                    "message": "Configuración guardada correctamente.",
                    "category": "success"
                }],
                "redirect_url": kwargs["request_url"]
            }
        
        source = "{{ form|safe }}"
        return {"status": 0, "web_content": {"source": source, "form": form}}
