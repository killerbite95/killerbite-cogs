import asyncio
import contextlib
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import discord
import numpy as np
from discord import ButtonStyle, Interaction, TextStyle
from discord.ui import Button, Modal, Select, TextInput, View
from discord.ui.item import Item
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box, humanize_list, pagify
from redbot.core.utils.mod import is_admin_or_superior

from .utils import (
    can_close,
    close_ticket,
    update_active_overview,
    claim_ticket,
    unclaim_ticket,
    transfer_ticket,
    add_ticket_note,
    check_cooldown,
    check_rate_limit,
    check_panel_max_open,
    check_account_age,
    check_server_age,
    check_blacklist,
    update_user_cooldown,
    increment_stats_opened,
    log_audit_action,
    update_last_message,
    get_overview_stats,
    prep_overview_text_paginated,
)
from .models import PanelSchedule, WelcomeSections, TimeParser
from .constants import TICKET_STATUSES

_ = Translator("SupportViews", __file__)
log = logging.getLogger("red.killerbite95.ticketstrini.views")


async def wait_reply(
    ctx: commands.Context,
    timeout: Optional[int] = 60,
    delete: Optional[bool] = True,
) -> Optional[str]:
    def check(message: discord.Message):
        return message.author == ctx.author and message.channel == ctx.channel

    try:
        reply = await ctx.bot.wait_for("message", timeout=timeout, check=check)
        res = reply.content
        if delete:
            with contextlib.suppress(discord.HTTPException, discord.NotFound, discord.Forbidden):
                await reply.delete(delay=10)
        if res.lower().strip() == _("cancel"):
            return None
        return res.strip()
    except asyncio.TimeoutError:
        return None


def get_color(color: str) -> ButtonStyle:
    if color == "red":
        style = ButtonStyle.red
    elif color == "blue":
        style = ButtonStyle.blurple
    elif color == "green":
        style = ButtonStyle.green
    else:
        style = ButtonStyle.grey
    return style


def get_modal_style(styletype: str) -> TextStyle:
    if styletype == "short":
        style = TextStyle.short
    elif styletype == "long":
        style = TextStyle.long
    else:
        style = TextStyle.paragraph
    return style


class Confirm(View):
    def __init__(self, ctx):
        self.ctx = ctx
        self.value = None
        super().__init__(timeout=60)

    async def interaction_check(self, interaction: Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                content=_("You are not allowed to interact with this button."),
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Yes", style=ButtonStyle.green)
    async def confirm(self, interaction: Interaction, button: Button):
        if not await self.interaction_check(interaction):
            return
        self.value = True
        with contextlib.suppress(discord.NotFound):
            await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="No", style=ButtonStyle.red)
    async def cancel(self, interaction: Interaction, button: Button):
        if not await self.interaction_check(interaction):
            return
        self.value = False
        with contextlib.suppress(discord.NotFound):
            await interaction.response.defer()
        self.stop()


async def confirm(ctx, msg: discord.Message):
    try:
        view = Confirm(ctx)
        await msg.edit(view=view)
        await view.wait()
        if view.value is None:
            await msg.delete()
        else:
            await msg.edit(view=None)
        return view.value
    except Exception as e:
        log.warning(f"Confirm Error: {e}")
        return None


class TestButton(View):
    def __init__(
        self,
        style: str = "grey",
        label: str = "Button Test",
        emoji: Union[discord.Emoji, discord.PartialEmoji, str] = None,
    ):
        super().__init__()
        style = get_color(style)
        butt = discord.ui.Button(label=label, style=style, emoji=emoji)
        self.add_item(butt)


class CloseReasonModal(Modal):
    def __init__(self):
        self.reason = None
        super().__init__(title=_("Closing your ticket"), timeout=120)
        self.field = TextInput(
            label=_("Reason for closing"),
            style=TextStyle.short,
            required=True,
        )
        self.add_item(self.field)

    async def on_submit(self, interaction: Interaction):
        self.reason = self.field.value
        with contextlib.suppress(discord.NotFound):
            await interaction.response.defer()
        self.stop()


