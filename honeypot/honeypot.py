import os
import typing

import discord
from discord import ui

from AAA3A_utils import Cog, Settings
from redbot.core import Config, commands, modlog
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import box

# Credits:
# General repo credits.
# Thanks to Matt for the cog idea!

_: Translator = Translator("Honeypot", __file__)


class HoneypotStatsView(ui.View):
    """View with stats button for honeypot channel."""

    def __init__(self, cog: "Honeypot", guild: discord.Guild):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild = guild

    @ui.button(
        label="Honeypot Stats",
        style=discord.ButtonStyle.blurple,
        emoji="🍯",
        custom_id="honeypot_stats_button",
    )
    async def stats_button(self, interaction: discord.Interaction, button: ui.Button):
        """Show honeypot statistics."""
        config = self.cog.config.guild(self.guild)
        count = await config.moderated_count()
        await interaction.response.send_message(
            embed=discord.Embed(
                title=_("🍯 Honeypot Statistics"),
                description=_(
                    "**Server Stats:**\n"
                    "Total moderated in this server: **{count}**"
                ).format(count=count),
                color=discord.Color.gold(),
            ),
            ephemeral=True,
        )


@cog_i18n(_)
class Honeypot(Cog):
    """Create a channel at the top of the server to attract self bots/scammers and notify/mute/kick/ban them immediately!"""

    def __init__(self, bot: Red) -> None:
        super().__init__(bot=bot)

        self.config: Config = Config.get_conf(
            self,
            identifier=84087103974849346152204789206146721878,
            force_registration=True,
        )
        self.config.register_guild(
            enabled=False,
            action=None,
            logs_channel=None,
            ping_role=None,
            honeypot_channel=None,
            honeypot_embed_id=None,
            mute_role=None,
            ban_delete_message_days=3,
            moderated_count=0,
        )

        _settings: dict[str, dict[str, typing.Any]] = {
            "enabled": {
                "converter": bool,
                "description": "Toggle the cog.",
            },
            "action": {
                "converter": typing.Literal["mute", "kick", "ban"],
                "description": "The action to take when a self bot/scammer is detected.",
            },
            "logs_channel": {
                "converter": typing.Union[
                    discord.TextChannel,
                    discord.VoiceChannel,
                    discord.Thread,
                ],
                "description": "The channel to send the logs to.",
            },
            "ping_role": {
                "converter": discord.Role,
                "description": "The role to ping when a self bot/scammer is detected.",
            },
            "mute_role": {
                "converter": discord.Role,
                "description": "The mute role to assign to the self bots/scammers, if the action is `mute`.",
            },
            "ban_delete_message_days": {
                "converter": commands.Range[int, 0, 7],
                "description": "The number of days of messages to delete when banning a self bot/scammer.",
            },
        }
        self.settings: Settings = Settings(
            bot=self.bot,
            cog=self,
            config=self.config,
            group=self.config.GUILD,
            settings=_settings,
            global_path=[],
            use_profiles_system=False,
            can_edit=True,
            commands_group=self.sethoneypot,
        )

    async def cog_load(self) -> None:
        await super().cog_load()
        await self.settings.add_commands()

    async def _update_honeypot_embed(self, guild: discord.Guild) -> None:
        """Update the honeypot channel embed with new stats."""
        config = self.config.guild(guild)
        honeypot_channel_id = await config.honeypot_channel()
        honeypot_embed_id = await config.honeypot_embed_id()
        if honeypot_channel_id is None or honeypot_embed_id is None:
            return
        channel = guild.get_channel(honeypot_channel_id)
        if channel is None:
            return
        try:
            message = await channel.fetch_message(honeypot_embed_id)
        except discord.HTTPException:
            return
        # Get new count
        count = await config.moderated_count()
        # Rebuild embed with same structure
        embed = discord.Embed(
            title=_("⚠️ DO NOT POST HERE! ⚠️"),
            description=_(
                "An action will be immediately taken against you if you send a message in this channel.",
            ),
            color=discord.Color.red(),
        )
        embed.add_field(
            name=_("What not to do?"),
            value=_("Do not send any messages in this channel."),
            inline=False,
        )
        embed.add_field(
            name=_("What WILL happen?"),
            value=_("An action will be taken against you."),
            inline=False,
        )
        embed.add_field(
            name=_("🍯 Honeypot Statistics"),
            value=_("**Server Stats:**\nTotal moderated in this server: **{count}**").format(
                count=count
            ),
            inline=False,
        )
        embed.set_footer(text=guild.name, icon_url=guild.icon)
        # Select image based on guild locale
        guild_locale = await self.bot._config.guild(guild).locale()
        if guild_locale and guild_locale.startswith("es"):
            image_file = "no_postear_aqui.png"
        else:
            image_file = "do_not_post_here.png"
        embed.set_image(url=f"attachment://{image_file}")
        # Update view
        view = HoneypotStatsView(cog=self, guild=guild)
        await message.edit(
            content=_("## ⚠️ WARNING ⚠️"),
            embed=embed,
            attachments=[discord.File(os.path.join(os.path.dirname(__file__), image_file))],
            view=view,
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None:
            return
        if await self.bot.cog_disabled_in_guild(self, message.guild):
            return
        if message.author.bot:
            return
        config = await self.config.guild(message.guild).all()
        if (
            not config["enabled"]
            or (honeypot_channel_id := config["honeypot_channel"]) is None
            or (logs_channel_id := config["logs_channel"]) is None
            or (logs_channel := message.guild.get_channel(logs_channel_id)) is None
        ):
            return
        if message.channel.id != honeypot_channel_id:
            return
        if (
            message.author.id in self.bot.owner_ids
            or await self.bot.is_mod(message.author)
            or await self.bot.is_admin(message.author)
            or message.author.guild_permissions.manage_guild
            or message.author.top_role >= message.guild.me.top_role
        ):
            return
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        action = config["action"]
        embed: discord.Embed = discord.Embed(
            title=_("Honeypot — Self Bot/Scammer Detected!"),
            description=f">>> {message.content}",
            color=discord.Color.red(),
            timestamp=message.created_at,
        )
        embed.set_author(
            name=f"{message.author.display_name} ({message.author.id})",
            icon_url=message.author.display_avatar,
        )
        embed.set_thumbnail(url=message.author.display_avatar)
        failed = None
        if action is not None:
            reason = _("Self bot/scammer detected (message in the HoneyPot channel).")
            try:
                if action == "mute":
                    if (mute_role_id := config["mute_role"]) is not None and (
                        mute_role := message.guild.get_role(mute_role_id)
                    ) is not None:
                        await message.author.add_roles(mute_role, reason=reason)
                    else:
                        failed = _("**Failed:** The mute role is not set or doesn't exist anymore.")
                elif action == "kick":
                    await message.author.kick(reason=reason)
                elif action == "ban":
                    await message.author.ban(
                        reason=reason,
                        delete_message_days=config["ban_delete_message_days"],
                    )
            except discord.HTTPException as e:
                failed = _(
                    "**Failed:** An error occurred while trying to take action against the member:\n",
                ) + box(str(e), lang="py")
            else:
                await modlog.create_case(
                    self.bot,
                    message.guild,
                    message.created_at,
                    action_type=action if action != "mute" else "smute",
                    user=message.author,
                    moderator=message.guild.me,
                    reason=reason,
                )
                # Increment moderated count
                current_count = await self.config.guild(message.guild).moderated_count()
                await self.config.guild(message.guild).moderated_count.set(current_count + 1)
                # Update honeypot embed with new count
                await self._update_honeypot_embed(message.guild)
            embed.add_field(
                name=_("Action:"),
                value=(
                    (
                        _("The member has been muted.")
                        if action == "mute"
                        else (
                            _("The member has been kicked.")
                            if action == "kick"
                            else _("The member has been banned.")
                        )
                    )
                    if failed is None
                    else failed
                ),
                inline=False,
            )
        embed.set_footer(text=message.guild.name, icon_url=message.guild.icon)
        await logs_channel.send(
            content=(
                ping_role.mention
                if (ping_role_id := config["ping_role"]) is not None
                and (ping_role := message.guild.get_role(ping_role_id)) is not None
                else None
            ),
            embed=embed,
            allowed_mentions=discord.AllowedMentions(roles=True),
        )

    @commands.guild_only()
    @commands.guildowner()
    @commands.hybrid_group()
    async def sethoneypot(self, ctx: commands.Context) -> None:
        """Set the honeypot settings. Only the server owner can use this command for security reasons."""
        pass

    @commands.bot_has_guild_permissions(manage_channels=True)
    @sethoneypot.command(aliases=["makechannel"])
    async def createchannel(self, ctx: commands.Context) -> None:
        """Create the honeypot channel."""
        if (
            honeypot_channel_id := await self.config.guild(ctx.guild).honeypot_channel()
        ) is not None and (
            honeypot_channel := ctx.guild.get_channel(honeypot_channel_id)
        ) is not None:
            raise commands.UserFeedbackCheckFailure(
                _(
                    "The honeypot channel already exists: {honeypot_channel.mention} ({honeypot_channel.id}).",
                ).format(honeypot_channel=honeypot_channel),
            )
        honeypot_channel = await ctx.guild.create_text_channel(
            name="honeypot",
            position=0,
            overwrites={
                ctx.guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    read_messages=True,
                    send_messages=True,
                    manage_messages=True,
                    manage_channels=True,
                ),
                ctx.guild.default_role: discord.PermissionOverwrite(
                    view_channel=True,
                    read_messages=True,
                    send_messages=True,
                ),
            },
            reason=f"Honeypot channel creation requested by {ctx.author.display_name} ({ctx.author.id}).",
        )
        embed = discord.Embed(
            title=_("⚠️ DO NOT POST HERE! ⚠️"),
            description=_(
                "An action will be immediately taken against you if you send a message in this channel.",
            ),
            color=discord.Color.red(),
        )
        embed.add_field(
            name=_("What not to do?"),
            value=_("Do not send any messages in this channel."),
            inline=False,
        )
        embed.add_field(
            name=_("What WILL happen?"),
            value=_("An action will be taken against you."),
            inline=False,
        )
        # Add stats field
        moderated_count = await self.config.guild(ctx.guild).moderated_count()
        embed.add_field(
            name=_("🍯 Honeypot Statistics"),
            value=_("**Server Stats:**\nTotal moderated in this server: **{count}**").format(
                count=moderated_count
            ),
            inline=False,
        )
        embed.set_footer(text=ctx.guild.name, icon_url=ctx.guild.icon)
        # Select image based on guild locale
        guild_locale = await self.bot._config.guild(ctx.guild).locale()
        if guild_locale and guild_locale.startswith("es"):
            image_file = "no_postear_aqui.png"
        else:
            image_file = "do_not_post_here.png"
        embed.set_image(url=f"attachment://{image_file}")
        # Create view with stats button
        view = HoneypotStatsView(cog=self, guild=ctx.guild)
        honeypot_msg = await honeypot_channel.send(
            content=_("## ⚠️ WARNING ⚠️"),
            embed=embed,
            files=[discord.File(os.path.join(os.path.dirname(__file__), image_file))],
            view=view,
        )
        await self.config.guild(ctx.guild).honeypot_channel.set(honeypot_channel.id)
        await self.config.guild(ctx.guild).honeypot_embed_id.set(honeypot_msg.id)
        await ctx.send(
            _(
                "The honeypot channel has been set to {honeypot_channel.mention} ({honeypot_channel.id}). You can now start attracting self bots/scammers!\n"
                "Please make sure to enable the cog and set the logs channel, the action to take, the role to ping (and the mute role) if you haven't already.",
            ).format(honeypot_channel=honeypot_channel),
        )

    @commands.bot_has_guild_permissions(manage_messages=True)
    @sethoneypot.command()
    async def resend(self, ctx: commands.Context) -> None:
        """Resend the honeypot embed (deletes the old one and sends a new one)."""
        config = self.config.guild(ctx.guild)
        honeypot_channel_id = await config.honeypot_channel()
        if honeypot_channel_id is None:
            raise commands.UserFeedbackCheckFailure(
                _("The honeypot channel is not configured. Use `[p]sethoneypot createchannel` first."),
            )
        honeypot_channel = ctx.guild.get_channel(honeypot_channel_id)
        if honeypot_channel is None:
            raise commands.UserFeedbackCheckFailure(
                _("The honeypot channel no longer exists. Use `[p]sethoneypot createchannel` to create a new one."),
            )
        # Delete old embed if exists
        old_embed_id = await config.honeypot_embed_id()
        if old_embed_id is not None:
            try:
                old_msg = await honeypot_channel.fetch_message(old_embed_id)
                await old_msg.delete()
            except discord.HTTPException:
                pass
        # Send new embed
        count = await config.moderated_count()
        embed = discord.Embed(
            title=_("⚠️ DO NOT POST HERE! ⚠️"),
            description=_(
                "An action will be immediately taken against you if you send a message in this channel.",
            ),
            color=discord.Color.red(),
        )
        embed.add_field(
            name=_("What not to do?"),
            value=_("Do not send any messages in this channel."),
            inline=False,
        )
        embed.add_field(
            name=_("What WILL happen?"),
            value=_("An action will be taken against you."),
            inline=False,
        )
        embed.add_field(
            name=_("🍯 Honeypot Statistics"),
            value=_("**Server Stats:**\nTotal moderated in this server: **{count}**").format(
                count=count
            ),
            inline=False,
        )
        embed.set_footer(text=ctx.guild.name, icon_url=ctx.guild.icon)
        # Select image based on guild locale
        guild_locale = await self.bot._config.guild(ctx.guild).locale()
        if guild_locale and guild_locale.startswith("es"):
            image_file = "no_postear_aqui.png"
        else:
            image_file = "do_not_post_here.png"
        embed.set_image(url=f"attachment://{image_file}")
        view = HoneypotStatsView(cog=self, guild=ctx.guild)
        honeypot_msg = await honeypot_channel.send(
            content=_("## ⚠️ WARNING ⚠️"),
            embed=embed,
            files=[discord.File(os.path.join(os.path.dirname(__file__), image_file))],
            view=view,
        )
        await config.honeypot_embed_id.set(honeypot_msg.id)
        await ctx.send(
            _("✅ Honeypot embed has been resent to {channel}.").format(channel=honeypot_channel.mention),
        )
