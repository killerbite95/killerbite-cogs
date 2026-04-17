import asyncio
import datetime
import logging
import time
from typing import Literal, Optional

import discord
import random
import math
from discord.ext import tasks
from redbot.core import commands, checks, Config, bank
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import box, pagify, humanize_number
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS

logger = logging.getLogger("red.killerbite95.trickortreat")

__version__ = "3.0.0"
__author__ = ["aikaterna", "Killerbite95"]

_ = Translator("TrickOrTreat", __file__)

# ──── Halloween Colors ────
HALLOWEEN_ORANGE = 0xF4731C
HALLOWEEN_PURPLE = 0x7B2D8B
HALLOWEEN_GREEN = 0x2ECC71
HALLOWEEN_RED = 0xE74C3C
HALLOWEEN_GOLD = 0xF1C40F
HALLOWEEN_DARK = 0x2C2F33

# ──── Candy Constants ────
CANDY_ALIASES = {
    "candy": "candies", "candies": "candies", "\U0001f36c": "candies",
    "chocolate": "chocolates", "chocolates": "chocolates", "\U0001f36b": "chocolates",
    "lollipop": "lollipops", "lollipops": "lollipops", "\U0001f36d": "lollipops",
    "cookie": "cookies", "cookies": "cookies", "\U0001f960": "cookies",
    "star": "stars", "stars": "stars", "\u2b50": "stars",
    "golden_candy": "golden_candies", "golden_candies": "golden_candies", "golden": "golden_candies",
    "ghost_pepper": "ghost_peppers", "ghost_peppers": "ghost_peppers", "pepper": "ghost_peppers",
}
CANDY_TYPES = ["candies", "chocolates", "lollipops", "cookies", "stars", "golden_candies", "ghost_peppers"]
CANDY_EMOJIS = {
    "candies": "\N{CANDY}",
    "chocolates": "\N{CHOCOLATE BAR}",
    "lollipops": "\N{LOLLIPOP}",
    "cookies": "\N{FORTUNE COOKIE}",
    "stars": "\N{WHITE MEDIUM STAR}",
    "golden_candies": "✨",
    "ghost_peppers": "🌶️",
}

# ──── Bonus Drop Table ────
# (min_roll, max_roll, quantity) — first match wins
BONUS_TABLE = {
    "chocolates": [
        (100, 100, 6), (95, 99, 5), (90, 94, 4),
        (80, 89, 3), (75, 79, 2), (70, 74, 1),
    ],
    "lollipops": [
        (100, 100, 4), (95, 99, 3), (85, 94, 2), (75, 84, 1),
    ],
    "cookies": [
        (100, 100, 4), (97, 99, 3), (85, 96, 2), (75, 84, 1),
    ],
    "stars": [
        (100, 100, 4), (97, 99, 3), (85, 96, 2), (75, 84, 1),
    ],
}

# ──── Shop Items ────
SHOP_ITEMS = {
    "chocolate": {
        "price": 15, "emoji": "🍫", "field": "chocolates",
        "desc": "Reduces sickness by 10 per piece",
    },
    "lollipop": {
        "price": 30, "emoji": "🍭", "field": "lollipops",
        "desc": "Reduces sickness by 20 per piece",
    },
    "cookie": {
        "price": 25, "emoji": "🥠", "field": "cookies",
        "desc": "Randomizes your sickness — gamble!",
    },
    "star": {
        "price": 50, "emoji": "⭐", "field": "stars",
        "desc": "Instantly resets sickness to 0",
    },
    "shield": {
        "price": 75, "emoji": "🛡️", "field": None,
        "desc": "Protects you from theft",
    },
    "golden_candy": {
        "price": 200, "emoji": "✨", "field": "golden_candies",
        "desc": "Worth 10× eaten count! No sickness.",
    },
}

# ──── Trick Events ────
TRICK_EVENTS = [
    {
        "type": "candy_tax",
        "title": "🎃 The Candy Tax!",
        "desc": "A shadowy figure appears from the darkness and demands a toll for passing through their territory...",
        "min_loss": 3, "max_loss": 10,
    },
    {
        "type": "sickness_curse",
        "title": "🧙 Witch's Curse!",
        "desc": "A cackling witch leaps from behind a tombstone and hexes you with her crooked wand!",
        "sickness_add": 20,
    },
    {
        "type": "haunted_house",
        "title": "👻 Haunted House!",
        "desc": "You stumbled into a haunted house! Ghostly hands grab at your candy bag...",
        "sickness_add": 15, "min_loss": 2, "max_loss": 7,
    },
    {
        "type": "candy_fumble",
        "title": "💨 Butterfingers!",
        "desc": "You tripped over a jack-o'-lantern and candy scattered everywhere!",
        "loss_pct": 0.15,
    },
    {
        "type": "cursed_candy",
        "title": "☠️ Cursed Candy!",
        "desc": "That candy had a strange glow... It was cursed! Your stomach churns violently!",
        "sickness_add": 30,
    },
]

# ──── Sickness Thresholds ────
SICKNESS_FACES = [
    (101, "💀"), (81, "🤮"), (61, "🤢"), (41, "😰"), (21, "😐"), (0, "😊"),
]

# ──── Guild Event Types ────
EVENT_TYPES = {
    "eat": {"verb": "eaten", "emoji": "🍬", "desc": "Eat candies collectively!"},
    "collect": {"verb": "collected", "emoji": "🎃", "desc": "Collect candies via trick-or-treat!"},
    "steal": {"verb": "stolen", "emoji": "🗡️", "desc": "Steal candies from others!"},
}


# ──── Module-Level Helpers ────

def _resolve_candy_type(raw: str) -> str | None:
    """Resolve a candy alias to its canonical name, or None."""
    return CANDY_ALIASES.get(raw.lower())


def _sickness_face(sickness: int) -> str:
    for threshold, face in SICKNESS_FACES:
        if sickness >= threshold:
            return face
    return "😊"


def _sickness_bar(sickness: int, length: int = 10) -> str:
    capped = min(sickness, 100)
    filled = round((capped / 100) * length)
    return "█" * filled + "░" * (length - filled)


def _streak_multiplier(streak: int) -> float:
    return min(3.0, 1.0 + (streak * 0.1))



# ════════════════════════════════════════════════════════════════
#  COG
# ════════════════════════════════════════════════════════════════

