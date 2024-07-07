from .f1 import F1

async def setup(bot):
    await bot.add_cog(F1(bot))