class CloseView(View):
    def __init__(
        self,
        bot: Red,
        config: Config,
        owner_id: int,
        channel: Union[discord.TextChannel, discord.Thread],
        claimed_by: Optional[int] = None,
    ):
        super().__init__(timeout=None)
        self.bot = bot
        self.config = config
        self.owner_id = owner_id
        self.channel = channel
        self.claimed_by = claimed_by

        self.closeticket.custom_id = f"close_{channel.id}"
        self.claimticket.custom_id = f"claim_{channel.id}"
        
        # Update claim button appearance based on status
        self._update_claim_button()

    def _update_claim_button(self):
        """Update claim button appearance based on claimed status"""
        if self.claimed_by:
            self.claimticket.label = "Claimed"
            self.claimticket.style = ButtonStyle.red
            self.claimticket.emoji = "✅"
        else:
            self.claimticket.label = "Claim"
            self.claimticket.style = ButtonStyle.green
            self.claimticket.emoji = "🙋"

    async def _is_support_staff(self, user: discord.Member, conf: dict) -> bool:
        """Check if user is support staff"""
        user_roles = [r.id for r in user.roles]
        support_roles = [i[0] for i in conf.get("support_roles", [])]
        
        # Get panel-specific roles
        ticket_data = None
        for uid, tickets in conf.get("opened", {}).items():
            if str(self.channel.id) in tickets:
                ticket_data = tickets[str(self.channel.id)]
                break
        
        if ticket_data:
            panel_name = ticket_data.get("panel")
            if panel_name and panel_name in conf.get("panels", {}):
                panel_roles = conf["panels"][panel_name].get("roles", [])
                support_roles.extend([i[0] for i in panel_roles])
        
        if any(rid in support_roles for rid in user_roles):
            return True
        if user.id == user.guild.owner_id:
            return True
        if await is_admin_or_superior(self.bot, user):
            return True
        
        return False

    async def on_error(self, interaction: Interaction, error: Exception, item: Item[Any]):
        log.warning(
            f"View failed for user ticket {self.owner_id} in channel {self.channel.name} in {self.channel.guild.name}",
            exc_info=error,
        )
        return await super().on_error(interaction, error, item)

    @discord.ui.button(label="Claim", style=ButtonStyle.green, emoji="🙋", row=0)
    async def claimticket(self, interaction: Interaction, button: Button):
        if not interaction.guild or not interaction.channel:
            return
        user = interaction.guild.get_member(interaction.user.id)
        if not user:
            return

        conf = await self.config.guild(interaction.guild).all()
        
        # Check if staff
        if not await self._is_support_staff(user, conf):
            return await interaction.response.send_message(
                _("Only support staff can claim tickets."),
                ephemeral=True,
            )
        
        # Get current ticket data
        ticket_data = None
        for uid, tickets in conf.get("opened", {}).items():
            if str(self.channel.id) in tickets:
                ticket_data = tickets[str(self.channel.id)]
                break
        
        if not ticket_data:
            return await interaction.response.send_message(
                _("This ticket no longer exists."),
                ephemeral=True,
            )
        
        current_claimer = ticket_data.get("claimed_by")
        
        if current_claimer:
            # Already claimed - show who
            claimer = interaction.guild.get_member(current_claimer)
            claimer_name = claimer.display_name if claimer else "Unknown"
            
            if current_claimer == user.id:
                # User is the claimer - unclaim
                success, message = await unclaim_ticket(
                    interaction.guild,
                    self.channel,
                    user,
                    self.config,
                    conf,
                )
                if success:
                    self.claimed_by = None
                    self._update_claim_button()
                    await interaction.response.edit_message(view=self)
                    await interaction.followup.send(
                        _("✅ You have released this ticket."),
                        ephemeral=True,
                    )
                else:
                    await interaction.response.send_message(message, ephemeral=True)
            else:
                # Someone else claimed it
                await interaction.response.send_message(
                    _("🔒 This ticket is already claimed by **{}**.").format(claimer_name),
                    ephemeral=True,
                )
        else:
            # Not claimed - claim it
            success, message = await claim_ticket(
                interaction.guild,
                self.channel,
                user,
                self.config,
                conf,
            )
            if success:
                self.claimed_by = user.id
                self._update_claim_button()
                await interaction.response.edit_message(view=self)
                await interaction.followup.send(
                    _("✅ You have claimed this ticket!"),
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(message, ephemeral=True)

    @discord.ui.button(label="Close", style=ButtonStyle.danger, row=0)
    async def closeticket(self, interaction: Interaction, button: Button):
        if not interaction.guild or not interaction.channel:
            return
        user = interaction.guild.get_member(interaction.user.id)
        if not user:
            return

        conf = await self.config.guild(interaction.guild).all()
        txt = _("This ticket has already been closed! Please delete it manually.")
        if str(self.owner_id) not in conf["opened"]:
            return await interaction.response.send_message(txt, ephemeral=True)
        if str(self.channel.id) not in conf["opened"][str(self.owner_id)]:
            return await interaction.response.send_message(txt, ephemeral=True)

        allowed = await can_close(
            bot=self.bot,
            guild=interaction.guild,
            channel=interaction.channel,
            author=user,
            owner_id=self.owner_id,
            conf=conf,
        )
        if not allowed:
            return await interaction.response.send_message(
                _("You do not have permissions to close this ticket"),
                ephemeral=True,
            )
        panel_name = conf["opened"][str(self.owner_id)][str(self.channel.id)]["panel"]
        requires_reason = conf["panels"][panel_name].get("close_reason", True)
        reason = None
        if requires_reason:
            modal = CloseReasonModal()
            try:
                await interaction.response.send_modal(modal)
            except discord.NotFound:
                txt = _("Something went wrong, please try again.")
                try:
                    await interaction.followup.send(txt, ephemeral=True)
                except discord.NotFound:
                    await interaction.channel.send(txt, delete_after=10)
                return

            await modal.wait()
            if modal.reason is None:
                return
            reason = modal.reason
            await interaction.followup.send(_("Closing..."), ephemeral=True)
        else:
            await interaction.response.send_message(_("Closing..."), ephemeral=True)
        owner = self.channel.guild.get_member(int(self.owner_id))
        if not owner:
            owner = await self.bot.fetch_user(int(self.owner_id))
        await close_ticket(
            bot=self.bot,
            member=owner,
            guild=self.channel.guild,
            channel=self.channel,
            conf=conf,
            reason=reason,
            closedby=interaction.user.name,
            config=self.config,
        )


class TicketModal(Modal):
    def __init__(self, title: str, data: dict):
        super().__init__(title=title, timeout=300)
        self.fields = {}
        self.inputs: Dict[str, TextInput] = {}
        for key, info in data.items():
            field = TextInput(
                label=info["label"],
                style=get_modal_style(info["style"]),
                placeholder=info["placeholder"],
                default=info["default"],
                required=info["required"],
                min_length=info["min_length"],
                max_length=info["max_length"],
            )
            self.add_item(field)
            self.inputs[key] = field

    async def on_submit(self, interaction: discord.Interaction):
        for k, v in self.inputs.items():
            self.fields[k] = {"question": v.label, "answer": v.value}
        with contextlib.suppress(discord.NotFound):
            await interaction.response.defer()
        self.stop()


class SupportButton(Button):
    def __init__(self, panel: dict, mock_user: discord.Member = None):
        super().__init__(
            style=get_color(panel["button_color"]),
            label=panel["button_text"],
            custom_id=panel["name"],
            emoji=panel["button_emoji"],
            row=panel.get("row"),
            disabled=panel.get("disabled", False),
        )
        self.panel_name = panel["name"]
        self.mock_user = mock_user

    async def callback(self, interaction: Interaction):
        try:
            await self.create_ticket(interaction)
        except Exception as e:
            guild = interaction.guild.name
            user = self.mock_user.name if self.mock_user else interaction.user.name
            log.exception(f"Failed to create ticket in {guild} for {user}", exc_info=e)

    async def create_ticket(self, interaction: Interaction):
        guild = interaction.guild
        user = self.mock_user or guild.get_member(interaction.user.id)
        if not isinstance(interaction.channel, discord.TextChannel) or not guild:
            return

        channel: discord.TextChannel = interaction.channel
        roles = [r.id for r in user.roles]
        conf = await self.view.config.guild(guild).all()
        if conf["suspended_msg"]:
            em = discord.Embed(
                title=_("Ticket System Suspended"),
                description=conf["suspended_msg"],
                color=discord.Color.yellow(),
            )
            return await interaction.response.send_message(embed=em, ephemeral=True)

        for rid_uid in conf["blacklist"]:
            if rid_uid == user.id:
                em = discord.Embed(
                    description=_("You been blacklisted from creating tickets!"),
                    color=discord.Color.red(),
                )
                return await interaction.response.send_message(embed=em, ephemeral=True)
            elif rid_uid in roles:
                em = discord.Embed(
                    description=_("You have a role that has been blacklisted from creating tickets!"),
                    color=discord.Color.red(),
                )
                return await interaction.response.send_message(embed=em, ephemeral=True)

        panel = conf["panels"][self.panel_name]
        if required_roles := panel.get("required_roles", []):
            if not any(r.id in required_roles for r in user.roles):
                roles = [guild.get_role(i).mention for i in required_roles if guild.get_role(i)]
                em = discord.Embed(
                    description=_("You must have one of the following roles to open this ticket: ")
                    + humanize_list(roles),
                    color=discord.Color.red(),
                )
                return await interaction.response.send_message(embed=em, ephemeral=True)

        max_tickets = conf["max_tickets"]
        opened = conf["opened"]
        uid = str(user.id)
        if uid in opened and max_tickets <= len(opened[uid]):
            channels = "\n".join([f"<#{i}>" for i in opened[uid]])
            em = discord.Embed(
                description=_("You have the maximum amount of tickets opened already!{}").format(f"\n{channels}"),
                color=discord.Color.red(),
            )
            return await interaction.response.send_message(embed=em, ephemeral=True)

        category = guild.get_channel(panel["category_id"]) if panel["category_id"] else None
        if not category:
            em = discord.Embed(
                description=_("The category for this support panel cannot be found!\n" "please contact an admin!"),
                color=discord.Color.red(),
            )
            return await interaction.response.send_message(embed=em, ephemeral=True)
        if not isinstance(category, discord.CategoryChannel):
            em = discord.Embed(
                description=_(
                    "The category for this support panel is not a category channel!\n" "please contact an admin!"
                ),
                color=discord.Color.red(),
            )
            return await interaction.response.send_message(embed=em, ephemeral=True)

        user_can_close = conf["user_can_close"]
        logchannel = guild.get_channel(panel["log_channel"]) if panel["log_channel"] else None

        # Throw modal before creating ticket if the panel has one
        form_embed = discord.Embed()
        modal = panel.get("modal")
        panel_title = panel.get("modal_title", "{} Ticket".format(self.panel_name))
        answers = {}
        has_response = False
        if modal:
            title = _("Submission Info")
            form_embed = discord.Embed(color=user.color)
            if user.avatar:
                form_embed.set_author(name=title, icon_url=user.display_avatar.url)
            else:
                form_embed.set_author(name=title)

            m = TicketModal(panel_title, modal)
            try:
                await interaction.response.send_modal(m)
            except discord.NotFound:
                return
            await m.wait()

            if not m.fields:
                return

            for submission_info in m.fields.values():
                question = submission_info["question"]
                answer = submission_info["answer"]
                if not answer:
                    answer = _("Unanswered")
                else:
                    has_response = True

                if "DISCOVERABLE" in guild.features and "discord" in answer.lower():
                    txt = _("Your response cannot contain the word 'Discord' in discoverable servers.")
                    return await interaction.followup.send(txt, ephemeral=True)

                answers[question] = answer

                if len(answer) <= 1024:
                    form_embed.add_field(name=question, value=answer, inline=False)
                    continue

                chunks = [ans for ans in pagify(answer, page_length=1024)]
                for index, chunk in enumerate(chunks):
                    form_embed.add_field(
                        name=f"{question} ({index + 1})",
                        value=chunk,
                        inline=False,
                    )

        open_txt = _("Your ticket is being created, one moment...")
        if modal:
            existing_msg = await interaction.followup.send(open_txt, ephemeral=True)
        else:
            await interaction.response.send_message(open_txt, ephemeral=True)
            existing_msg = await interaction.original_response()

        can_read_send = discord.PermissionOverwrite(
            read_messages=True,
            read_message_history=True,
            send_messages=True,
            attach_files=True,
            embed_links=True,
            use_application_commands=True,
        )
        read_and_manage = discord.PermissionOverwrite(
            read_messages=True,
            send_messages=True,
            attach_files=True,
            embed_links=True,
            manage_channels=True,
            manage_messages=True,
        )

        support_roles = []
        support_mentions = []
        panel_roles = []
        panel_mentions = []
        for role_id, mention_toggle in conf["support_roles"]:
            role = guild.get_role(role_id)
            if not role:
                continue
            support_roles.append(role)
            if mention_toggle:
                support_mentions.append(role.mention)
        for role_id, mention_toggle in panel.get("roles", []):
            role = guild.get_role(role_id)
            if not role:
                continue
            panel_roles.append(role)
            if mention_toggle:
                panel_mentions.append(role.mention)

        support_roles.extend(panel_roles)
        support_mentions.extend(panel_mentions)

        overwrite = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: read_and_manage,
            user: can_read_send,
        }
        for role in support_roles:
            overwrite[role] = can_read_send

        num = panel["ticket_num"]
        now = datetime.now().astimezone()
        name_fmt = panel["ticket_name"]
        params = {
            "num": str(num),
            "user": user.name,
            "displayname": user.display_name,
            "id": str(user.id),
            "shortdate": now.strftime("%m-%d"),
            "longdate": now.strftime("%m-%d-%Y"),
            "time": now.strftime("%I-%M-%p"),
        }
        channel_name = name_fmt.format(**params) if name_fmt else user.name
        default_channel_name = f"{self.panel_name}-{num}"
        try:
            if panel.get("threads"):
                if alt_cid := panel.get("alt_channel"):
                    alt_channel = guild.get_channel(alt_cid)
                    if alt_channel and isinstance(alt_channel, discord.TextChannel):
                        channel = alt_channel

                if not channel.permissions_for(guild.me).manage_threads:
                    return await interaction.followup.send(
                        "I don't have permissions to create threads!", ephemeral=True
                    )

                archive = round(conf["inactive"] * 60)
                arr = np.asarray([60, 1440, 4320, 10080])
                index = (np.abs(arr - archive)).argmin()
                auto_archive_duration = int(arr[index])

                reason = _("{} ticket for {}").format(self.panel_name, str(interaction.user))
                try:
                    channel_or_thread = await channel.create_thread(
                        name=channel_name,
                        auto_archive_duration=auto_archive_duration,  # type: ignore
                        reason=reason,
                        invitable=conf["user_can_manage"],
                    )
                except discord.Forbidden:
                    return await interaction.followup.send(
                        _("I don't have permissions to create threads!"), ephemeral=True
                    )
                except Exception as e:
                    if "Contains words not allowed" in str(e):
                        channel_or_thread = await channel.create_thread(
                            name=default_channel_name,
                            auto_archive_duration=auto_archive_duration,
                            reason=reason,
                            invitable=conf["user_can_manage"],
                        )
                        await channel_or_thread.send(
                            _(
                                "I was not able to name the ticket properly due to Discord's filter!\nIntended name: {}"
                            ).format(channel_name)
                        )
                    else:
                        raise e
                asyncio.create_task(channel_or_thread.add_user(interaction.user))
                if conf["auto_add"] and not support_mentions:
                    for role in support_roles:
                        for member in role.members:
                            asyncio.create_task(channel_or_thread.add_user(member))
            else:
                if alt_cid := panel.get("alt_channel"):
                    alt_channel = guild.get_channel(alt_cid)
                    if alt_channel and isinstance(alt_channel, discord.CategoryChannel):
                        category = alt_channel
                    elif alt_channel and isinstance(alt_channel, discord.TextChannel):
                        if alt_channel.category:
                            category = alt_channel.category
                if not category.permissions_for(guild.me).manage_channels:
                    return await interaction.followup.send(
                        _("I don't have permissions to create channels!"),
                        ephemeral=True,
                    )
                try:
                    channel_or_thread = await category.create_text_channel(channel_name, overwrites=overwrite)
                except discord.Forbidden:
                    return await interaction.followup.send(
                        _("I don't have permissions to create channels under this category!"),
                        ephemeral=True,
                    )
                except Exception as e:
                    if "Contains words not allowed" in str(e):
                        channel_or_thread = await category.create_text_channel(
                            default_channel_name, overwrites=overwrite
                        )
                        await channel_or_thread.send(
                            _(
                                "I was not able to name the ticket properly due to Discord's filter!\nIntended name: {}"
                            ).format(channel_name)
                        )
                    else:
                        raise e
        except discord.Forbidden:
            txt = _(
                "I am missing the required permissions to create a ticket for you. "
                "Please contact an admin so they may fix my permissions."
            )
            em = discord.Embed(description=txt, color=discord.Color.red())
            return await interaction.followup.send(embed=em, ephemeral=True)

        except Exception as e:
            em = discord.Embed(
                description=_("There was an error while preparing your ticket, please contact an admin!\n{}").format(
                    box(str(e), "py")
                ),
                color=discord.Color.red(),
            )
            log.info(
                f"Failed to create ticket for {user.name} in {guild.name}",
                exc_info=e,
            )
            return await interaction.followup.send(embed=em, ephemeral=True)

        prefix = (await self.view.bot.get_valid_prefixes(self.view.guild))[0]
        default_message = _("Welcome to your ticket channel ") + f"{user.display_name}!"
        if user_can_close:
            default_message += _("\nYou or an admin can close this with the `{}close` command").format(prefix)

        messages = panel["ticket_messages"]
        params = {
            "username": user.name,
            "displayname": user.display_name,
            "mention": user.mention,
            "id": str(user.id),
            "server": guild.name,
            "guild": guild.name,
            "members": int(guild.member_count or len(guild.members)),
            "toprole": user.top_role.name,
        }

        def fmt_params(text: str) -> str:
            for k, v in params.items():
                text = text.replace("{" + str(k) + "}", str(v))
            return text

        content = "" if panel.get("threads") else user.mention
        if support_mentions:
            if not panel.get("threads"):
                support_mentions.append(user.mention)
            content = " ".join(support_mentions)

        allowed_mentions = discord.AllowedMentions(roles=True)
        close_view = CloseView(
            self.view.bot,
            self.view.config,
            user.id,
            channel_or_thread,
            claimed_by=None,
        )
        if messages:
            embeds = []
            for index, einfo in enumerate(messages):
                em = discord.Embed(
                    title=fmt_params(einfo["title"]) if einfo["title"] else None,
                    description=fmt_params(einfo["desc"]),
                    color=user.color,
                )
                if index == 0:
                    em.set_thumbnail(url=user.display_avatar.url)
                if einfo["footer"]:
                    em.set_footer(text=fmt_params(einfo["footer"]))
                embeds.append(em)

            msg = await channel_or_thread.send(
                content=content,
                embeds=embeds,
                allowed_mentions=allowed_mentions,
                view=close_view,
            )
        else:
            # Default message
            em = discord.Embed(description=default_message, color=user.color)
            em.set_thumbnail(url=user.display_avatar.url)
            msg = await channel_or_thread.send(
                content=content,
                embed=em,
                allowed_mentions=allowed_mentions,
                view=close_view,
            )

        if len(form_embed.fields) > 0:
            form_msg = await channel_or_thread.send(embed=form_embed)
            try:
                asyncio.create_task(form_msg.pin(reason=_("Ticket form questions")))
            except discord.Forbidden:
                txt = _("I tried to pin the response message but don't have the manage messages permissions!")
                asyncio.create_task(channel_or_thread.send(txt))

        async def delete_delay():
            desc = _("Your ticket has been created! {}").format(channel_or_thread.mention)
            em = discord.Embed(description=desc, color=user.color)
            with contextlib.suppress(discord.HTTPException):
                if existing_msg:
                    await existing_msg.edit(content=None, embed=em)
                    await existing_msg.delete(delay=30)
                else:
                    msg = await interaction.followup.send(embed=em, ephemeral=True)
                    await msg.delete(delay=30)

        asyncio.create_task(delete_delay())

        if (
            logchannel
            and isinstance(logchannel, discord.TextChannel)
            and logchannel.permissions_for(guild.me).send_messages
        ):
            ts = int(now.timestamp())
            kwargs = {
                "user": str(user),
                "userid": user.id,
                "timestamp": f"<t:{ts}:R>",
                "channelname": channel_name,
                "panelname": self.panel_name,
                "jumpurl": msg.jump_url,
            }
            desc = _(
                "`Created By: `{user}\n"
                "`User ID:    `{userid}\n"
                "`Opened:     `{timestamp}\n"
                "`Ticket:     `{channelname}\n"
                "`Panel Name: `{panelname}\n"
                "**[Click to Jump!]({jumpurl})**"
            ).format(**kwargs)
            em = discord.Embed(
                title=_("Ticket Opened"),
                description=desc,
                color=discord.Color.red(),
            )
            if user.avatar:
                em.set_thumbnail(url=user.display_avatar.url)

            for question, answer in answers.items():
                em.add_field(name=f"__{question}__", value=answer, inline=False)

            view = LogView(guild, channel_or_thread, panel.get("max_claims", 0))
            log_message = await logchannel.send(embed=em, view=view)
        else:
            log_message = None

        async with self.view.config.guild(guild).all() as data:
            data["panels"][self.panel_name]["ticket_num"] += 1
            if uid not in data["opened"]:
                data["opened"][uid] = {}
            data["opened"][uid][str(channel_or_thread.id)] = {
                "panel": self.panel_name,
                "opened": now.isoformat(),
                "pfp": str(user.display_avatar.url) if user.avatar else None,
                "logmsg": log_message.id if log_message else None,
                "answers": answers,
                "has_response": has_response,
                "message_id": msg.id,
                "max_claims": data["panels"][self.panel_name].get("max_claims", 0),
            }

            new_id = await update_active_overview(guild, data)
            if new_id:
                data["overview_msg"] = new_id


