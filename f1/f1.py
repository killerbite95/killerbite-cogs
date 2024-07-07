import discord
from redbot.core import commands
import fastf1
import pandas as pd

class F1(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        fastf1.Cache.enable_cache('/root/.fastf1_cache')  # habilitar caché

    @commands.command()
    async def carrera_actual(self, ctx):
        '''Muestra información sobre la carrera actual.'''
        try:
            # Obtener el calendario de eventos del año actual
            schedule = fastf1.get_event_schedule(2023)
            
            # Inspeccionar las columnas disponibles en el calendario de eventos
            await ctx.send(f"Columnas disponibles: {schedule.columns.tolist()}")

            # Encontrar el próximo evento
            next_event = schedule.loc[schedule['EventDate'] >= pd.Timestamp.now()].iloc[0]
            
            await ctx.send(f"Próxima carrera: {next_event['EventName']} en {next_event['Location']} el {next_event['EventDate'].date()}")
        except Exception as e:
            await ctx.send("No se pudo obtener la información de la carrera actual.")
            await ctx.send(f"Error: {str(e)}")

    @commands.command()
    async def pilotos(self, ctx):
        '''Muestra la clasificación actual de pilotos.'''
        try:
            # Obtener la lista de eventos del año actual
            events = fastf1.get_event_schedule(2023)

            # Inspeccionar las columnas disponibles en el calendario de eventos
            await ctx.send(f"Columnas disponibles: {events.columns.tolist()}")
            
            # Tomar el último evento completado
            last_event = None
            for _, event in events.iterrows():
                if event['EventDate'] <= pd.Timestamp.now():
                    last_event = event
                    break

            if not last_event:
                await ctx.send("No se pudo obtener la clasificación de pilotos: No hay eventos completados.")
                return

            # Obtener la sesión de carrera del último evento completado
            session = fastf1.get_session(last_event['EventYear'], last_event['EventName'], 'R')
            session.load()

            # Obtener la clasificación de pilotos a partir de los resultados de la carrera
            driver_standings = session.results[['DriverNumber', 'FullName', 'TeamName', 'Points']].sort_values(by='Points', ascending=False)

            standings_message = "Clasificación actual de pilotos:\n"
            for index, row in driver_standings.iterrows():
                standings_message += f"{row['FullName']} ({row['TeamName']}): {row['Points']} puntos\n"

            await ctx.send(standings_message)
        except Exception as e:
            await ctx.send("Error al obtener la clasificación de pilotos.")
            await ctx.send(f"Error: {str(e)}")

    @commands.command()
    async def constructor(self, ctx):
        '''Muestra la clasificación actual de constructores.'''
        try:
            # Obtener la lista de eventos del año actual
            events = fastf1.get_event_schedule(2023)
            
            # Inspeccionar las columnas disponibles en el calendario de eventos
            await ctx.send(f"Columnas disponibles: {events.columns.tolist()}")
            
            # Tomar el último evento completado
            last_event = None
            for _, event in events.iterrows():
                if event['EventDate'] <= pd.Timestamp.now():
                    last_event = event
                    break

            if not last_event:
                await ctx.send("No se pudo obtener la clasificación de constructores: No hay eventos completados.")
                return

            # Obtener la sesión de carrera del último evento completado
            session = fastf1.get_session(last_event['EventYear'], last_event['EventName'], 'R')
            session.load()

            # Obtener la clasificación de constructores a partir de los resultados de la carrera
            constructor_standings = session.results[['TeamName', 'Points']].groupby('TeamName').sum().sort_values(by='Points', ascending=False)

            standings_message = "Clasificación actual de constructores:\n"
            for index, row in constructor_standings.iterrows():
                standings_message += f"{index}: {row['Points']} puntos\n"

            await ctx.send(standings_message)
        except Exception as e:
            await ctx.send("Error al obtener la clasificación de constructores.")
            await ctx.send(f"Error: {str(e)}")

def setup(bot):
    bot.add_cog(F1(bot))
