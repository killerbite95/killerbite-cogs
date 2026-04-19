import discord
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n
import logging

_ = Translator("ListRoles", __file__)


@cog_i18n(_)
class ListRoles(commands.Cog):
    """Cog to list server roles with their name and ID."""
    __author__ = "Killerbite95"
    __version__ = "1.0.0"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.log = logging.getLogger("red.cog.listroles")

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nVersion: {self.__version__}"

    @commands.command(name="listroles")
    async def listroles(self, ctx: commands.Context):
        """List all server roles with their name and ID."""
        roles = ctx.guild.roles
        if not roles:
            return await ctx.send(_("No roles found in this server."))

        role_lines = [f"{role.name}: {role.id}" for role in roles]
        role_text = "\n".join(role_lines)

        if len(role_text) > 2000:
            await ctx.send(file=discord.File(fp=role_text.encode("utf-8"), filename="roles.txt"))
        else:
            await ctx.send(_("Server roles:") + f"\n{role_text}")
