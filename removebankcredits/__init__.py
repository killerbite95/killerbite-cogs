from .removebankcredits import RemoveBankCredits

def setup(bot):
    bot.add_cog(RemoveBankCredits(bot))
