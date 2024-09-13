from .removebankcredits import RemoveBankCredits

async def setup(bot):
    await bot.add_cog(RemoveBankCredits(bot))
