import logging
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

log: logging.Logger = logging.getLogger("red.killerbite95.honeypot")

# Guild-level permission required by each action.
ACTION_PERMISSIONS: dict[str, str] = {
    "mute": "manage_roles",
    "kick": "kick_members",
    "ban": "ban_members",
}


class HoneypotStatsView(ui.View):
    """Persistent view with a stats button for the honeypot channel."""

    def __init__(self, cog: "Honeypot"):
        super().__init__(timeout=None)
        self.cog: "Honeypot" = cog

    @ui.button(
        label="Honeypot Stats",
        style=discord.ButtonStyle.blurple,
        emoji="🍯",
        custom_id="honeypot_stats_button",
    )
    async def stats_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Show honeypot statistics."""
        if interaction.guild is None:
            return
        count = await self.cog.config.guild(interaction.guild).moderated_count()
        await interaction.response.send_message(
            embed=discord.Embed(
                title=_("🍯 Honeypot Statistics"),
                description=_(
                    "**Server Stats:**\nTotal moderated in this server: **{count}**"
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
        # Register the view as persistent so the stats button keeps working after a restart.
        self.bot.add_view(HoneypotStatsView(cog=self))

    def _get_image_file(self, locale: typing.Optional[str]) -> str:
        """Return the warning image file name matching the guild locale."""
        if locale is not None and locale.startswith("es"):
            return "no_postear_aqui.png"
        return "do_not_post_here.png"

    async def _build_honeypot_embed(
        self, guild: discord.Guild
    ) -> tuple[discord.Embed, str]:
        """Build the honeypot warning embed and return it with its image file name."""
        count = await self.config.guild(guild).moderated_count()
        embed = discord.Embed(
            title=_("⚠️ DO NOT POST HERE! ⚠️"),
            description=_(
                "An action will be immediately taken against you if you send a message in this channel."
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
        image_file = self._get_image_file(await self.bot._config.guild(guild).locale())
        embed.set_image(url=f"attachment://{image_file}")
        return embed, image_file

    async def _send_honeypot_embed(
        self, channel: discord.abc.Messageable, guild: discord.Guild
    ) -> discord.Message:
        """Send a fresh honeypot warning message and return it."""
        embed, image_file = await self._build_honeypot_embed(guild)
        return await channel.send(
            content=_("## ⚠️ WARNING ⚠️"),
            embed=embed,
            files=[discord.File(os.path.join(os.path.dirname(__file__), image_file))],
            view=HoneypotStatsView(cog=self),
        )

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
        embed, image_file = await self._build_honeypot_embed(guild)
        try:
            await message.edit(
                content=_("## ⚠️ WARNING ⚠️"),
                embed=embed,
                attachments=[
                    discord.File(os.path.join(os.path.dirname(__file__), image_file))
                ],
                view=HoneypotStatsView(cog=self),
            )
        except discord.HTTPException as e:
            log.warning(
                "Failed to update the honeypot embed in guild %s (%s): %s", guild.name, guild.id, e
            )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None:
            return
        if message.author.bot or message.webhook_id is not None:
            return
        # Without the members intent (or on an uncached author) we can't evaluate permissions.
        if not isinstance(message.author, discord.Member):
            return
        if await self.bot.cog_disabled_in_guild(self, message.guild):
            return
        config = await self.config.guild(message.guild).all()
        if not config["enabled"]:
            return
        if (honeypot_channel_id := config["honeypot_channel"]) is None:
            return
        if message.channel.id != honeypot_channel_id:
            return
        # Staff exemptions. Hierarchy is deliberately NOT an exemption anymore: a member the bot
        # can't act on must still be reported, otherwise the cog looks like it does nothing.
        if (
            message.author.id in self.bot.owner_ids
            or message.author.id == message.guild.owner_id
            or await self.bot.is_mod(message.author)
            or await self.bot.is_admin(message.author)
            or message.author.guild_permissions.manage_guild
        ):
            return

        # Threads are not returned by `get_channel`, so resolve both.
        logs_channel = (
            message.guild.get_channel_or_thread(logs_channel_id)
            if (logs_channel_id := config["logs_channel"]) is not None
            else None
        )

        try:
            await message.delete()
        except discord.HTTPException as e:
            log.warning(
                "Failed to delete the honeypot message in guild %s (%s): %s",
                message.guild.name,
                message.guild.id,
                e,
            )

        action: typing.Optional[str] = config["action"]
        embed: discord.Embed = discord.Embed(
            title=_("Honeypot — Self Bot/Scammer Detected!"),
            description=f">>> {message.content[:4000]}",
            color=discord.Color.red(),
            timestamp=message.created_at,
        )
        embed.set_author(
            name=f"{message.author.display_name} ({message.author.id})",
            icon_url=message.author.display_avatar,
        )
        embed.set_thumbnail(url=message.author.display_avatar)
        failed: typing.Optional[str] = None
        if action is not None:
            reason = _("Self bot/scammer detected (message in the HoneyPot channel).")
            me: discord.Member = message.guild.me
            required_permission: str = ACTION_PERMISSIONS[action]
            mute_role: typing.Optional[discord.Role] = (
                message.guild.get_role(mute_role_id)
                if (mute_role_id := config["mute_role"]) is not None
                else None
            )
            if not getattr(me.guild_permissions, required_permission):
                failed = _(
                    "**Failed:** I'm missing the `{permission}` permission. Run `[p]sethoneypot diagnose` for details."
                ).format(permission=required_permission)
            elif me.top_role <= message.author.top_role:
                failed = _(
                    "**Failed:** My highest role (`{my_role}`) isn't above the member's highest role (`{their_role}`). Move my role higher in **Server Settings → Roles**."
                ).format(my_role=me.top_role.name, their_role=message.author.top_role.name)
            elif action == "mute" and mute_role is None:
                failed = _("**Failed:** The mute role is not set or doesn't exist anymore.")
            elif action == "mute" and mute_role >= me.top_role:
                failed = _(
                    "**Failed:** The mute role (`{mute_role}`) isn't below my highest role (`{my_role}`), so I can't assign it."
                ).format(mute_role=mute_role.name, my_role=me.top_role.name)
            else:
                try:
                    if action == "mute":
                        await message.author.add_roles(mute_role, reason=reason)
                    elif action == "kick":
                        await message.author.kick(reason=reason)
                    elif action == "ban":
                        await message.author.ban(
                            reason=reason,
                            delete_message_days=config["ban_delete_message_days"],
                        )
                except discord.HTTPException as e:
                    failed = _(
                        "**Failed:** An error occurred while trying to take action against the member:\n"
                    ) + box(str(e), lang="py")
                else:
                    # A modlog failure (unregistered case type, no modlog channel, ...) must never
                    # swallow the rest of the flow.
                    try:
                        await modlog.create_case(
                            self.bot,
                            message.guild,
                            message.created_at,
                            action_type=action if action != "mute" else "smute",
                            user=message.author,
                            moderator=message.guild.me,
                            reason=reason,
                        )
                    except Exception as e:
                        log.warning(
                            "Failed to create the modlog case in guild %s (%s): %s",
                            message.guild.name,
                            message.guild.id,
                            e,
                        )
                    await self.config.guild(message.guild).moderated_count.set(
                        config["moderated_count"] + 1
                    )
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

        if logs_channel is None:
            log.warning(
                "Honeypot triggered in guild %s (%s) but no reachable logs channel is configured.",
                message.guild.name,
                message.guild.id,
            )
            return
        try:
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
        except discord.HTTPException as e:
            log.warning(
                "Failed to send the honeypot log in guild %s (%s): %s",
                message.guild.name,
                message.guild.id,
                e,
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
                    "The honeypot channel already exists: {honeypot_channel.mention} ({honeypot_channel.id})."
                ).format(honeypot_channel=honeypot_channel),
            )
        honeypot_channel = await ctx.guild.create_text_channel(
            name="honeypot",
            position=0,
            overwrites={
                ctx.guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    read_messages=True,
                    read_message_history=True,
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
        honeypot_msg = await self._send_honeypot_embed(honeypot_channel, ctx.guild)
        await self.config.guild(ctx.guild).honeypot_channel.set(honeypot_channel.id)
        await self.config.guild(ctx.guild).honeypot_embed_id.set(honeypot_msg.id)
        await ctx.send(
            _(
                "The honeypot channel has been set to {honeypot_channel.mention} ({honeypot_channel.id}). You can now start attracting self bots/scammers!\n"
                "Please make sure to enable the cog and set the logs channel, the action to take, the role to ping (and the mute role) if you haven't already."
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
                _(
                    "The honeypot channel is not configured. Use `[p]sethoneypot createchannel` first."
                ),
            )
        honeypot_channel = ctx.guild.get_channel(honeypot_channel_id)
        if honeypot_channel is None:
            raise commands.UserFeedbackCheckFailure(
                _(
                    "The honeypot channel no longer exists. Use `[p]sethoneypot createchannel` to create a new one."
                ),
            )
        old_embed_id = await config.honeypot_embed_id()
        if old_embed_id is not None:
            try:
                old_msg = await honeypot_channel.fetch_message(old_embed_id)
                await old_msg.delete()
            except discord.HTTPException:
                pass
        honeypot_msg = await self._send_honeypot_embed(honeypot_channel, ctx.guild)
        await config.honeypot_embed_id.set(honeypot_msg.id)
        await ctx.send(
            _("✅ Honeypot embed has been resent to {channel}.").format(
                channel=honeypot_channel.mention
            ),
        )

    @sethoneypot.command(aliases=["check", "debug"])
    async def diagnose(self, ctx: commands.Context) -> None:
        """Check the setup and report everything that prevents the honeypot from working."""
        guild: discord.Guild = ctx.guild
        me: discord.Member = guild.me
        config = await self.config.guild(guild).all()

        blockers: list[str] = []
        warnings: list[str] = []
        sections: list[tuple[str, list[str]]] = []

        def ok(text: str) -> str:
            return f"✅ {text}"

        def warn(text: str) -> str:
            warnings.append(text)
            return f"⚠️ {text}"

        def bad(text: str) -> str:
            blockers.append(text)
            return f"❌ {text}"

        # 1. Cog status.
        status_lines: list[str] = []
        if config["enabled"]:
            status_lines.append(ok(_("The cog is enabled in this server.")))
        else:
            status_lines.append(
                bad(_("The cog is disabled. Run `[p]sethoneypot enabled True`."))
            )
        if await self.bot.cog_disabled_in_guild(self, guild):
            status_lines.append(
                bad(
                    _(
                        "The cog is blocked in this server by the bot owner (`[p]command listdisabled`) or by `[p]autoimmune`/`[p]cogdisable`."
                    )
                )
            )
        else:
            status_lines.append(ok(_("The cog is not blocked at the bot level.")))
        sections.append(("**1. Cog status**", status_lines))

        # 2. Honeypot channel.
        channel_lines: list[str] = []
        honeypot_channel = (
            guild.get_channel(honeypot_channel_id)
            if (honeypot_channel_id := config["honeypot_channel"]) is not None
            else None
        )
        if honeypot_channel_id is None:
            channel_lines.append(
                bad(
                    _(
                        "No honeypot channel is configured. Run `[p]sethoneypot createchannel`."
                    )
                )
            )
        elif honeypot_channel is None:
            channel_lines.append(
                bad(
                    _(
                        "The configured honeypot channel (`{channel_id}`) no longer exists or I can't see it. Run `[p]sethoneypot createchannel`."
                    ).format(channel_id=honeypot_channel_id)
                )
            )
        else:
            channel_lines.append(
                ok(
                    _("Honeypot channel: {channel} (`{channel_id}`).").format(
                        channel=honeypot_channel.mention, channel_id=honeypot_channel.id
                    )
                )
            )
            perms = honeypot_channel.permissions_for(me)
            if perms.view_channel and perms.read_messages:
                channel_lines.append(ok(_("I can see the channel, so I receive its messages.")))
            else:
                channel_lines.append(
                    bad(
                        _(
                            "I can't **View Channel** there, so Discord never sends me those messages and nothing can ever trigger. This is the most common cause of a silent honeypot."
                        )
                    )
                )
            if perms.manage_messages:
                channel_lines.append(ok(_("I can delete messages in the channel.")))
            else:
                channel_lines.append(
                    warn(
                        _(
                            "I'm missing **Manage Messages** there: the bait message won't be deleted."
                        )
                    )
                )
            if perms.read_message_history:
                channel_lines.append(ok(_("I can read the channel history.")))
            else:
                channel_lines.append(
                    warn(
                        _(
                            "I'm missing **Read Message History** there: the warning embed stats can't be updated."
                        )
                    )
                )
            everyone_perms = honeypot_channel.permissions_for(guild.default_role)
            if not everyone_perms.view_channel:
                channel_lines.append(
                    warn(
                        _(
                            "`@everyone` can't see the honeypot channel, so regular members will never fall for it."
                        )
                    )
                )
            elif not everyone_perms.send_messages:
                channel_lines.append(
                    warn(
                        _(
                            "`@everyone` can't send messages in the honeypot channel, so nobody can trigger it."
                        )
                    )
                )
            else:
                channel_lines.append(ok(_("`@everyone` can see and post in the channel.")))
            if (honeypot_embed_id := config["honeypot_embed_id"]) is None:
                channel_lines.append(
                    warn(_("No warning embed is tracked. Run `[p]sethoneypot resend`."))
                )
            else:
                try:
                    await honeypot_channel.fetch_message(honeypot_embed_id)
                except discord.HTTPException:
                    channel_lines.append(
                        warn(
                            _(
                                "The tracked warning embed is gone or unreachable. Run `[p]sethoneypot resend`."
                            )
                        )
                    )
                else:
                    channel_lines.append(ok(_("The warning embed is present.")))
        sections.append(("**2. Honeypot channel**", channel_lines))

        # 3. Logs channel.
        logs_lines: list[str] = []
        logs_channel = (
            guild.get_channel_or_thread(logs_channel_id)
            if (logs_channel_id := config["logs_channel"]) is not None
            else None
        )
        if logs_channel_id is None:
            logs_lines.append(
                warn(
                    _(
                        "No logs channel is set. Actions still happen, but nothing is reported. Run `[p]sethoneypot logschannel #channel`."
                    )
                )
            )
        elif logs_channel is None:
            logs_lines.append(
                warn(
                    _(
                        "The configured logs channel (`{channel_id}`) no longer exists or I can't see it."
                    ).format(channel_id=logs_channel_id)
                )
            )
        else:
            logs_perms = logs_channel.permissions_for(me)
            if logs_perms.send_messages and logs_perms.embed_links:
                logs_lines.append(
                    ok(
                        _("Logs channel: {channel}, and I can post embeds there.").format(
                            channel=logs_channel.mention
                        )
                    )
                )
            else:
                logs_lines.append(
                    warn(
                        _(
                            "I'm missing **Send Messages** and/or **Embed Links** in {channel}, so detections can't be reported."
                        ).format(channel=logs_channel.mention)
                    )
                )
        sections.append(("**3. Logs channel**", logs_lines))

        # 4. Action and permissions.
        action_lines: list[str] = []
        action: typing.Optional[str] = config["action"]
        if action is None:
            action_lines.append(
                warn(
                    _(
                        "No action is set: offenders are only reported. Run `[p]sethoneypot action mute|kick|ban`."
                    )
                )
            )
        else:
            action_lines.append(ok(_("Action: `{action}`.").format(action=action)))
            required_permission = ACTION_PERMISSIONS[action]
            if getattr(me.guild_permissions, required_permission):
                action_lines.append(
                    ok(
                        _("I have the `{permission}` permission.").format(
                            permission=required_permission
                        )
                    )
                )
            else:
                action_lines.append(
                    bad(
                        _("I'm missing the `{permission}` permission required by `{action}`.").format(
                            permission=required_permission, action=action
                        )
                    )
                )
            if action == "mute":
                mute_role = (
                    guild.get_role(mute_role_id)
                    if (mute_role_id := config["mute_role"]) is not None
                    else None
                )
                if mute_role is None:
                    action_lines.append(
                        bad(
                            _(
                                "The action is `mute` but no valid mute role is set. Run `[p]sethoneypot muterole @role`."
                            )
                        )
                    )
                elif mute_role >= me.top_role:
                    action_lines.append(
                        bad(
                            _(
                                "The mute role `{mute_role}` isn't below my highest role, so I can't assign it."
                            ).format(mute_role=mute_role.name)
                        )
                    )
                else:
                    action_lines.append(
                        ok(_("Mute role: `{mute_role}`.").format(mute_role=mute_role.name))
                    )
        if (ping_role_id := config["ping_role"]) is not None and guild.get_role(
            ping_role_id
        ) is None:
            action_lines.append(
                warn(
                    _("The configured ping role (`{role_id}`) no longer exists.").format(
                        role_id=ping_role_id
                    )
                )
            )
        sections.append(("**4. Action**", action_lines))

        # 5. Role hierarchy.
        hierarchy_lines: list[str] = []
        if me.top_role.is_default():
            hierarchy_lines.append(
                bad(
                    _(
                        "I have no role at all: I can't act on anyone. Give me a role and move it high in **Server Settings → Roles**."
                    )
                )
            )
        else:
            above = [
                member
                for member in guild.members
                if not member.bot and member.top_role >= me.top_role
            ]
            hierarchy_lines.append(
                ok(
                    _(
                        "My highest role is `{role}` (position {position} of {total})."
                    ).format(
                        role=me.top_role.name,
                        position=me.top_role.position,
                        total=len(guild.roles) - 1,
                    )
                )
            )
            if above:
                hierarchy_lines.append(
                    warn(
                        _(
                            "{count} non-bot member(s) sit at or above my highest role, so I can't moderate them. They'll still be reported."
                        ).format(count=len(above))
                    )
                )
            else:
                hierarchy_lines.append(ok(_("I'm above every non-bot member.")))
        sections.append(("**5. Role hierarchy**", hierarchy_lines))

        # 6. Intents and modlog.
        misc_lines: list[str] = []
        if self.bot.intents.members:
            misc_lines.append(ok(_("The `members` intent is enabled.")))
        else:
            misc_lines.append(
                bad(
                    _(
                        "The `members` intent is disabled, so I can't resolve message authors as members and every detection is skipped. Enable it in the Discord Developer Portal."
                    )
                )
            )
        if self.bot.intents.message_content:
            misc_lines.append(ok(_("The `message_content` intent is enabled.")))
        else:
            misc_lines.append(
                warn(
                    _(
                        "The `message_content` intent is disabled: detections still work, but logs won't show what was posted."
                    )
                )
            )
        if action is not None:
            case_type_name = action if action != "mute" else "smute"
            try:
                case_type = await modlog.get_casetype(case_type_name, guild)
            except Exception:
                case_type = None
            if case_type is None:
                misc_lines.append(
                    warn(
                        _(
                            "The modlog case type `{case_type}` isn't registered (the core `Mod` cog is probably unloaded). Cases won't be created."
                        ).format(case_type=case_type_name)
                    )
                )
            else:
                misc_lines.append(
                    ok(
                        _("The modlog case type `{case_type}` is registered.").format(
                            case_type=case_type_name
                        )
                    )
                )
        sections.append(("**6. Intents & modlog**", misc_lines))

        if blockers:
            color = discord.Color.red()
            summary = _(
                "**{count} blocking issue(s) found.** The honeypot will not work until they're fixed."
            ).format(count=len(blockers))
        elif warnings:
            color = discord.Color.orange()
            summary = _(
                "**No blocking issue.** {count} warning(s) worth reviewing."
            ).format(count=len(warnings))
        else:
            color = discord.Color.green()
            summary = _("**Everything looks good.** The honeypot is fully operational.")

        embed = discord.Embed(
            title=_("🍯 Honeypot Diagnostic"),
            description=summary,
            color=color,
        )
        for name, lines in sections:
            # Embed fields are capped at 1024 characters.
            embed.add_field(name=name, value="\n".join(lines)[:1024], inline=False)
        embed.set_footer(text=guild.name, icon_url=guild.icon)
        await ctx.send(embed=embed)
