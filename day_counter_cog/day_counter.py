import discord
from redbot.core import commands, Config

class DayCounter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_guild = {
            "day_counter": 0
        }
        self.config.register_guild(**default_guild)

    @commands.guild_only()
    @commands.command()
    async def contador_dias(self, ctx):
        '''Incrementa y muestra el contador de días.'''
        async with self.config.guild(ctx.guild).day_counter() as day_counter:
            day_counter += 1
            await ctx.send(f"Estamos en el día {day_counter}")

    @commands.guild_only()
    @commands.command()
    async def resetear_contador(self, ctx):
        '''Resetea el contador de días a 0.'''
        await self.config.guild(ctx.guild).day_counter.set(0)
        await ctx.send("El contador de días ha sido reseteado a 0.")
