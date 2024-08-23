import json
import os
from redbot.core import commands, Config
import discord

class ColaCoins(commands.Cog):
    """Gestiona las ColaCoins para los usuarios."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_global = {
            "colacoins": {}
        }
        self.config.register_global(**default_global)

    async def save_data(self):
        data = await self.config.colacoins()
        with open("colacoins_data.json", "w") as f:
            json.dump(data, f)

    async def load_data(self):
        if os.path.exists("colacoins_data.json"):
            with open("colacoins_data.json", "r") as f:
                data = json.load(f)
                await self.config.colacoins.set(data)

    @commands.Cog.listener()
    async def on_ready(self):
        await self.load_data()

    @commands.admin_or_permissions(administrator=True)
    @commands.command(name="givecolacoins")
    async def give_colacoins(self, ctx, user: discord.Member, amount: int):
        """Da ColaCoins a un usuario."""
        async with self.config.colacoins() as colacoins:
            if str(user.id) not in colacoins:
                colacoins[str(user.id)] = 0
            colacoins[str(user.id)] += amount
            await ctx.send(f"{amount} ColaCoins dados a {user.display_name}. Ahora tiene {colacoins[str(user.id)]} ColaCoins.")
        await self.save_data()

    @commands.admin_or_permissions(administrator=True)
    @commands.command(name="removecolacoins")
    async def remove_colacoins(self, ctx, user: discord.Member, amount: int):
        """Quita ColaCoins a un usuario."""
        async with self.config.colacoins() as colacoins:
            if str(user.id) not in colacoins or colacoins[str(user.id)] < amount:
                await ctx.send(f"No se puede quitar {amount} ColaCoins. {user.display_name} no tiene suficientes ColaCoins.")
                return
            colacoins[str(user.id)] -= amount
            await ctx.send(f"{amount} ColaCoins quitadas a {user.display_name}. Ahora tiene {colacoins[str(user.id)]} ColaCoins.")
        await self.save_data()

    @commands.admin_or_permissions(administrator=True)
    @commands.command(name="vercolacoins")
    async def ver_colacoins(self, ctx, user: discord.Member):
        """Verifica la cantidad de ColaCoins de un usuario."""
        colacoins = await self.config.colacoins()
        amount = colacoins.get(str(user.id), 0)
        await ctx.send(f"{user.display_name} tiene {amount} ColaCoins.")

    @commands.command(name="colacoins")
    async def user_colacoins(self, ctx):
        """Permite a un usuario ver cuántas ColaCoins tiene."""
        colacoins = await self.config.colacoins()
        amount = colacoins.get(str(ctx.author.id), 0)
        await ctx.send(f"Tienes {amount} ColaCoins.")
