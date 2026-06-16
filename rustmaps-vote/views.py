"""Discord views for RustMaps Vote COG. By Killerbite95

The buttons carry custom_ids in the form ``rustmaps_vote:vote:{session_id}:{map_id}``
and are handled entirely by the cog's ``on_interaction`` listener, so they keep
working after a bot restart without needing ``bot.add_view`` registration.
"""

import discord
from typing import List


class VoteView(discord.ui.View):
    """Persistent voting view with one numbered button per map in the session."""

    def __init__(self, session_id: int, map_ids: List[int], channel_id: int):
        super().__init__(timeout=None)  # persistent
        self.session_id = session_id
        self.map_ids = map_ids
        self.channel_id = channel_id

        for map_id in map_ids:
            self.add_item(
                discord.ui.Button(
                    label=str(map_id),
                    style=discord.ButtonStyle.primary,
                    custom_id=f"rustmaps_vote:vote:{session_id}:{map_id}",
                    row=(map_id - 1) // 5,
                )
            )
