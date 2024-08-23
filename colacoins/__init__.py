from .colacoins import ColaCoins

async def setup(bot):
    cog = ColaCoins(bot)
    await bot.add_cog(cog)
