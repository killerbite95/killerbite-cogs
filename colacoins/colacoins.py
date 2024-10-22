import json
import os
from redbot.core import commands, Config
import discord

class ColaCoins(commands.Cog):
    """Gestiona las ColaCoins para los usuarios. By Killerbite95"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_global = {
            "colacoins": {},
            "emoji": ""  # Emoji predeterminado, inicialmente vacío
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
        """Da ColaCoins a un usuario. / Give ColaCoins to a user."""
        async with self.config.colacoins() as colacoins:
            if str(user.id) not in colacoins:
                colacoins[str(user.id)] = 0
            colacoins[str(user.id)] += amount
            emoji = await self.config.emoji() or ""
            await ctx.send(f"{amount} {emoji} ColaCoins dados a {user.display_name}. Ahora tiene {colacoins[str(user.id)]} {emoji} ColaCoins." if ctx.invoked_with == 'darcolacoins' else f"{amount} {emoji} ColaCoins given to {user.display_name}. Now they have {colacoins[str(user.id)]} {emoji} ColaCoins.")
        await self.save_data()

    @commands.admin_or_permissions(administrator=True)
    @commands.command(name="removecolacoins", aliases=["quitarcolacoins"])
    async def remove_colacoins(self, ctx, user: discord.Member, amount: int):
        """Quita ColaCoins a un usuario. / Remove ColaCoins from a user."""
        async with self.config.colacoins() as colacoins:
            if str(user.id) not in colacoins or colacoins[str(user.id)] < amount:
                await ctx.send(f"No se puede quitar {amount} {emoji} ColaCoins. {user.display_name} no tiene suficientes ColaCoins." if ctx.invoked_with == 'quitarcolacoins' else f"Cannot remove {amount} {emoji} ColaCoins. {user.display_name} does not have enough ColaCoins.")
                return
            colacoins[str(user.id)] -= amount
            emoji = await self.config.emoji() or ""
            await ctx.send(f"{amount} {emoji} ColaCoins quitadas a {user.display_name}. Ahora tiene {colacoins[str(user.id)]} {emoji} ColaCoins. " if ctx.invoked_with == 'quitarcolacoins' else f"{amount} {emoji} ColaCoins removed from {user.display_name}. Now they have {colacoins[str(user.id)]} {emoji} ColaCoins.")
        await self.save_data()

    @commands.admin_or_permissions(administrator=True)
    @commands.command(name="vercolacoins", aliases=["viewcolacoins"])
    async def ver_colacoins(self, ctx, user: discord.Member):
        """Verifica la cantidad de ColaCoins de un usuario. / Check the ColaCoins amount of a user."""
        colacoins = await self.config.colacoins()
        amount = colacoins.get(str(user.id), 0)
        emoji = await self.config.emoji() or ""
        await ctx.send(f"{user.display_name} tiene {amount} {emoji} ColaCoins." if ctx.invoked_with == 'vercolacoins' else f"{user.display_name} has {amount}  {emoji} ColaCoins.")

    @commands.command(name="colacoins", aliases=["miscolacoins"])
    async def user_colacoins(self, ctx):
        """Permite a un usuario ver cuántas ColaCoins tiene. / Allows a user to see how many ColaCoins they have."""
        colacoins = await self.config.colacoins()
        amount = colacoins.get(str(ctx.author.id), 0)
        emoji = await self.config.emoji() or ""
        await ctx.send(f"Tienes {amount} {emoji} ColaCoins." if ctx.invoked_with == 'miscolacoins' else f"You have {amount} {emoji} ColaCoins.")

    @commands.admin_or_permissions(administrator=True)
    @commands.command(name="setcolacoinemoji", aliases=["establecercolacoinemoji"])
    async def set_colacoin_emoji(self, ctx, emoji: str):
        """Establece el emoji para las ColaCoins. / Set the emoji for ColaCoins."""
        await self.config.emoji.set(emoji)
        await ctx.send(f"Emoji de ColaCoins establecido a {emoji}." if ctx.invoked_with == 'establecercolacoinemoji' else f"ColaCoins emoji set to {emoji}.")
