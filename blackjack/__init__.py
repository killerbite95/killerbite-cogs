from .blackjack import Blackjack

def setup(bot):
    bot.add_cog(Blackjack(bot))
