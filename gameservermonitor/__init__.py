from .gameservermonitor import GameServerMonitor

async def setup(bot):
    cog = GameServerMonitor(bot)
    await bot.add_cog(cog)
