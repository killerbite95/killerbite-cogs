import json
import os
from redbot.core import commands, Config, checks
from redbot.core.i18n import Translator, cog_i18n
import discord
import asyncio
import logging

_ = Translator("ColaCoins", __file__)


@cog_i18n(_)
class ColaCoins(commands.Cog):
    """Manage ColaCoins for users."""
    __author__ = "Killerbite95"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_global = {
            "colacoins": {},
            "emoji": ""
        }
        self.config.register_global(**default_global)
        self.logger = logging.getLogger("red.ColaCoins")
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
        handler.setFormatter(formatter)
        if not self.logger.handlers:
            self.logger.addHandler(handler)

    async def save_data(self):
        data = await self.config.colacoins()
        with open("colacoins_data.json", "w") as f:
            json.dump(data, f)

    async def load_data(self):
        if os.path.exists("colacoins_data.json"):
            with open("colacoins_data.json", "r") as f:
                data = json.load(f)
                await self.config.colacoins.set(data)

    @commands.Cog.listener()
    async def on_ready(self):
        await self.load_data()

    @commands.admin_or_permissions(administrator=True)
    @commands.command(name="givecolacoins", aliases=["darcolacoins"])
    async def give_colacoins(self, ctx, user: discord.Member, amount: int):
        """Give ColaCoins to a user."""
        if amount <= 0:
            await ctx.send(_("The amount to give must be positive."))
            return

        async with self.config.colacoins() as colacoins:
            if str(user.id) not in colacoins:
                colacoins[str(user.id)] = 0
            colacoins[str(user.id)] += amount
            emoji = await self.config.emoji() or ""
            await ctx.send(
                _("{amount} {emoji} ColaCoins given to {user}. Now they have {total} {emoji} ColaCoins.").format(
                    amount=amount, emoji=emoji, user=user.display_name,
                    total=colacoins[str(user.id)]
                )
            )
        await self.save_data()
        self.logger.info(f"{ctx.author} gave {amount} ColaCoins to {user}.")

    @commands.admin_or_permissions(administrator=True)
    @commands.command(name="removecolacoins", aliases=["quitarcolacoins"])
    async def remove_colacoins(self, ctx, user: discord.Member, amount: int):
        """Remove ColaCoins from a user."""
        if amount <= 0:
            await ctx.send(_("The amount to remove must be positive."))
            return

        async with self.config.colacoins() as colacoins:
            current = colacoins.get(str(user.id), 0)
            if current < amount:
                emoji = await self.config.emoji() or ""
                await ctx.send(
                    _("Cannot remove {amount} {emoji} ColaCoins. {user} does not have enough ColaCoins.").format(
                        amount=amount, emoji=emoji, user=user.display_name
                    )
                )
                return
            colacoins[str(user.id)] -= amount
            emoji = await self.config.emoji() or ""
            await ctx.send(
                _("{amount} {emoji} ColaCoins removed from {user}. Now they have {total} {emoji} ColaCoins.").format(
                    amount=amount, emoji=emoji, user=user.display_name,
                    total=colacoins[str(user.id)]
                )
            )
        await self.save_data()
        self.logger.info(f"{ctx.author} removed {amount} ColaCoins from {user}.")

    @commands.admin_or_permissions(administrator=True)
    @commands.command(name="vercolacoins", aliases=["viewcolacoins"])
    async def ver_colacoins(self, ctx, user: discord.Member):
        """Check the ColaCoins amount of a user."""
        colacoins = await self.config.colacoins()
        amount = colacoins.get(str(user.id), 0)
        emoji = await self.config.emoji() or ""
        await ctx.send(
            _("{user} has {amount} {emoji} ColaCoins.").format(
                user=user.display_name, amount=amount, emoji=emoji
            )
        )

    @commands.command(name="colacoins", aliases=["miscolacoins"])
    async def user_colacoins(self, ctx):
        """See how many ColaCoins you have."""
        colacoins = await self.config.colacoins()
        amount = colacoins.get(str(ctx.author.id), 0)
        emoji = await self.config.emoji() or ""
        await ctx.send(
            _("You have {amount} {emoji} ColaCoins.").format(amount=amount, emoji=emoji)
        )

    @commands.admin_or_permissions(administrator=True)
    @commands.command(name="setcolacoinemoji", aliases=["establecercolacoinemoji"])
    async def set_colacoin_emoji(self, ctx, emoji: str):
        """Set the emoji for ColaCoins."""
        await self.config.emoji.set(emoji)
        await ctx.send(_("ColaCoins emoji set to {emoji}.").format(emoji=emoji))

    @commands.command(name="colacoinslist", aliases=["colacoinslista"])
    @checks.admin_or_permissions(administrator=True)
    async def colacoins_list_command(self, ctx):
        """Shows a leaderboard of users with the most ColaCoins."""
        colacoins = await self.config.colacoins()
        if not colacoins:
            await ctx.send(_("There are no users with ColaCoins currently."))
            return

        sorted_colacoins = sorted(
            ((user_id, amount) for user_id, amount in colacoins.items() if amount > 0),
            key=lambda x: x[1],
            reverse=True
        )

        if not sorted_colacoins:
            await ctx.send(_("There are no users with more than 0 ColaCoins currently."))
            return

        leaderboard = []
        for idx, (user_id, amount) in enumerate(sorted_colacoins, start=1):
            try:
                user = self.bot.get_user(int(user_id))
                if user:
                    username = user.display_name
                else:
                    username = _("User ID {user_id}").format(user_id=user_id)
            except ValueError:
                username = _("User ID {user_id}").format(user_id=user_id)
            emoji = await self.config.emoji() or ""
            if idx == 1:
                medal = "🥇"
            elif idx == 2:
                medal = "🥈"
            elif idx == 3:
                medal = "🥉"
            else:
                medal = f"{idx}."

            leaderboard.append(f"{medal} **{username}** - {amount} {emoji} ColaCoins")

        per_page = 10
        pages = [leaderboard[i:i + per_page] for i in range(0, len(leaderboard), per_page)]
        total_pages = len(pages)
        current_page = 0

        embed = discord.Embed(
            title=_("🏆 ColaCoins Leaderboard"),
            description="\n".join(pages[current_page]),
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else self.bot.user.default_avatar.url)
        embed.set_footer(text=_("Page {current} of {total} • Total Users: {users}").format(
            current=current_page + 1, total=total_pages, users=len(sorted_colacoins)
        ))

        message = await ctx.send(embed=embed)

        if total_pages <= 1:
            return

        await message.add_reaction("◀️")
        await message.add_reaction("▶️")

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["◀️", "▶️"] and reaction.message.id == message.id

        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=120.0, check=check)
            except asyncio.TimeoutError:
                await message.clear_reactions()
                break
            else:
                if str(reaction.emoji) == "▶️":
                    if current_page + 1 < total_pages:
                        current_page += 1
                        embed.description = "\n".join(pages[current_page])
                        embed.set_footer(text=_("Page {current} of {total} • Total Users: {users}").format(
                            current=current_page + 1, total=total_pages, users=len(sorted_colacoins)
                        ))
                        await message.edit(embed=embed)
                elif str(reaction.emoji) == "◀️":
                    if current_page > 0:
                        current_page -= 1
                        embed.description = "\n".join(pages[current_page])
                        embed.set_footer(text=_("Page {current} of {total} • Total Users: {users}").format(
                            current=current_page + 1, total=total_pages, users=len(sorted_colacoins)
                        ))
                        await message.edit(embed=embed)
                await message.remove_reaction(reaction, user)
