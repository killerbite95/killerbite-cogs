import asyncio
import contextlib
import logging
from copy import deepcopy
from datetime import datetime, timezone
from typing import List, Optional

import aiohttp
import discord
from redbot.core import Config, app_commands, commands
from redbot.core.commands.converter import TimedeltaConverter
from redbot.core.utils.chat_formatting import pagify
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu

from .converter import Args, EditArgs
from .menu import GiveawayButton, GiveawayView
from .objects import Giveaway, GiveawayEnterError, GiveawayExecError

log = logging.getLogger("red.killerbite95.giveaways")
GIVEAWAY_KEY = "giveaways"

# Theme colors for guide embeds
GW_BLUE = discord.Color.from_rgb(88, 101, 242)
GW_GREEN = discord.Color.from_rgb(87, 242, 135)
GW_GOLD = discord.Color.from_rgb(254, 231, 92)
GW_RED = discord.Color.from_rgb(237, 66, 69)
GW_PURPLE = discord.Color.from_rgb(155, 89, 182)


class Giveaways(commands.Cog):
    """Giveaway Commands"""

    __version__ = "2.0.0"
    __author__ = "flare, killerbite95"

    def format_help_for_context(self, ctx):
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=95932766180343808)
        self.config.init_custom(GIVEAWAY_KEY, 2)
        self.config.register_guild(
            defaults={
                "update_button": True,
                "congratulate": True,
                "notify": True,
                "show_requirements": True,
                "emoji": "🎉",
                "button-text": "Join Giveaway",
                "button-style": "green",
                "announce": False,
            },
            presets={},
            history=[],
        )
        self.giveaways = {}
        self.giveaway_bgloop = asyncio.create_task(self.init())
        self.session = None
        with contextlib.suppress(Exception):
            self.bot.add_dev_env_value("giveaways", lambda x: self)
        self.view = GiveawayView(self)
        bot.add_view(self.view)

    async def init(self) -> None:
        await self.bot.wait_until_ready()
        self.session = aiohttp.ClientSession()
        data = await self.config.custom(GIVEAWAY_KEY).all()
        for _, guild in data.items():
            for msgid, giveaway in guild.items():
                try:
                    if giveaway.get("ended", False):
                        continue
                    giveaway["endtime"] = datetime.fromtimestamp(giveaway["endtime"]).replace(
                        tzinfo=timezone.utc
                    )
                    giveaway_obj = Giveaway(
                        giveaway["guildid"],
                        giveaway["channelid"],
                        giveaway["messageid"],
                        giveaway["endtime"],
                        giveaway["prize"],
                        giveaway.get("emoji", "🎉"),
                        entrants=giveaway.get("entrants", []),
                        **giveaway.get("kwargs", {}),
                    )
                    self.giveaways[int(msgid)] = giveaway_obj
                    view = GiveawayView(self)
                    view.add_item(
                        GiveawayButton(
                            label=giveaway["kwargs"].get("button-text", "Join Giveaway"),
                            style=giveaway["kwargs"].get("button-style", "green"),
                            emoji=giveaway["emoji"],
                            cog=self,
                            id=giveaway["messageid"],
                            update=giveaway.get("kwargs", {}).get("update_button", False),
                        )
                    )
                    self.bot.add_view(view)
                except Exception as exc:
                    log.error(f"Error loading giveaway {msgid}: ", exc_info=exc)
        while True:
            try:
                await self.check_giveaways()
            except Exception as exc:
                log.error("Exception in giveaway loop: ", exc_info=exc)
            await asyncio.sleep(15)

    def cog_unload(self) -> None:
        with contextlib.suppress(Exception):
            self.bot.remove_dev_env_value("giveaways")
        self.giveaway_bgloop.cancel()
        if self.session:
            asyncio.create_task(self.session.close())

    async def check_giveaways(self) -> None:
        to_clear = []
        for msgid, giveaway in list(self.giveaways.items()):
            if giveaway.endtime < datetime.now(timezone.utc):
                winner_ids = await self.draw_winner(giveaway)
                to_clear.append(msgid)
                gw = await self.config.custom(GIVEAWAY_KEY, giveaway.guildid, str(msgid)).all()
                gw["ended"] = True
                await self.config.custom(GIVEAWAY_KEY, giveaway.guildid, str(msgid)).set(gw)
                await self._save_history(giveaway, winner_ids)
        for msgid in to_clear:
            del self.giveaways[msgid]

    async def _save_history(self, giveaway: Giveaway, winner_ids) -> None:
        """Save a giveaway result to guild history."""
        try:
            async with self.config.guild_from_id(giveaway.guildid).history() as history:
                history.append({
                    "prize": giveaway.prize,
                    "winners": winner_ids or [],
                    "ended_at": datetime.now(timezone.utc).timestamp(),
                    "channel_id": giveaway.channelid,
                    "message_id": giveaway.messageid,
                    "entrant_count": len(set(giveaway.entrants)),
                })
                if len(history) > 50:
                    del history[:-50]
        except Exception as exc:
            log.error("Error saving giveaway history: ", exc_info=exc)

    async def draw_winner(self, giveaway: Giveaway):
        guild = self.bot.get_guild(giveaway.guildid)
        if guild is None:
            return None
        channel_obj = guild.get_channel(giveaway.channelid)
        if channel_obj is None:
            return None

        winners = giveaway.draw_winner()
        winner_objs = None
        if winners is None:
            txt = "Not enough entries to roll the giveaway."
        else:
            winner_objs = []
            txt = ""
            for winner in winners:
                winner_obj = guild.get_member(winner)
                if winner_obj is None:
                    txt += f"{winner} (Not Found)\n"
                else:
                    txt += f"{winner_obj.mention} ({winner_obj.display_name})\n"
                    winner_objs.append(winner_obj)

        msg = channel_obj.get_partial_message(giveaway.messageid)
        winner_count = giveaway.kwargs.get("winners", 1) or 1
        embed = discord.Embed(
            title=f"{f'{winner_count}x ' if winner_count > 1 else ''}{giveaway.prize}",
            description=f"Winner(s):\n{txt}",
            color=await self.bot.get_embed_color(channel_obj),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(
            text=f"Reroll: {(await self.bot.get_prefix(msg))[-1]}gw reroll {giveaway.messageid} | Ended at"
        )
        try:
            await msg.edit(content="🎉 Giveaway Ended 🎉", embed=embed, view=None)
        except (discord.NotFound, discord.Forbidden) as exc:
            log.error("Error editing giveaway message: ", exc_info=exc)
            return winners
        if giveaway.kwargs.get("announce"):
            announce_embed = discord.Embed(
                title="Giveaway Ended",
                description=f"Congratulations to the {f'{str(winner_count)} ' if winner_count > 1 else ''}winner{'s' if winner_count > 1 else ''} of [{giveaway.prize}]({msg.jump_url}).\n{txt}",
                color=await self.bot.get_embed_color(channel_obj),
            )

            announce_embed.set_footer(
                text=f"Reroll: {(await self.bot.get_prefix(msg))[-1]}gw reroll {giveaway.messageid}"
            )
            await channel_obj.send(
                content=(
                    "Congratulations " + ",".join([x.mention for x in winner_objs])
                    if winner_objs is not None
                    else ""
                ),
                embed=announce_embed,
            )
        if winner_objs is not None:
            if giveaway.kwargs.get("congratulate", False):
                for winner in winner_objs:
                    with contextlib.suppress(discord.Forbidden):
                        await winner.send(
                            f"Congratulations! You won {giveaway.prize} in the giveaway on {guild}!"
                        )
        return winners

    async def _giveaway_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[int]]:
        """Autocomplete for active giveaway IDs in the current guild."""
        choices = []
        for msgid, gw in self.giveaways.items():
            if gw.guildid != interaction.guild_id:
                continue
            label = f"{gw.prize} (ID: {msgid})"
            if current.lower() in label.lower() or current in str(msgid):
                choices.append(app_commands.Choice(name=label[:100], value=msgid))
            if len(choices) >= 25:
                break
        return choices

    def _make_guide_embed(self, title: str, description: str, color: discord.Color):
        """Helper to create a themed guide embed."""
        return discord.Embed(title=title, description=description, color=color)

    async def _apply_guild_defaults(self, ctx: commands.Context, arguments: dict) -> dict:
        """Apply guild defaults to arguments where not explicitly set."""
        defaults = await self.config.guild(ctx.guild).defaults()
        for key, default_val in defaults.items():
            if arguments.get(key) is None:
                arguments[key] = default_val
        return arguments

    async def _create_advanced_giveaway(self, ctx: commands.Context, arguments: dict) -> None:
        """Shared logic for creating an advanced giveaway (used by advanced, preset use)."""
        prize = arguments["prize"]
        duration = arguments["duration"]
        channel = arguments["channel"] or ctx.channel

        winner_count = arguments.get("winners", 1) or 1
        end = datetime.now(timezone.utc) + duration
        description = arguments["description"] or ""

        # Apply guild default for show_requirements
        show_reqs = arguments.get("show_requirements")
        if show_reqs is None:
            defaults = await self.config.guild(ctx.guild).defaults()
            show_reqs = defaults.get("show_requirements", True)
        if show_reqs:
            req_text = self.generate_settings_text(ctx, arguments)
            if req_text:
                description += "\n\n**Requirements:**\n" + req_text

        emoji = arguments["emoji"] or "🎉"
        if isinstance(emoji, int):
            emoji = self.bot.get_emoji(emoji)
        hosted_by = ctx.guild.get_member(arguments.get("hosted-by", ctx.author.id)) or ctx.author
        embed = discord.Embed(
            title=f"{f'{winner_count}x ' if winner_count > 1 else ''}{prize}",
            description=f"{description}\n\nClick the button below to enter\n\n**Hosted by:** {hosted_by.mention}\n\nEnds: <t:{int(end.timestamp())}:R>",
            color=arguments.get("colour", await ctx.embed_color()),
        )
        if arguments["image"] is not None:
            embed.set_image(url=arguments["image"])
        if arguments["thumbnail"] is not None:
            embed.set_thumbnail(url=arguments["thumbnail"])
        embed.set_footer(text="🎉 0 participants")

        txt = "\n"
        if arguments["ateveryone"]:
            txt += "@everyone "
        if arguments["athere"]:
            txt += "@here "
        if arguments["mentions"]:
            for mention in arguments["mentions"]:
                role = ctx.guild.get_role(mention)
                if role is not None:
                    txt += f"{role.mention} "

        update_btn = arguments.get("update_button")
        if update_btn is None:
            defaults = await self.config.guild(ctx.guild).defaults()
            update_btn = defaults.get("update_button", True)

        view = GiveawayView(self)
        msg = await channel.send(
            content=f"🎉 Giveaway 🎉{txt}",
            embed=embed,
            allowed_mentions=discord.AllowedMentions(
                roles=bool(arguments["mentions"]),
                everyone=bool(arguments["ateveryone"]),
            ),
        )
        view.add_item(
            GiveawayButton(
                label=arguments["button-text"] or "Join Giveaway",
                style=arguments["button-style"] or "green",
                emoji=emoji,
                cog=self,
                update=update_btn,
                id=msg.id,
            )
        )
        self.bot.add_view(view)
        await msg.edit(view=view)
        if ctx.interaction:
            await ctx.send("Giveaway created!", ephemeral=True)

        giveaway_obj = Giveaway(
            ctx.guild.id,
            channel.id,
            msg.id,
            end,
            prize,
            str(emoji),
            **{
                k: v
                for k, v in arguments.items()
                if k not in ["prize", "duration", "channel", "emoji"]
            },
        )
        self.giveaways[msg.id] = giveaway_obj
        giveaway_dict = deepcopy(giveaway_obj.__dict__)
        giveaway_dict["endtime"] = giveaway_dict["endtime"].timestamp()
        giveaway_dict.get("kwargs", {}).pop("colour", None)
        await self.config.custom(GIVEAWAY_KEY, str(ctx.guild.id), str(msg.id)).set(giveaway_dict)

    @commands.hybrid_group(aliases=["gw"])
    @commands.bot_has_permissions(add_reactions=True, embed_links=True)
    @commands.has_permissions(manage_guild=True)
    async def giveaway(self, ctx: commands.Context):
        """
        Manage the giveaway system.

        Use `[p]gw guide` for a full interactive guide.
        """

    @giveaway.command()
    @commands.has_permissions(manage_guild=True)
    @app_commands.describe(
        channel="The channel in which to start the giveaway.",
        time="The time the giveaway should last.",
        prize="The prize for the giveaway.",
    )
    async def start(
        self,
        ctx: commands.Context,
        channel: Optional[discord.TextChannel],
        time: TimedeltaConverter(default_unit="minutes"),
        *,
        prize: str,
    ):
        """
        Start a giveaway.

        This by default will DM the winner and also DM a user if they cannot enter the giveaway.
        """
        channel = channel or ctx.channel
        defaults = await self.config.guild(ctx.guild).defaults()
        end = datetime.now(timezone.utc) + time

        emoji = defaults.get("emoji", "🎉")
        button_text = defaults.get("button-text", "Join Giveaway")
        button_style = defaults.get("button-style", "green")
        update_button = defaults.get("update_button", True)
        congratulate = defaults.get("congratulate", True)
        notify = defaults.get("notify", True)

        embed = discord.Embed(
            title=f"{prize}",
            description=f"\nClick the button below to enter\n\n**Hosted by:** {ctx.author.mention}\n\nEnds: <t:{int(end.timestamp())}:R>",
            color=await ctx.embed_color(),
        )
        embed.set_footer(text="🎉 0 participants")
        view = GiveawayView(self)

        msg = await channel.send(embed=embed)
        view.add_item(
            GiveawayButton(
                label=button_text,
                style=button_style,
                emoji=emoji,
                cog=self,
                id=msg.id,
                update=update_button,
            )
        )
        self.bot.add_view(view)
        await msg.edit(view=view)
        giveaway_obj = Giveaway(
            ctx.guild.id,
            channel.id,
            msg.id,
            end,
            prize,
            emoji,
            **{
                "congratulate": congratulate,
                "notify": notify,
                "update_button": update_button,
                "button-text": button_text,
                "button-style": button_style,
            },
        )
        if ctx.interaction:
            await ctx.send("Giveaway created!", ephemeral=True)
        self.giveaways[msg.id] = giveaway_obj
        giveaway_dict = deepcopy(giveaway_obj.__dict__)
        giveaway_dict["endtime"] = giveaway_dict["endtime"].timestamp()
        await self.config.custom(GIVEAWAY_KEY, str(ctx.guild.id), str(msg.id)).set(giveaway_dict)

    @giveaway.command()
    @commands.has_permissions(manage_guild=True)
    @app_commands.describe(msgid="The message ID of the giveaway to reroll.")
    @app_commands.autocomplete(msgid=_giveaway_autocomplete)
    async def reroll(self, ctx: commands.Context, msgid: int):
        """Reroll a giveaway."""
        data = await self.config.custom(GIVEAWAY_KEY, ctx.guild.id).all()
        if str(msgid) not in data:
            return await ctx.send("Giveaway not found.")
        if msgid in self.giveaways:
            return await ctx.send(
                f"Giveaway already running. Please wait for it to end or end it via `{ctx.clean_prefix}gw end {msgid}`."
            )
        giveaway_dict = data[str(msgid)]
        giveaway_dict["endtime"] = datetime.fromtimestamp(giveaway_dict["endtime"]).replace(
            tzinfo=timezone.utc
        )
        giveaway = Giveaway(
            giveaway_dict["guildid"],
            giveaway_dict["channelid"],
            giveaway_dict["messageid"],
            giveaway_dict["endtime"],
            giveaway_dict.get("prize", "Unknown"),
            giveaway_dict.get("emoji", "🎉"),
            entrants=giveaway_dict.get("entrants", []),
            **giveaway_dict.get("kwargs", {}),
        )
        try:
            await self.draw_winner(giveaway)
        except GiveawayExecError as e:
            await ctx.send(e.message)
        else:
            await ctx.tick()

    @giveaway.command()
    @commands.has_permissions(manage_guild=True)
    @app_commands.describe(msgid="The message ID of the giveaway to end.")
    @app_commands.autocomplete(msgid=_giveaway_autocomplete)
    async def end(self, ctx: commands.Context, msgid: int):
        """End a giveaway."""
        if msgid in self.giveaways:
            if self.giveaways[msgid].guildid != ctx.guild.id:
                return await ctx.send("Giveaway not found.")
            giveaway = self.giveaways[msgid]
            winner_ids = await self.draw_winner(giveaway)
            del self.giveaways[msgid]
            gw = await self.config.custom(GIVEAWAY_KEY, ctx.guild.id, str(msgid)).all()
            gw["ended"] = True
            await self.config.custom(GIVEAWAY_KEY, ctx.guild.id, str(msgid)).set(gw)
            await self._save_history(giveaway, winner_ids)
            await ctx.tick()
        else:
            await ctx.send("Giveaway not found.")

    @giveaway.command(aliases=["adv"])
    @commands.has_permissions(manage_guild=True)
    @app_commands.describe(
        arguments="The arguments for the giveaway. See `[p]gw explain` for more info."
    )
    async def advanced(self, ctx: commands.Context, *, arguments: Args):
        """Advanced creation of Giveaways.


        `[p]gw explain` for a further full listing of the arguments.
        """
        arguments = await self._apply_guild_defaults(ctx, arguments)
        await self._create_advanced_giveaway(ctx, arguments)

    @giveaway.command()
    @commands.has_permissions(manage_guild=True)
    @app_commands.describe(msgid="The message ID of the giveaway.")
    @app_commands.autocomplete(msgid=_giveaway_autocomplete)
    async def entrants(self, ctx: commands.Context, msgid: int):
        """List all entrants for a giveaway (active or ended)."""
        giveaway = self.giveaways.get(msgid)
        entrants_list = None
        prize = "Unknown"
        if giveaway:
            entrants_list = giveaway.entrants
            prize = giveaway.prize
        else:
            # Check ended giveaways in config
            data = await self.config.custom(GIVEAWAY_KEY, ctx.guild.id, str(msgid)).all()
            if data:
                entrants_list = data.get("entrants", [])
                prize = data.get("prize", "Unknown")

        if entrants_list is None:
            return await ctx.send("Giveaway not found.")
        if not entrants_list:
            return await ctx.send("No entrants.")
        count = {}
        for entrant in entrants_list:
            if entrant not in count:
                count[entrant] = 1
            else:
                count[entrant] += 1
        msg = ""
        for userid, count_int in count.items():
            user = ctx.guild.get_member(userid)
            extra = f" ×{count_int}" if count_int > 1 else ""
            msg += f"{user.mention}{extra}\n" if user else f"<{userid}>{extra}\n"
        embeds = []
        for page in pagify(msg, delims=["\n"], page_length=800):
            embed = discord.Embed(
                title=f"Entrants — {prize}", description=page, color=await ctx.embed_color()
            )
            embed.set_footer(text=f"Total unique entrants: {len(count)}")
            embeds.append(embed)

        if len(embeds) == 1:
            return await ctx.send(embed=embeds[0])
        return await menu(ctx, embeds, DEFAULT_CONTROLS)

    @giveaway.command()
    @commands.has_permissions(manage_guild=True)
    @app_commands.describe(msgid="The message ID of the giveaway.")
    @app_commands.autocomplete(msgid=_giveaway_autocomplete)
    async def info(self, ctx: commands.Context, msgid: int):
        """Information about a giveaway (active or ended)."""
        giveaway = self.giveaways.get(msgid)
        if giveaway:
            winner_count = giveaway.kwargs.get("winners", 1) or 1
            msg = f"**Status:** 🟢 Active\n**Entrants:** {len(set(giveaway.entrants))}\n**End:** <t:{int(giveaway.endtime.timestamp())}:R>\n"
            for kwarg in giveaway.kwargs:
                if giveaway.kwargs[kwarg]:
                    msg += f"**{kwarg.title()}:** {giveaway.kwargs[kwarg]}\n"
            embed = discord.Embed(
                title=f"{f'{winner_count}x ' if winner_count > 1 else ''}{giveaway.prize}",
                color=await ctx.embed_color(),
                description=msg,
            )
            embed.set_footer(text=f"Giveaway ID #{msgid}")
            return await ctx.send(embed=embed)

        # Check ended giveaways in config
        data = await self.config.custom(GIVEAWAY_KEY, ctx.guild.id, str(msgid)).all()
        if not data:
            return await ctx.send("Giveaway not found.")

        winner_count = data.get("kwargs", {}).get("winners", 1) or 1
        prize = data.get("prize", "Unknown")
        entrants = data.get("entrants", [])
        ended = data.get("ended", False)
        msg = f"**Status:** {'🔴 Ended' if ended else '⚪ Unknown'}\n"
        msg += f"**Entrants:** {len(set(entrants))}\n"
        kwargs = data.get("kwargs", {})
        for kwarg, value in kwargs.items():
            if value:
                msg += f"**{kwarg.title()}:** {value}\n"
        embed = discord.Embed(
            title=f"{f'{winner_count}x ' if winner_count > 1 else ''}{prize}",
            color=await ctx.embed_color(),
            description=msg,
        )
        embed.set_footer(text=f"Giveaway ID #{msgid}")
        await ctx.send(embed=embed)

    @giveaway.command(name="list")
    @commands.has_permissions(manage_guild=True)
    async def _list(self, ctx: commands.Context):
        """List all giveaways in the server."""
        if not self.giveaways:
            return await ctx.send("No giveaways are running.")
        giveaways = {
            x: self.giveaways[x]
            for x in self.giveaways
            if self.giveaways[x].guildid == ctx.guild.id
        }
        if not giveaways:
            return await ctx.send("No giveaways are running.")
        msg = "".join(
            f"{msgid}: [{giveaways[msgid].prize}](https://discord.com/channels/{value.guildid}/{giveaways[msgid].channelid}/{msgid})\n"
            for msgid, value in giveaways.items()
        )

        embeds = []
        for page in pagify(msg, delims=["\n"]):
            embed = discord.Embed(
                title=f"Giveaways in {ctx.guild}", description=page, color=await ctx.embed_color()
            )
            embeds.append(embed)
        if len(embeds) == 1:
            return await ctx.send(embed=embeds[0])
        return await menu(ctx, embeds, DEFAULT_CONTROLS)

    @giveaway.command()
    @commands.has_permissions(manage_guild=True)
    async def explain(self, ctx: commands.Context):
        """Explanation of giveaway advanced and the arguments it supports."""
        pages = []
        color = await ctx.embed_color()

        em1 = discord.Embed(title="Giveaway Advanced — Required Arguments", color=color)
        em1.description = (
            "**NOTE:** Giveaways are checked every 15 seconds, so they may end slightly later than specified.\n\n"
            "**Required arguments:**\n"
            "`--prize` / `-p`: The prize to be won.\n\n"
            "**Duration (one required):**\n"
            "`--duration` / `-d`: Duration like `2d3h30m`.\n"
            "`--end` / `-e`: End time like `tomorrow at 3am`, `2024-12-25T00:00:00Z`.\n\n"
            "**Optional:**\n"
            "`--channel`: The channel to post in (defaults to current).\n"
            "`--emoji`: Custom emoji for the giveaway.\n"
            "`--winners`: Number of winners to draw.\n"
            "`--description`: Description shown on the embed.\n"
            "`--hosted-by`: Override the host user."
        )
        em1.set_footer(text=f"Page 1/3 — {ctx.clean_prefix}gw explain")
        pages.append(em1)

        em2 = discord.Embed(title="Giveaway Advanced — Restrictions & Styling", color=color)
        em2.description = (
            "**Restrictions:**\n"
            "`--roles`: Restrict to specific roles.\n"
            "`--blacklist`: Blacklisted roles.\n"
            "`--joined`: Minimum days in server.\n"
            "`--created`: Minimum account age in days.\n"
            "`--cost`: Credit cost to enter.\n"
            "`--bypass-roles`: Roles that bypass restrictions.\n"
            "`--bypass-type`: `or` (any role) or `and` (all roles).\n\n"
            "**Multipliers:**\n"
            "`--multiplier` / `-m`: Entry multiplier.\n"
            "`--multi-roles` / `-mr`: Roles that receive the multiplier.\n\n"
            "**Styling:**\n"
            "`--colour`: Embed color.\n"
            "`--image`: Embed image URL.\n"
            "`--thumbnail`: Embed thumbnail URL.\n"
            "`--button-text`: Custom button text.\n"
            "`--button-style`: `green`, `blurple`, `grey`, or `red`.\n"
            "`--mentions`: Roles to @mention.\n"
            "`--ateveryone` / `--athere`: Mention everyone/here."
        )
        em2.set_footer(text=f"Page 2/3 — {ctx.clean_prefix}gw explain")
        pages.append(em2)

        em3 = discord.Embed(title="Giveaway Advanced — Toggles & Integrations", color=color)
        em3.description = (
            "**Toggles:**\n"
            "`--congratulate`: DM winners.\n"
            "`--notify`: DM users who fail to enter.\n"
            "`--multientry`: Allow multiple entries.\n"
            "`--announce`: Post a separate end message.\n"
            "`--show-requirements`: Show requirements in embed.\n"
            "`--update-button`: Update button with entrant count.\n\n"
            "**3rd Party Integrations:**\n"
            "`--level-req`: Red Leveler level.\n"
            "`--rep-req`: Red Leveler rep.\n"
            "`--tatsu-level` / `--tatsu-rep`: Tatsumaki.\n"
            "`--mee6-level`: MEE6 level.\n"
            "`--amari-level` / `--amari-weekly-xp`: Amari.\n\n"
            "**Examples:**\n"
            f"`{ctx.clean_prefix}gw adv --prize Nitro --duration 1h30m --winners 2 --congratulate`\n"
            f"`{ctx.clean_prefix}gw adv --prize VIP Role --end tomorrow at 6pm --roles @Members --cost 500`"
        )
        em3.set_footer(text=f"Page 3/3 — {ctx.clean_prefix}gw explain")
        pages.append(em3)

        if len(pages) == 1:
            return await ctx.send(embed=pages[0])
        await menu(ctx, pages, DEFAULT_CONTROLS)

    @giveaway.command()
    @commands.has_permissions(manage_guild=True)
    async def edit(self, ctx, msgid: int, *, flags: EditArgs):
        """Edit a giveaway.

        See `[p]gw explain` for more info on the flags.
        """
        if msgid not in self.giveaways:
            return await ctx.send("Giveaway not found.")
        giveaway = self.giveaways[msgid]
        if giveaway.guildid != ctx.guild.id:
            return await ctx.send("Giveaway not found.")
        if flags.get("prize"):
            giveaway.prize = flags["prize"]
        if flags.get("emoji"):
            giveaway.emoji = flags["emoji"]
        if flags.get("duration"):
            giveaway.endtime = datetime.now(timezone.utc) + flags["duration"]
        skip = {"prize", "duration", "end", "channel", "emoji"}
        for key, value in flags.items():
            if key in skip or not value:
                continue
            giveaway.kwargs[key] = value

        self.giveaways[msgid] = giveaway
        giveaway_dict = deepcopy(giveaway.__dict__)
        giveaway_dict["endtime"] = giveaway_dict["endtime"].timestamp()
        giveaway_dict.get("kwargs", {}).pop("colour", None)
        await self.config.custom(GIVEAWAY_KEY, ctx.guild.id, str(msgid)).set(giveaway_dict)
        channel = ctx.guild.get_channel(giveaway.channelid)
        if channel:
            message = channel.get_partial_message(giveaway.messageid)
            hosted_by = (
                ctx.guild.get_member(giveaway.kwargs.get("hosted-by", ctx.author.id)) or ctx.author
            )
            winners = giveaway.kwargs.get("winners", 1) or 1
            description = giveaway.kwargs.get("description", "") or ""
            new_embed = discord.Embed(
                title=f"{f'{winners}x ' if winners > 1 else ''}{giveaway.prize}",
                description=f"{description}\n\nClick the button below to enter\n\n**Hosted by:** {hosted_by.mention}\n\nEnds: <t:{int(giveaway_dict['endtime'])}:R>",
                color=flags.get("colour", await ctx.embed_color()),
            )
            if giveaway.kwargs.get("image"):
                new_embed.set_image(url=giveaway.kwargs["image"])
            if giveaway.kwargs.get("thumbnail"):
                new_embed.set_thumbnail(url=giveaway.kwargs["thumbnail"])
            with contextlib.suppress(discord.HTTPException):
                await message.edit(embed=new_embed)
        await ctx.tick()

    @giveaway.command()
    @commands.has_permissions(manage_guild=True)
    async def integrations(self, ctx: commands.Context):
        """Various 3rd party integrations for giveaways."""

        msg = """
        3rd party integrations for giveaways.

        You can use these integrations to integrate giveaways with other 3rd party services.

        `--level-req`: Integrate with the Red Level system Must be Fixator's leveler.
        `--rep-req`: Integrate with the Red Level Rep system Must be Fixator's leveler.
        `--tatsu-level`: Integrate with the Tatsumaki's levelling system, must have a valid Tatsumaki API key set.
        `--tatsu-rep`: Integrate with the Tatsumaki's rep system, must have a valid Tatsumaki API key set.
        `--mee6-level`: Integrate with the MEE6 levelling system.
        `--amari-level`: Integrate with the Amari's levelling system.
        `--amari-weekly-xp`: Integrate with the Amari's weekly xp system.""".format(
            prefix=ctx.clean_prefix
        )
        if await self.bot.is_owner(ctx.author):
            msg += """
                **API Keys**
                Tatsu's API key can be set with the following command (You must find where this key is yourself): `{prefix}set api tatsumaki authorization <key>`
                Amari's API key can be set with the following command (Apply [here](https://docs.google.com/forms/d/e/1FAIpQLScQDCsIqaTb1QR9BfzbeohlUJYA3Etwr-iSb0CRKbgjA-fq7Q/viewform)): `{prefix}set api amari authorization <key>`


                For any integration suggestions, suggest them via the [#support-flare-cogs](https://discord.gg/GET4DVk) channel on the support server or [flare-cogs](https://github.com/flaree/flare-cogs/issues/new/choose) github.""".format(
                prefix=ctx.clean_prefix
            )

        embed = discord.Embed(
            title="3rd Party Integrations", description=msg, color=await ctx.embed_color()
        )
        await ctx.send(embed=embed)

    def generate_settings_text(self, ctx: commands.Context, args):
        msg = ""

        def _role_text(role_id):
            role = ctx.guild.get_role(role_id)
            return role.mention if role else f"<deleted role {role_id}>"

        if args.get("roles"):
            msg += f"**Roles:** {', '.join(_role_text(x) for x in args['roles'])}\n"
        if args.get("multi"):
            msg += f"**Multiplier:** {args['multi']}\n"
        if args.get("multi-roles"):
            msg += f"**Multiplier Roles:** {', '.join(_role_text(x) for x in args['multi-roles'])}\n"
        if args.get("cost"):
            msg += f"**Cost:** {args['cost']}\n"
        if args.get("joined"):
            msg += f"**Joined:** {args['joined']} days\n"
        if args.get("created"):
            msg += f"**Created:** {args['created']} days\n"
        if args.get("blacklist"):
            msg += f"**Blacklist:** {', '.join(_role_text(x) for x in args['blacklist'])}\n"
        if args.get("winners"):
            msg += f"**Winners:** {args['winners']}\n"
        if args.get("mee6_level"):
            msg += f"**MEE6 Level:** {args['mee6_level']}\n"
        if args.get("amari_level"):
            msg += f"**Amari Level:** {args['amari_level']}\n"
        if args.get("amari_weekly_xp"):
            msg += f"**Amari Weekly XP:** {args['amari_weekly_xp']}\n"
        if args.get("tatsu_level"):
            msg += f"**Tatsu Level:** {args['tatsu_level']}\n"
        if args.get("tatsu_rep"):
            msg += f"**Tatsu Rep:** {args['tatsu_rep']}\n"
        if args.get("level_req"):
            msg += f"**Level Requirement:** {args['level_req']}\n"
        if args.get("rep_req"):
            msg += f"**Rep Requirement:** {args['rep_req']}\n"
        if args.get("bypass-roles"):
            msg += f"**Bypass Roles:** {', '.join(_role_text(x) for x in args['bypass-roles'])} ({args['bypass-type']})\n"

        return msg

    # ═══════════════════════════════════════════════════════════
    #  CANCEL / CLEANUP / DELETE
    # ═══════════════════════════════════════════════════════════

    @giveaway.command()
    @commands.has_permissions(manage_guild=True)
    @app_commands.describe(msgid="The message ID of the giveaway to cancel.")
    @app_commands.autocomplete(msgid=_giveaway_autocomplete)
    async def cancel(self, ctx: commands.Context, msgid: int):
        """Cancel a giveaway without drawing winners."""
        if msgid not in self.giveaways:
            return await ctx.send("Giveaway not found or already ended.")
        giveaway = self.giveaways[msgid]
        if giveaway.guildid != ctx.guild.id:
            return await ctx.send("Giveaway not found.")

        # Edit the original message
        guild = self.bot.get_guild(giveaway.guildid)
        channel_obj = guild.get_channel(giveaway.channelid) if guild else None
        if channel_obj:
            msg = channel_obj.get_partial_message(giveaway.messageid)
            embed = discord.Embed(
                title=f"~~{giveaway.prize}~~",
                description="🚫 Giveaway cancelled.",
                color=discord.Color.dark_grey(),
                timestamp=datetime.now(timezone.utc),
            )
            embed.set_footer(text="Cancelled")
            with contextlib.suppress(discord.HTTPException):
                await msg.edit(content="🚫 Giveaway Cancelled", embed=embed, view=None)

        del self.giveaways[msgid]
        gw = await self.config.custom(GIVEAWAY_KEY, ctx.guild.id, str(msgid)).all()
        gw["ended"] = True
        gw["cancelled"] = True
        await self.config.custom(GIVEAWAY_KEY, ctx.guild.id, str(msgid)).set(gw)
        await ctx.send(f"Giveaway for **{giveaway.prize}** has been cancelled.")

    @giveaway.command()
    @commands.has_permissions(manage_guild=True)
    async def cleanup(self, ctx: commands.Context):
        """Remove all ended giveaways from the config for this server."""
        data = await self.config.custom(GIVEAWAY_KEY, ctx.guild.id).all()
        if not data:
            return await ctx.send("No giveaway data found.")
        removed = 0
        for msgid, gw in list(data.items()):
            if gw.get("ended", False):
                await self.config.custom(GIVEAWAY_KEY, ctx.guild.id, str(msgid)).clear()
                removed += 1
        if removed == 0:
            return await ctx.send("No ended giveaways to clean up.")
        await ctx.send(f"Cleaned up **{removed}** ended giveaway(s) from the config.")

    @giveaway.command()
    @commands.has_permissions(manage_guild=True)
    @app_commands.describe(msgid="The message ID of the giveaway to delete.")
    async def delete(self, ctx: commands.Context, msgid: int):
        """Delete a specific giveaway from the config."""
        data = await self.config.custom(GIVEAWAY_KEY, ctx.guild.id, str(msgid)).all()
        if not data:
            return await ctx.send("Giveaway not found.")
        if msgid in self.giveaways:
            return await ctx.send(
                f"This giveaway is still active. Use `{ctx.clean_prefix}gw end {msgid}` or `{ctx.clean_prefix}gw cancel {msgid}` first."
            )
        prize = data.get("prize", "Unknown")
        await self.config.custom(GIVEAWAY_KEY, ctx.guild.id, str(msgid)).clear()
        await ctx.send(f"Giveaway **{prize}** (ID: {msgid}) deleted from config.")

    # ═══════════════════════════════════════════════════════════
    #  HISTORY
    # ═══════════════════════════════════════════════════════════

    @giveaway.command()
    @commands.has_permissions(manage_guild=True)
    async def history(self, ctx: commands.Context):
        """View recent giveaway history (last 50)."""
        hist = await self.config.guild(ctx.guild).history()
        if not hist:
            return await ctx.send("No giveaway history yet.")

        msg = ""
        for entry in reversed(hist):
            prize = entry.get("prize", "Unknown")
            winners = entry.get("winners", [])
            ended_at = entry.get("ended_at", 0)
            entrant_count = entry.get("entrant_count", 0)
            winner_text = ", ".join(
                f"<@{w}>" for w in winners
            ) if winners else "No winners"
            msg += (
                f"**{prize}** — <t:{int(ended_at)}:R>\n"
                f"  Winners: {winner_text} | Entrants: {entrant_count}\n\n"
            )

        embeds = []
        for page in pagify(msg, delims=["\n\n"], page_length=1000):
            embed = discord.Embed(
                title=f"Giveaway History — {ctx.guild.name}",
                description=page,
                color=await ctx.embed_color(),
            )
            embeds.append(embed)

        if len(embeds) == 1:
            return await ctx.send(embed=embeds[0])
        return await menu(ctx, embeds, DEFAULT_CONTROLS)

    # ═══════════════════════════════════════════════════════════
    #  SERVER DEFAULTS (gw set)
    # ═══════════════════════════════════════════════════════════

    @giveaway.group(name="set")
    @commands.has_permissions(manage_guild=True)
    async def gw_set(self, ctx: commands.Context):
        """Configure default giveaway settings for this server."""

    @gw_set.command(name="show")
    @commands.has_permissions(manage_guild=True)
    async def gw_set_show(self, ctx: commands.Context):
        """Show current default giveaway settings."""
        defaults = await self.config.guild(ctx.guild).defaults()
        lines = []
        for key, value in defaults.items():
            if isinstance(value, bool):
                lines.append(f"**{key}:** {'✅ On' if value else '❌ Off'}")
            else:
                lines.append(f"**{key}:** {value}")
        embed = discord.Embed(
            title=f"Giveaway Defaults — {ctx.guild.name}",
            description="\n".join(lines) or "No defaults set.",
            color=await ctx.embed_color(),
        )
        embed.set_footer(text=f"Use {ctx.clean_prefix}gw set <key> <value> to change")
        await ctx.send(embed=embed)

    @gw_set.command(name="updatebutton")
    @commands.has_permissions(manage_guild=True)
    async def gw_set_updatebutton(self, ctx: commands.Context, enabled: bool):
        """Set whether to update the button with entrant count by default."""
        async with self.config.guild(ctx.guild).defaults() as defaults:
            defaults["update_button"] = enabled
        await ctx.tick()

    @gw_set.command(name="congratulate")
    @commands.has_permissions(manage_guild=True)
    async def gw_set_congratulate(self, ctx: commands.Context, enabled: bool):
        """Set whether to DM winners by default."""
        async with self.config.guild(ctx.guild).defaults() as defaults:
            defaults["congratulate"] = enabled
        await ctx.tick()

    @gw_set.command(name="notify")
    @commands.has_permissions(manage_guild=True)
    async def gw_set_notify(self, ctx: commands.Context, enabled: bool):
        """Set whether to DM users when they fail to enter by default."""
        async with self.config.guild(ctx.guild).defaults() as defaults:
            defaults["notify"] = enabled
        await ctx.tick()

    @gw_set.command(name="showrequirements")
    @commands.has_permissions(manage_guild=True)
    async def gw_set_showrequirements(self, ctx: commands.Context, enabled: bool):
        """Set whether to show requirements on the embed by default."""
        async with self.config.guild(ctx.guild).defaults() as defaults:
            defaults["show_requirements"] = enabled
        await ctx.tick()

    @gw_set.command(name="announce")
    @commands.has_permissions(manage_guild=True)
    async def gw_set_announce(self, ctx: commands.Context, enabled: bool):
        """Set whether to post a separate announcement when a giveaway ends."""
        async with self.config.guild(ctx.guild).defaults() as defaults:
            defaults["announce"] = enabled
        await ctx.tick()

    @gw_set.command(name="emoji")
    @commands.has_permissions(manage_guild=True)
    async def gw_set_emoji(self, ctx: commands.Context, emoji: str):
        """Set the default emoji for giveaways."""
        async with self.config.guild(ctx.guild).defaults() as defaults:
            defaults["emoji"] = emoji
        await ctx.tick()

    @gw_set.command(name="buttontext")
    @commands.has_permissions(manage_guild=True)
    async def gw_set_buttontext(self, ctx: commands.Context, *, text: str):
        """Set the default button text for giveaways."""
        if len(text) > 70:
            return await ctx.send("Button text must be less than 70 characters.")
        async with self.config.guild(ctx.guild).defaults() as defaults:
            defaults["button-text"] = text
        await ctx.tick()

    @gw_set.command(name="buttonstyle")
    @commands.has_permissions(manage_guild=True)
    async def gw_set_buttonstyle(self, ctx: commands.Context, style: str):
        """Set the default button style. Options: green, blurple, grey, red."""
        from .menu import BUTTON_STYLE
        if style.lower() not in BUTTON_STYLE:
            return await ctx.send(f"Style must be one of: {', '.join(BUTTON_STYLE.keys())}")
        async with self.config.guild(ctx.guild).defaults() as defaults:
            defaults["button-style"] = style.lower()
        await ctx.tick()

    # ═══════════════════════════════════════════════════════════
    #  PRESETS (gw preset)
    # ═══════════════════════════════════════════════════════════

    @giveaway.group()
    @commands.has_permissions(manage_guild=True)
    async def preset(self, ctx: commands.Context):
        """Manage giveaway presets (reusable templates)."""

    @preset.command(name="save")
    @commands.has_permissions(manage_guild=True)
    async def preset_save(self, ctx: commands.Context, name: str, *, flags: str):
        """Save a giveaway preset. Use the same flags as `gw advanced`.

        The preset stores your flags so you can reuse them.
        Prize and duration are optional in presets.

        Example: `[p]gw preset save weekly --winners 3 --congratulate --announce --roles @Members`
        """
        try:
            await EditArgs().convert(ctx, flags)
        except Exception as e:
            return await ctx.send(f"Invalid flags: {e}")
        async with self.config.guild(ctx.guild).presets() as presets:
            presets[name.lower()] = flags
        await ctx.send(f"✅ Preset **{name}** saved.")

    @preset.command(name="use")
    @commands.has_permissions(manage_guild=True)
    async def preset_use(self, ctx: commands.Context, name: str, *, extra_flags: str = ""):
        """Use a preset to create a giveaway.

        You can add extra flags to override preset values.
        Prize and duration must be provided (in preset or extra flags).

        Example: `[p]gw preset use weekly --prize Nitro --duration 2d`
        """
        presets = await self.config.guild(ctx.guild).presets()
        if name.lower() not in presets:
            return await ctx.send(f"Preset `{name}` not found. Use `{ctx.clean_prefix}gw preset list` to see all presets.")
        combined = presets[name.lower()] + " " + extra_flags
        try:
            arguments = await Args().convert(ctx, combined)
        except Exception as e:
            return await ctx.send(f"Error: {e}")
        arguments = await self._apply_guild_defaults(ctx, arguments)
        await self._create_advanced_giveaway(ctx, arguments)

    @preset.command(name="list")
    @commands.has_permissions(manage_guild=True)
    async def preset_list(self, ctx: commands.Context):
        """List all saved presets."""
        presets = await self.config.guild(ctx.guild).presets()
        if not presets:
            return await ctx.send("No presets saved yet.")
        msg = ""
        for name, flags in presets.items():
            msg += f"**{name}** — `{flags[:80]}{'...' if len(flags) > 80 else ''}`\n"
        embed = discord.Embed(
            title=f"Giveaway Presets — {ctx.guild.name}",
            description=msg,
            color=await ctx.embed_color(),
        )
        await ctx.send(embed=embed)

    @preset.command(name="delete")
    @commands.has_permissions(manage_guild=True)
    async def preset_delete(self, ctx: commands.Context, name: str):
        """Delete a saved preset."""
        async with self.config.guild(ctx.guild).presets() as presets:
            if name.lower() not in presets:
                return await ctx.send(f"Preset `{name}` not found.")
            del presets[name.lower()]
        await ctx.send(f"Preset **{name}** deleted.")

    # ═══════════════════════════════════════════════════════════
    #  QUICK CREATE (gw create)
    # ═══════════════════════════════════════════════════════════

    @giveaway.command(name="create")
    @commands.has_permissions(manage_guild=True)
    @app_commands.describe(
        prize="The prize for the giveaway.",
        duration="How long the giveaway lasts (e.g. 1h30m, 2d, 30m).",
        winners="Number of winners (default: 1).",
        channel="The channel for the giveaway (defaults to current).",
        description="Optional description for the giveaway.",
    )
    async def create(
        self,
        ctx: commands.Context,
        prize: str,
        duration: TimedeltaConverter(default_unit="minutes"),
        winners: Optional[int] = 1,
        channel: Optional[discord.TextChannel] = None,
        *,
        description: Optional[str] = None,
    ):
        """Create a giveaway with simple parameters.

        Works with both prefix and slash commands.

        Examples:
        `[p]gw create Nitro 1h30m`
        `[p]gw create "Steam Key" 2d 3 #giveaways`
        `/giveaway create prize:Nitro duration:1h30m winners:2`
        """
        channel = channel or ctx.channel
        if winners is None or winners < 1:
            winners = 1

        defaults = await self.config.guild(ctx.guild).defaults()
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
                f"**Hosted by:** {ctx.author.mention}\n\n"
                f"Ends: <t:{int(end.timestamp())}:R>"
            ),
            color=await ctx.embed_color(),
        )
        embed.set_footer(text="🎉 0 participants")

        view = GiveawayView(self)
        msg = await channel.send(embed=embed)
        view.add_item(
            GiveawayButton(
                label=button_text,
                style=button_style,
                emoji=emoji,
                cog=self,
                id=msg.id,
                update=update_button,
            )
        )
        self.bot.add_view(view)
        await msg.edit(view=view)

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
            ctx.guild.id, channel.id, msg.id, end, prize, emoji,
            **kwargs,
        )
        self.giveaways[msg.id] = giveaway_obj
        giveaway_dict = deepcopy(giveaway_obj.__dict__)
        giveaway_dict["endtime"] = giveaway_dict["endtime"].timestamp()
        await self.config.custom(GIVEAWAY_KEY, str(ctx.guild.id), str(msg.id)).set(giveaway_dict)

        if ctx.interaction:
            await ctx.send("Giveaway created!", ephemeral=True)
        else:
            await ctx.tick()

    # ═══════════════════════════════════════════════════════════
    #  GUIDE / HELP (gw guide)
    # ═══════════════════════════════════════════════════════════

    @giveaway.command(name="guide")
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def guide(self, ctx: commands.Context):
        """📖 Full guide for the Giveaway system."""
        p = ctx.prefix
        pages = []
        footer_tpl = "🎉 Page {current}/{total} — Giveaways v{version}"

        # ── Page 1: Introduction ──
        em1 = self._make_guide_embed(
            "📖 Guide — Getting Started",
            "Welcome to the **Giveaway System**! 🎉\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**Quick Start:**\n"
            f"Use `{p}gw start #channel 1h Prize Name` to create a simple giveaway.\n\n"
            "**Interactive Creation:**\n"
            f"Use `/gw create` (slash command) to create a giveaway with a form.\n\n"
            "**Advanced Giveaways:**\n"
            f"Use `{p}gw advanced` with flags for full customization: "
            "role restrictions, multipliers, costs, descriptions, custom embeds, and more.\n\n"
            "**How it works:**\n"
            "Users click the button on the giveaway message to enter. "
            "When time is up, winners are drawn automatically and announced.",
            GW_BLUE,
        )
        em1.set_footer(text=footer_tpl.format(current=1, total=5, version=self.__version__))
        pages.append(em1)

        # ── Page 2: Features ──
        em2 = self._make_guide_embed(
            "⚙️ Guide — Features",
            "The giveaway system includes many powerful features:\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🔒 **Role Restrictions** — Limit who can enter by roles.\n\n"
            "🚫 **Blacklists** — Block specific roles from entering.\n\n"
            "✖️ **Multipliers** — Give specific roles extra entries.\n\n"
            "💰 **Entry Cost** — Charge credits to enter.\n\n"
            "📅 **Account Age** — Minimum account/server age.\n\n"
            "👥 **Multiple Winners** — Draw more than one winner.\n\n"
            "🔄 **Rerolls** — Reroll ended giveaways if needed.\n\n"
            "🎨 **Customizable** — Colors, images, emojis, button styles.\n\n"
            "📨 **DM Notifications** — Notify winners and failed entries.\n\n"
            "🔗 **3rd Party** — MEE6, Tatsu, Amari, Leveler integrations.",
            GW_GREEN,
        )
        em2.set_footer(text=footer_tpl.format(current=2, total=5, version=self.__version__))
        pages.append(em2)

        # ── Page 3: Server Defaults & Presets ──
        em3 = self._make_guide_embed(
            "🛠️ Guide — Defaults & Presets",
            "Customize defaults and save reusable templates:\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**Server Defaults:**\n"
            "Configure default settings that apply to all new giveaways.\n"
            f"`{p}gw set show` — View current defaults\n"
            f"`{p}gw set updatebutton true/false`\n"
            f"`{p}gw set congratulate true/false`\n"
            f"`{p}gw set notify true/false`\n"
            f"`{p}gw set showrequirements true/false`\n"
            f"`{p}gw set announce true/false`\n"
            f"`{p}gw set emoji 🎁`\n"
            f"`{p}gw set buttontext Join Now!`\n"
            f"`{p}gw set buttonstyle blurple`\n\n"
            "**Presets (Templates):**\n"
            "Save commonly used flag combinations.\n"
            f"`{p}gw preset save weekly --winners 3 --congratulate --roles @Members`\n"
            f"`{p}gw preset use weekly --prize Nitro --duration 7d`\n"
            f"`{p}gw preset list` — View all presets\n"
            f"`{p}gw preset delete weekly`",
            GW_GOLD,
        )
        em3.set_footer(text=footer_tpl.format(current=3, total=5, version=self.__version__))
        pages.append(em3)

        # ── Page 4: Managing Giveaways ──
        em4 = self._make_guide_embed(
            "📋 Guide — Managing Giveaways",
            "Commands for managing active and ended giveaways:\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**While Active:**\n"
            f"`{p}gw list` — List all active giveaways\n"
            f"`{p}gw info <id>` — View giveaway details\n"
            f"`{p}gw entrants <id>` — List all participants\n"
            f"`{p}gw edit <id> [flags]` — Edit an active giveaway\n"
            f"`{p}gw end <id>` — End and draw winners now\n"
            f"`{p}gw cancel <id>` — Cancel without drawing\n\n"
            "**After Ended:**\n"
            f"`{p}gw reroll <id>` — Reroll winners\n"
            f"`{p}gw info <id>` — View ended giveaway info\n"
            f"`{p}gw entrants <id>` — View entrants of ended giveaway\n"
            f"`{p}gw history` — View recent giveaway history\n\n"
            "**Maintenance:**\n"
            f"`{p}gw cleanup` — Remove all ended giveaways from config\n"
            f"`{p}gw delete <id>` — Delete a specific ended giveaway",
            GW_PURPLE,
        )
        em4.set_footer(text=footer_tpl.format(current=4, total=5, version=self.__version__))
        pages.append(em4)

        # ── Page 5: Command Reference ──
        em5 = self._make_guide_embed(
            "📚 Guide — Command Reference",
            "Full list of available commands:\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            GW_RED,
        )
        em5.add_field(
            name="🎉 Creation",
            value=(
                f"`{p}gw start [#ch] <time> <prize>` — Quick giveaway\n"
                f"`{p}gw create [#ch]` — Interactive form (slash)\n"
                f"`{p}gw advanced <flags>` — Full customization\n"
                f"`{p}gw preset use <name> [flags]` — From template"
            ),
            inline=False,
        )
        em5.add_field(
            name="🔧 Management",
            value=(
                f"`{p}gw list` — Active giveaways\n"
                f"`{p}gw info <id>` — Details\n"
                f"`{p}gw entrants <id>` — Participants\n"
                f"`{p}gw edit <id> <flags>` — Edit active\n"
                f"`{p}gw end <id>` — End & draw\n"
                f"`{p}gw cancel <id>` — Cancel\n"
                f"`{p}gw reroll <id>` — Reroll winners"
            ),
            inline=False,
        )
        em5.add_field(
            name="⚙️ Configuration",
            value=(
                f"`{p}gw set show` — View defaults\n"
                f"`{p}gw set <key> <value>` — Change default\n"
                f"`{p}gw preset save/use/list/delete`\n"
                f"`{p}gw history` — Winner history\n"
                f"`{p}gw cleanup` — Clear ended data\n"
                f"`{p}gw explain` — Flag reference\n"
                f"`{p}gw integrations` — 3rd party info"
            ),
            inline=False,
        )
        em5.set_footer(text=footer_tpl.format(current=5, total=5, version=self.__version__))
        pages.append(em5)

        await menu(ctx, pages, DEFAULT_CONTROLS)
