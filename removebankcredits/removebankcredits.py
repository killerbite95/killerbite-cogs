from redbot.core import commands, bank
import discord
from redbot.core.bot import Red

class RemoveBankCredits(commands.Cog):
    """Gestión de créditos para usuarios inactivos o baneados."""

    def __init__(self, bot: Red):
        self.bot = bot

    @commands.admin_or_permissions(administrator=True)
    @commands.command(name="removeeconomy")
    async def remove_economy(self, ctx: commands.Context, user_id: int, amount: int):
        """Quita créditos de un usuario por su ID.

        Uso: !removeeconomy <user_id> <cantidad>
        """
        try:
            # Buscar al usuario por su ID
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
            if not user:
                await ctx.send("No se encontró un usuario con ese ID.")
                return

            # Verificar si la cuenta está creada; si no, se crea automáticamente
            if not await bank.is_global():
                await bank.create_account(user)

            if not await bank.has_account(user):
                await ctx.send("El usuario no tiene una cuenta registrada.")
                return

            current_balance = await bank.get_balance(user)

            if amount > current_balance:
                await ctx.send(f"El usuario solo tiene {current_balance} créditos, no se puede eliminar {amount}.")
                return

            # Eliminar los créditos especificados
            await bank.withdraw_credits(user, amount)
            await ctx.send(f"Se han eliminado {amount} créditos a {user.name}. Ahora tiene {current_balance - amount} créditos.")

        except Exception as e:
            await ctx.send(f"Error: {e}")
