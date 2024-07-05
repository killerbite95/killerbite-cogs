from .day_counter import DayCounter

def setup(bot):
    bot.add_cog(DayCounter(bot))
