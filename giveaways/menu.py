import logging
import re
from datetime import datetime, timedelta, timezone

import discord
from discord.ui import Button, Modal, TextInput, View

from .objects import AlreadyEnteredError, GiveawayEnterError, GiveawayExecError

log = logging.getLogger("red.killerbite95.giveaways")


class GiveawayView(View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog


BUTTON_STYLE = {
    "blurple": discord.ButtonStyle.primary,
    "grey": discord.ButtonStyle.secondary,
    "green": discord.ButtonStyle.success,
    "red": discord.ButtonStyle.danger,
    "gray": discord.ButtonStyle.secondary,
}


class GiveawayButton(Button):
    def __init__(
        self,
        label: str,
        style: str,
        emoji,
        cog,
        id,
        update=False,
    ):
        super().__init__(
            label=label, style=BUTTON_STYLE[style], emoji=emoji, custom_id=f"giveaway_button:{id}"
        )
        self.default_label = label
        self.update = update
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        if interaction.message.id in self.cog.giveaways:
            giveaway = self.cog.giveaways[interaction.message.id]
            await interaction.response.defer()
            try:
                await giveaway.add_entrant(
                    interaction.user, bot=self.cog.bot, session=self.cog.session
                )
            except GiveawayEnterError as e:
                await interaction.followup.send(e.message, ephemeral=True)
                return
            except GiveawayExecError as e:
                log.exception("Error while adding user to giveaway", exc_info=e)
                return
            except AlreadyEnteredError:
                await interaction.followup.send(
                    "You have been removed from the giveaway.", ephemeral=True
                )
                await self.update_entrant(giveaway, interaction)
                await self.update_label(giveaway, interaction)
                return
            await self.update_entrant(giveaway, interaction)
            await interaction.followup.send(
                f"You have been entered into the giveaway for {giveaway.prize}.",
                ephemeral=True,
            )
            await self.update_label(giveaway, interaction)

    async def update_entrant(self, giveaway, interaction):
        await self.cog.config.custom(
            "giveaways", interaction.guild_id, interaction.message.id
        ).entrants.set(self.cog.giveaways[interaction.message.id].entrants)

    async def update_label(self, giveaway, interaction):
        if self.update:
            count = len(set(giveaway.entrants))
            if count >= 1:
                self.label = f"{self.default_label} ({count})"
            else:
                self.label = self.default_label
            # Also update embed footer with participant count
            embed = interaction.message.embeds[0] if interaction.message.embeds else None
            if embed:
                embed.set_footer(text=f"🎉 {count} participant{'s' if count != 1 else ''}")
                await interaction.message.edit(embed=embed, view=self.view)
            else:
                await interaction.message.edit(view=self.view)


def _parse_duration(text: str):
    """Parse a human-friendly duration like '1d2h30m' into a timedelta."""
    pattern = r'(?:(\d+)\s*d)?[\s,]*(?:(\d+)\s*h)?[\s,]*(?:(\d+)\s*m)?[\s,]*(?:(\d+)\s*s)?'
    match = re.fullmatch(pattern, text.strip(), re.IGNORECASE)
    if not match or not any(match.groups()):
        return None
    d, h, m, s = (int(g or 0) for g in match.groups())
    return timedelta(days=d, hours=h, minutes=m, seconds=s)


class GiveawayCreateModal(Modal, title="🎉 Create Giveaway"):
    prize_input = TextInput(
        label="Prize",
        placeholder="What's the prize?",
        required=True,
        max_length=200,
    )
    duration_input = TextInput(
        label="Duration (e.g. 1h30m, 2d, 30m)",
        placeholder="1h30m",
        required=True,
        max_length=50,
    )
    winners_input = TextInput(
        label="Number of Winners",
        placeholder="1",
        required=False,
        default="1",
        max_length=3,
    )
    description_input = TextInput(
        label="Description (optional)",
        placeholder="Optional description for the giveaway",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=1000,
    )

    def __init__(self, cog, channel: discord.TextChannel):
        super().__init__()
        self.cog = cog
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        prize = self.prize_input.value.strip()
        duration_text = self.duration_input.value.strip()
        winners_text = self.winners_input.value.strip() or "1"
        description = self.description_input.value.strip()

        duration = _parse_duration(duration_text)
        if duration is None or duration.total_seconds() < 60:
            return await interaction.response.send_message(
                "Invalid duration. Use formats like `1h30m`, `2d`, `30m`. Minimum 1 minute.",
                ephemeral=True,
            )

        try:
            winners = int(winners_text)
            if winners < 1:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message(
                "Number of winners must be a positive number.", ephemeral=True
            )

        guild = interaction.guild
        defaults = await self.cog.config.guild(guild).guild_defaults()

        end = datetime.now(timezone.utc) + duration
        emoji = defaults.get("emoji", "🎉")
        button_text = defaults.get("button-text", "Join Giveaway")
        button_style = defaults.get("button-style", "green")
        update_button = defaults.get("update_button", True)
        congratulate = defaults.get("congratulate", True)
        notify = defaults.get("notify", True)

        desc_text = f"{description}\n\n" if description else ""
        embed = discord.Embed(
            title=f"{f'{winners}x ' if winners > 1 else ''}{prize}",
            description=(
                f"{desc_text}Click the button below to enter\n\n"
                f"**Hosted by:** {interaction.user.mention}\n\n"
                f"Ends: <t:{int(end.timestamp())}:R>"
            ),
            color=discord.Color.greyple(),
        )
        embed.set_footer(text="🎉 0 participants")

        view = GiveawayView(self.cog)
        msg = await self.channel.send(embed=embed)
        view.add_item(
            GiveawayButton(
                label=button_text,
                style=button_style,
                emoji=emoji,
                cog=self.cog,
                id=msg.id,
                update=update_button,
            )
        )
        self.cog.bot.add_view(view)
        await msg.edit(view=view)

        from copy import deepcopy
        from .objects import Giveaway

        kwargs = {
            "congratulate": congratulate,
            "notify": notify,
            "update_button": update_button,
            "button-text": button_text,
            "button-style": button_style,
            "winners": winners,
        }
        if description:
            kwargs["description"] = description

        giveaway_obj = Giveaway(
            guild.id, self.channel.id, msg.id, end, prize, emoji,
            **kwargs,
        )
        self.cog.giveaways[msg.id] = giveaway_obj
        giveaway_dict = deepcopy(giveaway_obj.__dict__)
        giveaway_dict["endtime"] = giveaway_dict["endtime"].timestamp()
        await self.cog.config.custom(
            "giveaways", str(guild.id), str(msg.id)
        ).set(giveaway_dict)

        await interaction.response.send_message("Giveaway created!", ephemeral=True)
