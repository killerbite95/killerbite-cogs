from .cog import GameServerMonitor

async def setup(bot):
    await bot.add_cog(GameServerMonitor(bot))
