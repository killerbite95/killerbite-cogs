"""
GameServerMonitor - Cog para Red Discord Bot
Monitoriza servidores de juegos y actualiza su estado en Discord.
By Killerbite95

Versión: 2.2.0
Compatible con: Red-DiscordBot 3.5.22+
"""

import discord
from discord import app_commands
from discord.ext import tasks
from redbot.core import commands, Config, checks
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n, set_contextual_locales_from_guild
from redbot.core.utils.views import ConfirmView
from redbot.core.utils.chat_formatting import pagify
import contextlib
import datetime
import ipaddress
import pytz
import logging
import typing
import uuid
from typing import Optional, Dict, Any, List, Tuple

# Importaciones locales
from .dashboard_integration import DashboardIntegration, dashboard_page
from .models import (
    ServerStatus, GameType, QueryResult, ServerData, 
    EmbedConfig, ServerStats, PlayerHistory, PlayerInfo
)
from .query_handlers import QueryService
from .exceptions import (
    GameServerMonitorError, ServerNotFoundError, ServerAlreadyExistsError,
    InvalidPortError, UnsupportedGameError, ChannelNotFoundError,
    InsufficientPermissionsError, InvalidTimezoneError
)
from .views import ServerActionsView, setup_persistent_views, create_server_view

# Configuración de logging
logger = logging.getLogger("red.killerbite95.gameservermonitor")

# Días sin responder tras los que un servidor se considera muerto por defecto.
DEAD_SERVER_DEFAULT_DAYS = 7

# Internacionalización
_ = Translator("GameServerMonitor", __file__)


