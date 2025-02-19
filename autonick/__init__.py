from .autonick import AutoNick

async def setup(bot):
    await bot.add_cog(AutoNick(bot))
