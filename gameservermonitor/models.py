"""
Modelos de datos para GameServerMonitor.
Incluye Enums, dataclasses y estructuras de datos.
By Killerbite95
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
import discord
from redbot.core.i18n import Translator

# Internacionalización
_ = Translator("GameServerMonitor", __file__)


class ServerStatus(Enum):
    """Estados posibles de un servidor."""
    ONLINE = auto()
    OFFLINE = auto()
    MAINTENANCE = auto()  # Online pero con contraseña
    UNKNOWN = auto()
    
    @property
    def emoji(self) -> str:
        """Retorna el emoji correspondiente al estado."""
        emojis = {
            ServerStatus.ONLINE: "✅",
            ServerStatus.OFFLINE: "🔴",
            ServerStatus.MAINTENANCE: "🔐",
            ServerStatus.UNKNOWN: "❓"
        }
        return emojis.get(self, "❓")
    
    @property
    def color(self) -> discord.Color:
        """Retorna el color correspondiente al estado."""
        colors = {
            ServerStatus.ONLINE: discord.Color.green(),
            ServerStatus.OFFLINE: discord.Color.red(),
            ServerStatus.MAINTENANCE: discord.Color.orange(),
            ServerStatus.UNKNOWN: discord.Color.greyple()
        }
        return colors.get(self, discord.Color.greyple())
    
    @property
    def display_name(self) -> str:
        """Retorna el nombre para mostrar del estado."""
        names = {
            ServerStatus.ONLINE: "Online",
            ServerStatus.OFFLINE: "Offline",
            ServerStatus.MAINTENANCE: "Maintenance",
            ServerStatus.UNKNOWN: "Unknown"
        }
        return names.get(self, "Unknown")


class GameType(Enum):
    """Tipos de juegos soportados."""
    CS2 = "cs2"
    CSS = "css"
    GMOD = "gmod"
    RUST = "rust"
    MINECRAFT = "minecraft"
    DAYZ = "dayz"
    
    @property
    def display_name(self) -> str:
        """Retorna el nombre completo del juego."""
        names = {
            GameType.CS2: "Counter-Strike 2",
            GameType.CSS: "Counter-Strike: Source",
            GameType.GMOD: "Garry's Mod",
            GameType.RUST: "Rust",
            GameType.MINECRAFT: "Minecraft",
            GameType.DAYZ: "DayZ Standalone"
        }
        return names.get(self, self.value.upper())
    
    @property
    def default_port(self) -> int:
        """Retorna el puerto por defecto del juego."""
        ports = {
            GameType.CS2: 27015,
            GameType.CSS: 27015,
            GameType.GMOD: 27015,
            GameType.RUST: 28015,
            GameType.MINECRAFT: 25565,
            GameType.DAYZ: 2302
        }
        return ports.get(self, 27015)
    
    @property
    def protocol(self) -> str:
        """Retorna el tipo de protocolo usado."""
        if self == GameType.MINECRAFT:
            return "minecraft"
        return "source"
    
    @property
    def thumbnail_url(self) -> Optional[str]:
        """Retorna la URL del thumbnail del juego."""
        thumbnails = {
            GameType.CS2: "https://cdn.cloudflare.steamstatic.com/steam/apps/730/header.jpg",
            GameType.CSS: "https://cdn.cloudflare.steamstatic.com/steam/apps/240/header.jpg",
            GameType.GMOD: "https://cdn.cloudflare.steamstatic.com/steam/apps/4000/header.jpg",
            GameType.RUST: "https://cdn.cloudflare.steamstatic.com/steam/apps/252490/header.jpg",
            GameType.MINECRAFT: "https://www.minecraft.net/content/dam/games/minecraft/key-art/Games_Subnav_Minecraft-702x304.jpg",
            GameType.DAYZ: "https://cdn.cloudflare.steamstatic.com/steam/apps/221100/header.jpg"
        }
        return thumbnails.get(self)
    
    @classmethod
    def from_string(cls, game_str: str) -> Optional["GameType"]:
        """Convierte un string al GameType correspondiente."""
        game_str = game_str.lower().strip()
        for game in cls:
            if game.value == game_str:
                return game
        return None
    
    @classmethod
    def supported_games(cls) -> List[str]:
        """Retorna lista de juegos soportados."""
        return [game.value for game in cls]


@dataclass
class QueryResult:
    """Resultado de una query a un servidor de juegos."""
    success: bool
    status: ServerStatus
    players: int = 0
    max_players: int = 0
    map_name: str = "N/A"
    hostname: str = "Unknown Server"
    is_passworded: bool = False
    version: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    query_time: datetime = field(default_factory=datetime.utcnow)
    latency_ms: Optional[float] = None
    player_list: List[Dict[str, Any]] = field(default_factory=list)  # Lista de jugadores con detalles
    
    @property
    def player_percentage(self) -> int:
        """Calcula el porcentaje de jugadores."""
        if self.max_players <= 0:
            return 0
        return int(self.players / self.max_players * 100)
    
    @property
    def player_display(self) -> str:
        """Retorna string formateado de jugadores."""
        return f"{self.players}/{self.max_players} ({self.player_percentage}%)"


@dataclass
class ServerData:
    """Datos de configuración de un servidor."""
    server_key: str
    game: GameType
    channel_id: int
    message_id: Optional[int] = None
    domain: Optional[str] = None
    game_port: Optional[int] = None
    query_port: Optional[int] = None
    
    # Estadísticas
    total_queries: int = 0
    successful_queries: int = 0
    last_online: Optional[datetime] = None
    last_offline: Optional[datetime] = None
    last_status: Optional[ServerStatus] = None
    
    @property
    def host(self) -> str:
        """Extrae el host del server_key."""
        return self.server_key.split(":")[0]
    
    @property
    def port(self) -> int:
        """Extrae el puerto del server_key."""
        parts = self.server_key.split(":")
        if len(parts) > 1:
            return int(parts[1])
        return self.game.default_port if self.game else 27015
    
    @property
    def uptime_percentage(self) -> float:
        """Calcula el porcentaje de uptime basado en queries exitosas."""
        if self.total_queries == 0:
            return 0.0
        return (self.successful_queries / self.total_queries) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario para almacenamiento en Config."""
        data = {
            "game": self.game.value if self.game else None,
            "channel_id": self.channel_id,
            "message_id": self.message_id,
            "domain": self.domain,
            "total_queries": self.total_queries,
            "successful_queries": self.successful_queries,
            "last_online": self.last_online.isoformat() if self.last_online else None,
            "last_offline": self.last_offline.isoformat() if self.last_offline else None,
            "last_status": self.last_status.name if self.last_status else None
        }
        # Campos específicos de DayZ
        if self.game == GameType.DAYZ:
            data["game_port"] = self.game_port
            data["query_port"] = self.query_port
        return data
    
    @classmethod
    def from_dict(cls, server_key: str, data: Dict[str, Any]) -> "ServerData":
        """Crea una instancia desde un diccionario de Config."""
        game_str = data.get("game", "")
        game = GameType.from_string(game_str) if game_str else None
        
        last_online = None
        if data.get("last_online"):
            try:
                last_online = datetime.fromisoformat(data["last_online"])
            except (ValueError, TypeError):
                pass
        
        last_offline = None
        if data.get("last_offline"):
            try:
                last_offline = datetime.fromisoformat(data["last_offline"])
            except (ValueError, TypeError):
                pass
        
        last_status = None
        if data.get("last_status"):
            try:
                last_status = ServerStatus[data["last_status"]]
            except (KeyError, TypeError):
                pass
        
        return cls(
            server_key=server_key,
            game=game,
            channel_id=data.get("channel_id", 0),
            message_id=data.get("message_id"),
            domain=data.get("domain"),
            game_port=data.get("game_port"),
            query_port=data.get("query_port"),
            total_queries=data.get("total_queries", 0),
            successful_queries=data.get("successful_queries", 0),
            last_online=last_online,
            last_offline=last_offline,
            last_status=last_status
        )


