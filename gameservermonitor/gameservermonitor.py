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
from redbot.core.i18n import Translator, cog_i18n
import datetime
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

# Internacionalización
_ = Translator("GameServerMonitor", __file__)


@cog_i18n(_)
class GameServerMonitor(DashboardIntegration, commands.Cog):
    """Monitoriza servidores de juegos y actualiza su estado en Discord. By Killerbite95"""
    
    __author__ = "Killerbite95"
    __version__ = "2.3.0"
    
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
    
    async def cog_load(self) -> None:
        """Se ejecuta cuando el cog se carga."""
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
        Resetea los contadores de queries de todos los servidores.
        Se ejecuta en cada carga del cog para evitar acumulación infinita.
        """
        for guild in self.bot.guilds:
            async with self.config.guild(guild).servers() as servers:
                for server_key, server_data in servers.items():
                    server_data["total_queries"] = 0
                    server_data["successful_queries"] = 0
        logger.info("Contadores de queries reseteados")
    
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
                    if server_port == search_port and (
                        server_ip.startswith("10.") or
                        server_ip.startswith("192.168.") or
                        server_ip.startswith("172.16.") or
                        server_ip.startswith("172.17.") or
                        server_ip.startswith("172.18.") or
                        server_ip.startswith("172.19.") or
                        server_ip.startswith("172.2") or
                        server_ip.startswith("172.30.") or
                        server_ip.startswith("172.31.")
                    ):
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
            port = server_data.port
        
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
        
        # Obtener nombre para mostrar con fallback
        display_name = query_result.hostname
        if not display_name or display_name == "Unknown Server":
            public_ip = await self.config.guild(guild).public_ip()
            if public_ip:
                display_name = f"{public_ip}:{port}"
            elif server_data.domain:
                display_name = server_data.domain
            else:
                display_name = game_name
        
        # Crear embed
        embed = discord.Embed(
            title=_("Players - {hostname}").format(hostname=display_name[:50]),
            description=f"**{_('Game')}:** {game_name}\n"
                       f"**{_('Map')}:** {query_result.map_name}\n"
                       f"**{_('Players')}:** {query_result.players}/{query_result.max_players}",
            color=query_result.status.color
        )
        
        if server_data.game and server_data.game.thumbnail_url:
            embed.set_thumbnail(url=server_data.game.thumbnail_url)
        
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
            port = server_data.port
        
        query_result = await self.query_service.query_server(
            host=server_data.host,
            port=port,
            game=server_data.game,
            use_cache=False,
            **query_kwargs
        )
        
        # Obtener nombre para mostrar con fallback
        display_name = query_result.hostname
        if not display_name or display_name == "Unknown Server":
            public_ip = await self.config.guild(guild).public_ip()
            if public_ip:
                display_name = f"{public_ip}:{port}"
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
            port = server_data.port
        
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
                display_name = f"{public_ip}:{port}"
            else:
                display_name = server_data.domain or game_name
        
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
            port = server_data.port
        
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
        
        # Obtener nombre para mostrar con fallback
        display_name = query_result.hostname
        if not display_name or display_name == "Unknown Server":
            public_ip = await self.config.guild(guild).public_ip()
            if public_ip:
                display_name = f"{public_ip}:{port}"
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
            
            # Obtener nombre para mostrar (hostname > IP pública > dominio > juego)
            # Intentar obtener hostname de caché
            server_obj = ServerData.from_dict(server_key, server_data)
            port = server_obj.port
            
            # Intentar obtener hostname desde caché
            display_id = None
            cache_key = f"{server_obj.game.value if server_obj.game else 'unknown'}:{server_obj.host}:{port}"
            if hasattr(self, 'query_service') and hasattr(self.query_service, '_cache'):
                cached = self.query_service._cache.get(server_obj.host, port, server_obj.game)
                if cached and cached.hostname:
                    display_id = cached.hostname[:40]
            
            # Si no hay hostname en caché, usar IP pública o dominio
            if not display_id:
                if public_ip:
                    display_id = f"{public_ip}:{port}"
                elif server_obj.domain:
                    display_id = server_obj.domain
                else:
                    display_id = game_name
            
            # Crear nombre amigable para mostrar
            display_name = f"{display_id} ({game_name})"
            
            # Filtrar por texto actual (buscar en display_name y game_name)
            if current_lower in display_name.lower() or current_lower in game_name.lower():
                server_id = server_data.get("server_id", server_key)
                choices.append(
                    app_commands.Choice(name=display_name[:100], value=server_id)
                )
        
        return choices[:25]  # Discord limita a 25 opciones
    
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
            name=f"{status_emoji} {_('Status')}",
            value=status_name,
            inline=True
        )
        
        # Juego
        game_name = server_data.game.display_name if server_data.game else _("Unknown")
        embed.add_field(name=f"🎮 {_('Game')}", value=game_name, inline=True)
        
        # Botón de conexión (no para Minecraft)
        if embed_config.show_connect_button and server_data.game != GameType.MINECRAFT:
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
        title = self._truncate_title(f"{game_name} Server", " - ❌ Offline")
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
        
        # Botón de conexión (no para Minecraft)
        if embed_config.show_connect_button and server_data.game != GameType.MINECRAFT:
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
            
            if server_data.game == GameType.DAYZ:
                game_port = server_data.game_port or port
                ip_to_show = f"{public_ip}:{game_port}"
            else:
                ip_to_show = f"{public_ip}:{port}"
            
            # Realizar query (siempre usa la IP original del servidor)
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
            view = create_server_view(server_id, labels=button_labels) if buttons_enabled else None
            
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
            server_dict_to_save["server_id"] = server_id
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
            await ctx.send(_("❌ La zona horaria '{}' no es válida.").format(timezone))
            return
        
        await self.config.guild(ctx.guild).timezone.set(timezone)
        await ctx.send(_("✅ Zona horaria establecida en **{}**").format(timezone))
    
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
        Sets the connection URL template.
        
        Use `{ip}` as placeholder for the server IP:port.
        
        Example: `[p]setconnecturl https://mysite.com/connect?server={ip}`
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
        Sets the refresh interval in seconds.
        
        Minimum: 10 seconds
        
        Example: `[p]refreshtime 120`
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
        Enables or disables debug mode.
        
        Example: `[p]gameservermonitordebug true`
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
        Adds a server to monitor its status.

        **General usage:**
        `[p]addserver <ip[:port]> <game> [#channel] [domain]`

        **DayZ usage (separate ports):**
        `[p]addserver <ip> dayz <game_port> <query_port> [#channel] [domain]`

        **Supported games:** cs2, css, gmod, rust, minecraft, dayz
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
                    "last_status": None,
                    "server_id": self._generate_server_id()  # Nuevo: ID único para botones
                }
            
            msg = _("✅ Servidor **{}** (DayZ) añadido en {}.\n"
                   "Puertos → juego: **{}**").format(key, channel.mention, game_port)
            if query_port:
                msg += _(", query: **{}**").format(query_port)
            if domain:
                msg += _("\nDominio: {}").format(domain)
            
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
                "last_status": None,
                "server_id": self._generate_server_id()  # Nuevo: ID único para botones
            }
        
        msg = _("✅ Servidor **{}** ({}) añadido en {}.").format(
            server_key, game_type.display_name, channel.mention
        )
        if domain:
            msg += _("\nDominio: {}").format(domain)
        
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
        
        Pass exactly the listed key (e.g. `ip:port`).
        
        Example: `[p]removeserver 192.168.1.1:27015`
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
        """Forces a status update in the current channel."""
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
    
    @commands.command(name="gsmversion")
    async def gsm_version(self, ctx: commands.Context) -> None:
        """Shows the current GameServerMonitor cog version."""
        await ctx.send(_("🎮 **GameServerMonitor** v{version} by {author}").format(
            version=self.__version__, 
            author=self.__author__
        ))
    
    @commands.command(name="listaserver")
    async def list_servers(self, ctx: commands.Context) -> None:
        """Lists all monitored servers."""
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
            await ctx.send(_("❌ Servidor **{}** no encontrado.").format(server), ephemeral=True)
            return
        
        # Usar payload builder
        async with ctx.typing():
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
            ephemeral=ctx.interaction is not None,  # Ephemeral solo en slash
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
            await ctx.send(_("❌ Servidor **{}** no encontrado.").format(server), ephemeral=True)
            return
        
        # Usar payload builder
        async with ctx.typing():
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
            await ctx.send(_("❌ Servidor **{}** no encontrado.").format(server), ephemeral=True)
            return
        
        # Usar payload builder
        async with ctx.typing():
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
            await ctx.send(_("❌ Servidor **{}** no encontrado.").format(server), ephemeral=True)
            return
        
        # Usar payload builder
        async with ctx.typing():
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
