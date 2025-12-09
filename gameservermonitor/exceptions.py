"""
Excepciones personalizadas para GameServerMonitor.
By Killerbite95
"""

from typing import Optional


class GameServerMonitorError(Exception):
    """Excepción base para todos los errores del cog GameServerMonitor."""
    
    def __init__(self, message: str = "Error en GameServerMonitor"):
        self.message = message
        super().__init__(self.message)


class QueryError(GameServerMonitorError):
    """Excepción base para errores de query a servidores."""
    
    def __init__(self, host: str, port: int, message: Optional[str] = None):
        self.host = host
        self.port = port
        self.message = message or f"Error al consultar {host}:{port}"
        super().__init__(self.message)


class QueryTimeoutError(QueryError):
    """Se lanza cuando una query al servidor excede el tiempo de espera."""
    
    def __init__(self, host: str, port: int, timeout: float = 10.0):
        self.timeout = timeout
        message = f"Timeout ({timeout}s) al consultar {host}:{port}"
        super().__init__(host, port, message)


class QueryConnectionError(QueryError):
    """Se lanza cuando no se puede establecer conexión con el servidor."""
    
    def __init__(self, host: str, port: int, reason: Optional[str] = None):
        self.reason = reason
        message = f"No se pudo conectar a {host}:{port}"
        if reason:
            message += f": {reason}"
        super().__init__(host, port, message)


class InvalidPortError(GameServerMonitorError):
    """Se lanza cuando se proporciona un puerto inválido."""
    
    def __init__(self, port: int):
        self.port = port
        message = f"Puerto inválido: {port}. Debe estar entre 1 y 65535."
        super().__init__(message)


class ServerNotFoundError(GameServerMonitorError):
    """Se lanza cuando no se encuentra un servidor en la configuración."""
    
    def __init__(self, server_key: str):
        self.server_key = server_key
        message = f"Servidor '{server_key}' no encontrado en la configuración."
        super().__init__(message)


class ServerAlreadyExistsError(GameServerMonitorError):
    """Se lanza cuando se intenta añadir un servidor que ya existe."""
    
    def __init__(self, server_key: str):
        self.server_key = server_key
        message = f"El servidor '{server_key}' ya está siendo monitoreado."
        super().__init__(message)


class UnsupportedGameError(GameServerMonitorError):
    """Se lanza cuando se intenta usar un juego no soportado."""
    
    def __init__(self, game: str, supported_games: list):
        self.game = game
        self.supported_games = supported_games
        message = f"Juego '{game}' no soportado. Juegos disponibles: {', '.join(supported_games)}"
        super().__init__(message)


class ChannelNotFoundError(GameServerMonitorError):
    """Se lanza cuando no se encuentra el canal de Discord."""
    
    def __init__(self, channel_id: int):
        self.channel_id = channel_id
        message = f"Canal con ID {channel_id} no encontrado."
        super().__init__(message)


class InsufficientPermissionsError(GameServerMonitorError):
    """Se lanza cuando el bot no tiene permisos suficientes en el canal."""
    
    def __init__(self, channel_id: int, missing_permissions: list):
        self.channel_id = channel_id
        self.missing_permissions = missing_permissions
        perms_str = ", ".join(missing_permissions)
        message = f"Permisos insuficientes en canal {channel_id}. Faltan: {perms_str}"
        super().__init__(message)


class InvalidTimezoneError(GameServerMonitorError):
    """Se lanza cuando se proporciona una zona horaria inválida."""
    
    def __init__(self, timezone: str):
        self.timezone = timezone
        message = f"Zona horaria '{timezone}' no es válida."
        super().__init__(message)


class ConfigurationError(GameServerMonitorError):
    """Se lanza cuando hay un error en la configuración del cog."""
    
    def __init__(self, key: str, reason: Optional[str] = None):
        self.key = key
        self.reason = reason
        message = f"Error de configuración en '{key}'"
        if reason:
            message += f": {reason}"
        super().__init__(message)