@cog_i18n(_)
class GameServerMonitor(DashboardIntegration, commands.Cog):
    """Monitors game servers and updates their status in Discord. By Killerbite95"""
    
    __author__ = "Killerbite95"
    __version__ = "2.4.0"
    
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
            },
            "player_history": {},  # Historial de jugadores por servidor
            # Nueva configuración para interacciones v2.2.0
            "interaction_features": {
                "enabled": True,
                "buttons_enabled": True,
                "ephemeral_default": True,
                "delete_after_prefix_seconds": 20,  # None para no borrar
                "history_default_hours": 24,
                "history_max_hours": 168
            }
        }
        self.config.register_guild(**default_guild)
        
        # Servicio de queries con caché
        self.query_service: QueryService = QueryService(cache_max_age=5.0)
        
        # Set de servidores recién actualizados (evita duplicados)
        # Formato: {"guild_id:server_key": timestamp}
        self._recently_updated: Dict[str, datetime.datetime] = {}
        
        # Registrar views persistentes
        self._views_registered = False
        
        # Iniciar tarea de monitoreo
        self.server_monitor.start()
    

    # ------------------------------------------------------------------
    # Protocolo de La Trini: TriniProfiles (export/import) y TriniBackups
    # ------------------------------------------------------------------

    # Datos de funcionamiento (no son configuracion): ni se exportan ni se pisan.
    _TRINI_RUNTIME_KEYS = ('player_history',)
    # Configuracion que solo tiene sentido en el mismo servidor.
    _TRINI_LOCAL_KEYS = ()

    async def trini_export(self, guild):
        conf = await self.config.guild(guild).all()
        return {k: v for k, v in conf.items() if k not in self._TRINI_RUNTIME_KEYS}

    async def trini_import(self, guild, data, *, same_guild):
        skip = set(self._TRINI_RUNTIME_KEYS)
        if not same_guild:
            skip |= set(self._TRINI_LOCAL_KEYS)
        data = {k: v for k, v in data.items() if k not in skip}
        if not same_guild:
            # Los mensajes publicados y los contadores son del otro servidor:
            # el monitor creara mensajes nuevos en el siguiente refresco.
            for server in (data.get("servers") or {}).values():
                server["message_id"] = None
                for counter in ("total_queries", "successful_queries"):
                    server[counter] = 0
                for stamp in ("last_online", "last_offline", "last_status"):
                    server[stamp] = None
        group = self.config.guild(guild)
        current = await group.all()
        for key, value in data.items():
            if key in current:
                await group.set_raw(key, value=value)
        return []

    async def cog_load(self) -> None:
        """Se ejecuta cuando el cog se carga."""
        # Registrar en Dashboard si ya está cargado
        await super().cog_load()
        
        # Registrar views persistentes para botones
        if not self._views_registered:
            setup_persistent_views(self.bot, self)
            self._views_registered = True
            logger.info("Views persistentes registradas en cog_load")
        
        # Migrar servidores sin server_id
        await self._migrate_server_ids()
        
        # Resetear contadores de queries para evitar números gigantes
        await self._reset_query_counters()
    
    async def _reset_query_counters(self) -> None:
        """
        Limita los contadores de queries a un máximo de 100 000
        para evitar números desproporcionados, sin perder la
        proporción de uptime.
        """
        cap = 100_000
        for guild in self.bot.guilds:
            async with self.config.guild(guild).servers() as servers:
                for server_key, server_data in servers.items():
                    total = server_data.get("total_queries", 0)
                    success = server_data.get("successful_queries", 0)
                    if total > cap:
                        ratio = success / total if total else 0
                        server_data["total_queries"] = cap
                        server_data["successful_queries"] = int(cap * ratio)
        logger.info("Contadores de queries verificados (cap=%d)", cap)
    
    def cog_unload(self) -> None:
        """Limpieza al descargar el cog."""
        self.server_monitor.cancel()
        self.query_service.clear_cache()
        self._recently_updated.clear()
    
    async def _migrate_server_ids(self) -> None:
        """
        Migración automática: añade server_id a servidores existentes que no lo tengan.
        """
        for guild in self.bot.guilds:
            async with self.config.guild(guild).servers() as servers:
                modified = False
                for server_key, server_data in servers.items():
                    if "server_id" not in server_data or not server_data["server_id"]:
                        # Generar un UUID corto único
                        server_data["server_id"] = self._generate_server_id()
                        modified = True
                        logger.info(f"Migrado server_id para {server_key} en {guild.name}")
                
                if modified:
                    logger.info(f"Migración de server_ids completada para {guild.name}")
    
    def _generate_server_id(self) -> str:
        """Genera un ID único corto para un servidor."""
        return uuid.uuid4().hex[:8]
    
    async def red_delete_data_for_user(self, **kwargs) -> None:
        """Requerido por Red para GDPR compliance."""
        pass
    
    # ==================== Utilidades ====================
    
    @staticmethod
    def _is_private_ip(ip: str) -> bool:
        """Comprueba si una IP pertenece a un rango privado (RFC 1918)."""
        return (
            ip.startswith("10.")
            or ip.startswith("192.168.")
            or ip.startswith("172.16.")
            or ip.startswith("172.17.")
            or ip.startswith("172.18.")
            or ip.startswith("172.19.")
            or ip.startswith("172.2")
            or ip.startswith("172.30.")
            or ip.startswith("172.31.")
        )
    
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
    
    async def _resolve_server_key(
        self, 
        guild: discord.Guild, 
        search_key: str
    ) -> Optional[str]:
        """
        Resuelve la clave de servidor buscando por IP real o IP pública.
        
        Permite buscar servidores tanto por su IP:puerto real (privada) como por
        la IP pública mostrada en el embed (si tiene setpublicip configurado).
        
        Args:
            guild: Guild de Discord
            search_key: IP:puerto a buscar (puede ser la real o la pública)
            
        Returns:
            La clave real del servidor (IP:puerto real) o None si no se encuentra
        """
        servers = await self.config.guild(guild).servers()
        
        # Búsqueda directa - si existe como clave, devolverla
        if search_key in servers:
            return search_key
        
        # Búsqueda por IP pública
        # Si el usuario busca con IP_PUBLICA:PUERTO, buscar servidores con IP_PRIVADA:PUERTO
        # que tendrían esa IP pública
        public_ip = await self.config.guild(guild).public_ip()
        if not public_ip:
            return None
        
        # Extraer el puerto de la búsqueda
        if ":" not in search_key:
            return None
        
        search_parts = search_key.split(":")
        if len(search_parts) != 2:
            return None
        
        search_ip, search_port = search_parts
        
        # Si la búsqueda es con la IP pública, buscar servidor con ese puerto
        if search_ip == public_ip:
            for server_key, server_data in servers.items():
                if ":" in server_key:
                    server_ip, server_port = server_key.split(":", 1)
                    # Si el puerto coincide y la IP del servidor es privada
                    if server_port == search_port and self._is_private_ip(server_ip):
                        return server_key
        
        return None
    
    async def _resolve_server_key_by_id(
        self,
        guild: discord.Guild,
        server_id: str
    ) -> Optional[str]:
        """
        Resuelve la clave de servidor (IP:puerto) a partir del server_id.
        
        Args:
            guild: Guild de Discord
            server_id: ID único del servidor
            
        Returns:
            La clave real del servidor (IP:puerto) o None si no se encuentra
        """
        servers = await self.config.guild(guild).servers()
        
        for server_key, server_data in servers.items():
            if server_data.get("server_id") == server_id:
                return server_key
        
        return None
    
    async def _get_server_id(
        self,
        guild: discord.Guild,
        server_key: str
    ) -> Optional[str]:
        """
        Obtiene el server_id para una clave de servidor.
        
        Args:
            guild: Guild de Discord
            server_key: Clave del servidor (IP:puerto)
            
        Returns:
            El server_id o None si no se encuentra
        """
        servers = await self.config.guild(guild).servers()
        
        if server_key in servers:
            return servers[server_key].get("server_id")
        
        return None
    
    # ==================== Payload Builders (para botones y comandos) ====================
    
    async def _build_players_payload(
        self,
        guild: discord.Guild,
        server_key: str
    ) -> Dict[str, Any]:
        """
        Construye el payload para mostrar lista de jugadores.
        Reutilizable por comandos de prefijo, slash y botones.
        
        Args:
            guild: Guild de Discord
            server_key: Clave del servidor
            
        Returns:
            Dict con 'embed', 'content', 'file' o 'error'
        """
        servers = await self.config.guild(guild).servers()
        
        if server_key not in servers:
            return {"error": _("Server not found.")}
        
        server_data = ServerData.from_dict(server_key, servers[server_key])
        
        if not server_data.game:
            return {"error": _("Invalid game data for this server.")}
        
        # Obtener estado actual con lista de jugadores
        query_kwargs = {"fetch_players": True}
        if server_data.game == GameType.DAYZ:
            query_kwargs["query_port"] = server_data.query_port
            port = server_data.game_port or server_data.port
        else:
            port = server_data.effective_query_port
        
        query_result = await self.query_service.query_server(
            host=server_data.host,
            port=port,
            game=server_data.game,
            use_cache=False,
            **query_kwargs
        )
        
        if not query_result.success:
            # Construir nombre para mostrar: IP pública > dominio > nombre del juego
            public_ip = await self.config.guild(guild).public_ip()
            if public_ip:
                server_name = f"{public_ip}:{port}"
            elif server_data.domain:
                server_name = server_data.domain
            elif server_data.game:
                server_name = server_data.game.display_name
            else:
                server_name = "Server"
            return {"error": _("**{server_name}** is offline or not responding.").format(server_name=server_name)}
        
        game_name = server_data.game.display_name if server_data.game else "Unknown"
        
        # Obtener IP para mostrar y conectar
        public_ip = await self.config.guild(guild).public_ip()
        ip_to_show = self._format_display_address(server_data, public_ip)
        
        # Obtener nombre para mostrar con fallback
        display_name = query_result.hostname
        if not display_name or display_name == "Unknown Server":
            if public_ip:
                display_name = f"{public_ip}:{server_data.connect_port}"
            elif server_data.domain:
                display_name = server_data.domain
            else:
                display_name = game_name
        
        # Para Minecraft map_name contiene la versión
        map_or_version_label = _('Version') if server_data.game == GameType.MINECRAFT else _('Map')
        
        # Crear embed
        embed = discord.Embed(
            title=_("Players - {hostname}").format(hostname=display_name[:50]),
            description=f"**{_('Game')}:** {game_name}\n"
                       f"**{map_or_version_label}:** {query_result.map_name}\n"
                       f"**{_('Players')}:** {query_result.players}/{query_result.max_players}",
            color=query_result.status.color
        )
        
        if server_data.game and server_data.game.thumbnail_url:
            embed.set_thumbnail(url=server_data.game.thumbnail_url)
        
        # Botón de conexión (no para Minecraft ni Rust: se conectan por consola)
        if server_data.game and server_data.game.supports_connect_button:
            connect_template = await self.config.guild(guild).connect_url_template()
            connect_url = connect_template.format(ip=ip_to_show)
            embed.add_field(
                name=f"🔗 {_('Connect')}", 
                value=f"[{_('Connect')}]({connect_url})", 
                inline=False
            )
        
        if query_result.player_list:
            # Dividir jugadores en chunks para no exceder 1024 caracteres por field
            all_players = query_result.player_list
            header = f"{_('Name'):<20} {_('Score'):>6} {_('Time'):>10}\n" + "─" * 38 + "\n"
            
            # Calcular cuántos jugadores caben por field (~40 chars por línea, max ~900 para seguridad)
            players_per_field = 20
            chunks = [all_players[i:i + players_per_field] for i in range(0, len(all_players), players_per_field)]
            
            for idx, chunk in enumerate(chunks[:3]):  # Máximo 3 fields (60 jugadores)
                player_text = "```\n"
                if idx == 0:
                    player_text += header
                
                for player in chunk:
                    name = player["name"][:18] if player["name"] else "Unknown"
                    score = player.get("score", 0)
                    duration = player.get("duration_formatted", "N/A")
                    player_text += f"{name:<20} {score:>6} {duration:>10}\n"
                
                player_text += "```"
                
                # Nombre del field
                if len(chunks) == 1:
                    field_name = f"📋 {_('Player List')}"
                else:
                    field_name = f"📋 {_('Player List')} ({idx + 1}/{min(len(chunks), 3)})"
                
                embed.add_field(name=field_name, value=player_text, inline=False)
            
            # Si hay más de 60 jugadores, indicarlo
            if len(all_players) > 60:
                embed.add_field(
                    name="📋 ...",
                    value=f"*{_('... and {count} more players').format(count=len(all_players) - 60)}*",
                    inline=False
                )
        else:
            if query_result.players > 0:
                if server_data.game == GameType.MINECRAFT:
                    embed.add_field(
                        name=f"📋 {_('Player List')}",
                        value=f"*{_('The Minecraft server does not expose the full player list.')}*",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name=f"📋 {_('Player List')}",
                        value=f"*{_('Could not retrieve the player list.')}*",
                        inline=False
                    )
            else:
                embed.add_field(
                    name=f"📋 {_('Player List')}",
                    value=f"*{_('No players connected.')}*",
                    inline=False
                )
        
        if query_result.latency_ms:
            embed.add_field(name=f"📶 {_('Ping')}", value=f"{query_result.latency_ms:.0f}ms", inline=True)
        
        embed.set_footer(text=f"GSM v{self.__version__} by Killerbite95")
        
        return {"embed": embed}
    
    async def _build_stats_payload(
        self,
        guild: discord.Guild,
        server_key: str
    ) -> Dict[str, Any]:
        """
        Construye el payload para mostrar estadísticas del servidor.
        
        Args:
            guild: Guild de Discord
            server_key: Clave del servidor
            
        Returns:
            Dict con 'embed', 'content', 'file' o 'error'
        """
        servers = await self.config.guild(guild).servers()
        
        if server_key not in servers:
            return {"error": _("Server not found.")}
        
        server_data = ServerData.from_dict(server_key, servers[server_key])
        
        if not server_data.game:
            return {"error": _("Invalid game data for this server.")}
        
        # Obtener estado actual
        query_kwargs = {}
        if server_data.game == GameType.DAYZ:
            query_kwargs["query_port"] = server_data.query_port
            port = server_data.game_port or server_data.port
        else:
            port = server_data.effective_query_port
        
        query_result = await self.query_service.query_server(
            host=server_data.host,
            port=port,
            game=server_data.game,
            use_cache=False,
            **query_kwargs
        )
        
        # Obtener IP para mostrar y conectar
        public_ip = await self.config.guild(guild).public_ip()
        ip_to_show = self._format_display_address(server_data, public_ip)
        
        # Obtener nombre para mostrar con fallback
        display_name = query_result.hostname
        if not display_name or display_name == "Unknown Server":
            if public_ip:
                display_name = f"{public_ip}:{server_data.connect_port}"
            elif server_data.domain:
                display_name = server_data.domain
            elif server_data.game:
                display_name = server_data.game.display_name
            else:
                display_name = server_key
        
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
            hostname=display_name,
            map_name=query_result.map_name
        )
        
        timezone = await self.config.guild(guild).timezone()
        embed = stats.to_embed(timezone)
        
        # Botón de conexión (no para Minecraft ni Rust: se conectan por consola)
        if server_data.game and server_data.game.supports_connect_button:
            connect_template = await self.config.guild(guild).connect_url_template()
            connect_url = connect_template.format(ip=ip_to_show)
            embed.add_field(
                name=f"🔗 {_('Connect')}", 
                value=f"[{_('Connect')}]({connect_url})", 
                inline=False
            )
        
        return {"embed": embed}
    
    async def _build_history_payload(
        self,
        guild: discord.Guild,
        server_key: str,
        hours: int = 24
    ) -> Dict[str, Any]:
        """
        Construye el payload para mostrar historial de jugadores.
        
        Args:
            guild: Guild de Discord
            server_key: Clave del servidor
            hours: Horas de historial a mostrar
            
        Returns:
            Dict con 'embed', 'content', 'file' o 'error'
        """
        servers = await self.config.guild(guild).servers()
        
        if server_key not in servers:
            return {"error": _("Server not found.")}
        
        # Validar horas
        interaction_config = await self.config.guild(guild).interaction_features()
        max_hours = interaction_config.get("history_max_hours", 168)
        
        if hours < 1:
            hours = 1
        elif hours > max_hours:
            hours = max_hours
        
        # Obtener historial
        history = await self._get_player_history(guild, server_key)
        
        if not history or not history.entries:
            return {"error": _("No history available for this server.\nHistory will be generated with the next updates.")}
        
        # Obtener datos del servidor
        server_data = ServerData.from_dict(server_key, servers[server_key])
        game_name = server_data.game.display_name if server_data.game else "Unknown"
        
        # Obtener hostname del servidor (query rápido)
        query_kwargs = {}
        if server_data.game == GameType.DAYZ:
            query_kwargs["query_port"] = server_data.query_port
            port = server_data.game_port or server_data.port
        else:
            port = server_data.effective_query_port
        
        query_result = await self.query_service.query_server(
            host=server_data.host,
            port=port,
            game=server_data.game,
            use_cache=True  # Usar caché para rapidez
        )
        
        # Usar hostname si está disponible, sino IP pública, dominio o nombre del juego
        display_name = query_result.hostname if query_result.success else None
        if not display_name or display_name == "Unknown Server":
            # Intentar con IP pública configurada
            public_ip = await self.config.guild(guild).public_ip()
            if public_ip:
                display_name = f"{public_ip}:{server_data.connect_port}"
            else:
                display_name = server_data.domain or game_name
        
        # Obtener IP para conectar
        public_ip = await self.config.guild(guild).public_ip()
        ip_to_show = self._format_display_address(server_data, public_ip)
        
        # Generar gráfico
        graph = history.generate_ascii_graph(hours=hours, width=24)
        
        # Obtener estadísticas del período
        entries = history.get_entries_for_period(hours)
        if entries:
            online_entries = [e for e in entries if e.status != ServerStatus.OFFLINE]
            total_entries = len(entries)
            online_count = len(online_entries)
            uptime_pct = (online_count / total_entries * 100) if total_entries > 0 else 0
            
            if online_entries:
                peak_players = max(e.player_count for e in online_entries)
                avg_players = sum(e.player_count for e in online_entries) / len(online_entries)
            else:
                peak_players = 0
                avg_players = 0
        else:
            uptime_pct = 0
            peak_players = 0
            avg_players = 0
        
        # Crear embed
        embed = discord.Embed(
            title=_("History - {display_name}").format(display_name=display_name[:50]),
            description=f"**{_('Game')}:** {game_name}\n**{_('Period Statistics')}:** {_('Last {hours} hours').format(hours=hours)}",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name=f"📈 {_('Period Statistics')}",
            value=f"🔝 **{_('Peak')}:** {peak_players} {_('players')}\n"
                  f"📊 **{_('Average')}:** {avg_players:.1f} {_('players')}\n"
                  f"⏱️ **{_('Uptime')}:** {uptime_pct:.1f}%",
            inline=False
        )
        
        embed.add_field(
            name=f"📉 {_('Activity Graph')}",
            value=graph,
            inline=False
        )
        
        # Botón de conexión (no para Minecraft ni Rust: se conectan por consola)
        if server_data.game and server_data.game.supports_connect_button:
            connect_template = await self.config.guild(guild).connect_url_template()
            connect_url = connect_template.format(ip=ip_to_show)
            embed.add_field(
                name=f"🔗 {_('Connect')}", 
                value=f"[{_('Connect')}]({connect_url})", 
                inline=False
            )
        
        embed.set_footer(text=f"GSM v{self.__version__} by Killerbite95")
        
        return {"embed": embed}
    
    async def _build_map_payload(
        self,
        guild: discord.Guild,
        server_key: str
    ) -> Dict[str, Any]:
        """
        Construye el payload para mostrar el mapa actual del servidor.
        
        Args:
            guild: Guild de Discord
            server_key: Clave del servidor
            
        Returns:
            Dict con 'embed', 'content' o 'error'
        """
        servers = await self.config.guild(guild).servers()
        
        if server_key not in servers:
            return {"error": _("Server not found.")}
        
        server_data = ServerData.from_dict(server_key, servers[server_key])
        
        if not server_data.game:
            return {"error": _("Invalid game data for this server.")}
        
        # Obtener estado actual
        query_kwargs = {}
        if server_data.game == GameType.DAYZ:
            query_kwargs["query_port"] = server_data.query_port
            port = server_data.game_port or server_data.port
        else:
            port = server_data.effective_query_port
        
        query_result = await self.query_service.query_server(
            host=server_data.host,
            port=port,
            game=server_data.game,
            use_cache=False
        )
        
        if not query_result.success:
            server_name = server_data.domain or server_key
            return {"error": _("**{server_name}** is offline or not responding.").format(server_name=server_name)}
        
        game_name = server_data.game.display_name if server_data.game else _("Unknown")
        
        # Obtener IP para mostrar y conectar
        public_ip = await self.config.guild(guild).public_ip()
        ip_to_show = self._format_display_address(server_data, public_ip)
        
        # Obtener nombre para mostrar con fallback
        display_name = query_result.hostname
        if not display_name or display_name == "Unknown Server":
            if public_ip:
                display_name = f"{public_ip}:{server_data.connect_port}"
            elif server_data.domain:
                display_name = server_data.domain
            else:
                display_name = game_name
        
        # Para Minecraft, map_name contiene la versión
        if server_data.game == GameType.MINECRAFT:
            map_label = _("Version")
        else:
            map_label = _("Current Map")
        
        # Crear embed
        embed = discord.Embed(
            title=f"🗺️ {map_label} - {display_name[:50]}",
            color=query_result.status.color
        )
        
        if server_data.game and server_data.game.thumbnail_url:
            embed.set_thumbnail(url=server_data.game.thumbnail_url)
        
        embed.add_field(
            name=f"🎮 {_('Game')}",
            value=game_name,
            inline=True
        )
        
        embed.add_field(
            name=f"🗺️ {map_label}",
            value=query_result.map_name or "N/A",
            inline=True
        )
        
        embed.add_field(
            name=f"👥 {_('Players')}",
            value=query_result.player_display,
            inline=True
        )
        
        if query_result.latency_ms:
            embed.add_field(
                name=f"📶 {_('Ping')}",
                value=f"{query_result.latency_ms:.0f}ms",
                inline=True
            )
        
        # Botón de conexión (no para Minecraft ni Rust: se conectan por consola)
        if server_data.game and server_data.game.supports_connect_button:
            connect_template = await self.config.guild(guild).connect_url_template()
            connect_url = connect_template.format(ip=ip_to_show)
            embed.add_field(
                name=f"🔗 {_('Connect')}", 
                value=f"[{_('Connect')}]({connect_url})", 
                inline=False
            )
        
        embed.set_footer(text=f"GSM v{self.__version__} by Killerbite95")
        
        return {"embed": embed}
    
    # ==================== Autocomplete ====================
    
    async def _server_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        """
        Autocomplete para seleccionar servidores en slash commands.
        Muestra hostname o IP pública, nunca IP privada.
        
        Args:
            interaction: Interacción de Discord
            current: Texto actual ingresado por el usuario
            
        Returns:
            Lista de opciones para autocompletar
        """
        if not interaction.guild:
            return []
        
        servers = await self.config.guild(interaction.guild).servers()
        public_ip = await self.config.guild(interaction.guild).public_ip()
        choices = []
        
        current_lower = current.lower()
        
        for server_key, server_data in servers.items():
            game_type = GameType.from_string(server_data.get("game", ""))
            game_name = game_type.display_name if game_type else "Unknown"
            
            # Prioridad: last_hostname persistido > caché > IP pública > dominio > juego
            display_id = server_data.get("last_hostname")
            
            # Fallback a caché en memoria
            if not display_id:
                server_obj = ServerData.from_dict(server_key, server_data)
                if server_obj.game:
                    cached = self.query_service._cache.get(
                        server_obj.host, server_obj.port, server_obj.game
                    )
                    if cached and cached.hostname:
                        display_id = cached.hostname
            
            # Fallback a IP pública / dominio
            if not display_id or display_id == "Unknown Server":
                server_obj = ServerData.from_dict(server_key, server_data)
                if public_ip:
                    display_id = f"{public_ip}:{server_obj.port}"
                elif server_obj.domain:
                    display_id = server_obj.domain
                else:
                    display_id = server_key
            
            # Nombre amigable: "Hostname (Juego)"
            display_name = f"{display_id[:60]} ({game_name})"
            
            if current_lower in display_name.lower() or current_lower in game_name.lower():
                server_id = server_data.get("server_id", server_key)
                choices.append(
                    app_commands.Choice(name=display_name[:100], value=server_id)
                )
        
        return choices[:25]  # Discord limita a 25 opciones
    
    # ==================== Detección de servidores muertos ====================

    @staticmethod
    def _format_duration(delta: datetime.timedelta) -> str:
        """Formatea una duración de forma compacta ('12d 4h' o '4h')."""
        days = delta.days
        hours = delta.seconds // 3600
        if days:
            return f"{days}d {hours}h"
        if hours:
            return f"{hours}h"
        return f"{delta.seconds // 60}m"

    async def _find_dead_servers(
        self,
        guild: discord.Guild,
        days: int
    ) -> List[Dict[str, Any]]:
        """
        Busca servidores que llevan demasiado tiempo sin responder.

        Un servidor es candidato si su canal ya no existe, si nunca respondió
        desde que se añadió, o si su última query exitosa es más antigua que
        `days` días.

        Args:
            guild: Guild de Discord
            days: Días sin responder a partir de los que se considera muerto

        Returns:
            Lista de candidatos, los más muertos primero
        """
        servers = await self.config.guild(guild).servers()
        refresh_time = await self.config.guild(guild).refresh_time() or 60
        threshold = datetime.timedelta(days=days)
        now = datetime.datetime.utcnow()
        candidates: List[Dict[str, Any]] = []

        for server_key, data in servers.items():
            server_data = ServerData.from_dict(server_key, data)
            game_name = server_data.game.display_name if server_data.game else data.get("game", "N/A")
            display = data.get("last_hostname") or server_data.domain or server_key
            channel = self.bot.get_channel(server_data.channel_id)

            candidate = {
                "server_key": server_key,
                "display": display,
                "game": game_name,
                "channel": channel,
                "channel_id": server_data.channel_id,
                "message_id": server_data.message_id,
            }

            # El canal desapareció: el monitor falla en cada ciclo sin remedio posible.
            if channel is None:
                candidate["reason"] = _("Its channel no longer exists")
                candidate["offline_for"] = None
                candidate["sort"] = datetime.timedelta.max
                candidates.append(candidate)
                continue

            if server_data.last_online is not None:
                # Dato autoritativo: la última vez que respondió de verdad.
                last_online = server_data.last_online
                if last_online.tzinfo is not None:
                    last_online = last_online.astimezone(
                        datetime.timezone.utc
                    ).replace(tzinfo=None)
                offline_for = now - last_online
                reason = _("Unresponsive for {duration}").format(
                    duration=self._format_duration(offline_for)
                )
            elif server_data.total_queries > 0:
                # Nunca respondió: aproximamos el tiempo por el número de intentos.
                offline_for = datetime.timedelta(
                    seconds=server_data.total_queries * refresh_time
                )
                reason = _("Never responded since it was added")
            else:
                # Recién añadido y aún sin consultar: no es candidato.
                continue

            if offline_for < threshold:
                continue

            candidate["reason"] = reason
            candidate["offline_for"] = offline_for
            candidate["sort"] = offline_for
            candidates.append(candidate)

        candidates.sort(key=lambda c: c["sort"], reverse=True)
        return candidates

    async def _delete_server_message(
        self,
        channel_id: Optional[int],
        message_id: Optional[int]
    ) -> None:
        """Borra el embed de estado de un servidor, ignorando cualquier fallo."""
        if not channel_id or not message_id:
            return
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            return
        try:
            msg = await channel.fetch_message(message_id)
            await msg.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

    async def _forget_servers(
        self,
        guild: discord.Guild,
        server_keys: List[str]
    ) -> None:
        """Elimina servidores de la config junto con su historial de jugadores."""
        async with self.config.guild(guild).servers() as servers:
            for server_key in server_keys:
                servers.pop(server_key, None)
        async with self.config.guild(guild).player_history() as history:
            for server_key in server_keys:
                history.pop(server_key, None)
        for server_key in server_keys:
            self._recently_updated.pop(f"{guild.id}:{server_key}", None)

    def _build_dead_servers_embed(
        self,
        candidates: List[Dict[str, Any]],
        days: int,
        title: str,
        color: discord.Color
    ) -> discord.Embed:
        """Construye el embed con el listado de servidores muertos."""
        lines: List[str] = []
        shown = candidates[:20]
        for candidate in shown:
            channel = candidate["channel"]
            channel_text = channel.mention if channel else _("deleted channel")
            lines.append(
                f"**{candidate['display'][:60]}**\n"
                f"`{candidate['server_key']}` · {candidate['game']} · {channel_text}\n"
                f"⤷ {candidate['reason']}"
            )
        if len(candidates) > len(shown):
            lines.append(
                _("*... and {count} more server(s).*").format(
                    count=len(candidates) - len(shown)
                )
            )

        embed = discord.Embed(
            title=title,
            description=_(
                "{count} server(s) have been unresponsive for more than **{days}** day(s).\n\n"
            ).format(count=len(candidates), days=days) + "\n\n".join(lines),
            color=color
        )
        embed.description = embed.description[:4096]
        embed.set_footer(text=f"GSM v{self.__version__} by Killerbite95")
        return embed

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
        if public_ip and self._is_private_ip(original_ip):
            return public_ip
        return original_ip

    def _format_display_address(
        self,
        server_data: ServerData,
        public_ip: Optional[str]
    ) -> str:
        """Dirección a mostrar en el campo IP del embed.

        Prioriza el dominio configurado; si no, la IP pública; si no, el host
        real. Se omite el puerto cuando coincide con el puerto por defecto del
        juego (es el principal, p.ej. 28015 en Rust); en otro caso se incluye
        para que la dirección sea directamente usable.
        """
        host = server_data.domain or public_ip or server_data.host
        port = server_data.connect_port
        if server_data.game and port == server_data.game.default_port:
            return host
        return f"{host}:{port}"

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
        suffix = _(" - Server Status")
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
            name=f"{status_emoji} {_('Status')}",
            value=status_name,
            inline=True
        )
        
        # Juego
        game_name = server_data.game.display_name if server_data.game else _("Unknown")
        embed.add_field(name=f"🎮 {_('Game')}", value=game_name, inline=True)
        
        # Botón de conexión (no para Minecraft ni Rust: se conectan por consola)
        if embed_config.show_connect_button and server_data.game and server_data.game.supports_connect_button:
            connect_template = await self.config.guild(guild).connect_url_template()
            connect_url = connect_template.format(ip=ip_to_show)
            embed.add_field(
                name=f"\n\u200b\n🔗 {_('Connect')}", 
                value=f"[{_('Connect')}]({connect_url})\n\u200b\n", 
                inline=False
            )
        
        # IP
        embed.add_field(name=f"📌 {_('IP')}", value=ip_to_show, inline=True)
        
        # Mapa o Versión
        if server_data.game == GameType.MINECRAFT:
            embed.add_field(name=f"💎 {_('Version')}", value=query_result.map_name, inline=True)
        else:
            embed.add_field(name=f"🗺️ {_('Current Map')}", value=query_result.map_name, inline=True)
        
        # Jugadores
        embed.add_field(
            name=f"👥 {_('Players')}", 
            value=query_result.player_display, 
            inline=True
        )
        
        # Latencia si está disponible
        if query_result.latency_ms:
            embed.add_field(
                name=f"📶 {_('Ping')}", 
                value=f"{query_result.latency_ms:.0f}ms", 
                inline=True
            )
        
        embed.set_footer(
            text=f"GSM v{self.__version__} by Killerbite95 | {local_time}"
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
        
        game_name = server_data.game.display_name if server_data.game else _("Game")
        title = self._truncate_title(_("{game} Server").format(game=game_name), _(" - ❌ Offline"))
        color = embed_config.get_color(ServerStatus.OFFLINE)
        
        embed = discord.Embed(title=title, color=color)
        
        # Thumbnail
        if embed_config.show_thumbnail and server_data.game:
            thumbnail_url = server_data.game.thumbnail_url
            if thumbnail_url:
                embed.set_thumbnail(url=thumbnail_url)
        
        embed.add_field(name=_("Status"), value=f"🔴 {_('Offline')}", inline=True)
        embed.add_field(
            name=f"🎮 {_('Game')}", 
            value=game_name,
            inline=True
        )
        embed.add_field(name=f"📌 {_('IP')}", value=ip_to_show, inline=True)
        
        # Botón de conexión (no para Minecraft ni Rust: se conectan por consola)
        if embed_config.show_connect_button and server_data.game and server_data.game.supports_connect_button:
            connect_template = await self.config.guild(guild).connect_url_template()
            connect_url = connect_template.format(ip=ip_to_show)
            embed.add_field(
                name=f"\n\u200b\n🔗 {_('Connect')}", 
                value=f"[{_('Connect')}]({connect_url})\n\u200b\n", 
                inline=False
            )
        
        embed.set_footer(text=f"GSM v{self.__version__} by Killerbite95")
        
        return embed
    
    # ==================== Historial de Jugadores ====================
    
    async def _record_player_history(
        self,
        guild: discord.Guild,
        server_key: str,
        player_count: int,
        max_players: int,
        status: ServerStatus
    ) -> None:
        """
        Registra una entrada en el historial de jugadores.
        
        Args:
            guild: Guild de Discord
            server_key: Clave del servidor
            player_count: Número de jugadores actuales
            max_players: Máximo de jugadores
            status: Estado actual del servidor
        """
        async with self.config.guild(guild).player_history() as history:
            if server_key not in history:
                history[server_key] = {"server_key": server_key, "entries": []}
            
            # Crear nueva entrada
            entry = {
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "player_count": player_count,
                "max_players": max_players,
                "status": status.name
            }
            
            history[server_key]["entries"].append(entry)
            
            # Limitar a últimas 1440 entradas (24h con updates cada minuto)
            max_entries = 1440
            if len(history[server_key]["entries"]) > max_entries:
                history[server_key]["entries"] = history[server_key]["entries"][-max_entries:]
    
    async def _get_player_history(
        self,
        guild: discord.Guild,
        server_key: str
    ) -> Optional[PlayerHistory]:
        """
        Obtiene el historial de jugadores de un servidor.
        
        Args:
            guild: Guild de Discord
            server_key: Clave del servidor
            
        Returns:
            PlayerHistory o None si no existe
        """
        history_data = await self.config.guild(guild).player_history()
        
        if server_key not in history_data:
            return None
        
        return PlayerHistory.from_dict(history_data[server_key])
    
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
    
    # ==================== Avisos extra (antiguo MapTrack) ====================

    # Claves por servidor que no forman parte de ServerData y deben conservarse al guardar.
    _EXTRA_SERVER_KEYS = (
        "map_alert_channel", "status_alert_channel",
        "last_map", "current_map", "last_map_change",
    )

    async def _send_alert(self, guild: discord.Guild, channel_id: int, embed: discord.Embed) -> None:
        channel = guild.get_channel_or_thread(channel_id)
        if channel is None:
            return
        perms = channel.permissions_for(guild.me)
        if not (perms.send_messages and perms.embed_links):
            logger.warning(f"Sin permisos para avisos en {channel_id} ({guild.id})")
            return
        try:
            await channel.send(embed=embed)
        except discord.HTTPException as e:
            logger.error(f"Error enviando aviso en {channel_id}: {e!r}")

    async def _process_extra_alerts(
        self,
        guild: discord.Guild,
        server_key: str,
        server_dict: Dict[str, Any],
        server_data: ServerData,
        query_result: QueryResult,
        old_status: Optional[ServerStatus],
        ip_to_show: str,
    ) -> Dict[str, Any]:
        """Cambio de mapa y caidas del servidor. Devuelve las claves extra a guardar."""
        extras = {k: server_dict[k] for k in self._EXTRA_SERVER_KEYS if k in server_dict}
        hostname = query_result.hostname if query_result.success else None
        if hostname == "Unknown Server":
            hostname = None
        name = hostname or server_dict.get("last_hostname") or server_key
        game_name = server_data.game.display_name if server_data.game else ""
        connect_url = None
        if server_data.game and server_data.game.supports_connect_button:
            template = await self.config.guild(guild).connect_url_template()
            connect_url = template.format(ip=ip_to_show) if template else None

        # En Minecraft map_name es la version: no hay cambios de mapa que avisar.
        map_name = (query_result.map_name or "").strip() if query_result.success else ""
        if map_name and map_name != "N/A" and server_data.game != GameType.MINECRAFT:
            previous = extras.get("last_map")
            if previous != map_name:
                extras["last_map_change"] = discord.utils.utcnow().isoformat()
                if previous and extras.get("map_alert_channel"):
                    embed = discord.Embed(
                        title=_("🗺️ Map change"),
                        description=f"**{discord.utils.escape_markdown(name)}**\n{game_name}",
                        color=discord.Color.green(),
                        timestamp=discord.utils.utcnow(),
                    )
                    embed.add_field(name=_("Previous map"), value=previous, inline=True)
                    embed.add_field(name=_("New map"), value=f"**{map_name}**", inline=True)
                    embed.add_field(name=_("Players"), value=query_result.player_display, inline=True)
                    if connect_url:
                        embed.add_field(name=_("Connect"), value=f"[{ip_to_show}]({connect_url})", inline=False)
                    elif server_data.game == GameType.RUST:
                        embed.add_field(name=_("Connect (F1)"), value=f"`client.connect {ip_to_show}`", inline=False)
                    else:
                        embed.add_field(name=_("IP"), value=f"`{ip_to_show}`", inline=False)
                    await self._send_alert(guild, extras["map_alert_channel"], embed)
            extras["last_map"] = map_name
            extras["current_map"] = map_name

        new_status = query_result.status
        channel_id = extras.get("status_alert_channel")
        if channel_id and old_status is not None and old_status != new_status:
            went_down = new_status == ServerStatus.OFFLINE
            came_back = old_status == ServerStatus.OFFLINE and new_status in (ServerStatus.ONLINE, ServerStatus.MAINTENANCE)
            if went_down or came_back:
                embed = discord.Embed(
                    title=_("🔴 Server down") if went_down else _("✅ Server back online"),
                    description=f"**{discord.utils.escape_markdown(name)}**\n{game_name} · `{ip_to_show}`",
                    color=discord.Color.red() if went_down else discord.Color.green(),
                    timestamp=discord.utils.utcnow(),
                )
                if came_back and query_result.success:
                    embed.add_field(name=_("Players"), value=query_result.player_display, inline=True)
                    if map_name and server_data.game != GameType.MINECRAFT:
                        embed.add_field(name=_("Map"), value=map_name, inline=True)
                await self._send_alert(guild, channel_id, embed)
        return extras

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
        # Se llama desde el bucle de monitorizacion: el idioma debe ser el del servidor.
        await set_contextual_locales_from_guild(self.bot, guild)
        async with self.config.guild(guild).servers() as servers:
            server_dict = servers.get(server_key)
            if not server_dict:
                logger.warning(f"Servidor {server_key} no encontrado en {guild.name}.")
                return
            
            # Debug: mostrar message_id actual
            logger.debug(f"Server {server_key} - message_id en config: {server_dict.get('message_id')}")
            
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
            
            # Obtener IP pública (solo para mostrar en embed)
            host = server_data.host
            port = server_data.port
            public_ip = await self._get_public_ip(guild, host)

            # Dirección a mostrar: dominio > IP pública > host, con el puerto de conexión
            ip_to_show = self._format_display_address(server_data, public_ip)
            
            # Realizar query (siempre usa la IP original del servidor)
            query_kwargs = {}
            if server_data.game == GameType.DAYZ:
                query_kwargs["query_port"] = server_data.query_port
                query_target_port = server_data.game_port or port
            else:
                # Juegos Source (Rust, etc.): usar query_port si difiere del de conexión
                query_target_port = server_data.effective_query_port

            query_result = await self.query_service.query_server(
                host=host,
                port=query_target_port,
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
            
            # Registrar en historial de jugadores
            await self._record_player_history(
                guild, server_key, 
                query_result.players, 
                query_result.max_players,
                query_result.status
            )
            
            # Disparar eventos de cambio de estado
            await self._dispatch_status_event(
                guild, server_key, old_status, query_result.status
            )

            # Avisos extra (antiguo MapTrack): cambio de mapa y caidas/vuelta
            extras = await self._process_extra_alerts(
                guild, server_key, server_dict, server_data,
                query_result, old_status, ip_to_show
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
            
            # Obtener o generar server_id para botones
            server_id = server_dict.get("server_id")
            if not server_id:
                server_id = self._generate_server_id()
                server_dict["server_id"] = server_id
            
            # Crear View con botones si está habilitado
            interaction_config = await self.config.guild(guild).interaction_features()
            buttons_enabled = interaction_config.get("buttons_enabled", True)
            
            # Labels traducidos para los botones
            button_labels = {
                "players": _("Players"),
                "stats": _("Stats"),
                "history": _("History")
            }
            show_players_button = server_data.game.supports_player_list if server_data.game else True
            view = create_server_view(
                server_id, labels=button_labels, show_players=show_players_button
            ) if buttons_enabled else None
            
            # Enviar o editar mensaje
            try:
                if first_time or not server_data.message_id:
                    logger.info(f"Creando nuevo mensaje para {server_key} (first_time={first_time}, message_id={server_data.message_id})")
                    msg = await channel.send(embed=embed, view=view)
                    server_data.message_id = msg.id
                else:
                    try:
                        msg = await channel.fetch_message(server_data.message_id)
                        await msg.edit(embed=embed, view=view)
                    except discord.NotFound:
                        # Mensaje eliminado, crear uno nuevo
                        logger.info(f"Mensaje {server_data.message_id} no encontrado para {server_key}, creando nuevo")
                        msg = await channel.send(embed=embed, view=view)
                        server_data.message_id = msg.id
            except discord.Forbidden:
                logger.error(f"Sin permisos para enviar mensaje en {channel.name}")
            except discord.HTTPException as e:
                logger.error(f"Error HTTP al enviar mensaje: {e}")
            
            # Guardar datos actualizados (incluyendo server_id si fue generado)
            server_dict_to_save = server_data.to_dict()
            server_dict_to_save.update(extras)
            server_dict_to_save["server_id"] = server_id
            # Persistir hostname para autocomplete
            if query_result.success and query_result.hostname:
                server_dict_to_save["last_hostname"] = query_result.hostname
            elif "last_hostname" in server_dict:
                server_dict_to_save["last_hostname"] = server_dict["last_hostname"]
            servers[server_key] = server_dict_to_save
    
    # ==================== Tareas ====================
    
    @tasks.loop(seconds=60)
    async def server_monitor(self) -> None:
        """Tarea principal de monitoreo de servidores."""
        # Limpiar caché expirada
        self.query_service.cleanup_cache()
        
        # Limpiar servidores recién actualizados (más de 30 segundos)
        now = datetime.datetime.utcnow()
        expired_keys = [
            key for key, timestamp in self._recently_updated.items()
            if (now - timestamp).total_seconds() > 30
        ]
        for key in expired_keys:
            del self._recently_updated[key]
        
        for guild in self.bot.guilds:
            servers = await self.config.guild(guild).servers()
            for server_key in servers.keys():
                # Saltar si fue actualizado recientemente (evita duplicados)
                update_key = f"{guild.id}:{server_key}"
                if update_key in self._recently_updated:
                    logger.debug(f"Saltando {server_key} - actualizado recientemente")
                    continue
                
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
        Sets the timezone for status updates.
        
        Example: `[p]settimezone Europe/Madrid`
        """
        try:
            pytz.timezone(timezone)
        except pytz.UnknownTimeZoneError:
            await ctx.send(_("❌ Invalid timezone '{}'.").format(timezone))
            return
        
        await self.config.guild(ctx.guild).timezone.set(timezone)
        await ctx.send(_("✅ Timezone set to **{}**").format(timezone))
    
    @commands.command(name="setpublicip")
    @checks.admin_or_permissions(administrator=True)
    async def set_public_ip(self, ctx: commands.Context, ip: Optional[str] = None) -> None:
        """
        Sets the public IP to replace private IPs in embeds.
        
        Use without arguments to disable replacement.
        
        Example: `[p]setpublicip 123.45.67.89`
        """
        if ip is None:
            await self.config.guild(ctx.guild).public_ip.set(None)
            await ctx.send(_("✅ Public IP replacement disabled."))
        else:
            await self.config.guild(ctx.guild).public_ip.set(ip)
            await ctx.send(
                _("✅ Public IP set to **{}**. Private IPs will be replaced.").format(ip)
            )
    
    @commands.command(name="setconnecturl")
    @checks.admin_or_permissions(administrator=True)
    async def set_connect_url(self, ctx: commands.Context, *, url: str) -> None:
        """
        Sets the connection URL template.
        
        Use `{ip}` as placeholder for the server IP:port.
        
        Example: `[p]setconnecturl https://mysite.com/connect?server={ip}`
        """
        if "{ip}" not in url:
            await ctx.send(_("❌ The URL must contain `{ip}` as placeholder."))
            return
        
        await self.config.guild(ctx.guild).connect_url_template.set(url)
        await ctx.send(_("✅ Connection URL set to: {}").format(url))
    
    @commands.command(name="refreshtime")
    @checks.admin_or_permissions(administrator=True)
    async def refresh_time(self, ctx: commands.Context, seconds: int) -> None:
        """
        Sets the refresh interval in seconds.
        
        Minimum: 10 seconds
        
        Example: `[p]refreshtime 120`
        """
        if seconds < 10:
            await ctx.send(_("❌ Time must be at least 10 seconds."))
            return
        
        await self.config.guild(ctx.guild).refresh_time.set(seconds)
        self.server_monitor.change_interval(seconds=seconds)
        await ctx.send(_("✅ Refresh time set to **{}** seconds.").format(seconds))
    
    @commands.command(name="gameservermonitordebug")
    @checks.admin_or_permissions(administrator=True)
    async def toggle_debug(self, ctx: commands.Context, state: bool) -> None:
        """
        Enables or disables debug mode.
        
        Example: `[p]gameservermonitordebug true`
        """
        self.query_service.debug = state
        status = _("enabled") if state else _("disabled")
        await ctx.send(_("✅ Debug mode {}.").format(status))
    
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
        Adds a server to monitor its status.

        **General usage:**
        `[p]addserver <ip[:port]> <game> [#channel] [domain]`

        **Source games with a separate query port (e.g. Rust with +queryport):**
        `[p]addserver <ip:game_port> <game> <game_port> <query_port> [#channel] [domain]`
        The A2S query is sent to `query_port`; players still connect to `game_port`.

        **DayZ usage (separate ports):**
        `[p]addserver <ip> dayz <game_port> <query_port> [#channel] [domain]`

        **Supported games:** cs2, css, gmod, rust, minecraft, dayz, valheim, ark, tf2, l4d2, 7dtd, palworld
        """
        channel = channel or ctx.channel
        game_type = GameType.from_string(game)
        
        if game_type is None:
            supported = ", ".join(GameType.supported_games())
            await ctx.send(
                _("❌ Game '{}' not supported. Available: {}").format(game, supported)
            )
            return
        
        # Verificar permisos del canal
        has_perms, missing = await self._check_channel_permissions(channel)
        if not has_perms:
            await ctx.send(
                _("❌ Missing permissions in {}: {}").format(channel.mention, ", ".join(missing))
            )
            return
        
        # Manejo especial para DayZ
        if game_type == GameType.DAYZ:
            host = server_ip.split(":")[0]
            
            if game_port is None:
                await ctx.send(
                    _("❌ For **DayZ** provide at least `game_port` (e.g. 2302).\nExample: `{}addserver 1.2.3.4 dayz 2302 27016 #channel`").format(ctx.prefix)
                )
                return
            
            if not self._valid_port(game_port):
                await ctx.send(_("❌ Invalid game port (1-65535)."))
                return
            
            if query_port is not None and not self._valid_port(query_port):
                await ctx.send(_("❌ Invalid query port (1-65535)."))
                return
            
            key = f"{host}:{game_port}"
            
            async with self.config.guild(ctx.guild).servers() as servers:
                if key in servers:
                    await ctx.send(_("❌ Server **{}** is already being monitored.").format(key))
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
                    "last_status": None,
                    "server_id": self._generate_server_id()  # Nuevo: ID único para botones
                }
            
            msg = _("✅ Server **{}** (DayZ) added in {}.\nPorts → game: **{}**").format(key, channel.mention, game_port)
            if query_port:
                msg += _(", query: **{}**").format(query_port)
            if domain:
                msg += _("\nDomain: {}").format(domain)
            
            await ctx.send(msg)
            
            # Marcar como recién actualizado para evitar duplicados del loop
            update_key = f"{ctx.guild.id}:{key}"
            self._recently_updated[update_key] = datetime.datetime.utcnow()
            
            await self.update_server_status(ctx.guild, key, first_time=True)
            return
        
        # Resto de juegos
        parsed = self._parse_server_ip(server_ip, game_type)
        if not parsed:
            await ctx.send(
                _("❌ Invalid format. Use 'ip:port' or just 'ip' (default port will be used).")
            )
            return

        ip_part, port_part, server_key = parsed

        # Puerto de query opcional (p.ej. Rust con +queryport distinto del puerto de juego).
        # En estos juegos el primer puerto posicional es el de juego/conexión (ya viene en
        # server_ip), por lo que solo necesitamos validar el query_port para la consulta A2S.
        if query_port is not None and not self._valid_port(query_port):
            await ctx.send(_("❌ Invalid query port (1-65535)."))
            return
        if game_port is not None and not self._valid_port(game_port):
            await ctx.send(_("❌ Invalid game port (1-65535)."))
            return

        async with self.config.guild(ctx.guild).servers() as servers:
            if server_key in servers:
                await ctx.send(
                    _("❌ Server **{}** is already being monitored.").format(server_key)
                )
                return

            servers[server_key] = {
                "game": game_type.value,
                "channel_id": channel.id,
                "message_id": None,
                "domain": domain,
                "game_port": game_port,
                "query_port": query_port,
                "total_queries": 0,
                "successful_queries": 0,
                "last_online": None,
                "last_offline": None,
                "last_status": None,
                "server_id": self._generate_server_id()  # Nuevo: ID único para botones
            }

        msg = _("✅ Server **{}** ({}) added in {}.").format(
            server_key, game_type.display_name, channel.mention
        )
        if query_port:
            msg += _("\nQuery port: **{}**").format(query_port)
        if domain:
            msg += _("\nDomain: {}").format(domain)
        
        await ctx.send(msg)
        
        # Marcar como recién actualizado para evitar duplicados del loop
        update_key = f"{ctx.guild.id}:{server_key}"
        self._recently_updated[update_key] = datetime.datetime.utcnow()
        
        await self.update_server_status(ctx.guild, server_key, first_time=True)
    
    @commands.command(name="removeserver")
    @checks.admin_or_permissions(administrator=True)
    async def remove_server(self, ctx: commands.Context, server_key: str) -> None:
        """
        Removes a server from monitoring.
        
        Accepts `ip:port` or the short server_id.
        
        Example: `[p]removeserver 192.168.1.1:27015`
        """
        # Intentar resolver server_id -> server_key real
        resolved = await self._resolve_server_key_by_id(ctx.guild, server_key)
        if resolved:
            server_key = resolved
        elif ":" not in server_key:
            await ctx.send(_("❌ Format: `ip:port` or `server_id`"))
            return
        
        servers = await self.config.guild(ctx.guild).servers()
        if server_key not in servers:
            await ctx.send(_("❌ Server with key **{}** not found.").format(server_key))
            return

        await self._delete_server_message(
            servers[server_key].get("channel_id"),
            servers[server_key].get("message_id")
        )
        await self._forget_servers(ctx.guild, [server_key])
        await ctx.send(_("✅ Server **{}** removed from monitoring.").format(server_key))

    @commands.command(name="deadservers", aliases=["serversmuertos"])
    @checks.admin_or_permissions(administrator=True)
    async def dead_servers(
        self,
        ctx: commands.Context,
        days: Optional[int] = None
    ) -> None:
        """
        Lists servers that stopped responding, without removing anything.

        A server is listed when its channel was deleted, when it never
        responded since it was added, or when its last successful query is
        older than `days` days (default: 7).

        Example: `[p]deadservers 14`
        """
        days = days if days is not None else DEAD_SERVER_DEFAULT_DAYS
        if days < 1:
            await ctx.send(_("❌ Days must be at least 1."))
            return

        candidates = await self._find_dead_servers(ctx.guild, days)
        if not candidates:
            await ctx.send(
                _("✅ No server has been unresponsive for more than **{days}** day(s).").format(days=days)
            )
            return

        embed = self._build_dead_servers_embed(
            candidates,
            days,
            title=_("💀 Unresponsive servers"),
            color=discord.Color.orange()
        )
        embed.add_field(
            name="​",
            value=_("Use `{prefix}purgeservers {days}` to remove them.").format(
                prefix=ctx.clean_prefix, days=days
            ),
            inline=False
        )
        await ctx.send(embed=embed)

    @commands.command(name="purgeservers", aliases=["purgedeadservers", "limpiarservers"])
    @checks.admin_or_permissions(administrator=True)
    async def purge_servers(
        self,
        ctx: commands.Context,
        days: Optional[int] = None
    ) -> None:
        """
        Removes servers that stopped responding, after confirmation.

        Stops the monitor from querying servers that no longer exist, which is
        what floods the logs with timeouts. Deletes their status embed and their
        player history too.

        Use `[p]deadservers` first for a dry run.

        Example: `[p]purgeservers 14`
        """
        days = days if days is not None else DEAD_SERVER_DEFAULT_DAYS
        if days < 1:
            await ctx.send(_("❌ Days must be at least 1."))
            return

        candidates = await self._find_dead_servers(ctx.guild, days)
        if not candidates:
            await ctx.send(
                _("✅ No server has been unresponsive for more than **{days}** day(s).").format(days=days)
            )
            return

        embed = self._build_dead_servers_embed(
            candidates,
            days,
            title=_("🧹 Purge dead servers"),
            color=discord.Color.red()
        )
        embed.add_field(
            name="​",
            value=_(
                "⚠️ They will be removed from monitoring along with their status embed and their player history. This action cannot be undone."
            ),
            inline=False
        )

        view = ConfirmView(ctx.author, disable_buttons=True)
        view.confirm_button.style = discord.ButtonStyle.red
        view.confirm_button.label = _("Purge {count}").format(count=len(candidates))
        view.dismiss_button.label = _("Cancel")
        view.message = await ctx.send(embed=embed, view=view)
        await view.wait()

        if not view.result:
            await ctx.send(_("❌ Purge cancelled. Nothing was removed."))
            return

        # Volver a calcular: el estado pudo cambiar mientras se confirmaba.
        candidates = await self._find_dead_servers(ctx.guild, days)
        if not candidates:
            await ctx.send(_("✅ The servers responded again. Nothing was removed."))
            return

        async with ctx.typing():
            for candidate in candidates:
                await self._delete_server_message(
                    candidate["channel_id"], candidate["message_id"]
                )
            server_keys = [candidate["server_key"] for candidate in candidates]
            await self._forget_servers(ctx.guild, server_keys)

        logger.info(
            "Purgados %d servidores muertos en %s (%s): %s",
            len(server_keys), ctx.guild.name, ctx.guild.id, ", ".join(server_keys)
        )
        await ctx.send(
            _("✅ **{count}** server(s) removed from monitoring.").format(
                count=len(server_keys)
            )
        )

    @commands.command(name="forcestatus", aliases=["forzarstatus"])
    async def force_status(self, ctx: commands.Context) -> None:
        """Forces a status update in the current channel."""
        servers = await self.config.guild(ctx.guild).servers()
        updated = False
        
        for server_key, data in servers.items():
            if data.get("channel_id") == ctx.channel.id:
                # Limpiar caché para este servidor (usar el puerto real de query)
                game = GameType.from_string(data.get("game", ""))
                if game:
                    server_data = ServerData.from_dict(server_key, data)
                    if game == GameType.DAYZ:
                        cache_port = server_data.game_port or server_data.port
                    else:
                        cache_port = server_data.effective_query_port
                    self.query_service._cache.invalidate(
                        server_data.host, int(cache_port), game
                    )
                
                await self.update_server_status(ctx.guild, server_key, first_time=False)
                updated = True
        
        if updated:
            await ctx.send(_("✅ Force update completed."))
        else:
            await ctx.send(_("❌ No servers monitored in this channel."))
    
    @commands.command(name="gsmversion")
    async def gsm_version(self, ctx: commands.Context) -> None:
        """Shows the current GameServerMonitor cog version."""
        await ctx.send(_("🎮 **GameServerMonitor** v{version} by {author}").format(
            version=self.__version__, 
            author=self.__author__
        ))
    
    # ==================== Avisos extra (antiguo MapTrack) ====================

    async def _alert_target(self, ctx: commands.Context, server: str) -> Optional[str]:
        key = await self._resolve_server_key_by_id(ctx.guild, server) or await self._resolve_server_key(ctx.guild, server)
        if not key:
            await ctx.send(_("❌ Server **{}** not found. Use `ip:port` or the server_id (`{}listservers`).").format(server, ctx.clean_prefix))
        return key

    async def _set_alert_channel(self, ctx, server: str, key_name: str, channel, label: str) -> None:
        server_key = await self._alert_target(ctx, server)
        if not server_key:
            return
        if channel is not None:
            perms = channel.permissions_for(ctx.guild.me)
            if not (perms.send_messages and perms.embed_links):
                await ctx.send(_("❌ I need *Send Messages* and *Embed Links* in {}.").format(channel.mention))
                return
        async with self.config.guild(ctx.guild).servers() as servers:
            if server_key not in servers:
                await ctx.send(_("❌ Server not found."))
                return
            servers[server_key][key_name] = channel.id if channel else None
        if channel:
            await ctx.send(_("✅ {} alerts for **{}** in {}.").format(label, server_key, channel.mention))
        else:
            await ctx.send(_("✅ {} alerts for **{}** disabled.").format(label, server_key))

    @commands.group(name="gsmalerts", aliases=["gsmavisos"])
    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    async def gsm_alerts(self, ctx: commands.Context) -> None:
        """Extra per-server alerts: map changes and outages (replaces MapTrack)."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @gsm_alerts.command(name="map")
    async def gsm_alerts_map(
        self, ctx: commands.Context, server: str,
        channel: Optional[typing.Union[discord.TextChannel, discord.Thread]] = None
    ) -> None:
        """Alert in a channel when the server changes map. Without a channel it is disabled.

                Example: `[p]gsmalerts map 1.2.3.4:28015 #map-changes`

        """
        await self._set_alert_channel(ctx, server, "map_alert_channel", channel, _("map change"))

    @gsm_alerts.command(name="status")
    async def gsm_alerts_status(
        self, ctx: commands.Context, server: str,
        channel: Optional[typing.Union[discord.TextChannel, discord.Thread]] = None
    ) -> None:
        """Alert in a channel when the server goes down or comes back. Without a channel it is disabled.

                Example: `[p]gsmalerts status 1.2.3.4:28015 #server-status`

        """
        await self._set_alert_channel(ctx, server, "status_alert_channel", channel, _("outage"))

    @gsm_alerts.command(name="list")
    async def gsm_alerts_list(self, ctx: commands.Context) -> None:
        """Show the configured alerts and the current map of each server."""
        servers = await self.config.guild(ctx.guild).servers()
        lines = []
        for server_key, data in servers.items():
            map_ch = data.get("map_alert_channel")
            st_ch = data.get("status_alert_channel")
            current = data.get("current_map") or "-"
            name = data.get("last_hostname") or server_key
            parts = [f"🗺️ {current}"]
            if map_ch:
                parts.append(_("map → <#{}>").format(map_ch))
            if st_ch:
                parts.append(_("outages → <#{}>").format(st_ch))
            lines.append(f"**{discord.utils.escape_markdown(name)}** (`{server_key}`)\n" + " · ".join(parts))
        if not lines:
            await ctx.send(_("📋 No servers being monitored."))
            return
        for page in pagify("\n\n".join(lines), delims=["\n\n"], page_length=3900):
            await ctx.send(embed=discord.Embed(title=_("🔔 Server alerts"), description=page, color=discord.Color.blue()))

    @gsm_alerts.command(name="importmaptrack")
    async def gsm_alerts_import_maptrack(self, ctx: commands.Context) -> None:
        """Import the map alerts configured in the MapTrack cog.

                Each MapTrack server is looked up among the GameServerMonitor ones (by ip:port
                or by the configured public IP). Servers that are not monitored are listed
                so you can add them with `addserver`.

        """
        mt_config = Config.get_conf(None, identifier=1234567890, cog_name="MapTrack")
        mt_config.register_guild(map_track_channels={})
        tracks = await mt_config.guild(ctx.guild).map_track_channels()
        if not tracks:
            await ctx.send(_("MapTrack has no servers configured in this server."))
            return
        servers = await self.config.guild(ctx.guild).servers()
        imported, missing = [], []
        for ip, channel_id in tracks.items():
            key = ip if ip in servers else await self._resolve_server_key(ctx.guild, ip)
            if key is None:
                # MapTrack guardaba a veces la IP interna con otro puerto de query.
                host, _sep, port = ip.rpartition(":")
                key = next((k for k, d in servers.items() if str(d.get("query_port")) == port and k.split(":")[0] == host), None)
            if key is None:
                missing.append(ip)
                continue
            imported.append((key, channel_id))
        if imported:
            async with self.config.guild(ctx.guild).servers() as current:
                for key, channel_id in imported:
                    if key in current:
                        current[key]["map_alert_channel"] = channel_id
        msg = _("✅ {} server(s) imported from MapTrack.").format(len(imported))
        if missing:
            msg += "\n" + _("⚠️ Not monitored by GameServerMonitor (add them with `{}addserver` and try again): {}").format(
                ctx.clean_prefix, ", ".join(f"`{m}`" for m in missing)
            )
        else:
            msg += "\n" + _("You can now unload MapTrack: `{}unload maptrack`.").format(ctx.clean_prefix)
        await ctx.send(msg)

    @commands.command(name="listservers", aliases=["listaserver"])
    async def list_servers(self, ctx: commands.Context) -> None:
        """Lists all monitored servers."""
        servers = await self.config.guild(ctx.guild).servers()
        
        if not servers:
            await ctx.send(_("📋 No servers being monitored."))
            return
        
        embed = discord.Embed(
            title=_("📋 Monitored Servers"),
            color=discord.Color.blue()
        )
        
        for server_key, data in servers.items():
            game_type = GameType.from_string(data.get("game", ""))
            game_name = game_type.display_name if game_type else data.get("game", "N/A").upper()
            
            channel = self.bot.get_channel(data.get("channel_id"))
            channel_mention = channel.mention if channel else _("Unknown")
            
            value = f"**{_('Game')}:** {game_name}\n**{_('Channel')}:** {channel_mention}"
            
            if data.get("game", "").lower() == "dayz":
                value += f"\n**{_('Ports')}:** game:{data.get('game_port')} | query:{data.get('query_port')}"
            
            if data.get("domain"):
                value += f"\n**{_('Domain')}:** {data.get('domain')}"
            
            # Estadísticas básicas
            uptime = 0
            if data.get("total_queries", 0) > 0:
                uptime = (data.get("successful_queries", 0) / data.get("total_queries", 1)) * 100
            value += f"\n**{_('Uptime')}:** {uptime:.1f}%"
            
            embed.add_field(name=f"📡 {server_key}", value=value, inline=False)
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name="serverstats")
    @app_commands.describe(
        server="Server to query (IP:port or select from the list)"
    )
    @app_commands.autocomplete(server=_server_autocomplete)
    async def server_stats(
        self, 
        ctx: commands.Context, 
        server: str
    ) -> None:
        """
        Shows detailed server statistics.
        
        You can use the real IP, public IP, or server_id.
        
        **Example:** `[p]serverstats 192.168.1.1:27015`
        """
        # Determinar si es server_id o IP:puerto
        resolved_key = await self._resolve_server_key_by_id(ctx.guild, server)
        if not resolved_key:
            resolved_key = await self._resolve_server_key(ctx.guild, server)
        
        if not resolved_key:
            await ctx.send(_("❌ Server **{}** not found.").format(server), ephemeral=True)
            return
        
        # Defer ephemeral para slash, typing para prefijo
        if ctx.interaction:
            await ctx.defer(ephemeral=True)
        else:
            await ctx.typing()
        
        payload = await self._build_stats_payload(ctx.guild, resolved_key)
        
        if "error" in payload:
            await ctx.send(f"❌ {payload['error']}", ephemeral=True)
            return
        
        # Determinar si borrar después (solo para prefijo)
        interaction_config = await self.config.guild(ctx.guild).interaction_features()
        delete_after = None
        
        if ctx.interaction is None:  # Es comando de prefijo
            delete_seconds = interaction_config.get("delete_after_prefix_seconds")
            if delete_seconds:
                delete_after = delete_seconds
        
        await ctx.send(
            embed=payload.get("embed"),
            ephemeral=ctx.interaction is not None,
            delete_after=delete_after
        )
    
    @commands.hybrid_command(name="gsmhistory")
    @app_commands.describe(
        server="Server to query (IP:port or select from the list)",
        hours="Hours of history to show (default: 24, max: 168)"
    )
    @app_commands.autocomplete(server=_server_autocomplete)
    async def gsm_history(
        self, 
        ctx: commands.Context, 
        server: str, 
        hours: typing.Optional[int] = 24
    ) -> None:
        """
        Shows the player history of a server with an ASCII graph.
        
        **Examples:**
        `[p]gsmhistory 192.168.1.1:27015` - Last 24 hours
        `[p]gsmhistory 192.168.1.1:27015 12` - Last 12 hours
        """
        # Determinar si es server_id o IP:puerto
        resolved_key = await self._resolve_server_key_by_id(ctx.guild, server)
        if not resolved_key:
            resolved_key = await self._resolve_server_key(ctx.guild, server)
        
        if not resolved_key:
            await ctx.send(_("❌ Server **{}** not found.").format(server), ephemeral=True)
            return
        
        # Defer ephemeral para slash, typing para prefijo
        if ctx.interaction:
            await ctx.defer(ephemeral=True)
        else:
            await ctx.typing()
        
        payload = await self._build_history_payload(ctx.guild, resolved_key, hours or 24)
        
        if "error" in payload:
            await ctx.send(f"❌ {payload['error']}", ephemeral=True)
            return
        
        # Determinar si borrar después (solo para prefijo)
        interaction_config = await self.config.guild(ctx.guild).interaction_features()
        delete_after = None
        
        if ctx.interaction is None:  # Es comando de prefijo
            delete_seconds = interaction_config.get("delete_after_prefix_seconds")
            if delete_seconds:
                delete_after = delete_seconds
        
        await ctx.send(
            embed=payload.get("embed"),
            ephemeral=ctx.interaction is not None,
            delete_after=delete_after
        )
    
    @commands.hybrid_command(name="gsmplayers")
    @app_commands.describe(
        server="Server to query (IP:port or select from the list)"
    )
    @app_commands.autocomplete(server=_server_autocomplete)
    async def gsm_players(
        self, 
        ctx: commands.Context, 
        server: str
    ) -> None:
        """
        Shows the list of players connected to a server.
        
        Displays name, score and connection time.
        
        **Example:** `[p]gsmplayers 192.168.1.1:27015`
        """
        # Determinar si es server_id o IP:puerto
        resolved_key = await self._resolve_server_key_by_id(ctx.guild, server)
        if not resolved_key:
            resolved_key = await self._resolve_server_key(ctx.guild, server)
        
        if not resolved_key:
            await ctx.send(_("❌ Server **{}** not found.").format(server), ephemeral=True)
            return
        
        # Defer ephemeral para slash, typing para prefijo
        if ctx.interaction:
            await ctx.defer(ephemeral=True)
        else:
            await ctx.typing()
        
        payload = await self._build_players_payload(ctx.guild, resolved_key)
        
        if "error" in payload:
            await ctx.send(f"❌ {payload['error']}", ephemeral=True)
            return
        
        # Determinar si borrar después (solo para prefijo)
        interaction_config = await self.config.guild(ctx.guild).interaction_features()
        delete_after = None
        
        if ctx.interaction is None:  # Es comando de prefijo
            delete_seconds = interaction_config.get("delete_after_prefix_seconds")
            if delete_seconds:
                delete_after = delete_seconds
        
        await ctx.send(
            embed=payload.get("embed"),
            ephemeral=ctx.interaction is not None,
            delete_after=delete_after
        )
    
    @commands.hybrid_command(name="gsmmap")
    @app_commands.describe(
        server="Server to query (IP:port or select from the list)"
    )
    @app_commands.autocomplete(server=_server_autocomplete)
    async def gsm_map(
        self, 
        ctx: commands.Context, 
        server: str
    ) -> None:
        """
        Shows the current map of a server.
        
        For Minecraft servers, shows the version instead.
        
        **Example:** `[p]gsmmap 192.168.1.1:27015`
        """
        # Determinar si es server_id o IP:puerto
        resolved_key = await self._resolve_server_key_by_id(ctx.guild, server)
        if not resolved_key:
            resolved_key = await self._resolve_server_key(ctx.guild, server)
        
        if not resolved_key:
            await ctx.send(_("❌ Server **{}** not found.").format(server), ephemeral=True)
            return
        
        # Defer ephemeral para slash, typing para prefijo
        if ctx.interaction:
            await ctx.defer(ephemeral=True)
        else:
            await ctx.typing()
        
        payload = await self._build_map_payload(ctx.guild, resolved_key)
        
        if "error" in payload:
            await ctx.send(f"❌ {payload['error']}", ephemeral=True)
            return
        
        # Determinar si borrar después (solo para prefijo)
        interaction_config = await self.config.guild(ctx.guild).interaction_features()
        delete_after = None
        
        if ctx.interaction is None:  # Es comando de prefijo
            delete_seconds = interaction_config.get("delete_after_prefix_seconds")
            if delete_seconds:
                delete_after = delete_seconds
        
        await ctx.send(
            embed=payload.get("embed"),
            ephemeral=ctx.interaction is not None,
            delete_after=delete_after
        )
