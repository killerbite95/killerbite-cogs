from .autoprune import AutoPrune

async def setup(bot):
    bot.add_cog(AutoPrune(bot))
