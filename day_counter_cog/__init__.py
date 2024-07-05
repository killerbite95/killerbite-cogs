from .day_counter import DayCounter

async def setup(bot):
    cog = DayCounter(bot)
    await bot.add_cog(cog)
