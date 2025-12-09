"""
Query Handlers para GameServerMonitor.
Implementa el patrón Strategy para diferentes protocolos de query.
By Killerbite95
"""

import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple, Type

from opengsq.protocols import Source, Minecraft

from .models import QueryResult, ServerStatus, GameType, CacheEntry
from .exceptions import (
    QueryTimeoutError,
    QueryConnectionError,
    QueryError,
    UnsupportedGameError
)

logger = logging.getLogger("red.killerbite95.gameservermonitor.query")


def extract_numeric_version(version_str: str) -> str:
    """Extrae la versión numérica de un string de versión."""
    m = re.search(r"(\d+(?:\.\d+)+)", version_str)
    if m:
        return m.group(1)
    return version_str


def convert_motd(motd: Any) -> str:
    """Convierte el MOTD de Minecraft a texto plano."""
    if isinstance(motd, str):
        text = motd.strip()
    elif isinstance(motd, dict):
        text = motd.get("text", "")
        if "extra" in motd and isinstance(motd["extra"], list):
            for extra in motd["extra"]:
                text += " " + convert_motd(extra)
        text = text.strip()
    elif isinstance(motd, list):
        text = " ".join([convert_motd(item) for item in motd]).strip()
    else:
        text = ""
    return " ".join(text.split())


class QueryHandler(ABC):
    """Clase base abstracta para handlers de query (Patrón Strategy)."""
    
    @property
    @abstractmethod
    def supported_games(self) -> List[GameType]:
        """Lista de juegos que este handler soporta."""
        pass
    
    @abstractmethod
    async def query(self, host: str, port: int, **kwargs) -> QueryResult:
        """
        Realiza una query al servidor.
        
        Args:
            host: IP o hostname del servidor
            port: Puerto de query
            **kwargs: Argumentos adicionales específicos del protocolo
            
        Returns:
            QueryResult con los datos obtenidos
        """
        pass
    
    def supports_game(self, game: GameType) -> bool:
        """Verifica si este handler soporta un juego específico."""
        return game in self.supported_games


class SourceQueryHandler(QueryHandler):
    """Handler para servidores que usan el protocolo Source Query."""
    
    @property
    def supported_games(self) -> List[GameType]:
        return [GameType.CS2, GameType.CSS, GameType.GMOD, GameType.RUST]
    
    async def query(self, host: str, port: int, **kwargs) -> QueryResult:
        """Realiza query usando Source Query Protocol."""
        debug = kwargs.get("debug", False)
        start_time = datetime.utcnow()
        
        try:
            source = Source(host=host, port=port)
            info = await source.get_info()
            
            end_time = datetime.utcnow()
            latency_ms = (end_time - start_time).total_seconds() * 1000
            
            if debug:
                logger.debug(f"Raw Source query para {host}:{port}: {info}")
            
            players = getattr(info, "players", 0)
            max_players = getattr(info, "max_players", 0)
            map_name = getattr(info, "map", "N/A")
            hostname = getattr(info, "name", "Unknown Server")
            is_passworded = hasattr(info, "visibility") and info.visibility == 1
            
            status = ServerStatus.MAINTENANCE if is_passworded else ServerStatus.ONLINE
            
            return QueryResult(
                success=True,
                status=status,
                players=players,
                max_players=max_players,
                map_name=map_name,
                hostname=hostname or "Game Server",
                is_passworded=is_passworded,
                raw_data={"info": info},
                query_time=datetime.utcnow(),
                latency_ms=latency_ms
            )
            
        except TimeoutError as e:
            logger.debug(f"Timeout en Source query {host}:{port}: {e}")
            raise QueryTimeoutError(host, port)
        except ConnectionError as e:
            logger.debug(f"Error de conexión en Source query {host}:{port}: {e}")
            raise QueryConnectionError(host, port, str(e))
        except Exception as e:
            logger.error(f"Error inesperado en Source query {host}:{port}: {e!r}")
            return QueryResult(
                success=False,
                status=ServerStatus.OFFLINE,
                error_message=str(e),
                query_time=datetime.utcnow()
            )


