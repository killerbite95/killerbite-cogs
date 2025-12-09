"""
GameServerMonitor - Cog para Red Discord Bot
Monitoriza servidores de juegos y actualiza su estado en Discord.

By Killerbite95

Estructura del paquete:
    - gameservermonitor.py: Cog principal con comandos y lógica
    - models.py: Dataclasses y Enums para estructuración de datos
    - query_handlers.py: Handlers de query con patrón Strategy
    - exceptions.py: Excepciones personalizadas
    - dashboard_integration.py: Integración con Red-Dashboard
"""

from redbot.core.bot import Red

from .gameservermonitor import GameServerMonitor

__all__ = ["GameServerMonitor", "setup"]
__version__ = "2.0.0"
__author__ = "Killerbite95"


async def setup(bot: Red) -> None:
    """
    Función de setup requerida por Red-DiscordBot.
    
    Args:
        bot: Instancia del bot de Red
    """
    cog = GameServerMonitor(bot)
    await bot.add_cog(cog)
