from .maptrack import MapTrack

async def setup(bot):
    await bot.add_cog(MapTrack(bot))
