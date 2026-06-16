"""
RustMapsVote - Map voting COG for Red-DiscordBot
By Killerbite95
"""

from redbot.core.bot import Red

from .rustmaps_vote import RustMapsVote

__all__ = ["RustMapsVote", "setup"]
__version__ = "1.0.0"
__author__ = "Killerbite95"


async def setup(bot: Red) -> None:
    await bot.add_cog(RustMapsVote(bot))
