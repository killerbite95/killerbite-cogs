from .kickalerts import KickAlerts

async def setup(bot):
    await bot.add_cog(KickAlerts(bot))
