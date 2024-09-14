from .prunebans import PruneBans

async def setup(bot):
    await bot.add_cog(PruneBans(bot))