class PanelView(View):
    def __init__(
        self,
        bot: Red,
        guild: discord.Guild,
        config: Config,
        panels: list,  # List of support panels that have the same message/channel ID
        mock_user: Optional[discord.Member] = None,
        timeout: Optional[int] = None,
    ):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.guild = guild
        self.config = config
        self.panels = panels
        for panel in self.panels:
            self.add_item(SupportButton(panel, mock_user=mock_user))

    async def start(self):
        chan = self.guild.get_channel(self.panels[0]["channel_id"])
        if not isinstance(chan, discord.TextChannel):
            return
        message = await chan.fetch_message(self.panels[0]["message_id"])
        await message.edit(view=self)


class LogView(View):
    def __init__(
        self,
        guild: discord.Guild,
        channel: Union[discord.TextChannel, discord.Thread],
        max_claims: int,
    ):
        super().__init__(timeout=None)
        self.guild = guild
        self.channel = channel
        self.max_claims = max_claims

        self.added = set()
        self.join_ticket.custom_id = str(channel.id)

    @discord.ui.button(label="Join Ticket", style=ButtonStyle.green)
    async def join_ticket(self, interaction: Interaction, button: Button):
        user = interaction.guild.get_member(interaction.user.id)
        if not user:
            return
        if user.id in self.added:
            return await interaction.response.send_message(
                _("You have already been added to the ticket **{}**!").format(self.channel.name),
                ephemeral=True,
                delete_after=60,
            )
        if self.max_claims and len(self.added) >= self.max_claims:
            return await interaction.response.send_message(
                _("The maximum amount of staff have claimed this ticket!"),
                ephemeral=True,
                delete_after=60,
            )
        perms = [
            self.channel.permissions_for(user).view_channel,
            self.channel.permissions_for(user).send_messages,
        ]
        if isinstance(self.channel, discord.TextChannel):
            if all(perms):
                return await interaction.response.send_message(
                    _("You already have access to the ticket **{}**!").format(self.channel.name),
                    ephemeral=True,
                    delete_after=60,
                )
            await self.channel.set_permissions(user, read_messages=True, send_messages=True)
            await self.channel.send(_("{} was added to the ticket").format(str(user)))
        else:
            await self.channel.add_user(user)
        self.added.add(user.id)
        await interaction.response.send_message(
            _("You have been added to the ticket **{}**").format(self.channel.name),
            ephemeral=True,
            delete_after=60,
        )