@dataclass
class EmbedConfig:
    """Configuración para la generación de embeds."""
    show_thumbnail: bool = True
    show_connect_button: bool = True
    show_map: bool = True
    show_players: bool = True
    show_version: bool = True
    show_uptime: bool = False
    custom_footer: Optional[str] = None
    
    # Colores personalizados (si None, usa los por defecto)
    color_online: Optional[int] = None
    color_offline: Optional[int] = None
    color_maintenance: Optional[int] = None
    
    def get_color(self, status: ServerStatus) -> discord.Color:
        """Obtiene el color para un estado, usando personalizado si existe."""
        if status == ServerStatus.ONLINE and self.color_online:
            return discord.Color(self.color_online)
        elif status == ServerStatus.OFFLINE and self.color_offline:
            return discord.Color(self.color_offline)
        elif status == ServerStatus.MAINTENANCE and self.color_maintenance:
            return discord.Color(self.color_maintenance)
        return status.color


@dataclass
class CacheEntry:
    """Entrada de caché para resultados de query."""
    result: QueryResult
    timestamp: datetime
    
    def is_expired(self, max_age_seconds: float = 5.0) -> bool:
        """Verifica si la entrada de caché ha expirado."""
        age = (datetime.utcnow() - self.timestamp).total_seconds()
        return age > max_age_seconds