class MinecraftQueryHandler(QueryHandler):
    """Handler para servidores Minecraft."""
    
    @property
    def supported_games(self) -> List[GameType]:
        return [GameType.MINECRAFT]
    
    async def query(self, host: str, port: int, **kwargs) -> QueryResult:
        """Realiza query usando Minecraft Status Protocol."""
        debug = kwargs.get("debug", False)
        start_time = datetime.utcnow()
        
        try:
            mc = Minecraft(host=host, port=port)
            info = await mc.get_status()
            
            end_time = datetime.utcnow()
            latency_ms = (end_time - start_time).total_seconds() * 1000
            
            if debug:
                logger.debug(f"Raw Minecraft query para {host}:{port}: {info}")
            
            players = info.get("players", {}).get("online", 0)
            max_players = info.get("players", {}).get("max", 0)
            raw_motd = info.get("description", "Minecraft Server")
            hostname = convert_motd(raw_motd)
            version_str = info.get("version", {}).get("name", "???")
            version = extract_numeric_version(version_str)
            
            return QueryResult(
                success=True,
                status=ServerStatus.ONLINE,
                players=players,
                max_players=max_players,
                map_name=version,  # En Minecraft mostramos la versión
                hostname=hostname or "Minecraft Server",
                is_passworded=False,
                version=version_str,
                raw_data=info,
                query_time=datetime.utcnow(),
                latency_ms=latency_ms
            )
            
        except TimeoutError as e:
            logger.debug(f"Timeout en Minecraft query {host}:{port}: {e}")
            raise QueryTimeoutError(host, port)
        except ConnectionError as e:
            logger.debug(f"Error de conexión en Minecraft query {host}:{port}: {e}")
            raise QueryConnectionError(host, port, str(e))
        except Exception as e:
            logger.error(f"Error inesperado en Minecraft query {host}:{port}: {e!r}")
            return QueryResult(
                success=False,
                status=ServerStatus.OFFLINE,
                error_message=str(e),
                query_time=datetime.utcnow()
            )


class DayZQueryHandler(QueryHandler):
    """Handler especializado para servidores DayZ con fallback de puertos."""
    
    @property
    def supported_games(self) -> List[GameType]:
        return [GameType.DAYZ]
    
    async def _try_query(self, host: str, port: int, debug: bool = False) -> Tuple[bool, Optional[Any]]:
        """Intenta una query en un puerto específico."""
        try:
            source = Source(host=host, port=port)
            info = await source.get_info()
            if debug:
                logger.debug(f"DayZ query exitosa en {host}:{port}")
            return True, info
        except Exception as e:
            logger.debug(f"DayZ query falló en {host}:{port}: {e!r}")
            return False, None
    
    async def query(self, host: str, port: int, **kwargs) -> QueryResult:
        """
        Realiza query a servidor DayZ con fallback de puertos.
        
        Args:
            host: IP del servidor
            port: Puerto del juego (game_port)
            **kwargs:
                query_port: Puerto de query alternativo
                debug: Modo debug
        """
        debug = kwargs.get("debug", False)
        query_port = kwargs.get("query_port")
        game_port = port
        
        start_time = datetime.utcnow()
        info = None
        used_port = None
        
        # 1. Intentar game_port primero
        success, info = await self._try_query(host, game_port, debug)
        if success:
            used_port = game_port
            logger.info(f"DayZ {host}: respondió en game_port={game_port}")
        
        # 2. Intentar query_port si está configurado y es diferente
        if info is None and query_port and int(query_port) != int(game_port):
            success, info = await self._try_query(host, int(query_port), debug)
            if success:
                used_port = query_port
                logger.info(f"DayZ {host}: respondió en query_port={query_port}")
        
        # 3. Intentar puertos candidatos comunes
        if info is None:
            candidates = [27016, game_port + 1, game_port + 2]
            for candidate_port in candidates:
                if candidate_port in (game_port, query_port):
                    continue
                success, info = await self._try_query(host, candidate_port, debug)
                if success:
                    used_port = candidate_port
                    logger.info(f"DayZ {host}: respondió en candidato={candidate_port}")
                    break
        
        end_time = datetime.utcnow()
        latency_ms = (end_time - start_time).total_seconds() * 1000
        
        if info is None:
            logger.warning(f"DayZ no respondió en {host} (gp:{game_port}, qp:{query_port})")
            return QueryResult(
                success=False,
                status=ServerStatus.OFFLINE,
                error_message=f"No response from {host}",
                query_time=datetime.utcnow(),
                latency_ms=latency_ms
            )
        
        players = getattr(info, "players", 0)
        max_players = getattr(info, "max_players", 0)
        map_name = getattr(info, "map", "N/A")
        hostname = getattr(info, "name", "Unknown Server")
        is_passworded = hasattr(info, "visibility") and info.visibility == 1
        
        status = ServerStatus.MAINTENANCE if is_passworded else ServerStatus.ONLINE
        
        return QueryResult(
            success=True,
            status=status,
            players=players,
            max_players=max_players,
            map_name=map_name,
            hostname=hostname or "DayZ Server",
            is_passworded=is_passworded,
            raw_data={"info": info, "used_port": used_port},
            query_time=datetime.utcnow(),
            latency_ms=latency_ms
        )


