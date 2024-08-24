from .maptrack import MapTrack

async def setup(bot):
    cog = MapTrack(bot)
    await bot.add_cog(cog)
