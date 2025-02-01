from .blackjack_cog import BlackJack

def setup(bot):
    bot.add_cog(BlackJack(bot))
