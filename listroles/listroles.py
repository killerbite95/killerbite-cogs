import discord
from redbot.core import commands
import logging

class ListRoles(commands.Cog):
    """Cog para listar los roles del servidor con su nombre e ID."""
    __author__ = "Killerbite95"  # Aquí se declara el autor
    __version__ = "1.0.0"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.log = logging.getLogger("red.cog.listroles")

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """Agrega la versión del cog al mensaje de ayuda."""
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nVersion: {self.__version__}"

    @commands.command(name="listroles")
    async def listroles(self, ctx: commands.Context):
        """Lista todos los roles del servidor con su nombre e ID."""
        roles = ctx.guild.roles
        if not roles:
            return await ctx.send("No se encontraron roles en este servidor.")

        # Genera una lista con cada línea: Nombre: ID
        role_lines = [f"{role.name}: {role.id}" for role in roles]
        role_text = "\n".join(role_lines)

        # Verifica si el mensaje excede el límite de 2000 caracteres
        if len(role_text) > 2000:
            # Si es muy largo, lo envía como un archivo de texto
            await ctx.send(file=discord.File(fp=role_text.encode("utf-8"), filename="roles.txt"))
        else:
            await ctx.send(f"Roles del servidor:\n{role_text}")
