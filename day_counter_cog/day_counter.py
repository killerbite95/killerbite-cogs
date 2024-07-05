import discord
from discord.ext import commands
import os

class DayCounter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.file_path = "data/day_counter_cog/day_counter.txt"
        self.current_day = self.read_day_counter()

    def read_day_counter(self):
        if os.path.exists(self.file_path):
            with open(self.file_path, "r") as file:
                return int(file.read().strip())
        return 1

    def write_day_counter(self):
        with open(self.file_path, "w") as file:
            file.write(str(self.current_day))

    @commands.command()
    async def contador_dias(self, ctx):
        self.current_day += 1
        self.write_day_counter()
        await ctx.send(f"Hoy es el día {self.current_day}. Mañana será el día {self.current_day + 1}.")

def setup(bot):
    bot.add_cog(DayCounter(bot))