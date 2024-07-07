import discord
from discord.ext import commands
import requests

class F1(commands.Cog):
    """Cog para obtener información de Fórmula 1 usando la API de openf1.org."""

    def __init__(self, bot):
        self.bot = bot
        self.api_base_url = "https://api.openf1.org/v1/"

    def get_data_from_api(self, endpoint):
        """Función para obtener datos de la API de openf1.org."""
        url = f"{self.api_base_url}{endpoint}"
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        else:
            return None

    @commands.command(name="pilotos")
    async def get_driver_standings(self, ctx):
        """Obtener la clasificación de pilotos."""
        data = self.get_data_from_api("driverStandings")
        if data:
            embed = discord.Embed(title="Clasificación de Pilotos", color=discord.Color.blue())
            for driver in data["standings"]:
                embed.add_field(
                    name=f"{driver['position']}. {driver['driver']['givenName']} {driver['driver']['familyName']}",
                    value=f"Puntos: {driver['points']}",
                    inline=False
                )
            await ctx.send(embed=embed)
        else:
            await ctx.send("No se pudo obtener la información de la clasificación de pilotos.")

    @commands.command(name="constructores")
    async def get_constructor_standings(self, ctx):
        """Obtener la clasificación de constructores."""
        data = self.get_data_from_api("constructorStandings")
        if data:
            embed = discord.Embed(title="Clasificación de Constructores", color=discord.Color.green())
            for constructor in data["standings"]:
                embed.add_field(
                    name=f"{constructor['position']}. {constructor['constructor']['name']}",
                    value=f"Puntos: {constructor['points']}",
                    inline=False
                )
            await ctx.send(embed=embed)
        else:
            await ctx.send("No se pudo obtener la información de la clasificación de constructores.")

    @commands.command(name="calendario")
    async def get_race_schedule(self, ctx):
        """Obtener el calendario de carreras."""
        data = self.get_data_from_api("races")
        if data:
            embed = discord.Embed(title="Calendario de Carreras", color=discord.Color.red())
            for race in data["races"]:
                embed.add_field(
                    name=f"{race['raceName']} - {race['date']}",
                    value=f"Circuito: {race['circuit']['circuitName']}",
                    inline=False
                )
            await ctx.send(embed=embed)
        else:
            await ctx.send("No se pudo obtener la información del calendario de carreras.")

    @commands.command(name="carrera_actual")
    async def get_current_race(self, ctx):
        """Obtener información de la carrera actual."""
        data = self.get_data_from_api("currentRace")
        if data:
            race = data["race"]
            embed = discord.Embed(title=f"{race['raceName']} - {race['date']}", color=discord.Color.purple())
            embed.add_field(name="Circuito", value=race['circuit']['circuitName'], inline=False)
            embed.add_field(name="Localización", value=f"{race['circuit']['location']['locality']}, {race['circuit']['location']['country']}", inline=False)
            await ctx.send(embed=embed)
        else:
            await ctx.send("No se pudo obtener la información de la carrera actual.")

def setup(bot):
    bot.add_cog(F1(bot))