@dataclass
class ServerStats:
    """Estadísticas de un servidor para el comando serverstats."""
    server_key: str
    game: GameType
    status: ServerStatus
    uptime_percentage: float
    total_queries: int
    successful_queries: int
    last_online: Optional[datetime]
    last_offline: Optional[datetime]
    current_players: int
    max_players: int
    hostname: str
    map_name: str
    
    def to_embed(self, timezone_str: str = "UTC") -> discord.Embed:
        """Genera un embed con las estadísticas."""
        import pytz
        try:
            tz = pytz.timezone(timezone_str)
        except pytz.UnknownTimeZoneError:
            tz = pytz.UTC
        
        embed = discord.Embed(
            title=_("Statistics - {hostname}").format(hostname=self.hostname),
            color=self.status.color
        )
        
        embed.add_field(
            name=_("Current Status"),
            value=f"{self.status.emoji} {self.status.display_name}",
            inline=True
        )
        embed.add_field(
            name=_("Game"),
            value=self.game.display_name if self.game else "N/A",
            inline=True
        )
        embed.add_field(
            name=_("Players"),
            value=f"{self.current_players}/{self.max_players}",
            inline=True
        )
        
        embed.add_field(
            name=f"📈 {_('Uptime')}",
            value=f"{self.uptime_percentage:.1f}%",
            inline=True
        )
        embed.add_field(
            name=f"📊 {_('Total Queries')}",
            value=str(self.total_queries),
            inline=True
        )
        embed.add_field(
            name=f"✅ {_('Successful Queries')}",
            value=str(self.successful_queries),
            inline=True
        )
        
        if self.last_online:
            local_time = self.last_online.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S")
            embed.add_field(name=f"🟢 {_('Last Online')}", value=local_time, inline=True)
        
        if self.last_offline:
            local_time = self.last_offline.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S")
            embed.add_field(name=f"🔴 {_('Last Offline')}", value=local_time, inline=True)
        
        embed.add_field(name=f"🗺️ {_('Map')}", value=self.map_name, inline=True)
        
        return embed


@dataclass
class PlayerHistoryEntry:
    """Una entrada en el historial de jugadores."""
    timestamp: datetime
    player_count: int
    max_players: int
    status: ServerStatus
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario para almacenamiento."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "player_count": self.player_count,
            "max_players": self.max_players,
            "status": self.status.name
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlayerHistoryEntry":
        """Crea una instancia desde un diccionario."""
        try:
            timestamp = datetime.fromisoformat(data["timestamp"])
        except (ValueError, KeyError):
            timestamp = datetime.utcnow()
        
        try:
            status = ServerStatus[data.get("status", "UNKNOWN")]
        except KeyError:
            status = ServerStatus.UNKNOWN
        
        return cls(
            timestamp=timestamp,
            player_count=data.get("player_count", 0),
            max_players=data.get("max_players", 0),
            status=status
        )


