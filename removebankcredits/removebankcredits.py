import discord
from redbot.core import commands, bank
from redbot.core.errors import BalanceTooHigh

class RemoveBankCredits(commands.Cog):
    """Cog para gestionar la eliminación de créditos de usuarios baneados"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="removeeconomy")
    @commands.admin_or_permissions(administrator=True)
    async def remove_economy(self, ctx, user_id: int, amount: int):
        """Elimina una cantidad específica de créditos de la cuenta de un usuario."""
        try:
            # Intentar obtener el miembro del servidor
            user = self.bot.get_user(user_id)
            if not user:
                await ctx.send(f"Usuario con ID {user_id} no encontrado.")
                return

            # Verificar si el usuario tiene una cuenta de banco
            if not await bank.is_global():
                if not await bank.account_exists(user):
                    await ctx.send("La cuenta del usuario no existe.")
                    return

            # Verificar si el usuario tiene suficientes créditos
            balance = await bank.get_balance(user)
            if balance < amount:
                await ctx.send(f"El usuario no tiene suficientes créditos. Balance actual: {balance}.")
                return

            # Remover créditos
            await bank.withdraw_credits(user, amount)
            await ctx.send(f"{amount} créditos removidos de la cuenta de {user.mention}.")
        except BalanceTooHigh:
            await ctx.send("El balance es demasiado alto para hacer la operación.")
        except Exception as e:
            await ctx.send(f"Ha ocurrido un error: {e}")