# ============================================================================
# Staff Action Views - Claim, Unclaim, Transfer
# ============================================================================

class StaffActionsView(View):
    """View with staff action buttons inside a ticket"""
    
    def __init__(
        self,
        bot: Red,
        config: Config,
        owner_id: int,
        channel: Union[discord.TextChannel, discord.Thread],
        show_close: bool = True,
    ):
        super().__init__(timeout=None)
        self.bot = bot
        self.config = config
        self.owner_id = owner_id
        self.channel = channel
        
        # Set custom IDs for persistence
        self.claim_btn.custom_id = f"staff_claim_{channel.id}"
        self.unclaim_btn.custom_id = f"staff_unclaim_{channel.id}"
        if show_close:
            self.close_btn.custom_id = f"staff_close_{channel.id}"
        else:
            self.remove_item(self.close_btn)
    
    async def is_support_staff(self, user: discord.Member, conf: dict) -> bool:
        """Check if user is support staff"""
        user_roles = [r.id for r in user.roles]
        support_roles = [i[0] for i in conf.get("support_roles", [])]
        
        # Get panel-specific roles
        ticket_data = None
        for uid, tickets in conf.get("opened", {}).items():
            if str(self.channel.id) in tickets:
                ticket_data = tickets[str(self.channel.id)]
                break
        
        if ticket_data:
            panel_name = ticket_data.get("panel")
            if panel_name and panel_name in conf.get("panels", {}):
                panel_roles = conf["panels"][panel_name].get("roles", [])
                support_roles.extend([i[0] for i in panel_roles])
        
        if any(rid in support_roles for rid in user_roles):
            return True
        if user.id == user.guild.owner_id:
            return True
        if await is_admin_or_superior(self.bot, user):
            return True
        
        return False
    
    @discord.ui.button(label="Claim", style=ButtonStyle.green, emoji="🙋", row=0)
    async def claim_btn(self, interaction: Interaction, button: Button):
        user = interaction.guild.get_member(interaction.user.id)
        if not user:
            return
        
        conf = await self.config.guild(interaction.guild).all()
        
        if not await self.is_support_staff(user, conf):
            return await interaction.response.send_message(
                _("Only support staff can claim tickets."),
                ephemeral=True,
            )
        
        success, message = await claim_ticket(
            interaction.guild,
            self.channel,
            user,
            self.config,
            conf,
        )
        
        if success:
            # Update the view to show unclaim button
            self.claim_btn.disabled = True
            self.unclaim_btn.disabled = False
            await interaction.message.edit(view=self)
            await interaction.response.send_message(
                _("✅ {} claimed this ticket!").format(user.mention),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        else:
            await interaction.response.send_message(message, ephemeral=True)
    
    @discord.ui.button(label="Unclaim", style=ButtonStyle.grey, emoji="🚫", row=0, disabled=True)
    async def unclaim_btn(self, interaction: Interaction, button: Button):
        user = interaction.guild.get_member(interaction.user.id)
        if not user:
            return
        
        conf = await self.config.guild(interaction.guild).all()
        
        success, message = await unclaim_ticket(
            interaction.guild,
            self.channel,
            user,
            self.config,
            conf,
        )
        
        if success:
            self.claim_btn.disabled = False
            self.unclaim_btn.disabled = True
            await interaction.message.edit(view=self)
            await interaction.response.send_message(
                _("🚫 {} unclaimed this ticket.").format(user.mention),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        else:
            await interaction.response.send_message(message, ephemeral=True)
    
    @discord.ui.button(label="Close", style=ButtonStyle.danger, emoji="🔒", row=0)
    async def close_btn(self, interaction: Interaction, button: Button):
        user = interaction.guild.get_member(interaction.user.id)
        if not user:
            return
        
        conf = await self.config.guild(interaction.guild).all()
        
        allowed = await can_close(
            bot=self.bot,
            guild=interaction.guild,
            channel=self.channel,
            author=user,
            owner_id=self.owner_id,
            conf=conf,
        )
        
        if not allowed:
            return await interaction.response.send_message(
                _("You do not have permission to close this ticket."),
                ephemeral=True,
            )
        
        # Check if close reason modal is required
        ticket_data = None
        for uid, tickets in conf.get("opened", {}).items():
            if str(self.channel.id) in tickets:
                ticket_data = tickets[str(self.channel.id)]
                break
        
        panel_name = ticket_data.get("panel") if ticket_data else None
        requires_reason = True
        if panel_name and panel_name in conf.get("panels", {}):
            requires_reason = conf["panels"][panel_name].get("close_reason", True)
        
        reason = None
        if requires_reason:
            modal = CloseReasonModal()
            await interaction.response.send_modal(modal)
            await modal.wait()
            if modal.reason is None:
                return
            reason = modal.reason
            await interaction.followup.send(_("Closing..."), ephemeral=True)
        else:
            await interaction.response.send_message(_("Closing..."), ephemeral=True)
        
        owner = interaction.guild.get_member(self.owner_id)
        if not owner:
            owner = await self.bot.fetch_user(self.owner_id)
        
        await close_ticket(
            bot=self.bot,
            member=owner,
            guild=interaction.guild,
            channel=self.channel,
            conf=conf,
            reason=reason,
            closedby=interaction.user.name,
            config=self.config,
        )


class TransferModal(Modal):
    """Modal for transferring ticket to another staff member"""
    
    def __init__(self):
        super().__init__(title=_("Transfer Ticket"), timeout=120)
        self.staff_id = None
        
        self.field = TextInput(
            label=_("Staff Member ID or @mention"),
            style=TextStyle.short,
            placeholder=_("Enter user ID or @mention"),
            required=True,
        )
        self.add_item(self.field)
    
    async def on_submit(self, interaction: Interaction):
        value = self.field.value.strip()
        
        # Try to extract user ID from mention
        if value.startswith("<@") and value.endswith(">"):
            value = value[2:-1]
            if value.startswith("!"):
                value = value[1:]
        
        try:
            self.staff_id = int(value)
        except ValueError:
            self.staff_id = None
        
        await interaction.response.defer()
        self.stop()


class TransferView(View):
    """View for selecting staff member to transfer to"""
    
    def __init__(
        self,
        bot: Red,
        config: Config,
        channel: Union[discord.TextChannel, discord.Thread],
        from_staff: discord.Member,
    ):
        super().__init__(timeout=120)
        self.bot = bot
        self.config = config
        self.channel = channel
        self.from_staff = from_staff
        self.selected_staff = None
    
    @discord.ui.button(label="Select by ID/Mention", style=ButtonStyle.blurple)
    async def select_btn(self, interaction: Interaction, button: Button):
        modal = TransferModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        
        if modal.staff_id:
            self.selected_staff = interaction.guild.get_member(modal.staff_id)
            if self.selected_staff:
                conf = await self.config.guild(interaction.guild).all()
                success, message = await transfer_ticket(
                    interaction.guild,
                    self.channel,
                    self.from_staff,
                    self.selected_staff,
                    self.config,
                    conf,
                )
                await interaction.followup.send(message, ephemeral=True)
                if success:
                    await self.channel.send(
                        _("🔄 Ticket transferred from {} to {}").format(
                            self.from_staff.mention,
                            self.selected_staff.mention,
                        ),
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
            else:
                await interaction.followup.send(_("User not found in this server."), ephemeral=True)
        
        self.stop()


# ============================================================================
# Quick Reply Views
# ============================================================================

class QuickReplySelect(Select):
    """Dropdown for selecting quick reply templates"""
    
    def __init__(self, templates: Dict[str, dict], config: Config, channel):
        self.templates = templates
        self.config = config
        self.channel = channel
        
        options = [
            discord.SelectOption(
                label=name[:25],
                value=name,
                description=(data.get("content", "")[:50] + "...") if len(data.get("content", "")) > 50 else data.get("content", ""),
            )
            for name, data in list(templates.items())[:25]
        ]
        
        super().__init__(
            placeholder=_("Select a quick reply..."),
            options=options,
            min_values=1,
            max_values=1,
        )
    
    async def callback(self, interaction: Interaction):
        selected = self.values[0]
        template = self.templates.get(selected, {})
        
        title = template.get("title", "")
        content = template.get("content", "")
        close_after = template.get("close_after", False)
        delay_close = template.get("delay_close", 0)
        
        # Send the reply
        if title:
            embed = discord.Embed(
                title=title,
                description=content,
                color=discord.Color.blue(),
            )
            await self.channel.send(embed=embed)
        else:
            await self.channel.send(content)
        
        await interaction.response.send_message(_("Quick reply sent!"), ephemeral=True)
        
        # Close if configured
        if close_after:
            if delay_close > 0:
                await asyncio.sleep(delay_close)
            
            conf = await self.config.guild(interaction.guild).all()
            
            # Find ticket owner
            owner_id = None
            for uid, tickets in conf.get("opened", {}).items():
                if str(self.channel.id) in tickets:
                    owner_id = uid
                    break
            
            if owner_id:
                owner = interaction.guild.get_member(int(owner_id))
                if not owner:
                    owner = await interaction.client.fetch_user(int(owner_id))
                
                await close_ticket(
                    bot=interaction.client,
                    member=owner,
                    guild=interaction.guild,
                    channel=self.channel,
                    conf=conf,
                    reason=f"Quick reply: {selected}",
                    closedby=interaction.user.name,
                    config=self.config,
                )


class QuickReplyView(View):
    """View containing quick reply dropdown"""
    
    def __init__(self, templates: Dict[str, dict], config: Config, channel):
        super().__init__(timeout=120)
        self.add_item(QuickReplySelect(templates, config, channel))


# ============================================================================
# Note Modal
# ============================================================================

class NoteModal(Modal):
    """Modal for adding internal staff notes"""
    
    def __init__(self):
        super().__init__(title=_("Add Internal Note"), timeout=300)
        self.note_content = None
        
        self.field = TextInput(
            label=_("Note"),
            style=TextStyle.long,
            placeholder=_("Enter your internal note (only visible to staff)..."),
            required=True,
            max_length=1000,
        )
        self.add_item(self.field)
    
    async def on_submit(self, interaction: Interaction):
        self.note_content = self.field.value
        await interaction.response.defer()
        self.stop()


# ============================================================================
# Panel Selector View
# ============================================================================

class PanelSelectView(View):
    """View for selecting a panel when multiple are available"""
    
    def __init__(self, panels: List[dict], bot: Red, config: Config, user: discord.Member):
        super().__init__(timeout=120)
        self.panels = panels
        self.bot = bot
        self.config = config
        self.user = user
        self.selected_panel = None
        
        # Create select menu
        options = [
            discord.SelectOption(
                label=panel.get("button_text", panel.get("name", "Unknown"))[:25],
                value=panel.get("name"),
                emoji=panel.get("button_emoji"),
                description=f"Panel: {panel.get('name')}"[:50],
            )
            for panel in panels
        ]
        
        self.select = Select(
            placeholder=_("Select a ticket type..."),
            options=options,
            min_values=1,
            max_values=1,
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)
    
    async def select_callback(self, interaction: Interaction):
        selected_name = self.select.values[0]
        self.selected_panel = next((p for p in self.panels if p.get("name") == selected_name), None)
        
        if self.selected_panel:
            await interaction.response.send_message(
                _("Opening ticket for panel: **{}**...").format(selected_name),
                ephemeral=True,
            )
        self.stop()


# ============================================================================
# Preview/Confirm View for Ticket Creation
# ============================================================================

class TicketPreviewView(View):
    """View for previewing and confirming ticket creation"""
    
    def __init__(self, panel_name: str, answers: Dict[str, str]):
        super().__init__(timeout=120)
        self.panel_name = panel_name
        self.answers = answers
        self.confirmed = None
    
    @discord.ui.button(label="Confirm & Create", style=ButtonStyle.green, emoji="✅")
    async def confirm(self, interaction: Interaction, button: Button):
        self.confirmed = True
        await interaction.response.defer()
        self.stop()
    
    @discord.ui.button(label="Cancel", style=ButtonStyle.red, emoji="❌")
    async def cancel(self, interaction: Interaction, button: Button):
        self.confirmed = False
        await interaction.response.send_message(_("Ticket creation cancelled."), ephemeral=True)
        self.stop()


# ============================================================================
# Enhanced Overview View with Pagination and Filters
# ============================================================================

class OverviewView(View):
    """Enhanced overview view with pagination, filters, and quick actions"""
    
    def __init__(
        self,
        bot: Red,
        guild: discord.Guild,
        config: Config,
        conf: dict,
        page: int = 0,
        filter_panel: Optional[str] = None,
        filter_status: Optional[str] = None,
        filter_staff: Optional[int] = None,
    ):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild = guild
        self.config = config
        self.conf = conf
        self.page = page
        self.filter_panel = filter_panel
        self.filter_status = filter_status
        self.filter_staff = filter_staff
        self.per_page = 10
        
        # Add filter selects if there are panels
        panels = list(conf.get("panels", {}).keys())
        if panels:
            panel_options = [discord.SelectOption(label="All Panels", value="all")] + [
                discord.SelectOption(label=p[:25], value=p) for p in panels[:24]
            ]
            self.panel_select = Select(
                placeholder=_("Filter by panel"),
                options=panel_options,
                row=0,
            )
            self.panel_select.callback = self.panel_filter_callback
            self.add_item(self.panel_select)
        
        # Status filter
        status_options = [
            discord.SelectOption(label="All Statuses", value="all"),
            discord.SelectOption(label="🟢 Open", value="open"),
            discord.SelectOption(label="🔵 Claimed", value="claimed"),
            discord.SelectOption(label="🟡 Awaiting User", value="awaiting_user"),
            discord.SelectOption(label="🟠 Awaiting Staff", value="awaiting_staff"),
        ]
        self.status_select = Select(
            placeholder=_("Filter by status"),
            options=status_options,
            row=1,
        )
        self.status_select.callback = self.status_filter_callback
        self.add_item(self.status_select)
    
    async def panel_filter_callback(self, interaction: Interaction):
        value = self.panel_select.values[0]
        self.filter_panel = None if value == "all" else value
        self.page = 0
        await self.refresh(interaction)
    
    async def status_filter_callback(self, interaction: Interaction):
        value = self.status_select.values[0]
        self.filter_status = None if value == "all" else value
        self.page = 0
        await self.refresh(interaction)
    
    @discord.ui.button(label="◀", style=ButtonStyle.grey, row=2)
    async def prev_page(self, interaction: Interaction, button: Button):
        if self.page > 0:
            self.page -= 1
        await self.refresh(interaction)
    
    @discord.ui.button(label="▶", style=ButtonStyle.grey, row=2)
    async def next_page(self, interaction: Interaction, button: Button):
        self.page += 1
        await self.refresh(interaction)
    
    @discord.ui.button(label="📊 Stats", style=ButtonStyle.blurple, row=2)
    async def show_stats(self, interaction: Interaction, button: Button):
        stats = get_overview_stats(self.guild, self.conf.get("opened", {}), self.conf)
        
        embed = discord.Embed(
            title=_("📊 Ticket Statistics"),
            color=discord.Color.blue(),
            timestamp=datetime.now(),
        )
        
        embed.add_field(
            name=_("Current"),
            value=_(
                "**Total Open:** {total}\n"
                "**Open:** {open}\n"
                "**Claimed:** {claimed}\n"
                "**Awaiting User:** {awaiting_user}\n"
                "**Awaiting Staff:** {awaiting_staff}"
            ).format(
                total=stats["total_open"],
                open=stats["by_status"].get("open", 0),
                claimed=stats["by_status"].get("claimed", 0),
                awaiting_user=stats["by_status"].get("awaiting_user", 0),
                awaiting_staff=stats["by_status"].get("awaiting_staff", 0),
            ),
            inline=True,
        )
        
        embed.add_field(
            name=_("All Time"),
            value=_(
                "**Opened:** {opened}\n"
                "**Closed:** {closed}\n"
                "**Avg Claim Time:** {claim}\n"
                "**Avg Close Time:** {close}"
            ).format(
                opened=stats["total_opened_all_time"],
                closed=stats["total_closed_all_time"],
                claim=stats["avg_claim_time"],
                close=stats["avg_close_time"],
            ),
            inline=True,
        )
        
        # By panel
        if stats["by_panel"]:
            panel_text = "\n".join([f"**{k}:** {v}" for k, v in stats["by_panel"].items()])
            if len(panel_text) <= 1024:
                embed.add_field(name=_("By Panel"), value=panel_text, inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="🔄 Refresh", style=ButtonStyle.grey, row=2)
    async def refresh_btn(self, interaction: Interaction, button: Button):
        self.conf = await self.config.guild(self.guild).all()
        await self.refresh(interaction)
    
    async def refresh(self, interaction: Interaction):
        """Refresh the overview embed"""
        text, page, total_pages = prep_overview_text_paginated(
            self.guild,
            self.conf.get("opened", {}),
            mention=self.conf.get("overview_mention", False),
            page=self.page,
            per_page=self.per_page,
            filter_panel=self.filter_panel,
            filter_status=self.filter_status,
            filter_staff=self.filter_staff,
        )
        
        self.page = page  # Correct if out of bounds
        
        # Update button states
        self.prev_page.disabled = self.page <= 0
        self.next_page.disabled = self.page >= total_pages - 1 if total_pages > 0 else True
        
        title = _("Ticket Overview")
        if self.filter_panel or self.filter_status:
            filters = []
            if self.filter_panel:
                filters.append(f"Panel: {self.filter_panel}")
            if self.filter_status:
                filters.append(f"Status: {TICKET_STATUSES.get(self.filter_status, self.filter_status)}")
            title += f" ({', '.join(filters)})"
        
        embed = discord.Embed(
            title=title,
            description=text,
            color=discord.Color.greyple(),
            timestamp=datetime.now(),
        )
        
        if total_pages > 0:
            embed.set_footer(text=_("Page {}/{}").format(page + 1, total_pages))
        
        await interaction.response.edit_message(embed=embed, view=self)


# ============================================================================
# Embed Wizard View
# ============================================================================

class EmbedWizardView(View):
    """Interactive wizard for creating embeds"""
    
    def __init__(self, ctx: commands.Context):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.embed_data = {
            "title": None,
            "description": None,
            "color": ctx.author.color,
            "footer": None,
            "thumbnail": None,
            "image": None,
            "fields": [],
        }
        self.step = 0
        self.cancelled = False
        self.channel = None
    
    def get_preview_embed(self) -> discord.Embed:
        """Generate preview embed"""
        embed = discord.Embed(
            title=self.embed_data["title"] or _("(No title)"),
            description=self.embed_data["description"] or _("(No description)"),
            color=self.embed_data["color"],
        )
        if self.embed_data["footer"]:
            embed.set_footer(text=self.embed_data["footer"])
        if self.embed_data["thumbnail"]:
            embed.set_thumbnail(url=self.embed_data["thumbnail"])
        if self.embed_data["image"]:
            embed.set_image(url=self.embed_data["image"])
        for field in self.embed_data["fields"]:
            embed.add_field(
                name=field["name"],
                value=field["value"],
                inline=field.get("inline", False),
            )
        return embed
    
    @discord.ui.button(label="Set Title", style=ButtonStyle.blurple, row=0)
    async def set_title(self, interaction: Interaction, button: Button):
        modal = SingleFieldModal(_("Set Title"), _("Title"), max_length=256)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.value:
            self.embed_data["title"] = modal.value
            await self.update_preview(interaction)
    
    @discord.ui.button(label="Set Description", style=ButtonStyle.blurple, row=0)
    async def set_description(self, interaction: Interaction, button: Button):
        modal = SingleFieldModal(_("Set Description"), _("Description"), style=TextStyle.long, max_length=4000)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.value:
            self.embed_data["description"] = modal.value
            await self.update_preview(interaction)
    
    @discord.ui.button(label="Set Footer", style=ButtonStyle.grey, row=0)
    async def set_footer(self, interaction: Interaction, button: Button):
        modal = SingleFieldModal(_("Set Footer"), _("Footer text"), required=False)
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.embed_data["footer"] = modal.value if modal.value else None
        await self.update_preview(interaction)
    
    @discord.ui.button(label="Set Color", style=ButtonStyle.grey, row=1)
    async def set_color(self, interaction: Interaction, button: Button):
        modal = SingleFieldModal(_("Set Color"), _("Hex color (e.g., #5865F2)"), required=False)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.value:
            try:
                color_str = modal.value.strip().lstrip("#")
                self.embed_data["color"] = discord.Color(int(color_str, 16))
            except ValueError:
                pass
        await self.update_preview(interaction)
    
    @discord.ui.button(label="Set Thumbnail", style=ButtonStyle.grey, row=1)
    async def set_thumbnail(self, interaction: Interaction, button: Button):
        modal = SingleFieldModal(_("Set Thumbnail"), _("Image URL"), required=False)
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.embed_data["thumbnail"] = modal.value if modal.value else None
        await self.update_preview(interaction)
    
    @discord.ui.button(label="Set Image", style=ButtonStyle.grey, row=1)
    async def set_image(self, interaction: Interaction, button: Button):
        modal = SingleFieldModal(_("Set Image"), _("Image URL"), required=False)
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.embed_data["image"] = modal.value if modal.value else None
        await self.update_preview(interaction)
    
    @discord.ui.button(label="Add Field", style=ButtonStyle.grey, row=2)
    async def add_field(self, interaction: Interaction, button: Button):
        if len(self.embed_data["fields"]) >= 25:
            await interaction.response.send_message(_("Maximum 25 fields allowed."), ephemeral=True)
            return
        
        modal = FieldModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.field_name and modal.field_value:
            self.embed_data["fields"].append({
                "name": modal.field_name,
                "value": modal.field_value,
                "inline": modal.inline,
            })
            await self.update_preview(interaction)
    
    @discord.ui.button(label="Send", style=ButtonStyle.green, emoji="✅", row=3)
    async def send_embed(self, interaction: Interaction, button: Button):
        if not self.embed_data["title"] and not self.embed_data["description"]:
            await interaction.response.send_message(
                _("Please set at least a title or description."),
                ephemeral=True,
            )
            return
        
        # Ask for channel
        modal = SingleFieldModal(_("Send to Channel"), _("Channel ID or #mention"))
        await interaction.response.send_modal(modal)
        await modal.wait()
        
        if modal.value:
            # Parse channel
            value = modal.value.strip()
            if value.startswith("<#") and value.endswith(">"):
                value = value[2:-1]
            try:
                channel_id = int(value)
                channel = interaction.guild.get_channel(channel_id)
            except ValueError:
                channel = None
            
            if channel and isinstance(channel, discord.TextChannel):
                embed = self.get_preview_embed()
                try:
                    await channel.send(embed=embed)
                    await interaction.followup.send(
                        _("✅ Embed sent to {}!").format(channel.mention),
                        ephemeral=True,
                    )
                    self.channel = channel
                    self.stop()
                except discord.HTTPException as e:
                    await interaction.followup.send(
                        _("Failed to send embed: {}").format(str(e)),
                        ephemeral=True,
                    )
            else:
                await interaction.followup.send(_("Invalid channel."), ephemeral=True)
    
    @discord.ui.button(label="Cancel", style=ButtonStyle.red, emoji="❌", row=3)
    async def cancel(self, interaction: Interaction, button: Button):
        self.cancelled = True
        await interaction.response.send_message(_("Embed creation cancelled."), ephemeral=True)
        self.stop()
    
    async def update_preview(self, interaction: Interaction):
        """Update the preview message"""
        try:
            embed = self.get_preview_embed()
            embed.set_author(name=_("Preview"))
            await interaction.message.edit(embed=embed, view=self)
        except discord.HTTPException:
            pass


class SingleFieldModal(Modal):
    """Modal with a single text field"""
    
    def __init__(
        self,
        title: str,
        label: str,
        style: TextStyle = TextStyle.short,
        required: bool = True,
        max_length: int = 256,
    ):
        super().__init__(title=title, timeout=120)
        self.value = None
        
        self.field = TextInput(
            label=label,
            style=style,
            required=required,
            max_length=max_length,
        )
        self.add_item(self.field)
    
    async def on_submit(self, interaction: Interaction):
        self.value = self.field.value
        await interaction.response.defer()
        self.stop()


class FieldModal(Modal):
    """Modal for adding embed fields"""
    
    def __init__(self):
        super().__init__(title=_("Add Embed Field"), timeout=120)
        self.field_name = None
        self.field_value = None
        self.inline = False
        
        self.name_input = TextInput(
            label=_("Field Name"),
            style=TextStyle.short,
            max_length=256,
        )
        self.add_item(self.name_input)
        
        self.value_input = TextInput(
            label=_("Field Value"),
            style=TextStyle.long,
            max_length=1024,
        )
        self.add_item(self.value_input)
        
        self.inline_input = TextInput(
            label=_("Inline? (yes/no)"),
            style=TextStyle.short,
            default="no",
            required=False,
        )
        self.add_item(self.inline_input)
    
    async def on_submit(self, interaction: Interaction):
        self.field_name = self.name_input.value
        self.field_value = self.value_input.value
        self.inline = self.inline_input.value.lower() in ("yes", "y", "true", "1")
        await interaction.response.defer()
        self.stop()
