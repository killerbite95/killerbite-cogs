import discord
from discord.ext import commands, tasks
from redbot.core import commands, Config, checks, bank
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n
import asyncio
import datetime

from redbot.core.bank import bank_prune
from .dashboard_integration import DashboardIntegration

_ = Translator("PruneBans", __file__)


@cog_i18n(_)
class PruneBans(DashboardIntegration, commands.Cog):
    """Cog to manage credit removal of banned users and track bans."""
    __author__ = "Killerbite95"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        self.config.register_guild(
            log_channel=None,
            ban_log_channel=None,
            ban_track={}
        )
        self.update_ban_countdown.start()

    def cog_unload(self):
        self.update_ban_countdown.cancel()

    @commands.command(name="setlogprune")
    @checks.admin_or_permissions(administrator=True)
    async def set_log_prune(self, ctx, channel: discord.TextChannel):
        """Set the channel where prune logs will be sent."""
        await self.config.guild(ctx.guild).log_channel.set(channel.id)
        await ctx.send(_("Prune log channel set to: {channel}").format(channel=channel.mention))

    @commands.command(name="setbanlog")
    @checks.admin_or_permissions(administrator=True)
    async def set_ban_log(self, ctx, channel: discord.TextChannel):
        """Set the channel where ban logs will be sent."""
        await self.config.guild(ctx.guild).ban_log_channel.set(channel.id)
        await ctx.send(_("Ban log channel set to: {channel}").format(channel=channel.mention))

    @commands.command(name="prune")
    @checks.admin_or_permissions(administrator=True)
    async def manual_prune(self, ctx):
        """Execute prune manually after confirmation."""
        guild = ctx.guild

        banned_users = [ban async for ban in guild.bans()]
        if not banned_users:
            await ctx.send(_("There are no banned users in this server."))
            return

        async with self.config.guild(guild).ban_track() as ban_track:
            users_to_prune = []
            for ban_entry in banned_users:
                user = ban_entry.user
                user_id_str = str(user.id)
                ban_info = ban_track.get(user_id_str)
                if ban_info:
                    users_to_prune.append((user, ban_info.get("balance", _("Unknown"))))

        if not users_to_prune:
            await ctx.send(_("There are no banned users with tracking records to prune."))
            return

        description = _("**Users that will be affected by prune:**") + "\n"
        for user, balance in users_to_prune:
            description += _("- {user} (ID: `{user_id}`), Credits: `{balance}`").format(
                user=user.mention, user_id=user.id, balance=balance
            ) + "\n"

        description += "\n" + _("**Do you want to continue?** React with ✅ to confirm or ❌ to cancel. *This action is irreversible.*")

        message = await ctx.send(description)

        await message.add_reaction("✅")
        await message.add_reaction("❌")

        def check(reaction, user):
            return (
                user == ctx.author
                and str(reaction.emoji) in ["✅", "❌"]
                and reaction.message.id == message.id
            )

        try:
            reaction, user = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)
            if str(reaction.emoji) == "✅":
                failed_prunes = await bank_prune(self.bot, guild=guild)

                if not failed_prunes:
                    await ctx.send(_("Prune executed successfully. Bank accounts of banned users have been removed."))
                else:
                    error_messages = "\n".join([f"ID {uid}: {error}" for uid, error in failed_prunes])
                    await ctx.send(_("Prune executed with errors. Details:") + f"\n{error_messages}")

                async with self.config.guild(guild).ban_track() as ban_track:
                    for user, _ in users_to_prune:
                        user_id_str = str(user.id)
                        if user_id_str in ban_track:
                            del ban_track[user_id_str]

                log_channel_id = await self.config.guild(guild).log_channel()
                if log_channel_id:
                    log_channel = guild.get_channel(log_channel_id)
                    if log_channel:
                        await log_channel.send(
                            _("Prune executed by {user}. Bank accounts of banned users have been removed.").format(
                                user=ctx.author.mention
                            )
                        )
            else:
                await ctx.send(_("Operation cancelled."))
        except asyncio.TimeoutError:
            await ctx.send(_("No confirmation received in time. Operation cancelled."))

    @commands.command(name="prunetest")
    @checks.admin_or_permissions(administrator=True)
    async def prune_test(self, ctx):
        """Test command to show users that would be affected by prune."""
        guild = ctx.guild

        banned_users = [ban async for ban in guild.bans()]
        if not banned_users:
            await ctx.send(_("There are no banned users in this server."))
            return

        async with self.config.guild(guild).ban_track() as ban_track:
            users_to_prune = []
            for ban_entry in banned_users:
                user = ban_entry.user
                user_id_str = str(user.id)
                ban_info = ban_track.get(user_id_str)
                if ban_info:
                    users_to_prune.append((user, ban_info.get("balance", _("Unknown"))))

        if not users_to_prune:
            await ctx.send(_("There are no banned users with tracking records to prune."))
            return

        description = _("**Users that would be affected by prune:**") + "\n"
        for user, balance in users_to_prune:
            description += _("- {user} (ID: `{user_id}`), Credits: `{balance}`").format(
                user=user.mention, user_id=user.id, balance=balance
            ) + "\n"

        await ctx.send(description)

    @commands.command(name="listbans")
    @checks.admin_or_permissions(administrator=True)
    async def list_bans(self, ctx):
        """List banned users with their credits."""
        guild = ctx.guild
        async with self.config.guild(guild).ban_track() as ban_track:
            if not ban_track:
                await ctx.send(_("There are no tracked bans."))
                return

            description = _("**Current Bans:**") + "\n"
            for user_id_str, ban_info in ban_track.items():
                user_id = int(user_id_str)
                balance = ban_info.get("balance", _("Unknown"))
                description += _("- User ID: `{user_id}`, Credits: `{balance}`").format(
                    user_id=user_id, balance=balance
                ) + "\n"
            await ctx.send(description)

    @commands.command(name="countdown")
    @checks.admin_or_permissions(administrator=True)
    async def countdown_bans(self, ctx):
        """Show a custom 7-day countdown for each ban."""
        guild = ctx.guild
        async with self.config.guild(guild).ban_track() as ban_track:
            if not ban_track:
                await ctx.send(_("There are no tracked bans."))
                return

            description = _("**Ban Countdown:**") + "\n"
            now = datetime.datetime.utcnow()
            for user_id_str, ban_info in ban_track.items():
                user_id = int(user_id_str)
                unban_date = datetime.datetime.fromisoformat(ban_info["unban_date"])
                remaining_time = unban_date - now
                remaining_days = max(0, remaining_time.days)
                remaining_seconds = remaining_time.seconds
                remaining_hours, remaining_minutes = divmod(remaining_seconds, 3600)
                remaining_minutes, _ = divmod(remaining_minutes, 60)
                remaining_hours = max(0, remaining_hours)
                remaining_minutes = max(0, remaining_minutes)
                user = guild.get_member(user_id)
                if user:
                    user_display = f"{user} (ID: {user_id})"
                else:
                    user_display = f"ID: {user_id}"
                balance = ban_info.get("balance", _("Unknown"))
                description += (
                    _("- {user}: `{days}` days, `{hours}` hours, `{minutes}` minutes remaining, Credits: `{balance}`").format(
                        user=user_display, days=remaining_days, hours=remaining_hours,
                        minutes=remaining_minutes, balance=balance
                    ) + "\n"
                )
            await ctx.send(description)

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        """Event triggered when a user is banned."""
        ban_log_channel_id = await self.config.guild(guild).ban_log_channel()
        if ban_log_channel_id:
            ban_log_channel = guild.get_channel(ban_log_channel_id)
            if ban_log_channel:
                ban_date = datetime.datetime.utcnow()
                unban_date = ban_date + datetime.timedelta(days=7)

                try:
                    balance = await bank.get_balance(user)
                    if not isinstance(balance, int):
                        balance = _("Unknown")
                except Exception:
                    balance = _("Unknown")

                if isinstance(balance, int) and balance > 0:
                    balance_info = balance
                else:
                    balance_info = _("Unknown")

                embed = discord.Embed(
                    title=_("🔨 User Banned"),
                    color=discord.Color.red(),
                    timestamp=ban_date
                )
                embed.add_field(name=_("User"), value=f"{user.mention} (ID: {user.id})", inline=False)
                embed.add_field(name=_("Ban Date"), value=ban_date.strftime('%Y-%m-%d %H:%M:%S UTC'), inline=False)
                embed.add_field(name=_("Countdown"), value=_("in 7 days"), inline=False)
                embed.add_field(name=_("End Date"), value=unban_date.strftime('%Y-%m-%d %H:%M:%S UTC'), inline=False)
                embed.add_field(name=_("Credits"), value=f"{balance_info}", inline=False)
                await ban_log_channel.send(embed=embed)

                async with self.config.guild(guild).ban_track() as ban_track:
                    ban_track[str(user.id)] = {
                        "ban_date": ban_date.isoformat(),
                        "unban_date": unban_date.isoformat(),
                        "balance": balance_info,
                        "message_id": None
                    }

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        """Event triggered when a user is unbanned manually."""
        async with self.config.guild(guild).ban_track() as ban_track:
            if str(user.id) in ban_track:
                del ban_track[str(user.id)]
                ban_log_channel_id = await self.config.guild(guild).ban_log_channel()
                if ban_log_channel_id:
                    ban_log_channel = guild.get_channel(ban_log_channel_id)
                    if ban_log_channel:
                        await ban_log_channel.send(
                            _("🔓 **User Unbanned Manually:** {user} (ID: {user_id})").format(
                                user=user.mention, user_id=user.id
                            )
                        )

    @tasks.loop(hours=24)
    async def update_ban_countdown(self):
        """Update ban countdowns every 24 hours."""
        for guild in self.bot.guilds:
            ban_log_channel_id = await self.config.guild(guild).ban_log_channel()
            if not ban_log_channel_id:
                continue
            ban_log_channel = guild.get_channel(ban_log_channel_id)
            if not ban_log_channel:
                continue
            async with self.config.guild(guild).ban_track() as ban_track:
                for user_id_str, ban_info in list(ban_track.items()):
                    ban_date = datetime.datetime.fromisoformat(ban_info["ban_date"])
                    now = datetime.datetime.utcnow()
                    time_since_ban = now - ban_date

                    if time_since_ban >= datetime.timedelta(days=7):
                        await ban_log_channel.send(
                            _("⏰ **User ID {user_id} has passed the 7-day ban period and is ready to be pruned.**").format(
                                user_id=user_id_str
                            )
                        )

    @update_ban_countdown.before_loop
    async def before_update_ban_countdown(self):
        await self.bot.wait_until_ready()
