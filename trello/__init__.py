from .trello import TrelloCog

async def setup(bot):
    await bot.add_cog(TrelloCog(bot))
