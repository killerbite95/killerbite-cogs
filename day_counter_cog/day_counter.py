import discord
from redbot.core import commands, Config
from datetime import datetime, timedelta, timezone

class DayCounter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_guild = {
            "start_date": None  # Almacenará la fecha de inicio como una cadena
        }
        self.config.register_guild(**default_guild)

    @commands.guild_only()
    @commands.command()
    async def dias(self, ctx):
        '''Muestra el número de días pasados desde la fecha de inicio.'''
        start_date_str = await self.config.guild(ctx.guild).start_date()
        if start_date_str is None:
            await ctx.send("La fecha de inicio no está establecida. Usa el comando `!establecer_fecha` para establecerla.")
            return
        
        start_date = datetime.fromisoformat(start_date_str).replace(tzinfo=timezone.utc) + timedelta(hours=2)
        current_date = datetime.now(timezone.utc) + timedelta(hours=2)
        days_passed = (current_date - start_date).days
        
        await ctx.send(f"Han pasado {days_passed} días desde la fecha de inicio.")

    @commands.guild_only()
    @commands.command()
    async def establecer_fecha(self, ctx, year: int, month: int, day: int):
        '''Establece la fecha de inicio en formato año, mes, día.'''
        start_date = datetime(year, month, day, tzinfo=timezone.utc) - timedelta(hours=2)
        await self.config.guild(ctx.guild).start_date.set(start_date.isoformat())
        await ctx.send(f"La fecha de inicio se ha establecido en {start_date.strftime('%Y-%m-%d')}.")

    @commands.guild_only()
    @commands.command()
    async def resetear_dias(self, ctx):
        '''Resetea la fecha de inicio.'''
        await self.config.guild(ctx.guild).start_date.set(None)
        await ctx.send("La fecha de inicio ha sido reseteada.")
