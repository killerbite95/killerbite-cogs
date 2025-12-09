"""
Modelos de datos para GameServerMonitor.
Incluye Enums, dataclasses y estructuras de datos.
By Killerbite95
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Dict, Any, List
from datetime import datetime
import discord


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
            title=f"📊 Estadísticas - {self.hostname}",
            color=self.status.color
        )
        
        embed.add_field(
            name="Estado Actual",
            value=f"{self.status.emoji} {self.status.display_name}",
            inline=True
        )
        embed.add_field(
            name="Juego",
            value=self.game.display_name if self.game else "N/A",
            inline=True
        )
        embed.add_field(
            name="Jugadores",
            value=f"{self.current_players}/{self.max_players}",
            inline=True
        )
        
        embed.add_field(
            name="📈 Uptime",
            value=f"{self.uptime_percentage:.1f}%",
            inline=True
        )
        embed.add_field(
            name="📊 Queries Totales",
            value=str(self.total_queries),
            inline=True
        )
        embed.add_field(
            name="✅ Queries Exitosas",
            value=str(self.successful_queries),
            inline=True
        )
        
        if self.last_online:
            local_time = self.last_online.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S")
            embed.add_field(name="🟢 Último Online", value=local_time, inline=True)
        
        if self.last_offline:
            local_time = self.last_offline.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S")
            embed.add_field(name="🔴 Último Offline", value=local_time, inline=True)
        
        embed.add_field(name="🗺️ Mapa", value=self.map_name, inline=True)
        embed.set_footer(text=f"Server Key: {self.server_key}")
        
        return embed