@cog_i18n(_)
class TrickOrTreatV2(commands.Cog):
    """🎃 Trick or Treat — A spooky candy collecting game!

    Collect candy, manage your sickness, steal from others,
    visit the shop, build streaks, and compete for glory!

    Originally by aikaterna. Expanded by Killerbite95.
    """

    async def red_delete_data_for_user(
        self,
        *,
        requester: Literal["discord", "owner", "user", "user_strict"],
        user_id: int,
    ):
        await self.config.user_from_id(user_id).clear()

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 9581437026, force_registration=True)

        default_guild = {
            "cooldown": 180,
            "channel": [],
            "pick": 200,
            "toggle": False,
            "pickup_cooldown": 600,
            "steal_cooldown": 600,
            "shield_hours": 4,
            # Guild events
            "event_active": False,
            "event_type": "",
            "event_goal": 0,
            "event_progress": 0,
            "event_reward": 50,
        }
        default_global = {"schema": "v1"}
        default_user = {
            "candies": 0,
            "chocolates": 0,
            "cookies": 0,
            "eaten": 0,
            "golden_candies": 0,
            "ghost_peppers": 0,
            "last_tot": "2018-01-01 00:00:00.000001",
            "lollipops": 0,
            "sickness": 0,
            "stars": 0,
            # Gameplay stats
            "stolen": 0,
            "been_stolen": 0,
            "shield_until": 0,
            "streak": 0,
            "best_streak": 0,
            "last_streak_date": "",
            "trick_count": 0,
            "treat_count": 0,
        }

        self.config.register_user(**default_user)
        self.config.register_guild(**default_guild)
        self.config.register_global(**default_global)

        self._toggle_cache: dict[int, bool] = {}
        self._channel_cache: dict[int, list[int]] = {}
        self._pickup_cooldown: dict[int, float] = {}
        self._steal_cooldown: dict[int, float] = {}
        self.replenish_candies.start()

    def cog_unload(self):
        self.replenish_candies.cancel()

    async def cleanup(self):
        schema = await self.config.schema()
        if schema == "v2":
            return
        await self.bot.wait_until_red_ready()
        users = await self.config.all_users()
        for uid, data in users.items():
            if "chocolate" not in data:
                continue
            async with self.config.user_from_id(uid).all() as user:
                user["chocolates"] += user["chocolate"]
                del user["chocolate"]
        await self.config.schema.set("v2")

    @tasks.loop(hours=3)
    async def replenish_candies(self):
        for guild in self.bot.guilds:
            try:
                pick = await self.config.guild(guild).pick()
                added_candies = random.randint(50, 100)
                await self.config.guild(guild).pick.set(pick + added_candies)
            except Exception:
                logger.exception(f"Error replenishing candies for guild {guild.id}")

    @replenish_candies.before_loop
    async def before_replenish(self):
        await self.bot.wait_until_red_ready()

    # ──── Helper Methods ────

    def _make_embed(self, title: str, description: str = "", color: int = HALLOWEEN_ORANGE) -> discord.Embed:
        em = discord.Embed(title=title, description=description, color=color)
        em.set_footer(text=_("🎃 Trick or Treat v{version}").format(version=__version__))
        return em

    async def _check_shield(self, user) -> bool:
        shield_until = await self.config.user(user).shield_until()
        return time.time() < shield_until

    async def _shield_remaining(self, user) -> str:
        shield_until = await self.config.user(user).shield_until()
        remaining = shield_until - time.time()
        if remaining <= 0:
            return ""
        hours = int(remaining // 3600)
        minutes = int((remaining % 3600) // 60)
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

    async def _update_event_progress(self, guild, event_type: str, amount: int) -> bool | None:
        if not await self.config.guild(guild).event_active():
            return None
        current_type = await self.config.guild(guild).event_type()
        if current_type != event_type:
            return None
        progress = await self.config.guild(guild).event_progress()
        goal = await self.config.guild(guild).event_goal()
        new_progress = progress + amount
        await self.config.guild(guild).event_progress.set(new_progress)
        if new_progress >= goal:
            await self.config.guild(guild).event_active.set(False)
            return True
        return False

    async def _announce_event_completion(self, channel, guild):
        reward = await self.config.guild(guild).event_reward()
        event_em = self._make_embed(
            _("🎉 Guild Event Complete!"),
            _("The event goal has been reached!\n\n"
            "🍬 All participants receive **{reward}** bonus candies!\n"
            "*Congratulations!* 🎃").format(reward=humanize_number(reward)),
            HALLOWEEN_GOLD,
        )
        await channel.send(embed=event_em)
        candy_users = await self.config._all_from_scope(scope="USER")
        guild_member_ids = {m.id for m in guild.members if not m.bot}
        for uid in guild_member_ids & set(candy_users.keys()):
            current = await self.config.user_from_id(uid).candies()
            await self.config.user_from_id(uid).candies.set(current + reward)

    # ════════════════════════════════════════════════════════════
    #  EAT CANDY
    # ════════════════════════════════════════════════════════════

    @commands.guild_only()
    @commands.cooldown(1, 1, commands.BucketType.user)
    @commands.command()
    async def eatcandy(self, ctx, number: Optional[int] = 1, candy_type=None):
        """Eat some candy.

        Valid types: candy, chocolate, lollipop, cookie, star, golden_candy, ghost_pepper
        Examples:
            `[p]eatcandy 3 lollipops`
            `[p]eatcandy star`
            `[p]eatcandy 1 golden_candy`

        \N{CANDY} — The main candy. Eat to score, but watch your sickness!
        \N{CHOCOLATE BAR} — Reduces sickness by 10.
        \N{LOLLIPOP} — Reduces sickness by 20.
        \N{FORTUNE COOKIE} — Sets sickness randomly — fortune favours the brave.
        \N{WHITE MEDIUM STAR} — Resets sickness to 0.
        ✨ Golden Candy — Worth 10× eaten count! No sickness gain.
        🌶️ Ghost Pepper — Resets your sickness to 0. Spicy!
        """
        userdata = await self.config.user(ctx.author).all()
        pick = await self.config.guild(ctx.guild).pick()
        if not candy_type:
            candy_type = "candies"
        else:
            candy_type = _resolve_candy_type(candy_type) or candy_type
        if number < 0:
            return await ctx.send(
                _("That doesn't sound fun."),
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
        if number == 0:
            return await ctx.send(
                _("You pretend to eat a candy."),
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
        if candy_type not in CANDY_TYPES:
            return await ctx.send(
                _("That's not a candy type! Use the inventory command to see what you have."),
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
        if userdata[candy_type] < number:
            return await ctx.send(
                _("You don't have that many {candy_type}.").format(candy_type=candy_type),
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
        if userdata[candy_type] == 0:
            return await ctx.send(
                _("You contemplate the idea of eating {candy_type}.").format(candy_type=candy_type),
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )

        eat_phrase = [
            _("You leisurely enjoy"),
            _("You take the time to savor"),
            _("You eat"),
            _("You scarf down"),
            _("You sigh in contentment after eating"),
            _("You gobble up"),
            _("You make a meal of"),
            _("You devour"),
            _("You monstrously pig out on"),
            _("You hastily chomp down on"),
            _("You daintily partake of"),
            _("You earnestly consume"),
        ]

        # ── Golden Candy (10× eaten, no sickness) ──
        if candy_type == "golden_candies":
            eaten_value = number * 10
            em = self._make_embed(
                _("✨ Golden Candy!"),
                _("{eat_phrase} {number} golden {candy_word}!\n\n"
                "The golden shimmer fills you with warmth.\n"
                "**+{eaten_value}** eaten count! *(10× bonus!)*\n"
                "No sickness gained!").format(
                    eat_phrase=random.choice(eat_phrase),
                    number=number,
                    candy_word=_("candy") if number == 1 else _("candies"),
                    eaten_value=eaten_value,
                ),
                color=HALLOWEEN_GOLD,
            )
            await self.config.user(ctx.author).golden_candies.set(userdata["golden_candies"] - number)
            await self.config.user(ctx.author).eaten.set(userdata["eaten"] + eaten_value)
            result = await self._update_event_progress(ctx.guild, "eat", eaten_value)
            if result is True:
                await self._announce_event_completion(ctx.channel, ctx.guild)
            return await ctx.send(embed=em, reference=ctx.message.to_reference(fail_if_not_exists=False))

        # ── Ghost Pepper (reset sickness) ──
        if candy_type == "ghost_peppers":
            em = self._make_embed(
                _("🌶️ Ghost Pepper!"),
                _("{eat_phrase} {number} ghost {pepper_word}!\n\n"
                "🔥 **SPICY!** Your mouth is on fire!\n"
                "...but the heat burns away all your sickness!\n"
                "💊 Sickness reset to **0**!").format(
                    eat_phrase=random.choice(eat_phrase),
                    number=number,
                    pepper_word=_("pepper") if number == 1 else _("peppers"),
                ),
                color=HALLOWEEN_RED,
            )
            await self.config.user(ctx.author).ghost_peppers.set(userdata["ghost_peppers"] - number)
            await self.config.user(ctx.author).sickness.set(0)
            await self.config.user(ctx.author).eaten.set(userdata["eaten"] + number)
            return await ctx.send(embed=em, reference=ctx.message.to_reference(fail_if_not_exists=False))

        # ── Regular Candies ──
        if candy_type in ["candies", "candy"]:
            if 70 <= (userdata["sickness"] + number * 2) < 95:
                await ctx.send(
                    _("After all that candy, sugar doesn't sound so good."),
                    reference=ctx.message.to_reference(fail_if_not_exists=False),
                )
                yuck = random.randint(1, 10)
                if yuck == 10:
                    await self.config.user(ctx.author).sickness.set(userdata["sickness"] + 25)
                else:
                    await self.config.user(ctx.author).sickness.set(userdata["sickness"] + (yuck * 2))

                if userdata["candies"] > 3 + number:
                    lost_candy = userdata["candies"] - random.randint(1, 3) - number
                else:
                    lost_candy = userdata["candies"]

                pick_now = await self.config.guild(ctx.guild).pick()
                if lost_candy < 0:
                    await self.config.user(ctx.author).candies.set(0)
                    await self.config.guild(ctx.guild).pick.set(pick_now + lost_candy)
                else:
                    await self.config.user(ctx.author).candies.set(userdata["candies"] - lost_candy)
                    await self.config.guild(ctx.guild).pick.set(pick_now + lost_candy)

                eaten_amount = userdata["candies"] - lost_candy
                await self.config.user(ctx.author).eaten.set(userdata["eaten"] + eaten_amount)
                result = await self._update_event_progress(ctx.guild, "eat", max(0, eaten_amount))
                if result is True:
                    await self._announce_event_completion(ctx.channel, ctx.guild)

                return await ctx.send(
                    _("You begin to think you don't need all this candy, maybe...\n*{lost_candy} candies are left behind*").format(lost_candy=lost_candy),
                    reference=ctx.message.to_reference(fail_if_not_exists=False),
                )

            if (userdata["sickness"] + number) > 96:
                await self.config.user(ctx.author).sickness.set(userdata["sickness"] + 30)
                lost_candy = userdata["candies"] - random.randint(1, 5)
                if lost_candy <= 0:
                    await self.config.user(ctx.author).candies.set(0)
                    message = await ctx.send(
                        "...",
                        reference=ctx.message.to_reference(fail_if_not_exists=False),
                    )
                    await asyncio.sleep(2)
                    await message.edit(content="..........")
                    await asyncio.sleep(2)
                    return await message.edit(
                        content=_("You feel absolutely disgusted. At least you don't have any candies left.")
                    )
                await self.config.guild(ctx.guild).pick.set(pick + lost_candy)
                await self.config.user(ctx.author).candies.set(0)
                eaten_amount = userdata["candies"] - lost_candy
                await self.config.user(ctx.author).eaten.set(userdata["eaten"] + eaten_amount)
                result = await self._update_event_progress(ctx.guild, "eat", max(0, eaten_amount))
                if result is True:
                    await self._announce_event_completion(ctx.channel, ctx.guild)
                message = await ctx.send("...", reference=ctx.message.to_reference(fail_if_not_exists=False))
                await asyncio.sleep(2)
                await message.edit(content="..........")
                await asyncio.sleep(2)
                return await message.edit(
                    content=_("You toss your candies on the ground in disgust.\n*{lost_candy} candies are left behind*").format(lost_candy=lost_candy)
                )

            pluralcandy = "candy" if number == 1 else "candies"
            new_eaten = userdata["eaten"] + number
            await ctx.send(
                _("{eat_phrase} {number} {pluralcandy}. (Total eaten: `{eaten_count}` 🍬)").format(eat_phrase=random.choice(eat_phrase), number=number, pluralcandy=pluralcandy, eaten_count=humanize_number(new_eaten)),
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
            await self.config.user(ctx.author).sickness.set(userdata["sickness"] + (number * 2))
            await self.config.user(ctx.author).candies.set(userdata["candies"] - number)
            await self.config.user(ctx.author).eaten.set(new_eaten)
            result = await self._update_event_progress(ctx.guild, "eat", number)
            if result is True:
                await self._announce_event_completion(ctx.channel, ctx.guild)

        if candy_type in ["chocolates", "chocolate"]:
            pluralchoc = "chocolate" if number == 1 else "chocolates"
            await ctx.send(
                _("{eat_phrase} {number} {pluralchoc}. You feel slightly better!\n*Sickness has gone down by {sickness_down}*").format(eat_phrase=random.choice(eat_phrase), number=number, pluralchoc=pluralchoc, sickness_down=number * 10),
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
            new_sickness = max(0, userdata["sickness"] - (number * 10))
            await self.config.user(ctx.author).sickness.set(new_sickness)
            await self.config.user(ctx.author).chocolates.set(userdata["chocolates"] - number)
            await self.config.user(ctx.author).eaten.set(userdata["eaten"] + number)
            result = await self._update_event_progress(ctx.guild, "eat", number)
            if result is True:
                await self._announce_event_completion(ctx.channel, ctx.guild)

        if candy_type in ["lollipops", "lollipop"]:
            pluralpop = "lollipop" if number == 1 else "lollipops"
            await ctx.send(
                _("{eat_phrase} {number} {pluralpop}. You feel slightly better!\n*Sickness has gone down by {sickness_down}*").format(eat_phrase=random.choice(eat_phrase), number=number, pluralpop=pluralpop, sickness_down=number * 20),
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
            new_sickness = max(0, userdata["sickness"] - (number * 20))
            await self.config.user(ctx.author).sickness.set(new_sickness)
            await self.config.user(ctx.author).lollipops.set(userdata["lollipops"] - number)
            await self.config.user(ctx.author).eaten.set(userdata["eaten"] + number)
            result = await self._update_event_progress(ctx.guild, "eat", number)
            if result is True:
                await self._announce_event_completion(ctx.channel, ctx.guild)

        if candy_type in ["cookies", "cookie"]:
            pluralcookie = "cookie" if number == 1 else "cookies"
            new_sickness = random.randint(0, 100)
            old_sickness = userdata["sickness"]
            if new_sickness > old_sickness:
                phrase = _("You feel worse!\n*Sickness has gone up by {amount}*").format(amount=new_sickness - old_sickness)
            else:
                phrase = _("You feel better!\n*Sickness has gone down by {amount}*").format(amount=old_sickness - new_sickness)
            await ctx.reply(_("{eat_phrase} {number} {pluralcookie}. {phrase}").format(eat_phrase=random.choice(eat_phrase), number=number, pluralcookie=pluralcookie, phrase=phrase))
            await self.config.user(ctx.author).sickness.set(new_sickness)
            await self.config.user(ctx.author).cookies.set(userdata["cookies"] - number)
            await self.config.user(ctx.author).eaten.set(userdata["eaten"] + number)
            result = await self._update_event_progress(ctx.guild, "eat", number)
            if result is True:
                await self._announce_event_completion(ctx.channel, ctx.guild)

        if candy_type in ["stars", "star"]:
            pluralstar = "star" if number == 1 else "stars"
            await ctx.send(
                _("{eat_phrase} {number} {pluralstar}. You feel great!\n*Sickness has been reset*").format(eat_phrase=random.choice(eat_phrase), number=number, pluralstar=pluralstar),
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
            await self.config.user(ctx.author).sickness.set(0)
            await self.config.user(ctx.author).stars.set(userdata["stars"] - number)
            await self.config.user(ctx.author).eaten.set(userdata["eaten"] + number)
            result = await self._update_event_progress(ctx.guild, "eat", number)
            if result is True:
                await self._announce_event_completion(ctx.channel, ctx.guild)

    # ════════════════════════════════════════════════════════════
    #  ADMIN CANDY COMMANDS
    # ════════════════════════════════════════════════════════════

    @commands.guild_only()
    @checks.mod_or_permissions(administrator=True)
    @commands.command()
    async def totbalance(self, ctx):
        """[Admin] Check how many candies are 'on the ground' in the guild."""
        pick = await self.config.guild(ctx.guild).pick()
        em = self._make_embed(
            _("🎃 Guild Candy Pool"),
            _("**{pick}** 🍬 on the ground").format(pick=humanize_number(pick)),
            HALLOWEEN_ORANGE,
        )
        await ctx.send(embed=em)

    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    @commands.command()
    async def totgivecandy(self, ctx, user: discord.Member, candy_type: str, amount: int):
        """[Admin] Add candy to a user's inventory."""
        if amount <= 0:
            return await ctx.send(_("Amount must be greater than zero."))
        resolved = _resolve_candy_type(candy_type)
        if resolved is None:
            return await ctx.send(_("Invalid candy type. Valid types are: {types}.").format(types=", ".join(CANDY_TYPES)))
        userdata = await self.config.user(user).all()
        userdata[resolved] += amount
        await self.config.user(user).set(userdata)
        emoji = CANDY_EMOJIS.get(resolved, '')
        await ctx.send(_("Added {amount} {resolved} {emoji} to {name}'s inventory.").format(amount=amount, resolved=resolved, emoji=emoji, name=user.display_name))

    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    @commands.command()
    async def totremovecandy(self, ctx, user: discord.Member, candy_type: str, amount: int):
        """[Admin] Remove candy from a user's inventory."""
        if amount <= 0:
            return await ctx.send(_("Amount must be greater than zero."))
        resolved = _resolve_candy_type(candy_type)
        if resolved is None:
            return await ctx.send(_("Invalid candy type. Valid types are: {types}.").format(types=", ".join(CANDY_TYPES)))
        userdata = await self.config.user(user).all()
        if userdata[resolved] < amount:
            emoji = CANDY_EMOJIS.get(resolved, '')
            return await ctx.send(_("{name} only has {current} {resolved} {emoji}. Cannot remove {amount}.").format(name=user.display_name, current=userdata[resolved], resolved=resolved, emoji=emoji, amount=amount))
        userdata[resolved] -= amount
        await self.config.user(user).set(userdata)
        emoji = CANDY_EMOJIS.get(resolved, '')
        await ctx.send(_("Removed {amount} {resolved} {emoji} from {name}'s inventory. Now has {current} {resolved} {emoji}.").format(amount=amount, resolved=resolved, emoji=emoji, name=user.display_name, current=userdata[resolved]))

    # ════════════════════════════════════════════════════════════
    #  BUY WITH CURRENCY
    # ════════════════════════════════════════════════════════════

    @commands.guild_only()
    @commands.command()
    async def buycandy(self, ctx, pieces: int):
        """Buy some candy with server currency. Prices could vary at any time."""
        candy_now = await self.config.user(ctx.author).candies()
        credits_name = await bank.get_currency_name(ctx.guild)
        if pieces <= 0:
            return await ctx.send(
                _("Not in this reality."),
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
        per_piece = max(10, int(round(await bank.get_balance(ctx.author)) * 0.04))
        candy_price = per_piece * pieces
        try:
            await bank.withdraw_credits(ctx.author, candy_price)
        except ValueError:
            return await ctx.send(
                _("Not enough {credits_name} ({candy_price} required).").format(credits_name=credits_name, candy_price=candy_price),
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
        await self.config.user(ctx.author).candies.set(candy_now + pieces)
        em = self._make_embed(
            _("🍬 Candy Purchased!"),
            _("Bought **{pieces}** candies for **{candy_price}** {credits_name}.").format(pieces=pieces, candy_price=humanize_number(candy_price), credits_name=credits_name),
            HALLOWEEN_GREEN,
        )
        await ctx.send(embed=em, reference=ctx.message.to_reference(fail_if_not_exists=False))

    # ════════════════════════════════════════════════════════════
    #  CANDY SHOP
    # ════════════════════════════════════════════════════════════

    @commands.guild_only()
    @commands.command()
    @commands.bot_has_permissions(embed_links=True)
    async def totshop(self, ctx):
        """Browse the Candy Shop! Spend candy on special items."""
        shield_hours = await self.config.guild(ctx.guild).shield_hours()
        em = self._make_embed(
            _("🏪 Candy Shop"),
            _("Spend your hard-earned candies on special treats!\n━━━━━━━━━━━━━━━━━━━━━━━━━━━"),
            HALLOWEEN_PURPLE,
        )
        for name, item in SHOP_ITEMS.items():
            desc = _(item["desc"])
            if name == "shield":
                desc += f" ({shield_hours}h)"
            em.add_field(
                name=f"{item['emoji']} {name.replace('_', ' ').title()} — {item['price']} 🍬",
                value=desc,
                inline=False,
            )
        em.add_field(
            name="\u200b",
            value=_("Use `{prefix}totbuy <item> [amount]` to purchase!").format(prefix=ctx.prefix),
            inline=False,
        )
        user_candies = await self.config.user(ctx.author).candies()
        em.set_footer(text=_("🎃 Your candies: {candies} | Trick or Treat v{version}").format(candies=humanize_number(user_candies), version=__version__))
        await ctx.send(embed=em)

    @commands.guild_only()
    @commands.command()
    async def totbuy(self, ctx, item_name: str, amount: int = 1):
        """Buy items from the Candy Shop.

        Items: chocolate, lollipop, cookie, star, shield, golden_candy
        """
        item_key = item_name.lower().replace(" ", "_")
        if item_key not in SHOP_ITEMS:
            return await ctx.send(
                _("Unknown item! Available: {items}").format(items=", ".join(SHOP_ITEMS.keys())),
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
        if amount <= 0:
            return await ctx.send(_("Nice try."), reference=ctx.message.to_reference(fail_if_not_exists=False))

        item = SHOP_ITEMS[item_key]

        # Shield — only 1 at a time
        if item_key == "shield":
            amount = 1
            if await self._check_shield(ctx.author):
                remaining = await self._shield_remaining(ctx.author)
                return await ctx.send(
                    _("🛡️ You already have an active shield! ({remaining} remaining)").format(remaining=remaining),
                    reference=ctx.message.to_reference(fail_if_not_exists=False),
                )

        total_cost = item["price"] * amount
        user_candies = await self.config.user(ctx.author).candies()
        if user_candies < total_cost:
            return await ctx.send(
                _("Not enough candies! You need **{total_cost}** 🍬 but have **{user_candies}** 🍬.").format(total_cost=total_cost, user_candies=user_candies),
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )

        # Deduct candies
        await self.config.user(ctx.author).candies.set(user_candies - total_cost)

        if item_key == "shield":
            shield_hours = await self.config.guild(ctx.guild).shield_hours()
            shield_until = time.time() + (shield_hours * 3600)
            await self.config.user(ctx.author).shield_until.set(shield_until)
            em = self._make_embed(
                _("🛡️ Shield Activated!"),
                _("A magical shield now protects your candy bag!\n\n"
                "⏱️ Duration: **{shield_hours} hours**\n"
                "🍬 Cost: **{total_cost}** candies").format(shield_hours=shield_hours, total_cost=total_cost),
                HALLOWEEN_GREEN,
            )
        else:
            field = item["field"]
            current = await getattr(self.config.user(ctx.author), field)()
            await getattr(self.config.user(ctx.author), field).set(current + amount)
            em = self._make_embed(
                _("{emoji} Purchase Complete!").format(emoji=item["emoji"]),
                _("Bought **{amount}** {item_name} for **{total_cost}** 🍬\n"
                "Remaining candies: **{remaining}** 🍬").format(
                    amount=amount, item_name=item_key.replace("_", " "),
                    total_cost=total_cost, remaining=user_candies - total_cost,
                ),
                HALLOWEEN_GREEN,
            )
        await ctx.send(embed=em, reference=ctx.message.to_reference(fail_if_not_exists=False))

    # ════════════════════════════════════════════════════════════
    #  LEADERBOARD & INVENTORY
    # ════════════════════════════════════════════════════════════

    @commands.guild_only()
    @commands.command()
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def cboard(self, ctx):
        """Show the candy eating leaderboard."""
        space = "\N{SPACE}"
        userinfo = await self.config._all_from_scope(scope="USER")
        if not userinfo:
            return await ctx.send(
                _("No one has any candy."),
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
        async with ctx.typing():
            sorted_acc = sorted(userinfo.items(), key=lambda x: x[1]["eaten"], reverse=True)
        pound_len = len(str(len(sorted_acc)))
        score_len = 10
        header = "{pound:{pound_len}}{score:{score_len}}{name:2}\n".format(
            pound="#",
            pound_len=pound_len + 3,
            score=_("Candies Eaten"),
            score_len=score_len + 6,
            name=_("Name"),
        )
        scoreboard_msg = self._red(header)
        guild_member_ids = {m.id for m in ctx.guild.members}
        rank = 0
        for _pos, account in enumerate(sorted_acc):
            if account[1]["eaten"] == 0:
                continue
            uid = account[0]
            if uid in guild_member_ids:
                user_obj = ctx.guild.get_member(uid)
            else:
                user_obj = self.bot.get_user(uid)
            if user_obj is None:
                user_name = f"User {uid}"
            elif len(user_obj.display_name) > 28:
                user_name = f"{user_obj.display_name[:25]}..."
            else:
                user_name = user_obj.display_name

            rank += 1
            user_idx = rank
            if user_obj == ctx.author:
                user_highlight = self._yellow(f"<<{user_name}>>")
                scoreboard_msg += (
                    f"{self._yellow(user_idx)}. {space*pound_len}"
                    f"{humanize_number(account[1]['eaten']) + ' 🍬': <{score_len + 4}} {user_highlight}\n"
                )
            else:
                scoreboard_msg += (
                    f"{self._yellow(user_idx)}. {space*pound_len}"
                    f"{humanize_number(account[1]['eaten']) + ' 🍬': <{score_len + 4}} {user_name}\n"
                )

        page_list = []
        pages = 1
        for page in pagify(scoreboard_msg, delims=["\n"], page_length=1000):
            embed = discord.Embed(
                colour=HALLOWEEN_ORANGE,
                description=box(_("\N{CANDY} Global Leaderboard \N{CANDY}"), lang="prolog") + (box(page, lang="ansi")),
            )
            embed.set_footer(
                text=_("🎃 Page {current}/{total} | Trick or Treat v{version}").format(
                    current=humanize_number(pages),
                    total=humanize_number(math.ceil(len(scoreboard_msg) / 1000)),
                    version=__version__,
                )
            )
            pages += 1
            page_list.append(embed)
        return await menu(ctx, page_list, DEFAULT_CONTROLS, timeout=300)

    @commands.guild_only()
    @commands.command()
    @commands.bot_has_permissions(embed_links=True)
    async def cinventory(self, ctx):
        """Check your candy bag — full inventory with stats!"""
        userdata = await self.config.user(ctx.author).all()
        sickness = userdata["sickness"]
        streak = userdata.get("streak", 0)
        best_streak = userdata.get("best_streak", 0)
        face = _sickness_face(sickness)
        bar = _sickness_bar(sickness)
        multiplier = _streak_multiplier(streak)

        # Color based on health
        if sickness > 80:
            color = HALLOWEEN_RED
        elif sickness > 40:
            color = HALLOWEEN_ORANGE
        else:
            color = HALLOWEEN_GREEN

        em = discord.Embed(color=color)
        em.set_author(
            name=_("🎃 {name}'s Candy Bag").format(name=ctx.author.display_name),
            icon_url=ctx.author.display_avatar.url,
        )
        em.set_thumbnail(url=ctx.author.display_avatar.url)

        # Inventory
        inv_lines = []
        for ctype in CANDY_TYPES:
            count = userdata.get(ctype, 0)
            emoji = CANDY_EMOJIS[ctype]
            label = ctype.replace("_", " ").title()
            if count > 0 or ctype == "candies":
                inv_lines.append(f"{emoji} **{humanize_number(count)}** {label}")
        em.add_field(name=_("🍬 Inventory"), value="\n".join(inv_lines), inline=False)

        # Sickness
        sick_text = f"{face} {bar} **{sickness}**/100"
        if sickness > 100:
            sick_text += _("\n⚠️ *Rewards quartered! You might lose candy...*")
        elif sickness > 80:
            sick_text += _("\n⚠️ *Rewards halved! Eat chocolate to recover.*")
        elif sickness > 60:
            sick_text += _("\n😨 *You really don't feel so good...*")
        elif sickness > 40:
            sick_text += _("\n😰 *You don't feel so great...*")
        em.add_field(name=_("💊 Sickness"), value=sick_text, inline=False)

        # Streak & Shield
        status_lines = []
        if streak > 0:
            streak_emoji = "🔥" if streak >= 5 else "📅"
            status_lines.append(f"{streak_emoji} **Streak:** {streak} day{'s' if streak != 1 else ''} (×{multiplier:.1f} bonus)")
        if best_streak > 0:
            status_lines.append(f"🏆 **Best Streak:** {best_streak} days")
        if await self._check_shield(ctx.author):
            remaining = await self._shield_remaining(ctx.author)
            status_lines.append(_("🛡️ **Shield:** ✅ Active ({remaining} left)").format(remaining=remaining))
        if status_lines:
            em.add_field(name=_("📋 Status"), value="\n".join(status_lines), inline=False)

        # Stats
        stats_lines = [
            f"🍬 **Eaten:** {humanize_number(userdata.get('eaten', 0))}",
            f"🎭 **Tricks:** {userdata.get('trick_count', 0)} │ **Treats:** {userdata.get('treat_count', 0)}",
            f"🗡️ **Stolen:** {humanize_number(userdata.get('stolen', 0))} │ **Lost:** {humanize_number(userdata.get('been_stolen', 0))}",
        ]
        em.add_field(name=_("📊 Stats"), value="\n".join(stats_lines), inline=False)

        em.set_footer(text=_("🎃 Trick or Treat v{version}").format(version=__version__))
        await ctx.send(embed=em)

    # ════════════════════════════════════════════════════════════
    #  GAME GUIDE
    # ════════════════════════════════════════════════════════════

    @commands.guild_only()
    @commands.command()
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def tothelp(self, ctx):
        """📖 Full game guide for Trick or Treat."""
        p = ctx.prefix
        pages = []
        footer_tpl = _("🎃 Page {current}/{total} — Trick or Treat v{version}")

        # ── Page 1: Introduction ──
        em1 = self._make_embed(
            _("📖 Guide — How to Play?"),
            _("Welcome to **Trick or Treat**! 🎃\n"
              "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
              "**How to start?**\n"
              "Type **`trick or treat`** in an enabled channel to go door-to-door "
              "asking for candy. But be careful! You don't always get treats...\n\n"
              "**🎁 Treat (75%)** — You receive candy and possible bonus drops.\n"
              "**👻 Trick (25%)** — Something bad happens: lose candy, get sick, or both.\n\n"
              "**Goal:** Eat as many candies as possible and climb the global leaderboard.\n\n"
              "Use `{p}cinventory` to see your inventory and `{p}cboard` for the leaderboard.").format(p=p),
            HALLOWEEN_ORANGE,
        )
        em1.set_footer(text=footer_tpl.format(current=1, total=6, version=__version__))
        pages.append(em1)

        # ── Page 2: Candy Types ──
        em2 = self._make_embed(
            _("🍬 Guide — Candy Types"),
            _("Each candy type has a special effect when eaten:\n"
              "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
              "🍬 **Candies** — The main candy. Eating them increases your *eaten* score, "
              "but **also raises sickness** (+2 per candy).\n\n"
              "🍫 **Chocolates** — Reduces sickness by **10** per piece. Sweet medicine!\n\n"
              "🍭 **Lollipops** — Reduces sickness by **20** per piece. More effective.\n\n"
              "🥠 **Cookies** — Sets your sickness to a **random** number (0-100). A gamble!\n\n"
              "⭐ **Stars** — Resets your sickness to **0** instantly. The best!\n\n"
              "✨ **Golden Candy** — *LEGENDARY*. Worth **10×** in score and **no sickness**.\n\n"
              "🌶️ **Ghost Pepper** — *ULTRA RARE*. Resets sickness to **0** when eaten."),
            HALLOWEEN_PURPLE,
        )
        em2.add_field(
            name=_("📝 How to eat"),
            value=_('`{p}eatcandy [amount] [type]`\nExamples: `{p}eatcandy 3 chocolate` · `{p}eatcandy star`').format(p=p),
            inline=False,
        )
        em2.set_footer(text=footer_tpl.format(current=2, total=6, version=__version__))
        pages.append(em2)

        # ── Page 3: Sickness ──
        em3 = self._make_embed(
            _("💊 Guide — Sickness System"),
            _("Sickness rises when you eat candies and affects your rewards:\n"
              "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
              "😊 **0-40** — Everything normal. No penalty.\n\n"
              "😰 **41-80** — You start feeling unwell, but no punishment yet.\n\n"
              "🤮 **81-100** — ⚠️ **Rewards halved.** If you were going to "
              "get 20 candies, you get 10.\n\n"
              "💀 **>100** — ⚠️ **Rewards quartered** + a **50% chance** "
              "of **dropping** candies on the ground when trick-or-treating.\n\n"
              "**How to cure?**\n"
              "🍫 Chocolates (-10) · 🍭 Lollipops (-20) · ⭐ Stars (reset) · 🌶️ Ghost Peppers (reset)\n"
              "You also recover a little passively by chatting in ToT channels."),
            HALLOWEEN_RED,
        )
        em3.add_field(
            name=_("💡 Tip"),
            value=_("Don't let sickness go above 80. Buy cures from the shop if you don't get them as bonus drops."),
            inline=False,
        )
        em3.set_footer(text=footer_tpl.format(current=3, total=6, version=__version__))
        pages.append(em3)

        # ── Page 4: Shop & Shield ──
        em4 = self._make_embed(
            _("🏪 Guide — Shop & Shield"),
            _("Spend your candies at the shop to buy useful items:\n"
              "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
              "Use `{p}totshop` to browse and `{p}totbuy <item> [amount]` to purchase.\n\n"
              "🍫 **Chocolate** — 15 🍬 · Reduces sickness\n"
              "🍭 **Lollipop** — 30 🍬 · Reduces more sickness\n"
              "🥠 **Cookie** — 25 🍬 · Random sickness\n"
              "⭐ **Star** — 50 🍬 · Resets sickness\n"
              "🛡️ **Shield** — 75 🍬 · Theft protection\n"
              "✨ **Golden Candy** — 200 🍬 · 10× score, no sickness\n").format(p=p),
            HALLOWEEN_PURPLE,
        )
        em4.add_field(
            name=_("🛡️ What does the Shield do?"),
            value=_("The shield protects your candy bag from theft via `stealcandy`. "
                    "It lasts several hours (configurable by admins). You can only have **1 active** at a time."),
            inline=False,
        )
        em4.set_footer(text=footer_tpl.format(current=4, total=6, version=__version__))
        pages.append(em4)

        # ── Page 5: Streaks, Stealing, Rare ──
        em5 = self._make_embed(
            _("🔥 Guide — Streaks, Stealing & Rare Items"),
            _("━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
              "**🔥 Daily Streaks**\n"
              "Play `trick or treat` every consecutive day to build your streak.\n"
              "Each streak day adds **×0.1** to your reward multiplier.\n"
              "Day 1: ×1.0 · Day 5: ×1.5 · Day 10: ×2.0 · Max: **×3.0**\n"
              "Miss a day and the streak resets!\n\n"
              "**🗡️ Stealing Candy**\n"
              "Use `{p}stealcandy [@user]` to attempt a theft.\n"
              "It doesn't always work — there are various success/failure chances.\n"
              "The victim receives a **DM notification** when stolen from. 📩\n"
              "Buy a **🛡️ Shield** to protect yourself.\n\n"
              "**💎 Rare Items**\n"
              "When doing `trick or treat`, there's a small chance of getting:\n"
              "✨ **Golden Candy** (0.5%) — Worth ×10 when eaten.\n"
              "🌶️ **Ghost Pepper** (0.3%) — Resets your sickness.\n").format(p=p),
            HALLOWEEN_GOLD,
        )
        em5.set_footer(text=footer_tpl.format(current=5, total=6, version=__version__))
        pages.append(em5)

        # ── Page 6: Commands ──
        em6 = self._make_embed(
            _("📋 Guide — Command List"),
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            HALLOWEEN_ORANGE,
        )
        em6.add_field(
            name=_("🎮 Player"),
            value=_("`trick or treat` — Go door to door\n"
                    "`{p}eatcandy [n] [type]` — Eat candy\n"
                    "`{p}cinventory` — View your inventory\n"
                    "`{p}totstats [@user]` — Detailed statistics\n"
                    "`{p}cboard` — Global eaten leaderboard\n"
                    "`{p}totshop` — View the shop\n"
                    "`{p}totbuy <item> [n]` — Buy from the shop\n"
                    "`{p}buycandy <n>` — Buy candy with bot currency\n"
                    "`{p}pickup` — Pick up candy from the ground\n"
                    "`{p}stealcandy [@user]` — Steal candy\n"
                    "`{p}tothelp` — This guide").format(p=p),
            inline=False,
        )
        em6.add_field(
            name=_("🔧 Admin / Mod"),
            value=_("`{p}tottoggle` — Toggle the game on/off\n"
                    "`{p}totchannel add/remove` — Game channels\n"
                    "`{p}totcooldown [s]` — Trick or treat cooldown\n"
                    "`{p}totpickupcooldown [s]` — Pickup cooldown\n"
                    "`{p}totstealcooldown [s]` — Steal cooldown\n"
                    "`{p}totshieldhours [h]` — Shield duration\n"
                    "`{p}totbalance` — Candies in the pool\n"
                    "`{p}totaddcandies <n>` — Add to pool\n"
                    "`{p}totgivecandy @user type n` — Give candy\n"
                    "`{p}totremovecandy @user type n` — Remove candy\n"
                    "`{p}totevent start/status/stop` — Guild events").format(p=p),
            inline=False,
        )
        em6.set_footer(text=footer_tpl.format(current=6, total=6, version=__version__))
        pages.append(em6)

        await menu(ctx, pages, DEFAULT_CONTROLS, timeout=300)

    # ════════════════════════════════════════════════════════════
    #  PERSONAL STATS
    # ════════════════════════════════════════════════════════════

    @commands.guild_only()
    @commands.command()
    @commands.bot_has_permissions(embed_links=True)
    async def totstats(self, ctx, user: discord.Member = None):
        """View detailed trick-or-treat statistics."""
        user = user or ctx.author
        userdata = await self.config.user(user).all()
        streak = userdata.get("streak", 0)
        best_streak = userdata.get("best_streak", 0)
        tricks = userdata.get("trick_count", 0)
        treats = userdata.get("treat_count", 0)
        total_visits = tricks + treats
        treat_pct = round((treats / total_visits) * 100) if total_visits > 0 else 0

        em = self._make_embed("", color=HALLOWEEN_PURPLE)
        em.set_author(
            name=_("📊 {name}'s Statistics").format(name=user.display_name),
            icon_url=user.display_avatar.url,
        )
        em.set_thumbnail(url=user.display_avatar.url)

        em.add_field(
            name=_("🍬 Candy Stats"),
            value=(
                f"Total Eaten: **{humanize_number(userdata.get('eaten', 0))}**\n"
                f"Current Candies: **{humanize_number(userdata.get('candies', 0))}**\n"
                f"Sickness: {_sickness_face(userdata.get('sickness', 0))} **{userdata.get('sickness', 0)}**/100"
            ),
            inline=True,
        )
        em.add_field(
            name=_("🔥 Streaks"),
            value=(
                f"Current: **{streak}** day{'s' if streak != 1 else ''}\n"
                f"Best: **{best_streak}** day{'s' if best_streak != 1 else ''}\n"
                f"Multiplier: **×{_streak_multiplier(streak):.1f}**"
            ),
            inline=True,
        )
        em.add_field(
            name=_("🎭 Trick or Treat"),
            value=(
                f"Total Visits: **{total_visits}**\n"
                f"Treats: **{treats}** ({treat_pct}%)\n"
                f"Tricks: **{tricks}** ({100 - treat_pct}%)"
            ),
            inline=True,
        )
        em.add_field(
            name=_("🗡️ Theft Record"),
            value=(
                f"Stolen from others: **{humanize_number(userdata.get('stolen', 0))}** 🍬\n"
                f"Lost to theft: **{humanize_number(userdata.get('been_stolen', 0))}** 🍬"
            ),
            inline=True,
        )

        # Rare items
        golden = userdata.get("golden_candies", 0)
        peppers = userdata.get("ghost_peppers", 0)
        if golden > 0 or peppers > 0:
            rare_text = ""
            if golden > 0:
                rare_text += f"✨ Golden Candies: **{golden}**\n"
            if peppers > 0:
                rare_text += f"🌶️ Ghost Peppers: **{peppers}**\n"
            em.add_field(name=_("💎 Rare Items"), value=rare_text.strip(), inline=True)

        if await self._check_shield(user):
            remaining = await self._shield_remaining(user)
            em.add_field(name=_("🛡️ Shield"), value=_("✅ Active ({remaining} left)").format(remaining=remaining), inline=True)

        await ctx.send(embed=em)

    # ════════════════════════════════════════════════════════════
    #  ADMIN SETTINGS
    # ════════════════════════════════════════════════════════════

    @commands.guild_only()
    @checks.is_owner()
    @commands.command()
    async def totclearall(self, ctx, are_you_sure=False):
        """[Owner] Clear all saved game data."""
        if not are_you_sure:
            msg = _("This will clear ALL saved data for this cog and reset it to the defaults.\n")
            msg += _("If you are absolutely sure you want to do this, use `{prefix}totclearall yes`.").format(prefix=ctx.prefix)
            return await ctx.send(msg)
        await self.config.clear_all()
        await ctx.send(_("All data for this cog has been cleared."))

    @commands.guild_only()
    @checks.mod_or_permissions(administrator=True)
    @commands.command()
    async def totcooldown(self, ctx, cooldown_time: int = 0):
        """Set the cooldown time for trick or treating on the server."""
        if cooldown_time < 0:
            return await ctx.send(_("Nice try."))
        if cooldown_time == 0:
            await self.config.guild(ctx.guild).cooldown.set(300)
            return await ctx.send(_("Trick or treating cooldown time reset to 5m."))
        elif 1 <= cooldown_time <= 30:
            await self.config.guild(ctx.guild).cooldown.set(30)
            return await ctx.send(_("Trick or treating cooldown time set to the minimum of 30s."))
        else:
            await self.config.guild(ctx.guild).cooldown.set(cooldown_time)
            await ctx.send(_("Trick or treating cooldown time set to {cooldown_time}s.").format(cooldown_time=cooldown_time))

    @commands.guild_only()
    @checks.mod_or_permissions(administrator=True)
    @commands.command()
    async def totpickupcooldown(self, ctx, seconds: int = 0):
        """Set the cooldown time for the pickup command (default: 600s)."""
        if seconds < 0:
            return await ctx.send(_("Nice try."))
        if seconds == 0:
            await self.config.guild(ctx.guild).pickup_cooldown.set(600)
            return await ctx.send(_("Pickup cooldown reset to 10m (600s)."))
        val = max(30, seconds)
        await self.config.guild(ctx.guild).pickup_cooldown.set(val)
        await ctx.send(_("Pickup cooldown set to {val}s.").format(val=val))

    @commands.guild_only()
    @checks.mod_or_permissions(administrator=True)
    @commands.command()
    async def totstealcooldown(self, ctx, seconds: int = 0):
        """Set the cooldown time for the stealcandy command (default: 600s)."""
        if seconds < 0:
            return await ctx.send(_("Nice try."))
        if seconds == 0:
            await self.config.guild(ctx.guild).steal_cooldown.set(600)
            return await ctx.send(_("Steal cooldown reset to 10m (600s)."))
        val = max(30, seconds)
        await self.config.guild(ctx.guild).steal_cooldown.set(val)
        await ctx.send(_("Steal cooldown set to {val}s.").format(val=val))

    @commands.guild_only()
    @checks.mod_or_permissions(administrator=True)
    @commands.command()
    async def totshieldhours(self, ctx, hours: int = 0):
        """Set how many hours a shield lasts (default: 4)."""
        if hours <= 0:
            await self.config.guild(ctx.guild).shield_hours.set(4)
            return await ctx.send(_("Shield duration reset to 4 hours."))
        await self.config.guild(ctx.guild).shield_hours.set(hours)
        await ctx.send(_("Shield duration set to {hours} hours.").format(hours=hours))

    # ════════════════════════════════════════════════════════════
    #  PICKUP & STEAL
    # ════════════════════════════════════════════════════════════

    @commands.guild_only()
    @commands.command()
    async def pickup(self, ctx):
        """Pick up some candy, if there is any."""
        cooldown_secs = await self.config.guild(ctx.guild).pickup_cooldown()
        bucket = self._pickup_cooldown
        retry_after = bucket.get(ctx.author.id, 0)
        now = datetime.datetime.now(datetime.timezone.utc).timestamp()
        if now < retry_after:
            remaining = int(retry_after - now)
            return await ctx.send(
                _("You need to wait {remaining}s before picking up candy again.").format(remaining=remaining),
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
        bucket[ctx.author.id] = now + cooldown_secs
        candies = await self.config.user(ctx.author).candies()
        to_pick = await self.config.guild(ctx.guild).pick()
        if to_pick <= 0:
            message = await ctx.send(
                _("You start searching the area for candy..."),
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
            await asyncio.sleep(3)
            return await message.edit(content=_("There's no candy left on the ground!"))
        chance = random.randint(1, 100)
        found = min(round((chance / 100) * to_pick), to_pick)
        await self.config.user(ctx.author).candies.set(candies + found)
        await self.config.guild(ctx.guild).pick.set(to_pick - found)
        message = await ctx.send(
            _("You start searching the area for candy..."),
            reference=ctx.message.to_reference(fail_if_not_exists=False),
        )
        await asyncio.sleep(3)
        await message.edit(content=_("You found {found} 🍬!").format(found=found))

    @commands.guild_only()
    @commands.command()
    async def stealcandy(self, ctx, user: discord.Member = None):
        """Steal some candy. Beware of shields!"""
        cooldown_secs = await self.config.guild(ctx.guild).steal_cooldown()
        bucket = self._steal_cooldown
        retry_after = bucket.get(ctx.author.id, 0)
        now = datetime.datetime.now(datetime.timezone.utc).timestamp()
        if now < retry_after:
            remaining = int(retry_after - now)
            return await ctx.send(
                _("You need to wait {remaining}s before stealing again.").format(remaining=remaining),
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
        bucket[ctx.author.id] = now + cooldown_secs
        guild_users = [m.id for m in ctx.guild.members if not m.bot and m != ctx.author]
        candy_users = await self.config._all_from_scope(scope="USER")
        valid_user = list(set(guild_users) & set(candy_users))
        if not valid_user:
            return await ctx.send(
                _("No one has any candy yet!"),
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
        if user and user != ctx.author and not user.bot:
            picked_user = user
        else:
            picked_user = self.bot.get_user(random.choice(valid_user))

        if picked_user is None:
            return await ctx.send(
                _("You couldn't find anyone to steal from."),
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )

        # ── Shield check ──
        if await self._check_shield(picked_user):
            remaining = await self._shield_remaining(picked_user)
            em = self._make_embed(
                _("🛡️ Shield Blocked!"),
                _("You tried to steal from **{name}**, but their candy bag\n"
                "is protected by a **magical shield**! ✨\n\n"
                "Shield expires in: {remaining}").format(name=picked_user.display_name, remaining=remaining),
                HALLOWEEN_PURPLE,
            )
            return await ctx.send(embed=em, reference=ctx.message.to_reference(fail_if_not_exists=False))

        picked_user_name = picked_user.display_name
        picked_candy_now = await self.config.user(picked_user).candies()

        if picked_candy_now == 0:
            chance = random.randint(1, 25)
            if chance in range(21, 25):
                new_picked_user = self.bot.get_user(random.choice(valid_user))
                if new_picked_user is None:
                    return await ctx.send(
                        _("You snuck around for a while but didn't find anything."),
                        reference=ctx.message.to_reference(fail_if_not_exists=False),
                    )
                new_picked_user_name = new_picked_user.display_name

                new_picked_candy_now = await self.config.user(new_picked_user).candies()
                if chance in range(24, 25):
                    if new_picked_candy_now == 0:
                        message = await ctx.send(
                            _("You see an unsuspecting guildmate..."),
                            reference=ctx.message.to_reference(fail_if_not_exists=False),
                        )
                        await asyncio.sleep(random.randint(3, 6))
                        return await message.edit(
                            content=_("There was nothing in {user1}'s pockets, so you picked {user2}'s pockets but they had no candy either!").format(user1=picked_user, user2=new_picked_user_name)
                        )
                else:
                    message = await ctx.send(
                        _("You see an unsuspecting guildmate..."),
                        reference=ctx.message.to_reference(fail_if_not_exists=False),
                    )
                    await asyncio.sleep(random.randint(3, 6))
                    return await message.edit(
                        content=_("There was nothing in {user1}'s pockets, so you looked around again... you saw {user2} in the distance, but you didn't think you could catch up...").format(user1=picked_user, user2=new_picked_user_name)
                    )
            if chance in range(10, 20):
                message = await ctx.send(
                    _("You start sneaking around in the shadows..."),
                    reference=ctx.message.to_reference(fail_if_not_exists=False),
                )
                await asyncio.sleep(random.randint(3, 6))
                return await message.edit(
                    content=_("You snuck up on {user} and tried picking their pockets but there was nothing there!").format(user=picked_user)
                )
            else:
                message = await ctx.send(
                    _("You start looking around for a target..."),
                    reference=ctx.message.to_reference(fail_if_not_exists=False),
                )
                await asyncio.sleep(random.randint(3, 6))
                return await message.edit(content=_("You snuck around for a while but didn't find anything."))

        user_candy_now = await self.config.user(ctx.author).candies()
        multip = random.randint(1, 100) / 100
        if multip > 0.7:
            multip = 0.7
        pieces = round(picked_candy_now * multip)
        if pieces <= 0:
            message = await ctx.send(
                _("You stealthily move over to an unsuspecting person..."),
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
            await asyncio.sleep(4)
            return await message.edit(content=_("You found someone to pickpocket, but they had nothing but pocket lint."))

        chance = random.randint(1, 25)
        sneak_phrases = [
            _("You look around furtively..."),
            _("You glance around slowly, looking for your target..."),
            _("You see someone with a full candy bag..."),
        ]
        if chance <= 10:
            message = await ctx.send(
                _("You creep closer to the target..."),
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
            await asyncio.sleep(random.randint(3, 5))
            return await message.edit(content=_("You snuck around for a while but didn't find anything."))

        # Determine stolen amount
        if chance > 18:
            stolen = pieces
        elif chance in range(11, 17):
            stolen = round(pieces / 2)
        else:
            message = await ctx.send(
                random.choice(sneak_phrases),
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
            await asyncio.sleep(4)
            noise_msg = [
                _("You hear a sound behind you! When you turn back, your target is gone."),
                _("You look away for a moment and your target has vanished."),
                _("Something flashes in your peripheral vision, and as you turn to look, your target gets away..."),
            ]
            return await message.edit(content=random.choice(noise_msg))

        # ── Successful steal! ──
        await self.config.user(picked_user).candies.set(picked_candy_now - stolen)
        await self.config.user(ctx.author).candies.set(user_candy_now + stolen)

        # Update stats
        author_stolen = await self.config.user(ctx.author).stolen()
        await self.config.user(ctx.author).stolen.set(author_stolen + stolen)
        victim_lost = await self.config.user(picked_user).been_stolen()
        await self.config.user(picked_user).been_stolen.set(victim_lost + stolen)

        # Update guild event
        result = await self._update_event_progress(ctx.guild, "steal", stolen)
        if result is True:
            await self._announce_event_completion(ctx.channel, ctx.guild)

        message = await ctx.send(
            random.choice(sneak_phrases),
            reference=ctx.message.to_reference(fail_if_not_exists=False),
        )
        await asyncio.sleep(4)
        await message.edit(content=_("There seems to be an unsuspecting victim in the corner..."))
        await asyncio.sleep(4)
        await message.edit(content=_("You stole {stolen} 🍬 from {user}!").format(stolen=stolen, user=picked_user))

        # ── Theft notification to victim ──
        try:
            notif_em = self._make_embed(
                _("🗡️ Candy Theft Alert!"),
                _("**{thief}** just stole **{stolen}** 🍬 from your bag!\n\n"
                "Remaining candies: **{remaining}** 🍬\n\n"
                "*Buy a 🛡️ Shield from the shop to protect yourself!*").format(
                    thief=ctx.author.display_name, stolen=stolen, remaining=picked_candy_now - stolen,
                ),
                HALLOWEEN_RED,
            )
            await picked_user.send(embed=notif_em)
        except (discord.Forbidden, discord.HTTPException):
            pass

    # ════════════════════════════════════════════════════════════
    #  GUILD EVENTS
    # ════════════════════════════════════════════════════════════

    @commands.guild_only()
    @checks.mod_or_permissions(administrator=True)
    @commands.group()
    async def totevent(self, ctx):
        """Manage guild-wide trick-or-treat events!"""
        if ctx.invoked_subcommand is None:
            if not await self.config.guild(ctx.guild).event_active():
                return await ctx.send(
                    _("No active event. Use `{prefix}totevent start <type> <goal>` to start one!\n"
                    "Event types: {event_types}").format(prefix=ctx.prefix, event_types=", ".join(EVENT_TYPES.keys()))
                )
            await self._show_event_status(ctx)

    async def _show_event_status(self, ctx):
        event_type = await self.config.guild(ctx.guild).event_type()
        goal = await self.config.guild(ctx.guild).event_goal()
        progress = await self.config.guild(ctx.guild).event_progress()
        reward = await self.config.guild(ctx.guild).event_reward()
        info = EVENT_TYPES.get(event_type, {})

        pct = min(100, round((progress / goal) * 100)) if goal > 0 else 0
        bar_filled = round(pct / 5)
        bar = "█" * bar_filled + "░" * (20 - bar_filled)

        em = self._make_embed(
            _("🎃 Guild Event — {desc}").format(desc=_(info.get("desc", "Unknown"))),
            f"**Goal:** {info.get('emoji', '🍬')} {event_type.title()} **{humanize_number(goal)}** candies!\n\n"
            f"**Progress:**\n{bar} **{humanize_number(progress)}**/{humanize_number(goal)} ({pct}%)\n\n"
            f"**Reward:** {humanize_number(reward)} 🍬 per participant\n\n"
            f"{'🎉 *Almost there! Keep going!*' if pct >= 75 else '💪 *Keep going!*'}",
            HALLOWEEN_GOLD if pct >= 75 else HALLOWEEN_PURPLE,
        )
        await ctx.send(embed=em)

    @totevent.command(name="start")
    async def totevent_start(self, ctx, event_type: str, goal: int, reward: int = 50):
        """Start a guild event!

        Types: eat, collect, steal
        Example: [p]totevent start eat 5000 100
        """
        event_type = event_type.lower()
        if event_type not in EVENT_TYPES:
            return await ctx.send(_("Invalid event type! Choose from: {types}").format(types=", ".join(EVENT_TYPES.keys())))
        if goal <= 0:
            return await ctx.send(_("Goal must be positive!"))
        if reward <= 0:
            return await ctx.send(_("Reward must be positive!"))
        if await self.config.guild(ctx.guild).event_active():
            return await ctx.send(_("An event is already active! Use `{prefix}totevent stop` to cancel it first.").format(prefix=ctx.prefix))

        await self.config.guild(ctx.guild).event_active.set(True)
        await self.config.guild(ctx.guild).event_type.set(event_type)
        await self.config.guild(ctx.guild).event_goal.set(goal)
        await self.config.guild(ctx.guild).event_progress.set(0)
        await self.config.guild(ctx.guild).event_reward.set(reward)

        info = EVENT_TYPES[event_type]
        em = self._make_embed(
            _("🎃 New Guild Event Started!"),
            _("**{desc}**\n\n"
            "{emoji} Goal: **{goal}** candies {event_type}!\n"
            "🍬 Reward: **{reward}** candies per participant!\n\n"
            "*Everyone's progress counts! Work together!* 🎃").format(
                desc=_(info["desc"]), emoji=info["emoji"],
                goal=humanize_number(goal), event_type=event_type,
                reward=humanize_number(reward),
            ),
            HALLOWEEN_GOLD,
        )
        await ctx.send(embed=em)

    @totevent.command(name="status")
    async def totevent_status(self, ctx):
        """Check the current event progress."""
        if not await self.config.guild(ctx.guild).event_active():
            return await ctx.send(_("No active event right now."))
        await self._show_event_status(ctx)

    @totevent.command(name="stop")
    async def totevent_stop(self, ctx):
        """Stop the current guild event."""
        if not await self.config.guild(ctx.guild).event_active():
            return await ctx.send(_("No active event to stop."))
        await self.config.guild(ctx.guild).event_active.set(False)
        em = self._make_embed(_("🎃 Event Cancelled"), _("The guild event has been cancelled."), HALLOWEEN_RED)
        await ctx.send(embed=em)

    # ════════════════════════════════════════════════════════════
    #  CHANNEL MANAGEMENT
    # ════════════════════════════════════════════════════════════

    @commands.guild_only()
    @checks.mod_or_permissions(administrator=True)
    @commands.group()
    async def totchannel(self, ctx):
        """Channel management for Trick or Treat."""
        if ctx.invoked_subcommand is not None:
            return
        channel_list = await self.config.guild(ctx.guild).channel()
        channel_msg = _("Trick or Treat Channels:\n")
        for chan in channel_list:
            channel_obj = self.bot.get_channel(chan)
            if channel_obj:
                channel_msg += f"{channel_obj.name}\n"
        await ctx.send(box(channel_msg))

    @commands.guild_only()
    @totchannel.command()
    async def add(self, ctx, channel: discord.TextChannel):
        """Add a text channel for Trick or Treating."""
        channel_list = await self.config.guild(ctx.guild).channel()
        tottoggle = await self.config.guild(ctx.guild).toggle()
        if not tottoggle:
            toggle_info = (
                _("\nThe game toggle for this server is **Off**. Turn it on with the `{prefix}tottoggle` command.").format(prefix=ctx.prefix)
            )
        else:
            toggle_info = ""
        if channel.id not in channel_list:
            channel_list.append(channel.id)
            await self.config.guild(ctx.guild).channel.set(channel_list)
            self._channel_cache[ctx.guild.id] = channel_list
            await ctx.send(_("{channel} added to the valid Trick or Treat channels.{toggle_info}").format(channel=channel.mention, toggle_info=toggle_info))
        else:
            await ctx.send(_("{channel} is already in the list of Trick or Treat channels.{toggle_info}").format(channel=channel.mention, toggle_info=toggle_info))

    @commands.guild_only()
    @totchannel.command()
    async def remove(self, ctx, channel: discord.TextChannel):
        """Remove a text channel from Trick or Treating."""
        channel_list = await self.config.guild(ctx.guild).channel()
        if channel.id in channel_list:
            channel_list.remove(channel.id)
        else:
            return await ctx.send(_("{channel} not in whitelist.").format(channel=channel.mention))
        await self.config.guild(ctx.guild).channel.set(channel_list)
        self._channel_cache[ctx.guild.id] = channel_list
        await ctx.send(_("{channel} removed from the list of Trick or Treat channels.").format(channel=channel.mention))

    @commands.guild_only()
    @checks.mod_or_permissions(administrator=True)
    @commands.command()
    async def tottoggle(self, ctx):
        """Toggle trick or treating on the whole server."""
        toggle = await self.config.guild(ctx.guild).toggle()
        msg = _("Trick or Treating active: {status}.\n").format(status=not toggle)
        channel_list = await self.config.guild(ctx.guild).channel()
        if not channel_list:
            channel_list.append(ctx.message.channel.id)
            await self.config.guild(ctx.guild).channel.set(channel_list)
            msg += _("Trick or Treating channel added: {channel}").format(channel=ctx.message.channel.mention)
        await self.config.guild(ctx.guild).toggle.set(not toggle)
        self._toggle_cache[ctx.guild.id] = not toggle
        await ctx.send(msg)

    @commands.guild_only()
    @checks.mod_or_permissions(administrator=True)
    @commands.command()
    async def totaddcandies(self, ctx, amount: int):
        """Add candies to the guild pool."""
        if amount <= 0:
            return await ctx.send(_("Amount must be greater than zero."))
        pick = await self.config.guild(ctx.guild).pick()
        await self.config.guild(ctx.guild).pick.set(pick + amount)
        await ctx.send(_("Added {amount} 🍬 to the pool. Now there are {total} 🍬 available to pick up.").format(amount=amount, total=pick + amount))

    @commands.guild_only()
    @commands.command(hidden=True)
    async def totversion(self, ctx):
        """Trick or Treat version."""
        await ctx.send(_("Trick or Treat version {version}").format(version=__version__))

    async def has_perm(self, user):
        return await self.bot.allowed_by_whitelist_blacklist(user)

    # ════════════════════════════════════════════════════════════
    #  MAIN GAME LOOP
    # ════════════════════════════════════════════════════════════

    @commands.Cog.listener()
    async def on_message_without_command(self, message):
        if isinstance(message.channel, discord.abc.PrivateChannel):
            return
        if message.author.bot:
            return

        guild = message.guild
        # Fast toggle check using cache
        if guild.id not in self._toggle_cache:
            self._toggle_cache[guild.id] = await self.config.guild(guild).toggle()
        if not self._toggle_cache[guild.id]:
            return

        if guild.id not in self._channel_cache:
            self._channel_cache[guild.id] = await self.config.guild(guild).channel()
        if message.channel.id not in self._channel_cache[guild.id]:
            return

        if not await self.has_perm(message.author):
            return

        # Passive sickness recovery and pool growth
        chance = random.randint(1, 12)
        if chance % 4 == 0:
            sickness_now = await self.config.user(message.author).sickness()
            sick_chance = random.randint(1, 12)
            if sick_chance % 3 == 0:
                new_sickness = max(0, sickness_now - sick_chance)
                await self.config.user(message.author).sickness.set(new_sickness)

        pick_chance = random.randint(1, 12)
        if pick_chance % 4 == 0:
            random_candies = random.randint(1, 3)
            guild_pool = await self.config.guild(guild).pick()
            await self.config.guild(guild).pick.set(guild_pool + random_candies)

        content = message.content.lower()
        if not content.startswith("trick or treat"):
            return
        userdata = await self.config.user(message.author).all()

        last_time = datetime.datetime.strptime(str(userdata["last_tot"]), "%Y-%m-%d %H:%M:%S.%f")
        now = datetime.datetime.now(datetime.timezone.utc)
        now = now.replace(tzinfo=None)
        if int((now - last_time).total_seconds()) < await self.config.guild(message.guild).cooldown():
            cooldown_messages = [
                _("The thought of candy right now doesn't really sound like a good idea."),
                _("All the lights on this street are dark..."),
                _("It's starting to get late."),
                _("The wind howls through the trees. Does it seem darker all of a sudden?"),
                _("You start to walk the long distance to the next house..."),
                _("You take a moment to count your candy before moving on."),
                _("The house you were approaching just turned the light off."),
                _("The wind starts to pick up as you look for the next house..."),
            ]
            return await message.channel.send(
                random.choice(cooldown_messages), reference=message.to_reference(fail_if_not_exists=False)
            )
        await self.config.user(message.author).last_tot.set(str(now))

        # ── Daily Streak ──
        today = now.strftime("%Y-%m-%d")
        yesterday = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        last_date = userdata.get("last_streak_date", "")
        streak = userdata.get("streak", 0)

        if last_date == today:
            pass  # Already played today
        elif last_date == yesterday:
            streak += 1
        else:
            streak = 1

        best_streak = max(userdata.get("best_streak", 0), streak)
        await self.config.user(message.author).streak.set(streak)
        await self.config.user(message.author).best_streak.set(best_streak)
        await self.config.user(message.author).last_streak_date.set(today)
        multiplier = _streak_multiplier(streak)

        sickness = userdata.get("sickness", 0)

        # ── Walking Phase ──
        walking_messages = [
            _("*You hear footsteps...*"),
            _("*You're left alone with your thoughts as you wait for the door to open...*"),
            _("*The wind howls through the trees...*"),
            _("*Does it feel colder out here all of a sudden?*"),
            _("*Somewhere inside the house, you hear wood creaking...*"),
            _("*You walk up the path to the door and knock...*"),
            _("*You knock on the door...*"),
            _("*There's a movement in the shadows by the side of the house...*"),
        ]
        bot_talking = await message.channel.send(
            random.choice(walking_messages), reference=message.to_reference(fail_if_not_exists=False)
        )
        await asyncio.sleep(random.randint(4, 7))

        door_messages = [
            _("*The door slowly opens...*"),
            _("*The ancient wooden door starts to open...*"),
            _("*A light turns on overhead...*"),
            _("*You hear a scuffling noise...*"),
            _("*There's someone talking inside...*"),
            _("*The wind whips around your feet...*"),
            _("*A crow caws ominously...*"),
            _("*You hear an owl hooting in the distance...*"),
        ]
        await bot_talking.edit(content=random.choice(door_messages))
        await asyncio.sleep(random.randint(4, 7))

        # ══════════════════════════════════════════════
        #  TRICK OR TREAT ROLL
        # ══════════════════════════════════════════════
        trick_roll = random.randint(1, 100)

        if trick_roll <= 25:
            # ══ TRICK! ══
            event = random.choice(TRICK_EVENTS)
            await self.config.user(message.author).trick_count.set(userdata.get("trick_count", 0) + 1)

            candy_lost = 0
            sickness_gained = 0

            if event["type"] == "candy_tax":
                candy_lost = min(random.randint(event["min_loss"], event["max_loss"]), userdata["candies"])
                await self.config.user(message.author).candies.set(userdata["candies"] - candy_lost)
                pool = await self.config.guild(guild).pick()
                await self.config.guild(guild).pick.set(pool + candy_lost)

            elif event["type"] == "sickness_curse":
                sickness_gained = event["sickness_add"]
                await self.config.user(message.author).sickness.set(sickness + sickness_gained)

            elif event["type"] == "haunted_house":
                sickness_gained = event["sickness_add"]
                candy_lost = min(random.randint(event["min_loss"], event["max_loss"]), userdata["candies"])
                await self.config.user(message.author).sickness.set(sickness + sickness_gained)
                await self.config.user(message.author).candies.set(userdata["candies"] - candy_lost)
                pool = await self.config.guild(guild).pick()
                await self.config.guild(guild).pick.set(pool + candy_lost)

            elif event["type"] == "candy_fumble":
                candy_lost = min(round(userdata["candies"] * event["loss_pct"]), userdata["candies"])
                await self.config.user(message.author).candies.set(userdata["candies"] - candy_lost)
                pool = await self.config.guild(guild).pick()
                await self.config.guild(guild).pick.set(pool + candy_lost)

            elif event["type"] == "cursed_candy":
                sickness_gained = event["sickness_add"]
                await self.config.user(message.author).sickness.set(sickness + sickness_gained)

            # Build trick embed
            trick_desc = _(event["desc"])
            effects = []
            if candy_lost > 0:
                effects.append(_("💔 Lost **{candy_lost}** candies!").format(candy_lost=candy_lost))
            if sickness_gained > 0:
                new_sick = sickness + sickness_gained
                effects.append(f"{_sickness_face(new_sick)} Sickness: **+{sickness_gained}** ({_sickness_bar(new_sick)} {new_sick}/100)")
            if effects:
                trick_desc += "\n\n" + "\n".join(effects)
            trick_desc += "\n\n" + _("*Better luck next time...* 👻")

            em = discord.Embed(
                title=_(event["title"]),
                description=trick_desc,
                color=HALLOWEEN_RED,
            )
            em.set_author(
                name=_("🎃 TRICK! — {name}").format(name=message.author.display_name),
                icon_url=message.author.display_avatar.url,
            )
            em.set_footer(text=_("🎃 Trick or Treat v{version}").format(version=__version__))
            await bot_talking.edit(content=None, embed=em)
            return

        # ══ TREAT! ══
        await self.config.user(message.author).treat_count.set(userdata.get("treat_count", 0) + 1)

        # Base candy
        candy = random.randint(1, 25)

        # Apply streak multiplier
        candy = round(candy * multiplier)

        # Apply sickness penalty
        sickness_penalty = ""
        if sickness > 100:
            candy = max(1, candy // 4)
            sickness_penalty = _("⚠️ *Sickness penalty: rewards quartered!*")
            # 50% chance of losing candy instead
            if random.random() < 0.5:
                lost = min(random.randint(1, 5), userdata["candies"])
                await self.config.user(message.author).candies.set(userdata["candies"] - lost)
                pool = await self.config.guild(guild).pick()
                await self.config.guild(guild).pick.set(pool + lost)
                em = discord.Embed(
                    title=_("🤮 Too Sick!"),
                    description=(
                        _("You're so sick that you **dropped** {lost} candies!\n\n"
                        "{face} {bar} **{sickness}**/100\n"
                        "*Eat chocolate or lollipops to recover!*").format(
                            lost=lost, face=_sickness_face(sickness),
                            bar=_sickness_bar(sickness), sickness=sickness,
                        )
                    ),
                    color=HALLOWEEN_RED,
                )
                em.set_author(
                    name=f"🎃 {message.author.display_name}",
                    icon_url=message.author.display_avatar.url,
                )
                em.set_footer(text=_("🎃 Trick or Treat v{version}").format(version=__version__))
                await bot_talking.edit(content=None, embed=em)
                return
        elif sickness > 80:
            candy = max(1, candy // 2)
            sickness_penalty = _("⚠️ *Sickness penalty: rewards halved!*")

        await self.config.user(message.author).candies.set(userdata["candies"] + candy)

        # Build treat embed
        greet_messages = [
            _("Oh, hello. What a cute costume!"),
            _("Look at that costume!"),
            _("Out this late at night?"),
            _("Here's a little something for you."),
            _("The peppermint ones are my favorite."),
            _("Come back again later if the light is still on."),
            _("Go ahead, take a few."),
            _("Aww, look at you. Here, take this."),
            _("Don't eat all those at once!"),
            _("Well, I think this is the last of it."),
        ]

        treat_desc = f"*\"{random.choice(greet_messages)}\"*\n\n"

        # Streak display
        streak_text = ""
        if streak > 1:
            streak_text = f" *(×{multiplier:.1f} streak!)*"
        treat_desc += f"🍬 **+{candy}** Candies{streak_text}\n"

        # Bonus drops
        bonus_lines = []
        for bonus_type, tiers in BONUS_TABLE.items():
            roll = random.randint(0, 100)
            for min_r, max_r, qty in tiers:
                if min_r <= roll <= max_r:
                    current = userdata.get(bonus_type, 0)
                    await getattr(self.config.user(message.author), bonus_type).set(current + qty)
                    bonus_lines.append(f"{CANDY_EMOJIS[bonus_type]} **+{qty}** {bonus_type.title()}")
                    break

        # Rare drops
        rare_lines = []
        golden_roll = random.random()
        if golden_roll < 0.005:  # 0.5% chance
            current_golden = userdata.get("golden_candies", 0)
            await self.config.user(message.author).golden_candies.set(current_golden + 1)
            rare_lines.append("✨ **+1 Golden Candy!** *(LEGENDARY!)*")

        pepper_roll = random.random()
        if pepper_roll < 0.003:  # 0.3% chance
            current_peppers = userdata.get("ghost_peppers", 0)
            await self.config.user(message.author).ghost_peppers.set(current_peppers + 1)
            rare_lines.append("🌶️ **+1 Ghost Pepper!** *(ULTRA RARE!)*")

        if bonus_lines:
            treat_desc += "\n" + _("**Bonus Drops:**") + "\n" + "\n".join(bonus_lines) + "\n"
        if rare_lines:
            treat_desc += "\n" + _("🌟 **RARE DROPS:**") + "\n" + "\n".join(rare_lines) + "\n"

        # Streak info
        if streak >= 2:
            treat_desc += f"\n🔥 **Streak:** {streak} day{'s' if streak != 1 else ''}"
        if sickness_penalty:
            treat_desc += f"\n{sickness_penalty}"

        # Sickness display
        treat_desc += f"\n💊 {_sickness_face(sickness)} {_sickness_bar(sickness)} {sickness}/100"

        # Color choice
        if rare_lines:
            embed_color = HALLOWEEN_GOLD
        elif sickness_penalty:
            embed_color = HALLOWEEN_ORANGE
        else:
            embed_color = HALLOWEEN_GREEN

        em = discord.Embed(
            description=treat_desc,
            color=embed_color,
        )
        em.set_author(
            name=_("🎃 TREAT! — {name}").format(name=message.author.display_name),
            icon_url=message.author.display_avatar.url,
        )
        em.set_footer(text=_("🎃 Trick or Treat v{version}").format(version=__version__))
        await bot_talking.edit(content=None, embed=em)

        # Update guild event
        result = await self._update_event_progress(guild, "collect", candy)
        if result is True:
            await self._announce_event_completion(message.channel, guild)

    # ──── ANSI Helpers ────

    @staticmethod
    def _red(to_transform: str):
        red_ansi_prefix = "\u001b[0;31m"
        reset_ansi_prefix = "\u001b[0;0m"
        new_string = f"{red_ansi_prefix}{to_transform}{reset_ansi_prefix}"
        return new_string

    @staticmethod
    def _yellow(to_transform: str):
        yellow_ansi_prefix = "\u001b[0;33m"
        reset_ansi_prefix = "\u001b[0;0m"
        new_string = f"{yellow_ansi_prefix}{to_transform}{reset_ansi_prefix}"
        return new_string
