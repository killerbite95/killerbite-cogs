import discord
from redbot.core import commands
import fastf1
from datetime import datetime

class F1(commands.Cog):
    """Cog de Fórmula 1 para Red Discord Bot usando FastF1"""

    def __init__(self, bot):
        self.bot = bot
        fastf1.Cache.enable_cache('/root/.fastf1_cache')  # habilitar caché

    @commands.command()
    async def pilotos(self, ctx):
        """Obtiene la clasificación de pilotos"""
        current_year = datetime.now().year
        try:
            drivers = fastf1.get_driver_standings(current_year)
            if drivers is not None:
                embed = discord.Embed(title="Clasificación de Pilotos", color=discord.Color.blue())
                for driver in drivers.iterrows():
                    driver_name = f"{driver[1]['Driver']['givenName']} {driver[1]['Driver']['familyName']}"
                    points = driver[1]['points']
                    embed.add_field(name=f"{driver[1]['position']}. {driver_name}", value=f"Puntos: {points}", inline=False)
                await ctx.send(embed=embed)
            else:
                await ctx.send("No se pudo obtener la clasificación de pilotos.")
        except Exception as e:
            await ctx.send(f"Error al obtener la clasificación de pilotos: {e}")

    @commands.command()
    async def constructores(self, ctx):
        """Obtiene la clasificación de constructores"""
        current_year = datetime.now().year
        try:
            constructors = fastf1.get_constructor_standings(current_year)
            if constructors is not None:
                embed = discord.Embed(title="Clasificación de Constructores", color=discord.Color.green())
                for constructor in constructors.iterrows():
                    name = constructor[1]['Constructor']['name']
                    points = constructor[1]['points']
                    embed.add_field(name=f"{constructor[1]['position']}. {name}", value=f"Puntos: {points}", inline=False)
                await ctx.send(embed=embed)
            else:
                await ctx.send("No se pudo obtener la clasificación de constructores.")
        except Exception as e:
            await ctx.send(f"Error al obtener la clasificación de constructores: {e}")

    @commands.command()
    async def calendario(self, ctx):
        """Obtiene el calendario de carreras"""
        current_year = datetime.now().year
        try:
            schedule = fastf1.get_event_schedule(current_year)
            if schedule is not None:
                embed = discord.Embed(title="Calendario de Carreras", color=discord.Color.red())
                for event in schedule.iterrows():
                    race_date = event[1]['Date']
                    embed.add_field(name=event[1]['EventName'], value=f"Fecha: {race_date.strftime('%d/%m/%Y')}\nCircuito: {event[1]['Circuit']['Location']['longName']}", inline=False)
                await ctx.send(embed=embed)
            else:
                await ctx.send("No se pudo obtener el calendario de carreras.")
        except Exception as e:
            await ctx.send(f"Error al obtener el calendario de carreras: {e}")

    @commands.command()
    async def carrera_actual(self, ctx):
        """Obtiene información de la carrera actual"""
        current_year = datetime.now().year
        try:
            next_event = fastf1.get_event_schedule(current_year).iloc[0]
            if next_event is not None:
                race_date = next_event['Date']
                embed = discord.Embed(title="Carrera Actual", color=discord.Color.purple())
                embed.add_field(name=next_event['EventName'], value=f"Fecha: {race_date.strftime('%d/%m/%Y')}\nCircuito: {next_event['Circuit']['Location']['longName']}", inline=False)
                await ctx.send(embed=embed)
            else:
                await ctx.send("No se pudo obtener la información de la carrera actual.")
        except Exception as e:
            await ctx.send(f"Error al obtener la información de la carrera actual: {e}")

async def setup(bot):
    await bot.add_cog(F1(bot))
