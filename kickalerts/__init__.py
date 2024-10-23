from .kickalerts import KickAlerts

def setup(bot):
    bot.add_cog(KickAlerts(bot))
