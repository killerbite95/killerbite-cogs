import discord
from redbot.core import commands, Config
from datetime import datetime, timezone


class DayCounter(commands.Cog):
    __author__ = "Killerbite95"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_guild = {
            "start_date": None
        }
        self.config.register_guild(**default_guild)

    @commands.guild_only()
    @commands.command()
    async def dias(self, ctx):
        '''Muestra el número de días pasados desde la fecha de inicio.'''
        start_date_str = await self.config.guild(ctx.guild).start_date()
        if start_date_str is None:
            await ctx.send(
                f"La fecha de inicio no está establecida. "
                f"Usa `{ctx.prefix}establecer_fecha` para establecerla."
            )
            return

        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        current_date = datetime.now(timezone.utc).date()
        days_passed = (current_date - start_date).days

        embed = discord.Embed(
            title="📅 Contador de días",
            color=0x3498DB
        )
        embed.add_field(name="Fecha de inicio", value=start_date_str, inline=True)
        embed.add_field(name="Hoy", value=current_date.strftime("%Y-%m-%d"), inline=True)
        embed.add_field(name="Días transcurridos", value=str(days_passed), inline=False)
        await ctx.send(embed=embed)

    @commands.guild_only()
    @commands.command()
    async def establecer_fecha(self, ctx, year: int, month: int, day: int):
        '''Establece la fecha de inicio en formato año, mes, día.'''
        try:
            start_date = datetime(year, month, day)
        except ValueError:
            await ctx.send("❌ Fecha inválida. Verificá que el día y mes sean correctos.")
            return

        start_date_str = start_date.strftime("%Y-%m-%d")
        await self.config.guild(ctx.guild).start_date.set(start_date_str)

        embed = discord.Embed(
            title="📅 Fecha de inicio establecida",
            description=f"El contador de días ahora empieza desde el **{start_date_str}**.",
            color=0x2ECC71
        )
        await ctx.send(embed=embed)

    @commands.guild_only()
    @commands.command()
    async def resetear_dias(self, ctx):
        '''Resetea la fecha de inicio.'''
        await self.config.guild(ctx.guild).start_date.set(None)

        embed = discord.Embed(
            title="🔄 Fecha reiniciada",
            description="La fecha de inicio ha sido eliminada.",
            color=0xE74C3C
        )
        await ctx.send(embed=embed)
