import discord
from redbot.core import commands, bank

class RemoveBankCredits(commands.Cog):
    """Cog para gestionar la eliminación de créditos de usuarios baneados"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="removeeconomy")
    @commands.admin_or_permissions(administrator=True)
    async def remove_economy(self, ctx, user_id: int, amount: int):
        """Elimina una cantidad específica de créditos de la cuenta de un usuario."""
        user = self.bot.get_user(user_id) or discord.Object(id=user_id)

        try:
            # Intentar obtener el balance para verificar si la cuenta existe
            balance = await bank.get_balance(user)
        except ValueError:
            await ctx.send(f"La cuenta del usuario con ID {user_id} no existe.")
            return

        # Verificar si el usuario tiene suficientes créditos
        if balance < amount:
            await ctx.send(f"El usuario no tiene suficientes créditos. Balance actual: {balance}.")
            return

        try:
            # Remover créditos
            await bank.withdraw_credits(user, amount)
            await ctx.send(f"{amount} créditos removidos de la cuenta de {user_id}.")
        except Exception as e:
            await ctx.send(f"Ha ocurrido un error: {e}")
