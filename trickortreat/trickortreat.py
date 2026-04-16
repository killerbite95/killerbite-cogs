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
from redbot.core.utils.chat_formatting import box, pagify, humanize_number
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS

logger = logging.getLogger("red.killerbite95.trickortreat")

__version__ = "3.0.0"
__author__ = ["aikaterna", "Killerbite95"]

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
        em.set_footer(text=f"🎃 Trick or Treat v{__version__}")
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
            "🎉 Guild Event Complete!",
            f"The event goal has been reached!\n\n"
            f"🍬 All participants receive **{humanize_number(reward)}** bonus candies!\n"
            f"*Congratulations!* 🎃",
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
                "That doesn't sound fun.",
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
        if number == 0:
            return await ctx.send(
                "You pretend to eat a candy.",
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
        if candy_type not in CANDY_TYPES:
            return await ctx.send(
                "That's not a candy type! Use the inventory command to see what you have.",
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
        if userdata[candy_type] < number:
            return await ctx.send(
                f"You don't have that many {candy_type}.",
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
        if userdata[candy_type] == 0:
            return await ctx.send(
                f"You contemplate the idea of eating {candy_type}.",
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )

        eat_phrase = [
            "You leisurely enjoy",
            "You take the time to savor",
            "You eat",
            "You scarf down",
            "You sigh in contentment after eating",
            "You gobble up",
            "You make a meal of",
            "You devour",
            "You monstrously pig out on",
            "You hastily chomp down on",
            "You daintily partake of",
            "You earnestly consume",
        ]

        # ── Golden Candy (10× eaten, no sickness) ──
        if candy_type == "golden_candies":
            eaten_value = number * 10
            em = self._make_embed(
                "✨ Golden Candy!",
                f"{random.choice(eat_phrase)} {number} golden {'candy' if number == 1 else 'candies'}!\n\n"
                f"The golden shimmer fills you with warmth.\n"
                f"**+{eaten_value}** eaten count! *(10× bonus!)*\n"
                f"No sickness gained!",
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
                "🌶️ Ghost Pepper!",
                f"{random.choice(eat_phrase)} {number} ghost {'pepper' if number == 1 else 'peppers'}!\n\n"
                f"🔥 **SPICY!** Your mouth is on fire!\n"
                f"...but the heat burns away all your sickness!\n"
                f"💊 Sickness reset to **0**!",
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
                    "After all that candy, sugar doesn't sound so good.",
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
                    f"You begin to think you don't need all this candy, maybe...\n*{lost_candy} candies are left behind*",
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
                        content="You feel absolutely disgusted. At least you don't have any candies left."
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
                    content=f"You toss your candies on the ground in disgust.\n*{lost_candy} candies are left behind*"
                )

            pluralcandy = "candy" if number == 1 else "candies"
            new_eaten = userdata["eaten"] + number
            await ctx.send(
                f"{random.choice(eat_phrase)} {number} {pluralcandy}. (Total eaten: `{humanize_number(new_eaten)}` \N{CANDY})",
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
                f"{random.choice(eat_phrase)} {number} {pluralchoc}. You feel slightly better!\n*Sickness has gone down by {number * 10}*",
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
                f"{random.choice(eat_phrase)} {number} {pluralpop}. You feel slightly better!\n*Sickness has gone down by {number * 20}*",
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
                phrase = f"You feel worse!\n*Sickness has gone up by {new_sickness - old_sickness}*"
            else:
                phrase = f"You feel better!\n*Sickness has gone down by {old_sickness - new_sickness}*"
            await ctx.reply(f"{random.choice(eat_phrase)} {number} {pluralcookie}. {phrase}")
            await self.config.user(ctx.author).sickness.set(new_sickness)
            await self.config.user(ctx.author).cookies.set(userdata["cookies"] - number)
            await self.config.user(ctx.author).eaten.set(userdata["eaten"] + number)
            result = await self._update_event_progress(ctx.guild, "eat", number)
            if result is True:
                await self._announce_event_completion(ctx.channel, ctx.guild)

        if candy_type in ["stars", "star"]:
            pluralstar = "star" if number == 1 else "stars"
            await ctx.send(
                f"{random.choice(eat_phrase)} {number} {pluralstar}. You feel great!\n*Sickness has been reset*",
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
            "🎃 Guild Candy Pool",
            f"**{humanize_number(pick)}** \N{CANDY} on the ground",
            HALLOWEEN_ORANGE,
        )
        await ctx.send(embed=em)

    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    @commands.command()
    async def totgivecandy(self, ctx, user: discord.Member, candy_type: str, amount: int):
        """[Admin] Add candy to a user's inventory."""
        if amount <= 0:
            return await ctx.send("La cantidad debe ser mayor que cero.")
        resolved = _resolve_candy_type(candy_type)
        if resolved is None:
            return await ctx.send(f"Tipo de caramelo inválido. Los tipos válidos son: {', '.join(CANDY_TYPES)}.")
        userdata = await self.config.user(user).all()
        userdata[resolved] += amount
        await self.config.user(user).set(userdata)
        emoji = CANDY_EMOJIS.get(resolved, '')
        await ctx.send(f"Se han añadido {amount} {resolved} {emoji} al inventario de {user.display_name}.")

    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    @commands.command()
    async def totremovecandy(self, ctx, user: discord.Member, candy_type: str, amount: int):
        """[Admin] Remove candy from a user's inventory."""
        if amount <= 0:
            return await ctx.send("La cantidad debe ser mayor que cero.")
        resolved = _resolve_candy_type(candy_type)
        if resolved is None:
            return await ctx.send(f"Tipo de caramelo inválido. Los tipos válidos son: {', '.join(CANDY_TYPES)}.")
        userdata = await self.config.user(user).all()
        if userdata[resolved] < amount:
            emoji = CANDY_EMOJIS.get(resolved, '')
            return await ctx.send(f"{user.display_name} solo tiene {userdata[resolved]} {resolved} {emoji}. No se pueden quitar {amount}.")
        userdata[resolved] -= amount
        await self.config.user(user).set(userdata)
        emoji = CANDY_EMOJIS.get(resolved, '')
        await ctx.send(f"Se han quitado {amount} {resolved} {emoji} del inventario de {user.display_name}. Ahora tiene {userdata[resolved]} {resolved} {emoji}.")

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
                "Not in this reality.",
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
        per_piece = max(10, int(round(await bank.get_balance(ctx.author)) * 0.04))
        candy_price = per_piece * pieces
        try:
            await bank.withdraw_credits(ctx.author, candy_price)
        except ValueError:
            return await ctx.send(
                f"Not enough {credits_name} ({candy_price} required).",
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
        await self.config.user(ctx.author).candies.set(candy_now + pieces)
        em = self._make_embed(
            "🍬 Candy Purchased!",
            f"Bought **{pieces}** candies for **{humanize_number(candy_price)}** {credits_name}.",
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
            "🏪 Candy Shop",
            "Spend your hard-earned candies on special treats!\n━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            HALLOWEEN_PURPLE,
        )
        for name, item in SHOP_ITEMS.items():
            desc = item["desc"]
            if name == "shield":
                desc += f" ({shield_hours}h)"
            em.add_field(
                name=f"{item['emoji']} {name.replace('_', ' ').title()} — {item['price']} 🍬",
                value=desc,
                inline=False,
            )
        em.add_field(
            name="\u200b",
            value=f"Use `{ctx.prefix}totbuy <item> [amount]` to purchase!",
            inline=False,
        )
        user_candies = await self.config.user(ctx.author).candies()
        em.set_footer(text=f"🎃 Your candies: {humanize_number(user_candies)} | Trick or Treat v{__version__}")
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
                f"Unknown item! Available: {', '.join(SHOP_ITEMS.keys())}",
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
        if amount <= 0:
            return await ctx.send("Nice try.", reference=ctx.message.to_reference(fail_if_not_exists=False))

        item = SHOP_ITEMS[item_key]

        # Shield — only 1 at a time
        if item_key == "shield":
            amount = 1
            if await self._check_shield(ctx.author):
                remaining = await self._shield_remaining(ctx.author)
                return await ctx.send(
                    f"🛡️ You already have an active shield! ({remaining} remaining)",
                    reference=ctx.message.to_reference(fail_if_not_exists=False),
                )

        total_cost = item["price"] * amount
        user_candies = await self.config.user(ctx.author).candies()
        if user_candies < total_cost:
            return await ctx.send(
                f"Not enough candies! You need **{total_cost}** 🍬 but have **{user_candies}** 🍬.",
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )

        # Deduct candies
        await self.config.user(ctx.author).candies.set(user_candies - total_cost)

        if item_key == "shield":
            shield_hours = await self.config.guild(ctx.guild).shield_hours()
            shield_until = time.time() + (shield_hours * 3600)
            await self.config.user(ctx.author).shield_until.set(shield_until)
            em = self._make_embed(
                "🛡️ Shield Activated!",
                f"A magical shield now protects your candy bag!\n\n"
                f"⏱️ Duration: **{shield_hours} hours**\n"
                f"🍬 Cost: **{total_cost}** candies",
                HALLOWEEN_GREEN,
            )
        else:
            field = item["field"]
            current = await getattr(self.config.user(ctx.author), field)()
            await getattr(self.config.user(ctx.author), field).set(current + amount)
            em = self._make_embed(
                f"{item['emoji']} Purchase Complete!",
                f"Bought **{amount}** {item_key.replace('_', ' ')} for **{total_cost}** 🍬\n"
                f"Remaining candies: **{user_candies - total_cost}** 🍬",
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
                "No one has any candy.",
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
        async with ctx.typing():
            sorted_acc = sorted(userinfo.items(), key=lambda x: x[1]["eaten"], reverse=True)
        pound_len = len(str(len(sorted_acc)))
        score_len = 10
        header = "{pound:{pound_len}}{score:{score_len}}{name:2}\n".format(
            pound="#",
            pound_len=pound_len + 3,
            score="Candies Eaten",
            score_len=score_len + 6,
            name="Name",
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
                description=box(f"\N{CANDY} Global Leaderboard \N{CANDY}", lang="prolog") + (box(page, lang="ansi")),
            )
            embed.set_footer(
                text=f"🎃 Page {humanize_number(pages)}/{humanize_number(math.ceil(len(scoreboard_msg) / 1000))} | Trick or Treat v{__version__}"
            )
            pages += 1
            page_list.append(embed)
        return await menu(ctx, page_list, DEFAULT_CONTROLS)

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
            name=f"🎃 {ctx.author.display_name}'s Candy Bag",
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
        em.add_field(name="🍬 Inventory", value="\n".join(inv_lines), inline=False)

        # Sickness
        sick_text = f"{face} {bar} **{sickness}**/100"
        if sickness > 100:
            sick_text += "\n⚠️ *Rewards quartered! You might lose candy...*"
        elif sickness > 80:
            sick_text += "\n⚠️ *Rewards halved! Eat chocolate to recover.*"
        elif sickness > 60:
            sick_text += "\n😨 *You really don't feel so good...*"
        elif sickness > 40:
            sick_text += "\n😰 *You don't feel so great...*"
        em.add_field(name="💊 Sickness", value=sick_text, inline=False)

        # Streak & Shield
        status_lines = []
        if streak > 0:
            streak_emoji = "🔥" if streak >= 5 else "📅"
            status_lines.append(f"{streak_emoji} **Streak:** {streak} day{'s' if streak != 1 else ''} (×{multiplier:.1f} bonus)")
        if best_streak > 0:
            status_lines.append(f"🏆 **Best Streak:** {best_streak} days")
        if await self._check_shield(ctx.author):
            remaining = await self._shield_remaining(ctx.author)
            status_lines.append(f"🛡️ **Shield:** ✅ Active ({remaining} left)")
        if status_lines:
            em.add_field(name="📋 Status", value="\n".join(status_lines), inline=False)

        # Stats
        stats_lines = [
            f"🍬 **Eaten:** {humanize_number(userdata.get('eaten', 0))}",
            f"🎭 **Tricks:** {userdata.get('trick_count', 0)} │ **Treats:** {userdata.get('treat_count', 0)}",
            f"🗡️ **Stolen:** {humanize_number(userdata.get('stolen', 0))} │ **Lost:** {humanize_number(userdata.get('been_stolen', 0))}",
        ]
        em.add_field(name="📊 Stats", value="\n".join(stats_lines), inline=False)

        em.set_footer(text=f"🎃 Trick or Treat v{__version__}")
        await ctx.send(embed=em)

    # ════════════════════════════════════════════════════════════
    #  GAME GUIDE
    # ════════════════════════════════════════════════════════════

    @commands.guild_only()
    @commands.command()
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def tothelp(self, ctx):
        """📖 Guía completa del juego Trick or Treat."""
        p = ctx.prefix
        pages = []

        # ── Page 1: Introduction ──
        em1 = self._make_embed(
            "📖 Guía — ¿Cómo jugar?",
            (
                "¡Bienvenido a **Trick or Treat**! 🎃\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "**¿Cómo empezar?**\n"
                "Escribe **`trick or treat`** en un canal habilitado para ir de puerta en puerta "
                "pidiendo caramelos. ¡Pero cuidado! No siempre te dan dulces...\n\n"
                "**🎁 Treat (75%)** — Recibes caramelos y posibles bonus.\n"
                "**👻 Trick (25%)** — Algo malo pasa: pierdes caramelos, te enfermas, o ambas cosas.\n\n"
                "**Objetivo:** Comer la mayor cantidad de caramelos posible y subir en el ranking global.\n\n"
                f"Usa `{p}cinventory` para ver tu inventario y `{p}cboard` para el ranking."
            ),
            HALLOWEEN_ORANGE,
        )
        em1.set_footer(text=f"🎃 Página 1/6 — Trick or Treat v{__version__}")
        pages.append(em1)

        # ── Page 2: Candy Types ──
        em2 = self._make_embed(
            "🍬 Guía — Tipos de Caramelos",
            (
                "Cada tipo de caramelo tiene un efecto especial al comerlo:\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "🍬 **Candies** — El caramelo principal. Comerlos aumenta tu contador de *eaten* (puntuación), "
                "pero **también sube tu enfermedad** (+2 por candy).\n\n"
                "🍫 **Chocolates** — Reduce enfermedad en **10** por unidad. ¡Medicina dulce!\n\n"
                "🍭 **Lollipops** — Reduce enfermedad en **20** por unidad. Más efectivo.\n\n"
                "🥠 **Cookies** — Pone tu enfermedad en un número **aleatorio** (0-100). ¡Una apuesta!\n\n"
                "⭐ **Stars** — Resetea tu enfermedad a **0** instantáneamente. ¡Lo mejor!\n\n"
                "✨ **Golden Candy** — *LEGENDARIO*. Vale **10×** en puntuación y **no da enfermedad**.\n\n"
                "🌶️ **Ghost Pepper** — *ULTRA RARO*. Resetea enfermedad a **0** al comerlo."
            ),
            HALLOWEEN_PURPLE,
        )
        em2.add_field(
            name="📝 Cómo comer",
            value=f"`{p}eatcandy [cantidad] [tipo]`\nEjemplos: `{p}eatcandy 3 chocolate` · `{p}eatcandy star`",
            inline=False,
        )
        em2.set_footer(text=f"🎃 Página 2/6 — Trick or Treat v{__version__}")
        pages.append(em2)

        # ── Page 3: Sickness System ──
        em3 = self._make_embed(
            "💊 Guía — Sistema de Enfermedad",
            (
                "La enfermedad sube cuando comes candies y afecta tus recompensas:\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "😊 **0-40** — Todo normal. Sin penalización.\n\n"
                "😰 **41-80** — Empiezas a sentirte mal, pero no hay castigo aún.\n\n"
                "🤮 **81-100** — ⚠️ **Recompensas a la mitad.** Si ibas a "
                "ganar 20 candies, ganas 10.\n\n"
                "💀 **>100** — ⚠️ **Recompensas divididas entre 4** + un **50% de probabilidad** "
                "de que se te **caigan** candies al suelo al ir de puerta en puerta.\n\n"
                "**¿Cómo curarse?**\n"
                "🍫 Chocolates (-10) · 🍭 Lollipops (-20) · ⭐ Stars (reset) · 🌶️ Ghost Peppers (reset)\n"
                "También se recupera un poco de forma pasiva al chatear en canales de ToT."
            ),
            HALLOWEEN_RED,
        )
        em3.add_field(
            name="💡 Consejo",
            value="No dejes subir la enfermedad por encima de 80. Compra curas en la tienda si no te salen de bonus.",
            inline=False,
        )
        em3.set_footer(text=f"🎃 Página 3/6 — Trick or Treat v{__version__}")
        pages.append(em3)

        # ── Page 4: Shop & Shield ──
        em4 = self._make_embed(
            "🏪 Guía — Tienda y Escudo",
            (
                "Gasta tus candies en la tienda para comprar objetos útiles:\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Usa `{p}totshop` para ver la tienda y `{p}totbuy <item> [cantidad]` para comprar.\n\n"
                "🍫 **Chocolate** — 15 🍬 · Reduce enfermedad\n"
                "🍭 **Lollipop** — 30 🍬 · Reduce más enfermedad\n"
                "🥠 **Cookie** — 25 🍬 · Enfermedad aleatoria\n"
                "⭐ **Star** — 50 🍬 · Reset enfermedad\n"
                "🛡️ **Shield** — 75 🍬 · Protección contra robo\n"
                "✨ **Golden Candy** — 200 🍬 · 10× puntuación, sin enfermedad\n"
            ),
            HALLOWEEN_PURPLE,
        )
        em4.add_field(
            name="🛡️ ¿Qué hace el Escudo?",
            value=(
                "El escudo protege tu bolsa de caramelos contra robos con `stealcandy`. "
                "Dura varias horas (configurable por admins). Solo puedes tener **1 activo** a la vez."
            ),
            inline=False,
        )
        em4.set_footer(text=f"🎃 Página 4/6 — Trick or Treat v{__version__}")
        pages.append(em4)

        # ── Page 5: Streaks, Stealing & Rare Items ──
        em5 = self._make_embed(
            "🔥 Guía — Rachas, Robos e Ítems Raros",
            (
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "**🔥 Rachas Diarias (Streak)**\n"
                "Juega `trick or treat` cada día consecutivo para acumular racha.\n"
                "Cada día de racha añade un **×0.1** a tu multiplicador de recompensa.\n"
                "Día 1: ×1.0 · Día 5: ×1.5 · Día 10: ×2.0 · Máximo: **×3.0**\n"
                "¡Si fallas un día, la racha se resetea!\n\n"
                "**🗡️ Robar Caramelos**\n"
                f"Usa `{p}stealcandy [@usuario]` para intentar robar.\n"
                "No siempre funciona — hay varias probabilidades de éxito o fracaso.\n"
                "La víctima recibe una **notificación por DM** cuando le roban. 📩\n"
                "Compra un **🛡️ Shield** para protegerte.\n\n"
                "**💎 Ítems Raros**\n"
                "Al hacer `trick or treat`, hay una pequeña probabilidad de obtener:\n"
                "✨ **Golden Candy** (0.5%) — Vale ×10 al comerlo.\n"
                "🌶️ **Ghost Pepper** (0.3%) — Resetea tu enfermedad.\n"
            ),
            HALLOWEEN_GOLD,
        )
        em5.set_footer(text=f"🎃 Página 5/6 — Trick or Treat v{__version__}")
        pages.append(em5)

        # ── Page 6: Commands Reference ──
        em6 = self._make_embed(
            "📋 Guía — Lista de Comandos",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            HALLOWEEN_ORANGE,
        )
        em6.add_field(
            name="🎮 Jugador",
            value=(
                f"`trick or treat` — Ir de puerta en puerta\n"
                f"`{p}eatcandy [n] [tipo]` — Comer caramelos\n"
                f"`{p}cinventory` — Ver tu inventario\n"
                f"`{p}totstats [@user]` — Estadísticas detalladas\n"
                f"`{p}cboard` — Ranking global de eaten\n"
                f"`{p}totshop` — Ver la tienda\n"
                f"`{p}totbuy <item> [n]` — Comprar en la tienda\n"
                f"`{p}buycandy <n>` — Comprar candies con moneda del bot\n"
                f"`{p}pickup` — Recoger candy del suelo\n"
                f"`{p}stealcandy [@user]` — Robar caramelos\n"
                f"`{p}tothelp` — Esta guía"
            ),
            inline=False,
        )
        em6.add_field(
            name="🔧 Admin / Mod",
            value=(
                f"`{p}tottoggle` — Activar/desactivar el juego\n"
                f"`{p}totchannel add/remove` — Canales de juego\n"
                f"`{p}totcooldown [s]` — Cooldown de trick or treat\n"
                f"`{p}totpickupcooldown [s]` — Cooldown de pickup\n"
                f"`{p}totstealcooldown [s]` — Cooldown de steal\n"
                f"`{p}totshieldhours [h]` — Duración del escudo\n"
                f"`{p}totbalance` — Candies en el pool\n"
                f"`{p}totaddcandies <n>` — Añadir al pool\n"
                f"`{p}totgivecandy @user tipo n` — Dar candy\n"
                f"`{p}totremovecandy @user tipo n` — Quitar candy\n"
                f"`{p}totevent start/status/stop` — Eventos de guild"
            ),
            inline=False,
        )
        em6.set_footer(text=f"🎃 Página 6/6 — Trick or Treat v{__version__}")
        pages.append(em6)

        await menu(ctx, pages, DEFAULT_CONTROLS)

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
            name=f"📊 {user.display_name}'s Statistics",
            icon_url=user.display_avatar.url,
        )
        em.set_thumbnail(url=user.display_avatar.url)

        em.add_field(
            name="🍬 Candy Stats",
            value=(
                f"Total Eaten: **{humanize_number(userdata.get('eaten', 0))}**\n"
                f"Current Candies: **{humanize_number(userdata.get('candies', 0))}**\n"
                f"Sickness: {_sickness_face(userdata.get('sickness', 0))} **{userdata.get('sickness', 0)}**/100"
            ),
            inline=True,
        )
        em.add_field(
            name="🔥 Streaks",
            value=(
                f"Current: **{streak}** day{'s' if streak != 1 else ''}\n"
                f"Best: **{best_streak}** day{'s' if best_streak != 1 else ''}\n"
                f"Multiplier: **×{_streak_multiplier(streak):.1f}**"
            ),
            inline=True,
        )
        em.add_field(
            name="🎭 Trick or Treat",
            value=(
                f"Total Visits: **{total_visits}**\n"
                f"Treats: **{treats}** ({treat_pct}%)\n"
                f"Tricks: **{tricks}** ({100 - treat_pct}%)"
            ),
            inline=True,
        )
        em.add_field(
            name="🗡️ Theft Record",
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
            em.add_field(name="💎 Rare Items", value=rare_text.strip(), inline=True)

        if await self._check_shield(user):
            remaining = await self._shield_remaining(user)
            em.add_field(name="🛡️ Shield", value=f"✅ Active ({remaining} left)", inline=True)

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
            msg = "This will clear ALL saved data for this cog and reset it to the defaults.\n"
            msg += f"If you are absolutely sure you want to do this, use `{ctx.prefix}totclearall yes`."
            return await ctx.send(msg)
        await self.config.clear_all()
        await ctx.send("All data for this cog has been cleared.")

    @commands.guild_only()
    @checks.mod_or_permissions(administrator=True)
    @commands.command()
    async def totcooldown(self, ctx, cooldown_time: int = 0):
        """Set the cooldown time for trick or treating on the server."""
        if cooldown_time < 0:
            return await ctx.send("Nice try.")
        if cooldown_time == 0:
            await self.config.guild(ctx.guild).cooldown.set(300)
            return await ctx.send("Trick or treating cooldown time reset to 5m.")
        elif 1 <= cooldown_time <= 30:
            await self.config.guild(ctx.guild).cooldown.set(30)
            return await ctx.send("Trick or treating cooldown time set to the minimum of 30s.")
        else:
            await self.config.guild(ctx.guild).cooldown.set(cooldown_time)
            await ctx.send(f"Trick or treating cooldown time set to {cooldown_time}s.")

    @commands.guild_only()
    @checks.mod_or_permissions(administrator=True)
    @commands.command()
    async def totpickupcooldown(self, ctx, seconds: int = 0):
        """Set the cooldown time for the pickup command (default: 600s)."""
        if seconds < 0:
            return await ctx.send("Nice try.")
        if seconds == 0:
            await self.config.guild(ctx.guild).pickup_cooldown.set(600)
            return await ctx.send("Pickup cooldown reset to 10m (600s).")
        val = max(30, seconds)
        await self.config.guild(ctx.guild).pickup_cooldown.set(val)
        await ctx.send(f"Pickup cooldown set to {val}s.")

    @commands.guild_only()
    @checks.mod_or_permissions(administrator=True)
    @commands.command()
    async def totstealcooldown(self, ctx, seconds: int = 0):
        """Set the cooldown time for the stealcandy command (default: 600s)."""
        if seconds < 0:
            return await ctx.send("Nice try.")
        if seconds == 0:
            await self.config.guild(ctx.guild).steal_cooldown.set(600)
            return await ctx.send("Steal cooldown reset to 10m (600s).")
        val = max(30, seconds)
        await self.config.guild(ctx.guild).steal_cooldown.set(val)
        await ctx.send(f"Steal cooldown set to {val}s.")

    @commands.guild_only()
    @checks.mod_or_permissions(administrator=True)
    @commands.command()
    async def totshieldhours(self, ctx, hours: int = 0):
        """Set how many hours a shield lasts (default: 4)."""
        if hours <= 0:
            await self.config.guild(ctx.guild).shield_hours.set(4)
            return await ctx.send("Shield duration reset to 4 hours.")
        await self.config.guild(ctx.guild).shield_hours.set(hours)
        await ctx.send(f"Shield duration set to {hours} hours.")

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
                f"You need to wait {remaining}s before picking up candy again.",
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
        bucket[ctx.author.id] = now + cooldown_secs
        candies = await self.config.user(ctx.author).candies()
        to_pick = await self.config.guild(ctx.guild).pick()
        if to_pick <= 0:
            message = await ctx.send(
                "You start searching the area for candy...",
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
            await asyncio.sleep(3)
            return await message.edit(content="There's no candy left on the ground!")
        chance = random.randint(1, 100)
        found = min(round((chance / 100) * to_pick), to_pick)
        await self.config.user(ctx.author).candies.set(candies + found)
        await self.config.guild(ctx.guild).pick.set(to_pick - found)
        message = await ctx.send(
            "You start searching the area for candy...",
            reference=ctx.message.to_reference(fail_if_not_exists=False),
        )
        await asyncio.sleep(3)
        await message.edit(content=f"You found {found} \N{CANDY}!")

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
                f"You need to wait {remaining}s before stealing again.",
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
        bucket[ctx.author.id] = now + cooldown_secs
        guild_users = [m.id for m in ctx.guild.members if not m.bot and m != ctx.author]
        candy_users = await self.config._all_from_scope(scope="USER")
        valid_user = list(set(guild_users) & set(candy_users))
        if not valid_user:
            return await ctx.send(
                "No one has any candy yet!",
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
        if user and user != ctx.author and not user.bot:
            picked_user = user
        else:
            picked_user = self.bot.get_user(random.choice(valid_user))

        if picked_user is None:
            return await ctx.send(
                "You couldn't find anyone to steal from.",
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )

        # ── Shield check ──
        if await self._check_shield(picked_user):
            remaining = await self._shield_remaining(picked_user)
            em = self._make_embed(
                "🛡️ Shield Blocked!",
                f"You tried to steal from **{picked_user.display_name}**, but their candy bag\n"
                f"is protected by a **magical shield**! ✨\n\n"
                f"Shield expires in: {remaining}",
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
                        "You snuck around for a while but didn't find anything.",
                        reference=ctx.message.to_reference(fail_if_not_exists=False),
                    )
                new_picked_user_name = new_picked_user.display_name

                new_picked_candy_now = await self.config.user(new_picked_user).candies()
                if chance in range(24, 25):
                    if new_picked_candy_now == 0:
                        message = await ctx.send(
                            "You see an unsuspecting guildmate...",
                            reference=ctx.message.to_reference(fail_if_not_exists=False),
                        )
                        await asyncio.sleep(random.randint(3, 6))
                        return await message.edit(
                            content=f"There was nothing in {picked_user}'s pockets, so you picked {new_picked_user_name}'s pockets but they had no candy either!"
                        )
                else:
                    message = await ctx.send(
                        "You see an unsuspecting guildmate...",
                        reference=ctx.message.to_reference(fail_if_not_exists=False),
                    )
                    await asyncio.sleep(random.randint(3, 6))
                    return await message.edit(
                        content=f"There was nothing in {picked_user}'s pockets, so you looked around again... you saw {new_picked_user_name} in the distance, but you didn't think you could catch up..."
                    )
            if chance in range(10, 20):
                message = await ctx.send(
                    "You start sneaking around in the shadows...",
                    reference=ctx.message.to_reference(fail_if_not_exists=False),
                )
                await asyncio.sleep(random.randint(3, 6))
                return await message.edit(
                    content=f"You snuck up on {picked_user} and tried picking their pockets but there was nothing there!"
                )
            else:
                message = await ctx.send(
                    "You start looking around for a target...",
                    reference=ctx.message.to_reference(fail_if_not_exists=False),
                )
                await asyncio.sleep(random.randint(3, 6))
                return await message.edit(content="You snuck around for a while but didn't find anything.")

        user_candy_now = await self.config.user(ctx.author).candies()
        multip = random.randint(1, 100) / 100
        if multip > 0.7:
            multip = 0.7
        pieces = round(picked_candy_now * multip)
        if pieces <= 0:
            message = await ctx.send(
                "You stealthily move over to an unsuspecting person...",
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
            await asyncio.sleep(4)
            return await message.edit(content="You found someone to pickpocket, but they had nothing but pocket lint.")

        chance = random.randint(1, 25)
        sneak_phrases = [
            "You look around furtively...",
            "You glance around slowly, looking for your target...",
            "You see someone with a full candy bag...",
        ]
        if chance <= 10:
            message = await ctx.send(
                "You creep closer to the target...",
                reference=ctx.message.to_reference(fail_if_not_exists=False),
            )
            await asyncio.sleep(random.randint(3, 5))
            return await message.edit(content="You snuck around for a while but didn't find anything.")

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
                "You hear a sound behind you! When you turn back, your target is gone.",
                "You look away for a moment and your target has vanished.",
                "Something flashes in your peripheral vision, and as you turn to look, your target gets away...",
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
        await message.edit(content="There seems to be an unsuspecting victim in the corner...")
        await asyncio.sleep(4)
        await message.edit(content=f"You stole {stolen} \N{CANDY} from {picked_user}!")

        # ── Theft notification to victim ──
        try:
            notif_em = self._make_embed(
                "🗡️ Candy Theft Alert!",
                f"**{ctx.author.display_name}** just stole **{stolen}** 🍬 from your bag!\n\n"
                f"Remaining candies: **{picked_candy_now - stolen}** 🍬\n\n"
                f"*Buy a 🛡️ Shield from the shop to protect yourself!*",
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
                    f"No active event. Use `{ctx.prefix}totevent start <type> <goal>` to start one!\n"
                    f"Event types: {', '.join(EVENT_TYPES.keys())}"
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
            f"🎃 Guild Event — {info.get('desc', 'Unknown')}",
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
            return await ctx.send(f"Invalid event type! Choose from: {', '.join(EVENT_TYPES.keys())}")
        if goal <= 0:
            return await ctx.send("Goal must be positive!")
        if reward <= 0:
            return await ctx.send("Reward must be positive!")
        if await self.config.guild(ctx.guild).event_active():
            return await ctx.send(f"An event is already active! Use `{ctx.prefix}totevent stop` to cancel it first.")

        await self.config.guild(ctx.guild).event_active.set(True)
        await self.config.guild(ctx.guild).event_type.set(event_type)
        await self.config.guild(ctx.guild).event_goal.set(goal)
        await self.config.guild(ctx.guild).event_progress.set(0)
        await self.config.guild(ctx.guild).event_reward.set(reward)

        info = EVENT_TYPES[event_type]
        em = self._make_embed(
            "🎃 New Guild Event Started!",
            f"**{info['desc']}**\n\n"
            f"{info['emoji']} Goal: **{humanize_number(goal)}** candies {event_type}!\n"
            f"🍬 Reward: **{humanize_number(reward)}** candies per participant!\n\n"
            f"*Everyone's progress counts! Work together!* 🎃",
            HALLOWEEN_GOLD,
        )
        await ctx.send(embed=em)

    @totevent.command(name="status")
    async def totevent_status(self, ctx):
        """Check the current event progress."""
        if not await self.config.guild(ctx.guild).event_active():
            return await ctx.send("No active event right now.")
        await self._show_event_status(ctx)

    @totevent.command(name="stop")
    async def totevent_stop(self, ctx):
        """Stop the current guild event."""
        if not await self.config.guild(ctx.guild).event_active():
            return await ctx.send("No active event to stop.")
        await self.config.guild(ctx.guild).event_active.set(False)
        em = self._make_embed("🎃 Event Cancelled", "The guild event has been cancelled.", HALLOWEEN_RED)
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
        channel_msg = "Trick or Treat Channels:\n"
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
                f"\nThe game toggle for this server is **Off**. Turn it on with the `{ctx.prefix}tottoggle` command."
            )
        else:
            toggle_info = ""
        if channel.id not in channel_list:
            channel_list.append(channel.id)
            await self.config.guild(ctx.guild).channel.set(channel_list)
            self._channel_cache[ctx.guild.id] = channel_list
            await ctx.send(f"{channel.mention} added to the valid Trick or Treat channels.{toggle_info}")
        else:
            await ctx.send(f"{channel.mention} is already in the list of Trick or Treat channels.{toggle_info}")

    @commands.guild_only()
    @totchannel.command()
    async def remove(self, ctx, channel: discord.TextChannel):
        """Remove a text channel from Trick or Treating."""
        channel_list = await self.config.guild(ctx.guild).channel()
        if channel.id in channel_list:
            channel_list.remove(channel.id)
        else:
            return await ctx.send(f"{channel.mention} not in whitelist.")
        await self.config.guild(ctx.guild).channel.set(channel_list)
        self._channel_cache[ctx.guild.id] = channel_list
        await ctx.send(f"{channel.mention} removed from the list of Trick or Treat channels.")

    @commands.guild_only()
    @checks.mod_or_permissions(administrator=True)
    @commands.command()
    async def tottoggle(self, ctx):
        """Toggle trick or treating on the whole server."""
        toggle = await self.config.guild(ctx.guild).toggle()
        msg = f"Trick or Treating active: {not toggle}.\n"
        channel_list = await self.config.guild(ctx.guild).channel()
        if not channel_list:
            channel_list.append(ctx.message.channel.id)
            await self.config.guild(ctx.guild).channel.set(channel_list)
            msg += f"Trick or Treating channel added: {ctx.message.channel.mention}"
        await self.config.guild(ctx.guild).toggle.set(not toggle)
        self._toggle_cache[ctx.guild.id] = not toggle
        await ctx.send(msg)

    @commands.guild_only()
    @checks.mod_or_permissions(administrator=True)
    @commands.command()
    async def totaddcandies(self, ctx, amount: int):
        """Add candies to the guild pool."""
        if amount <= 0:
            return await ctx.send("La cantidad debe ser mayor que cero.")
        pick = await self.config.guild(ctx.guild).pick()
        await self.config.guild(ctx.guild).pick.set(pick + amount)
        await ctx.send(f"Se han añadido {amount} 🍬 al pool actual. Ahora hay {pick + amount} 🍬 disponibles para recoger.")

    @commands.guild_only()
    @commands.command(hidden=True)
    async def totversion(self, ctx):
        """Trick or Treat version."""
        await ctx.send(f"Trick or Treat version {__version__}")

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
                "The thought of candy right now doesn't really sound like a good idea.",
                "All the lights on this street are dark...",
                "It's starting to get late.",
                "The wind howls through the trees. Does it seem darker all of a sudden?",
                "You start to walk the long distance to the next house...",
                "You take a moment to count your candy before moving on.",
                "The house you were approaching just turned the light off.",
                "The wind starts to pick up as you look for the next house...",
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
            "*You hear footsteps...*",
            "*You're left alone with your thoughts as you wait for the door to open...*",
            "*The wind howls through the trees...*",
            "*Does it feel colder out here all of a sudden?*",
            "*Somewhere inside the house, you hear wood creaking...*",
            "*You walk up the path to the door and knock...*",
            "*You knock on the door...*",
            "*There's a movement in the shadows by the side of the house...*",
        ]
        bot_talking = await message.channel.send(
            random.choice(walking_messages), reference=message.to_reference(fail_if_not_exists=False)
        )
        await asyncio.sleep(random.randint(4, 7))

        door_messages = [
            "*The door slowly opens...*",
            "*The ancient wooden door starts to open...*",
            "*A light turns on overhead...*",
            "*You hear a scuffling noise...*",
            "*There's someone talking inside...*",
            "*The wind whips around your feet...*",
            "*A crow caws ominously...*",
            "*You hear an owl hooting in the distance...*",
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
            trick_desc = event["desc"]
            effects = []
            if candy_lost > 0:
                effects.append(f"💔 Lost **{candy_lost}** candies!")
            if sickness_gained > 0:
                new_sick = sickness + sickness_gained
                effects.append(f"{_sickness_face(new_sick)} Sickness: **+{sickness_gained}** ({_sickness_bar(new_sick)} {new_sick}/100)")
            if effects:
                trick_desc += "\n\n" + "\n".join(effects)
            trick_desc += f"\n\n*Better luck next time...* 👻"

            em = discord.Embed(
                title=event["title"],
                description=trick_desc,
                color=HALLOWEEN_RED,
            )
            em.set_author(
                name=f"🎃 TRICK! — {message.author.display_name}",
                icon_url=message.author.display_avatar.url,
            )
            em.set_footer(text=f"🎃 Trick or Treat v{__version__}")
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
            sickness_penalty = "⚠️ *Sickness penalty: rewards quartered!*"
            # 50% chance of losing candy instead
            if random.random() < 0.5:
                lost = min(random.randint(1, 5), userdata["candies"])
                await self.config.user(message.author).candies.set(userdata["candies"] - lost)
                pool = await self.config.guild(guild).pick()
                await self.config.guild(guild).pick.set(pool + lost)
                em = discord.Embed(
                    title="🤮 Too Sick!",
                    description=(
                        f"You're so sick that you **dropped** {lost} candies!\n\n"
                        f"{_sickness_face(sickness)} {_sickness_bar(sickness)} **{sickness}**/100\n"
                        f"*Eat chocolate or lollipops to recover!*"
                    ),
                    color=HALLOWEEN_RED,
                )
                em.set_author(
                    name=f"🎃 {message.author.display_name}",
                    icon_url=message.author.display_avatar.url,
                )
                em.set_footer(text=f"🎃 Trick or Treat v{__version__}")
                await bot_talking.edit(content=None, embed=em)
                return
        elif sickness > 80:
            candy = max(1, candy // 2)
            sickness_penalty = "⚠️ *Sickness penalty: rewards halved!*"

        await self.config.user(message.author).candies.set(userdata["candies"] + candy)

        # Build treat embed
        greet_messages = [
            "Oh, hello. What a cute costume!",
            "Look at that costume!",
            "Out this late at night?",
            "Here's a little something for you.",
            "The peppermint ones are my favorite.",
            "Come back again later if the light is still on.",
            "Go ahead, take a few.",
            "Aww, look at you. Here, take this.",
            "Don't eat all those at once!",
            "Well, I think this is the last of it.",
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
            treat_desc += "\n**Bonus Drops:**\n" + "\n".join(bonus_lines) + "\n"
        if rare_lines:
            treat_desc += "\n🌟 **RARE DROPS:**\n" + "\n".join(rare_lines) + "\n"

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
            name=f"🎃 TREAT! — {message.author.display_name}",
            icon_url=message.author.display_avatar.url,
        )
        em.set_footer(text=f"🎃 Trick or Treat v{__version__}")
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