@dataclass
class PlayerHistory:
    """Historial de jugadores de un servidor."""
    server_key: str
    entries: List[PlayerHistoryEntry] = field(default_factory=list)
    max_entries: int = 1440  # 24 horas con actualizaciones cada minuto
    
    def add_entry(self, player_count: int, max_players: int, status: ServerStatus) -> None:
        """Añade una entrada al historial."""
        entry = PlayerHistoryEntry(
            timestamp=datetime.utcnow(),
            player_count=player_count,
            max_players=max_players,
            status=status
        )
        self.entries.append(entry)
        
        # Limitar tamaño del historial
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]
    
    def get_entries_for_period(self, hours: int = 24) -> List[PlayerHistoryEntry]:
        """Obtiene las entradas del historial para un período de tiempo."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        return [e for e in self.entries if e.timestamp >= cutoff]
    
    def generate_ascii_graph(self, hours: int = 24, width: int = 24) -> str:
        """
        Genera un gráfico ASCII del historial de jugadores.
        
        Args:
            hours: Número de horas a mostrar
            width: Ancho del gráfico en caracteres
            
        Returns:
            String con el gráfico ASCII
        """
        entries = self.get_entries_for_period(hours)
        
        if not entries:
            return "```\nNo hay datos de historial disponibles.\n```"
        
        # Agrupar entradas por intervalos de tiempo
        interval_minutes = (hours * 60) // width
        buckets: List[List[PlayerHistoryEntry]] = [[] for _ in range(width)]
        
        now = datetime.utcnow()
        start_time = now - timedelta(hours=hours)
        
        for entry in entries:
            # Calcular en qué bucket cae esta entrada
            time_diff = (entry.timestamp - start_time).total_seconds() / 60
            bucket_idx = min(int(time_diff / interval_minutes), width - 1)
            if 0 <= bucket_idx < width:
                buckets[bucket_idx].append(entry)
        
        # Calcular promedio de jugadores por bucket
        avg_players: List[float] = []
        for bucket in buckets:
            if bucket:
                avg_players.append(sum(e.player_count for e in bucket) / len(bucket))
            else:
                avg_players.append(0)
        
        # Obtener max_players del último dato disponible
        max_players = max(
            (e.max_players for e in entries if e.max_players > 0),
            default=1
        )
        
        # Generar gráfico
        height = 8
        graph_lines: List[str] = []
        
        # Caracteres para el gráfico
        blocks = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
        
        # Línea del gráfico
        graph_row = ""
        for avg in avg_players:
            if avg == 0:
                graph_row += "░"
            else:
                # Normalizar a 0-7
                level = min(int((avg / max_players) * 8), 7)
                graph_row += blocks[level]
        
        # Calcular estadísticas
        online_entries = [e for e in entries if e.status != ServerStatus.OFFLINE]
        if online_entries:
            peak = max(e.player_count for e in online_entries)
            avg_total = sum(e.player_count for e in online_entries) / len(online_entries)
        else:
            peak = 0
            avg_total = 0
        
        # Construir el gráfico completo
        result = "```\n"
        result += f"📊 Historial de jugadores ({hours}h)\n"
        result += "─" * (width + 2) + "\n"
        result += f"Max: {max_players:>3} │{graph_row}│\n"
        result += f"    0 │{'─' * width}│\n"
        result += "─" * (width + 2) + "\n"
        result += f"      -{hours}h" + " " * (width - 8) + "Ahora\n"
        result += f"\n📈 Peak: {peak} | 📊 Promedio: {avg_total:.1f}\n"
        result += "```"
        
        return result
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario para almacenamiento."""
        return {
            "server_key": self.server_key,
            "entries": [e.to_dict() for e in self.entries[-self.max_entries:]]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlayerHistory":
        """Crea una instancia desde un diccionario."""
        entries = [
            PlayerHistoryEntry.from_dict(e) 
            for e in data.get("entries", [])
        ]
        return cls(
            server_key=data.get("server_key", ""),
            entries=entries
        )


@dataclass
class PlayerInfo:
    """Información de un jugador conectado."""
    name: str
    score: int = 0
    duration_seconds: float = 0
    
    @property
    def duration_formatted(self) -> str:
        """Formatea la duración de conexión."""
        total_seconds = int(self.duration_seconds)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    
    @classmethod
    def from_source_player(cls, player_data: Any) -> "PlayerInfo":
        """Crea una instancia desde datos de Source query."""
        return cls(
            name=getattr(player_data, "name", "Unknown"),
            score=getattr(player_data, "score", 0),
            duration_seconds=getattr(player_data, "duration", 0)
        )
