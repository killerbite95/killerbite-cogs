from .citygame import CiudadVirtual

async def setup(bot):
    await bot.add_cog(CiudadVirtual(bot))