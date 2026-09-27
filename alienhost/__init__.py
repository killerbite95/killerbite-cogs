from redbot.core import errors
from redbot.core.bot import Red
from redbot.core.utils import get_end_user_data_statement

try:
    import cryptography  # noqa: F401
except ModuleNotFoundError:
    raise errors.CogLoadError(
        "AlienHost necesita `cryptography` para cifrar las claves API. Ejecuta `[p]pipinstall cryptography`."
    )

from .alienhost import AlienHost

__red_end_user_data_statement__ = get_end_user_data_statement(__file__)


async def setup(bot: Red) -> None:
    await bot.add_cog(AlienHost(bot))
