from .removebankcredits import RemoveBankCredits

async def setup(bot):
    cog = RemoveBankCredits(bot)
    await bot.add_cog(cog)
