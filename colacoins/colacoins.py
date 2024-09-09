import json
import os
from redbot.core import commands, Config
import discord

class ColaCoins(commands.Cog):
    """Manage ColaCoins for users."""

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
    @commands.command(name="givecolacoins", aliases=["darcolacoins"])
    async def give_colacoins(self, ctx, user: discord.Member, amount: int):
        """Gives ColaCoins to a user. / Da ColaCoins a un usuario."""
        async with self.config.colacoins() as colacoins:
            if str(user.id) not in colacoins:
                colacoins[str(user.id)] = 0
            colacoins[str(user.id)] += amount

            response = (
                f"{amount} ColaCoins given to {user.display_name}. They now have {colacoins[str(user.id)]} ColaCoins."
                if ctx.invoked_with == "givecolacoins" 
                else f"{amount} ColaCoins dados a {user.display_name}. Ahora tiene {colacoins[str(user.id)]} ColaCoins."
            )
            await ctx.send(response)
        await self.save_data()

    @commands.admin_or_permissions(administrator=True)
    @commands.command(name="removecolacoins", aliases=["quitacolacoins"])
    async def remove_colacoins(self, ctx, user: discord.Member, amount: int):
        """Removes ColaCoins from a user. / Quita ColaCoins a un usuario."""
        async with self.config.colacoins() as colacoins:
            if str(user.id) not in colacoins or colacoins[str(user.id)] < amount:
                response = (
                    f"Cannot remove {amount} ColaCoins. {user.display_name} does not have enough ColaCoins."
                    if ctx.invoked_with == "removecolacoins" 
                    else f"No se puede quitar {amount} ColaCoins. {user.display_name} no tiene suficientes ColaCoins."
                )
                await ctx.send(response)
                return

            colacoins[str(user.id)] -= amount
            response = (
                f"{amount} ColaCoins removed from {user.display_name}. They now have {colacoins[str(user.id)]} ColaCoins."
                if ctx.invoked_with == "removecolacoins" 
                else f"{amount} ColaCoins quitadas a {user.display_name}. Ahora tiene {colacoins[str(user.id)]} ColaCoins."
            )
            await ctx.send(response)
        await self.save_data()

    @commands.admin_or_permissions(administrator=True)
    @commands.command(name="viewcolacoins", aliases=["vercolacoins"])
    async def view_colacoins(self, ctx, user: discord.Member):
        """Check the amount of ColaCoins a user has. / Verifica la cantidad de ColaCoins de un usuario."""
        colacoins = await self.config.colacoins()
        amount = colacoins.get(str(user.id), 0)
        response = (
            f"{user.display_name} has {amount} ColaCoins."
            if ctx.invoked_with == "viewcolacoins" 
            else f"{user.display_name} tiene {amount} ColaCoins."
        )
        await ctx.send(response)

    @commands.command(name="colacoins", aliases=["miscolacoins"])
    async def user_colacoins(self, ctx):
        """Allows a user to see how many ColaCoins they have. / Permite a un usuario ver cuántas ColaCoins tiene."""
        colacoins = await self.config.colacoins()
        amount = colacoins.get(str(ctx.author.id), 0)
        response = (
            f"You have {amount} ColaCoins."
            if ctx.invoked_with == "colacoins" 
            else f"Tienes {amount} ColaCoins."
        )
        await ctx.send(response)