class QueryHandlerFactory:
    """Factory para obtener el handler apropiado según el tipo de juego."""
    
    _handlers: Dict[GameType, Type[QueryHandler]] = {
        GameType.CS2: SourceQueryHandler,
        GameType.CSS: SourceQueryHandler,
        GameType.GMOD: SourceQueryHandler,
        GameType.RUST: SourceQueryHandler,
        GameType.MINECRAFT: MinecraftQueryHandler,
        GameType.DAYZ: DayZQueryHandler,
    }
    
    _instances: Dict[Type[QueryHandler], QueryHandler] = {}
    
    @classmethod
    def get_handler(cls, game: GameType) -> QueryHandler:
        """
        Obtiene el handler apropiado para un tipo de juego.
        
        Args:
            game: Tipo de juego
            
        Returns:
            Instancia del handler apropiado
            
        Raises:
            UnsupportedGameError: Si el juego no está soportado
        """
        handler_class = cls._handlers.get(game)
        if handler_class is None:
            raise UnsupportedGameError(
                game.value if game else "unknown",
                GameType.supported_games()
            )
        
        # Singleton por tipo de handler
        if handler_class not in cls._instances:
            cls._instances[handler_class] = handler_class()
        
        return cls._instances[handler_class]
    
    @classmethod
    def register_handler(cls, game: GameType, handler_class: Type[QueryHandler]) -> None:
        """
        Registra un nuevo handler para un tipo de juego.
        Permite extensibilidad del sistema.
        """
        cls._handlers[game] = handler_class
        # Limpiar instancia cacheada si existe
        if handler_class in cls._instances:
            del cls._instances[handler_class]


class QueryCache:
    """Sistema de caché para resultados de queries."""
    
    def __init__(self, max_age_seconds: float = 5.0):
        self._cache: Dict[str, CacheEntry] = {}
        self._max_age = max_age_seconds
    
    def _make_key(self, host: str, port: int, game: GameType) -> str:
        """Genera la clave de caché."""
        return f"{game.value}:{host}:{port}"
    
    def get(self, host: str, port: int, game: GameType) -> Optional[QueryResult]:
        """
        Obtiene un resultado de la caché si existe y no ha expirado.
        
        Returns:
            QueryResult si existe en caché y es válido, None en caso contrario
        """
        key = self._make_key(host, port, game)
        entry = self._cache.get(key)
        
        if entry is None:
            return None
        
        if entry.is_expired(self._max_age):
            del self._cache[key]
            return None
        
        logger.debug(f"Cache hit para {key}")
        return entry.result
    
    def set(self, host: str, port: int, game: GameType, result: QueryResult) -> None:
        """Almacena un resultado en la caché."""
        key = self._make_key(host, port, game)
        self._cache[key] = CacheEntry(result=result, timestamp=datetime.utcnow())
        logger.debug(f"Cache set para {key}")
    
    def invalidate(self, host: str, port: int, game: GameType) -> None:
        """Invalida una entrada específica de la caché."""
        key = self._make_key(host, port, game)
        if key in self._cache:
            del self._cache[key]
    
    def clear(self) -> None:
        """Limpia toda la caché."""
        self._cache.clear()
    
    def cleanup_expired(self) -> int:
        """
        Limpia entradas expiradas de la caché.
        
        Returns:
            Número de entradas eliminadas
        """
        expired_keys = [
            key for key, entry in self._cache.items()
            if entry.is_expired(self._max_age)
        ]
        for key in expired_keys:
            del self._cache[key]
        return len(expired_keys)


class QueryService:
    """
    Servicio principal para realizar queries a servidores.
    Integra handlers, caché y logging.
    """
    
    def __init__(self, cache_max_age: float = 5.0):
        self._cache = QueryCache(max_age_seconds=cache_max_age)
        self._debug = False
    
    @property
    def debug(self) -> bool:
        return self._debug
    
    @debug.setter
    def debug(self, value: bool) -> None:
        self._debug = value
    
    async def query_server(
        self,
        host: str,
        port: int,
        game: GameType,
        use_cache: bool = True,
        **kwargs
    ) -> QueryResult:
        """
        Realiza una query a un servidor de juegos.
        
        Args:
            host: IP o hostname del servidor
            port: Puerto de query
            game: Tipo de juego
            use_cache: Si usar caché (default: True)
            **kwargs: Argumentos adicionales para el handler
            
        Returns:
            QueryResult con los datos obtenidos
        """
        # Verificar caché
        if use_cache:
            cached = self._cache.get(host, port, game)
            if cached is not None:
                return cached
        
        # Obtener handler y realizar query
        handler = QueryHandlerFactory.get_handler(game)
        kwargs["debug"] = self._debug
        
        try:
            result = await handler.query(host, port, **kwargs)
        except (QueryTimeoutError, QueryConnectionError) as e:
            logger.warning(f"Query falló para {game.value} {host}:{port}: {e}")
            result = QueryResult(
                success=False,
                status=ServerStatus.OFFLINE,
                error_message=str(e),
                query_time=datetime.utcnow()
            )
        except Exception as e:
            logger.error(f"Error inesperado en query {game.value} {host}:{port}: {e!r}")
            result = QueryResult(
                success=False,
                status=ServerStatus.OFFLINE,
                error_message=str(e),
                query_time=datetime.utcnow()
            )
        
        # Almacenar en caché
        if use_cache:
            self._cache.set(host, port, game, result)
        
        return result
    
    def clear_cache(self) -> None:
        """Limpia la caché de queries."""
        self._cache.clear()
    
    def cleanup_cache(self) -> int:
        """Limpia entradas expiradas de la caché."""
        return self._cache.cleanup_expired()
