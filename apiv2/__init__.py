"""
APIv2 - REST API server for Red-DiscordBot
Embeds an aiohttp HTTP server inside the bot process for external integrations.

By Killerbite95
"""

from redbot.core.bot import Red

from .apiv2 import APIv2
from .decorator import api_route

__all__ = ["APIv2", "api_route", "setup"]
__version__ = "2.0.0"
__author__ = "Killerbite95"


async def setup(bot: Red) -> None:
    cog = APIv2(bot)
    await bot.add_cog(cog)
