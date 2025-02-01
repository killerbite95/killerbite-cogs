from .trello import TrelloCog

def setup(bot):
    bot.add_cog(TrelloCog(bot))
