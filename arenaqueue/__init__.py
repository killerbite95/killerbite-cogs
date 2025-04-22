# -*- coding: utf-8 -*-
"""
arenaqueue Cog for Red Discord Bot
Provides in‐house queue management with seasons, challenges, captain picks,
MMR decay, suspensions, webhook integrations, presets and admin utilities.
"""

from redbot.core.utils import get_end_user_data_statement
from .queue import QueueCog
from .challenges import ChallengesCog
from .seasons import SeasonsCog
from .tasks import SeasonTasks
from .captain import CaptainQueueCog
from .decay import DecayCog
from .suspend import SuspendCog
from .webhooks import WebhooksCog
from .presets import PresetsCog
from .admin_utils import AdminUtilsCog

# Reutiliza la declaración de datos de usuario finales desde info.json
__red_end_user_data_statement__ = get_end_user_data_statement(__file__)

async def setup(bot):
    """Punto de entrada para cargar los Cogs de arenaqueue."""
    await bot.add_cog(QueueCog(bot))
    await bot.add_cog(ChallengesCog(bot))
    await bot.add_cog(SeasonsCog(bot))
    await bot.add_cog(SeasonTasks(bot))
    await bot.add_cog(CaptainQueueCog(bot))
    await bot.add_cog(DecayCog(bot))
    await bot.add_cog(SuspendCog(bot))
    await bot.add_cog(WebhooksCog(bot))
    await bot.add_cog(PresetsCog(bot))
    await bot.add_cog(AdminUtilsCog(bot))
