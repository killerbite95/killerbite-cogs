import asyncio
import json
import logging
from contextlib import suppress
from datetime import datetime, timedelta
from typing import Optional, Union

import discord
from discord import Embed
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box, pagify

from ..abc import MixinMeta
from ..common.constants import MODAL_SCHEMA, TICKET_PANEL_SCHEMA, QUICK_REPLY_SCHEMA, TICKET_STATUSES
from ..common.menu import SMALL_CONTROLS, MenuButton, menu
from ..common.models import TimeParser, QuickReply, BlacklistEntry
from ..common.utils import (
    prune_invalid_tickets,
    update_active_overview,
    add_to_blacklist,
    remove_from_blacklist,
    export_config,
    import_config,
    preflight_check_panel,
    preflight_check_all_panels,
    log_audit_action,
    get_overview_stats,
)
from ..common.views import (
    PanelView,
    TestButton,
    confirm,
    wait_reply,
    EmbedWizardView,
    OverviewView,
    QuickReplyView,
)

log = logging.getLogger("red.vrt.admincommands")
_ = Translator("TicketsCommands", __file__)


class AdminCommands(MixinMeta):
    @commands.group(name="ticketst", aliases=["tset", "tickets"])
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    async def tickets(self, ctx: commands.Context):
        """Base support ticket settings"""
        pass

    @tickets.command()
    async def setuphelp(self, ctx: commands.Context):
        """Ticket Setup Guide"""
        desc = (
            _("To create a support ticket panel, type ")
            + f"`{ctx.clean_prefix}tickets addpanel"
            + _(" <panel_name>`")
        )
        em = Embed(
            title=_("Ticket Setup Guide"),
            description=desc,
            color=ctx.author.color,
        )
        step1 = _(
            "Set the category ID that new tickets will be created under if using channel tickets.\n"
        )
        step1 += f"`{ctx.clean_prefix}tickets category " + _(
            "<panel_name> <category_id>`"
        )
        em.add_field(name=_("Step 1"), value=step1, inline=False)
        step2 = _("Set the channel that the bots ticket panel will be located in.\n")
        step2 += f"`{ctx.clean_prefix}tickets channel " + _(
            "<panel_name> <channel_id>`"
        )
        em.add_field(name=_("Step 2"), value=step2, inline=False)
        step3 = _("Set the ID of the bots ticket panel message.\n")
        step3 += f"`{ctx.clean_prefix}tickets panelmessage " + _(
            "<panel_name> <message_id>`\n"
        )
        step3 += _(
            "At this point the ticket panel will be activated, "
            "all following steps are for extra customization.\n"
            "If you need a message to add the buttons to, you can use the `{}tickets embed` command.\n"
        ).format(ctx.clean_prefix)
        step3 += _(
            "If the bot is having trouble finding the message, run the command in the same channel as it."
        )
        em.add_field(name=_("Step 3"), value=step3, inline=False)
        step4 = _("Set the text of the ticket panel button.\n")
        step4 += f"`{ctx.clean_prefix}tickets buttontext " + _(
            "<panel_name> <button_text>`"
        )
        em.add_field(name=_("Button Text"), value=step4, inline=False)
        step5 = _("Set the ticket panel button color.\n")
        step5 += _("Valid colors are ") + "`red`, `blue`, `green`, and `grey`.\n"
        step5 += f"`{ctx.clean_prefix}tickets buttoncolor " + _(
            "<panel_name> <button_color>`"
        )
        em.add_field(name=_("Button Color"), value=step5, inline=False)
        step6 = _("Set the button emoji for the ticket panel.\n")
        step6 += f"`{ctx.clean_prefix}tickets buttonemoji " + _("<panel_name> <emoji>`")
        em.add_field(name=_("Button Emoji"), value=step6, inline=False)

        step7 = _("Use threads instead of channels for tickets\n")
        step7 += f"`{ctx.clean_prefix}tickets usethreads " + _("<panel_name>`")
        em.add_field(name=_("Thread Tickets"), value=step7, inline=False)

        step8 = _("Add a message the bot sends to the user in their ticket.\n")
        step8 += f"`{ctx.clean_prefix}tickets addmessage " + _("<panel_name>`")
        em.add_field(name=_("Ticket Messages"), value=step8, inline=False)

        step9 = _(
            "View and remove a messages the bot sends to the user in their ticket.\n"
        )
        step9 += f"`{ctx.clean_prefix}tickets viewmessages " + _("<panel_name>`")
        em.add_field(name=_("Remove/View Ticket Messages"), value=step9, inline=False)

        step10 = _("Set the naming format for ticket channels that are opened.\n")
        step10 += f"`{ctx.clean_prefix}tickets ticketname " + _(
            "<panel_name> <name_format>`"
        )
        em.add_field(name=_("Ticket Channel Name"), value=step10, inline=False)
        step11 = _("Set log channel for a ticket panel.\n")
        step11 += f"`{ctx.clean_prefix}tickets logchannel " + _(
            "<panel_name> <channel>`"
        )
        em.add_field(name=_("Log Channel"), value=step11, inline=False)

        tip = _(
            "Tip: you can create multiple support panels using the same message for a multi-button panel"
        )
        em.set_footer(text=tip)
        await ctx.send(embed=em)

    @tickets.command()
    async def suspend(self, ctx: commands.Context, *, message: Optional[str] = None):
        """
        Suspend the ticket system
        If a suspension message is set, any user that tries to open a ticket will receive this message
        """
        suspended = await self.config.guild(ctx.guild).suspended_msg()
        if message is None and suspended is None:
            return await ctx.send_help()
        if not message:
            await self.config.guild(ctx.guild).suspended_msg.set(None)
            return await ctx.send(_("Ticket system is no longer suspended!"))
        if len(message) > 900:
            return await ctx.send(
                _("Message is too long! Must be less than 900 characters")
            )
        await self.config.guild(ctx.guild).suspended_msg.set(message)
        embed = discord.Embed(
            title=_("Ticket System Suspended"),
            description=message,
            color=discord.Color.yellow(),
        )
        await ctx.send(
            _(
                "Ticket system is now suspended! Users trying to open a ticket will be met with this message"
            ),
            embed=embed,
        )

    @tickets.command()
    async def addpanel(self, ctx: commands.Context, panel_name: str):
        """Add a support ticket panel"""
        panel_name = panel_name.lower()
        em = Embed(
            title=panel_name + _(" Panel Saved"),
            description=_("Your panel has been added and will need to be configured."),
            color=ctx.author.color,
        )
        async with self.config.guild(ctx.guild).panels() as panels:
            if panel_name in panels:
                return await ctx.send(_("Panel already exists!"))
            panels[panel_name] = TICKET_PANEL_SCHEMA
        await ctx.send(embed=em)

    @tickets.command()
    async def category(
        self,
        ctx: commands.Context,
        panel_name: str,
        category: discord.CategoryChannel,
    ):
        """Set the category ID for a ticket panel"""
        panel_name = panel_name.lower()
        if not category.permissions_for(ctx.me).manage_channels:
            return await ctx.send(
                _("I need the `manage channels` permission to set this category")
            )
        if not category.permissions_for(ctx.me).manage_permissions:
            return await ctx.send(_("I need `manage roles` enabled in this category"))
        if not category.permissions_for(ctx.me).attach_files:
            return await ctx.send(
                _("I need the `attach files` permission to set this category")
            )
        if not category.permissions_for(ctx.me).view_channel:
            return await ctx.send(_("I cannot see that category!"))
        if not category.permissions_for(ctx.me).read_message_history:
            return await ctx.send(_("I cannot see message history in that category!"))
        async with self.config.guild(ctx.guild).panels() as panels:
            if panel_name not in panels:
                return await ctx.send(_("Panel does not exist!"))
            panels[panel_name]["category_id"] = category.id
            await ctx.tick()
            await ctx.send(_("New tickets will now be opened under that category!"))

    @tickets.command()
    async def channel(
        self,
        ctx: commands.Context,
        panel_name: str,
        channel: discord.TextChannel,
    ):
        """Set the channel ID where a ticket panel is located"""
        panel_name = panel_name.lower()
        if not channel.permissions_for(ctx.guild.me).view_channel:
            return await ctx.send(_("I cannot see that channel!"))
        if not channel.permissions_for(ctx.guild.me).read_message_history:
            return await ctx.send(_("I cannot see message history in that channel!"))
        async with self.config.guild(ctx.guild).panels() as panels:
            if panel_name not in panels:
                return await ctx.send(_("Panel does not exist!"))
            panels[panel_name]["channel_id"] = channel.id
            await ctx.tick()

    @tickets.command()
    async def panelmessage(
        self, ctx: commands.Context, panel_name: str, message: discord.Message
    ):
        """
        Set the message ID of a ticket panel
        Run this command in the same channel as the ticket panel message
        """
        if message.author.id != self.bot.user.id:
            return await ctx.send(
                _("I cannot add buttons to messages sent by other users!")
            )
        if isinstance(
            message.channel,
            (discord.Thread, discord.VoiceChannel, discord.ForumChannel),
        ):
            return await ctx.send(_("Channel of message must be a TEXT CHANNEL!"))
        panel_name = panel_name.lower()
        async with self.config.guild(ctx.guild).panels() as panels:
            if panel_name not in panels:
                return await ctx.send(_("Panel does not exist!"))
            if not panels[panel_name]["category_id"]:
                return await ctx.send(
                    _("Category ID must be set for this panel first!")
                )
            current_channel = panels[panel_name]["channel_id"]
            if current_channel and current_channel != message.channel.id:
                return await ctx.send(
                    _(
                        "This message is part of a different channel from the one you set!"
                    )
                )
            panels[panel_name]["message_id"] = message.id
            panels[panel_name]["channel_id"] = message.channel.id
            await ctx.tick()
        await self.initialize(ctx.guild)

    @tickets.command()
    async def buttontext(
        self, ctx: commands.Context, panel_name: str, *, button_text: str
    ):
        """Set the button text for a support ticket panel"""
        panel_name = panel_name.lower()
        if len(button_text) > 80:
            return await ctx.send(
                _("The text content of a button must be less than 80 characters!")
            )
        butt = TestButton(label=button_text)  # hehe, butt
        await ctx.send(
            _("This is what your button will look like with this text!"),
            view=butt,
        )
        async with self.config.guild(ctx.guild).panels() as panels:
            if panel_name not in panels:
                return await ctx.send(_("Panel does not exist!"))
            panels[panel_name]["button_text"] = button_text
            await ctx.tick()
        await self.initialize(ctx.guild)

    @tickets.command()
    async def buttoncolor(
        self, ctx: commands.Context, panel_name: str, *, button_color: str
    ):
        """Set the button color for a support ticket panel"""
        panel_name = panel_name.lower()
        button_color = button_color.lower()
        valid = ["red", "blue", "green", "grey", "gray"]
        if button_color not in valid:
            return await ctx.send(
                button_color
                + _(" is not valid, must be one of the following\n")
                + f"`{valid}`"
            )
        butt = TestButton(style=button_color)  # hehe, butt
        await ctx.send(
            _("This is what your button will look like with this color!"),
            view=butt,
        )
        async with self.config.guild(ctx.guild).panels() as panels:
            if panel_name not in panels:
                return await ctx.send(_("Panel does not exist!"))
            panels[panel_name]["button_color"] = button_color
            await ctx.tick()
        await self.initialize(ctx.guild)

    @tickets.command()
    async def buttonemoji(
        self,
        ctx: commands.Context,
        panel_name: str,
        *,
        emoji: Union[discord.Emoji, discord.PartialEmoji, str],
    ):
        """Set the button emoji for a support ticket panel"""
        panel_name = panel_name.lower()
        try:
            butt = TestButton(emoji=emoji)  # hehe, butt
            await ctx.send(
                _("This is what your button will look like with this emoji!"),
                view=butt,
            )
        except Exception as e:
            return await ctx.send(
                _("Failed to create test button. Error:\n")
                + f"{box(str(e), lang='python')}"
            )
        async with self.config.guild(ctx.guild).panels() as panels:
            if panel_name not in panels:
                return await ctx.send(_("Panel does not exist!"))
            panels[panel_name]["button_emoji"] = str(emoji)
            await ctx.tick()
        await self.initialize(ctx.guild)

    @tickets.command()
    async def toggle(
        self,
        ctx: commands.Context,
        panel_name: str,
    ):
        """
        Toggle a panel on/off

        Disabled panels will still show the button but it will be disabled
        """
        panel_name = panel_name.lower()
        async with self.config.guild(ctx.guild).panels() as panels:
            if panel_name not in panels:
                return await ctx.send(_("Panel does not exist!"))
            if "disabled" not in panels[panel_name]:
                panels[panel_name]["disabled"] = False

            if panels[panel_name]["disabled"]:
                panels[panel_name]["disabled"] = False
                txt = _("Panel **Enabled**")
            else:
                panels[panel_name]["disabled"] = True
                txt = _("Panel **Disabled**")
            await ctx.send(txt)
        await asyncio.sleep(3)
        await self.initialize(ctx.guild)

    @tickets.command()
    async def ticketname(
        self, ctx: commands.Context, panel_name: str, *, ticket_name: str
    ):
        """
        Set the default ticket channel name for a panel

        You can include the following in the name
        `{num}` - Ticket number
        `{user}` - user's name
        `{displayname}` - user's display name
        `{id}` - user's ID
        `{shortdate}` - mm-dd
        `{longdate}` - mm-dd-yyyy
        `{time}` - hh-mm AM/PM according to bot host system time

        You can set this to {default} to use default "Ticket-Username
        """
        panel_name = panel_name.lower()
        ticket_name = ticket_name.lower()
        async with self.config.guild(ctx.guild).panels() as panels:
            if panel_name not in panels:
                return await ctx.send(_("Panel does not exist!"))
            panels[panel_name]["ticket_name"] = ticket_name
            await ctx.tick()
        await self.initialize(ctx.guild)

    @tickets.command()
    async def usethreads(self, ctx: commands.Context, panel_name: str):
        """Toggle whether a certain panel uses threads or channels"""
        panel_name = panel_name.lower()
        async with self.config.guild(ctx.guild).panels() as panels:
            if panel_name not in panels:
                return await ctx.send(_("Panel does not exist!"))
            cid = panels[panel_name]["channel_id"]
            if not cid:
                return await ctx.send(_("Set a panel channel first!"))
            channel = ctx.guild.get_channel(cid)
            if not channel.permissions_for(ctx.guild.me).create_private_threads:
                return await ctx.send(
                    _("I am missing the `Create Private Threads` permission!")
                )
            if not channel.permissions_for(ctx.guild.me).send_messages_in_threads:
                return await ctx.send(
                    _("I am missing the `Send Messages in Threads` permission!")
                )
            toggle = panels[panel_name].get("threads", False)
            if toggle:
                panels[panel_name]["threads"] = False
                await ctx.send(
                    _("The {} panel will no longer use threads").format(panel_name)
                )
            else:
                panels[panel_name]["threads"] = True
                await ctx.send(
                    _("The {} panel will now use threads").format(panel_name)
                )
        await self.initialize(ctx.guild)

    @tickets.command()
    async def closemodal(self, ctx: commands.Context, panel_name: str):
        """Throw a modal when the close button is clicked to enter a reason"""
        panel_name = panel_name.lower()
        async with self.config.guild(ctx.guild).panels() as panels:
            if "close_reason" not in panels[panel_name]:
                panels[panel_name]["close_reason"] = False
            toggle = panels[panel_name]["close_reason"]
            if toggle:
                panels[panel_name]["close_reason"] = False
                await ctx.send(
                    _("The {} panel will no longer show a close reason modal").format(
                        panel_name
                    )
                )
            else:
                panels[panel_name]["close_reason"] = True
                await ctx.send(
                    _("The {} panel will now show a close reason modal").format(
                        panel_name
                    )
                )
        await self.initialize(ctx.guild)

    @tickets.command()
    async def logchannel(
        self,
        ctx: commands.Context,
        panel_name: str,
        channel: discord.TextChannel,
    ):
        """Set the logging channel for each panel's tickets"""
        panel_name = panel_name.lower()
        if not channel.permissions_for(ctx.guild.me).view_channel:
            return await ctx.send(_("I cannot see that channel!"))
        if not channel.permissions_for(ctx.guild.me).read_message_history:
            return await ctx.send(_("I cannot see message history in that channel!"))
        if not channel.permissions_for(ctx.guild.me).send_messages:
            return await ctx.send(_("I cannot send messages in that channel!"))
        if not channel.permissions_for(ctx.guild.me).embed_links:
            return await ctx.send(_("I cannot embed links in that channel!"))
        if not channel.permissions_for(ctx.guild.me).attach_files:
            return await ctx.send(_("I cannot attach files in that channel!"))
        async with self.config.guild(ctx.guild).panels() as panels:
            if panel_name not in panels:
                return await ctx.send(_("Panel does not exist!"))
            panels[panel_name]["log_channel"] = channel.id
            await ctx.tick()
        await self.initialize(ctx.guild)

    @tickets.command()
    async def modaltitle(
        self, ctx: commands.Context, panel_name: str, *, title: str = ""
    ):
        """Set a title for a ticket panel's modal"""
        if len(title) > 45:
            return await ctx.send(_("The max length is 45!"))
        panel_name = panel_name.lower()
        async with self.config.guild(ctx.guild).panels() as panels:
            if panel_name not in panels:
                return await ctx.send(_("Panel does not exist!"))
            if title:
                panels[panel_name]["modal_title"] = title
                await ctx.send(_("Modal title set!"))
            else:
                panels[panel_name]["modal_title"] = ""
                await ctx.send(_("Modal title removed!"))
            await self.initialize(ctx.guild)

    @tickets.command()
    async def addmodal(self, ctx: commands.Context, panel_name: str, field_name: str):
        """
        Add a modal field a ticket panel

        Ticket panels can have up to 5 fields per modal for the user to fill out before opening a ticket.
        If modal fields are added and have required fields,
        the user will have to fill them out before they can open a ticket.

        There is no toggle for modals, if a panel has them it will use them, if they don't then it just opens the ticket
        When the ticket is opened, it sends the modal field responses in an embed below the ticket message

        **Note**
        `field_name` is just the name of the field stored in config,
        it won't be shown in the modal and should not have spaces in it


        Specify an existing field name to delete a modal field (non-case-sensitive)
        """
        panel_name = panel_name.lower()
        field_name = field_name.lower()
        await self.create_or_edit_modal(ctx, panel_name, field_name)

    async def create_or_edit_modal(
        self,
        ctx: commands.Context,
        panel_name: str,
        field_name: str,
        existing_modal: Optional[dict] = None,
        preview: Optional[discord.Message] = None,
    ):
        if not existing_modal:
            # User wants to add or delete a field
            panels = await self.config.guild(ctx.guild).panels()
            if panel_name not in panels:
                return await ctx.send(_("Panel does not exist!"))

            existing = panels[panel_name].get("modals", {})
            if field_name in existing:
                # Delete field
                async with self.config.guild(ctx.guild).panels() as panels:
                    del panels[panel_name]["modals"][field_name]
                    return await ctx.send(
                        _("Field for {} panel has been removed!").format(panel_name)
                    )

            if len(existing) >= 5:
                txt = _("The most fields a modal can have is 5!")
                return await ctx.send(txt)

        async def make_preview(m, mm: discord.Message):
            txt = ""
            for k, v in m.items():
                if k == "answer":
                    continue
                txt += f"{k}: {v}\n"
            title = "Modal Preview"
            await mm.edit(
                embed=discord.Embed(title=title, description=box(txt), color=color),
                view=None,
            )

        async def cancel(m):
            await m.edit(
                embed=discord.Embed(
                    description=_("Modal field addition cancelled"), color=color
                )
            )

        foot = _("type 'cancel' to cancel at any time")
        color = ctx.author.color

        modal = MODAL_SCHEMA.copy() if not existing_modal else existing_modal
        if preview:
            await make_preview(modal, preview)

        # Label
        em = Embed(
            description=_(
                "What would you like the field label to be? (45 chars or less)"
            ),
            color=color,
        )
        em.set_footer(text=foot)
        msg = await ctx.send(embed=em)
        label = await wait_reply(ctx, 300, False)
        if not label:
            return await cancel(msg)
        if len(label) > 45:
            em = Embed(
                description=_("Modal field labels must be 45 characters or less!"),
                color=color,
            )
            return await msg.edit(embed=em)
        modal["label"] = label

        if not preview:
            preview = msg

        await make_preview(modal, preview)

        # Style
        em = Embed(
            description=_("What style would you like the text box to be? (long/short)"),
            color=color,
        )
        em.set_footer(text=foot)
        msg = await ctx.send(embed=em)
        style = await wait_reply(ctx, 300, False)
        if not style:
            return await cancel(msg)
        if style not in ["long", "short"]:
            em = Embed(
                description=_("Style must be long or short!"),
                color=color,
            )
            return await msg.edit(embed=em)
        modal["style"] = style
        await make_preview(modal, preview)

        # Placeholder
        em = Embed(
            description=_(
                "Would you like to set a placeholder for the text field?\n"
                "This is text that shows up in the box before the user types."
            ),
            color=color,
        )
        await msg.edit(embed=em)
        yes = await confirm(ctx, msg)
        if yes is None:
            return
        if yes:
            em = Embed(
                description=_("Type your desired placeholder below (100 chars max)"),
                color=color,
            )
            em.set_footer(text=foot)
            await msg.edit(embed=em)
            placeholder = await wait_reply(ctx, 300, False)
            if not placeholder:
                return await cancel(msg)
            if len(placeholder) > 100:
                em = Embed(
                    description=_("Placeholders must be 100 characters or less!"),
                    color=discord.Color.red(),
                )
                return await msg.edit(embed=em)
            modal["placeholder"] = placeholder
            await make_preview(modal, preview)

        # Default
        em = Embed(
            description=_("Would you like to set a default value for the text field?"),
            color=color,
        )
        await msg.edit(embed=em)
        yes = await confirm(ctx, msg)
        if yes is None:
            return
        if yes:
            em = Embed(
                description=_("Type your desired default value below"),
                color=color,
            )
            em.set_footer(text=foot)
            await msg.edit(embed=em)
            default = await wait_reply(ctx, 300, False)
            if not default:
                return await cancel(msg)
            modal["default"] = default
            await make_preview(modal, preview)

        # Required?
        em = Embed(
            description=_("Would you like to make this field required?"),
            color=color,
        )
        await msg.edit(embed=em)
        yes = await confirm(ctx, msg)
        if yes is None:
            return
        if not yes:
            modal["required"] = False
            await make_preview(modal, preview)

        # Min length
        em = Embed(
            description=_("Would you like to set a minimum length for this field?"),
            color=color,
        )
        await msg.edit(embed=em)
        yes = await confirm(ctx, msg)
        if yes is None:
            return
        min_length = 0
        if yes:
            em = Embed(
                description=_(
                    "Type the minimum length for this field below (less than 1024)"
                ),
                color=color,
            )
            em.set_footer(text=foot)
            await msg.edit(embed=em)
            min_length = await wait_reply(ctx, 300, False)
            if not min_length:
                return await cancel(msg)
            if not min_length.isdigit():
                em = Embed(
                    description=_("That is not a number!"),
                    color=discord.Color.red(),
                )
                return await msg.edit(embed=em)
            min_length = min(
                1023, int(min_length)
            )  # Make sure answer is between 0 and 1023
            modal["min_length"] = min_length
            await make_preview(modal, preview)

        # Max length
        em = Embed(
            description=_("Would you like to set a maximum length for this field?"),
            color=color,
        )
        await msg.edit(embed=em)
        yes = await confirm(ctx, msg)
        if yes is None:
            return
        if yes:
            em = Embed(
                description=_(
                    "Type the maximum length for this field below (up to 1024)"
                ),
                color=color,
            )
            em.set_footer(text=foot)
            await msg.edit(embed=em)
            maxlength = await wait_reply(ctx, 300, False)
            if not maxlength:
                return await cancel(msg)
            if not maxlength.isdigit():
                em = discord.Embed(
                    description=_("That is not a number!"),
                    color=discord.Color.red(),
                )
                return await msg.edit(embed=em)
            max_length = max(
                min(1024, int(maxlength)), 1
            )  # Make sure answer is between 1 and 1024
            if max_length < min_length:
                em = Embed(
                    description=_(
                        "Max length cannot be less than the minimum length 😑"
                    ),
                    color=discord.Color.red(),
                )
                return await msg.edit(embed=em)

            modal["max_length"] = max_length  # Make sure answer is between 1 and 1024
            await make_preview(modal, preview)

        async with self.config.guild(ctx.guild).panels() as panels:
            # v1.3.10 schema update (Modals)
            if "modal" not in panels[panel_name]:
                panels[panel_name]["modal"] = {}
            if isinstance(panels[panel_name]["modal"], list):
                panels[panel_name]["modal"] = {}
            panels[panel_name]["modal"][field_name] = modal

        await ctx.tick()
        desc = _("Your modal field has been added!")
        if existing_modal:
            desc = _("Your modal field has been edited!")
        em = Embed(
            description=desc,
            color=discord.Color.green(),
        )
        await msg.edit(embed=em)
        await self.initialize(ctx.guild)

    @tickets.command()
    async def viewmodal(self, ctx: commands.Context, panel_name: str):
        """View/Delete a ticket message for a support ticket panel"""
        panel_name = panel_name.lower()
        panels = await self.config.guild(ctx.guild).panels()
        if panel_name not in panels:
            return await ctx.send(_("Panel does not exist!"))
        modal = panels[panel_name].get("modal", {})
        if not modal:
            return await ctx.send(_("This panel does not have any modal fields set!"))
        embeds = []
        for i, fieldname in enumerate(list(modal.keys())):
            info = modal[fieldname]
            txt = _("`Label: `{}\n").format(info["label"])
            txt += _("`Style: `{}\n").format(info["style"])
            txt += _("`Placeholder: `{}\n").format(info["placeholder"])
            txt += _("`Default:     `{}\n").format(info["default"])
            txt += _("`Required:    `{}\n").format(info["required"])
            txt += _("`Min Length:  `{}\n").format(info["min_length"])
            txt += _("`Max Length:  `{}\n").format(info["max_length"])

            desc = f"**{fieldname}**\n{txt}\n"
            desc += _("Page") + f" `{i + 1}/{len(list(modal.keys()))}`"

            em = Embed(
                title=_("Modal Fields for {}").format(panel_name),
                description=desc,
                color=ctx.author.color,
            )
            em.set_footer(text=f"{panel_name}|{fieldname}")
            embeds.append(em)

        controls = SMALL_CONTROLS.copy()
        controls["\N{WASTEBASKET}\N{VARIATION SELECTOR-16}"] = self.delete_modal_field
        controls["\N{MEMO}"] = self.edit_modal_field
        await menu(ctx, embeds, controls)

    async def edit_modal_field(self, instance, interaction: discord.Interaction):
        index = instance.view.page
        em: Embed = instance.view.pages[index]
        panel_name, fieldname = em.footer.text.split("|")
        panels = await self.config.guild(interaction.guild).panels()
        modal = panels[panel_name]["modal"][fieldname]
        em = Embed(
            description=_("Editing {} modal field for {}!").format(
                fieldname, panel_name
            )
        )
        await interaction.response.send_message(embed=em, ephemeral=True)
        instance.view.stop()
        await self.create_or_edit_modal(instance.view.ctx, panel_name, fieldname, modal)

    async def delete_modal_field(
        self, instance: MenuButton, interaction: discord.Interaction
    ):
        index = instance.view.page
        em: Embed = instance.view.pages[index]
        panel_name, fieldname = em.footer.text.split("|")
        async with self.config.guild(interaction.guild).panels() as panels:
            del panels[panel_name]["modal"][fieldname]

        em = Embed(
            description=_("Modal field has been deleted from ") + f"{panel_name}!"
        )
        await interaction.response.send_message(embed=em, ephemeral=True)
        del instance.view.pages[index]
        if not len(instance.view.pages):
            em = Embed(description="There are no more modal fields for this panel")
            await interaction.followup.send(embed=em, ephemeral=True)
            instance.view.stop()
            return await instance.view.message.delete()
        instance.view.page += 1
        instance.view.page %= len(instance.view.pages)
        for i, embed in enumerate(instance.view.pages):
            embed.set_footer(text=f"{i + 1}/{len(instance.view.pages)}")
        return await menu(
            instance.view.ctx,
            instance.view.pages,
            instance.view.controls,
            instance.view.message,
            instance.view.page,
        )

    @tickets.command()
    async def addmessage(self, ctx: commands.Context, panel_name: str):
        """
        Add a message embed to be sent when a ticket is opened

        You can include any of these in the embed to be replaced by their value when the message is sent
        `{username}` - Person's Discord username
        `{mention}` - This will mention the user
        `{id}` - This is the ID of the user that created the ticket

        The bot will walk you through a few steps to set up the embed
        """
        panel_name = panel_name.lower()
        panels = await self.config.guild(ctx.guild).panels()
        if panel_name not in panels:
            return await ctx.send(_("Panel does not exist!"))
        foot = _("type 'cancel' to cancel the setup")
        color = ctx.author.color
        # TITLE
        em = Embed(
            description=_("Would you like this ticket embed to have a title?"),
            color=color,
        )
        msg = await ctx.send(embed=em)
        yes = await confirm(ctx, msg)
        if yes is None:
            return
        if yes:
            em = Embed(description=_("Type your desired title below"), color=color)
            em.set_footer(text=foot)
            await msg.edit(embed=em)
            title = await wait_reply(ctx, 300)
            if title and title.lower().strip() == "cancel":
                em = Embed(description=_("Ticket message addition cancelled"))
                return await msg.edit(embed=em)
        else:
            title = None
        # BODY
        em = Embed(
            description=_("Type your desired ticket message below"),
            color=color,
        )
        em.set_footer(text=foot)
        await msg.edit(embed=em)
        desc = await wait_reply(ctx, 600)
        if desc and desc.lower().strip() == "cancel":
            em = Embed(description=_("Ticket message addition cancelled"))
            return await msg.edit(embed=em)
        if desc is None:
            em = Embed(description=_("Ticket message addition cancelled"))
            return await msg.edit(embed=em)
        # FOOTER
        em = Embed(
            description=_("Would you like this ticket embed to have a footer?"),
            color=color,
        )
        await msg.edit(embed=em)
        yes = await confirm(ctx, msg)
        if yes is None:
            return
        if yes:
            em = Embed(description=_("Type your footer"), color=color)
            em.set_footer(text=foot)
            await msg.edit(embed=em)
            footer = await wait_reply(ctx, 300)
            if footer and footer.lower().strip() == _("cancel"):
                em = Embed(description=_("Ticket message addition cancelled"))
                return await msg.edit(embed=em)
        else:
            footer = None

        embed = {"title": title, "desc": desc, "footer": footer}

        async with self.config.guild(ctx.guild).panels() as panels:
            panels[panel_name]["ticket_messages"].append(embed)
            await ctx.tick()
            em = Embed(description=_("Your ticket message has been added!"))
            await msg.edit(embed=em)
        await self.initialize(ctx.guild)

    @tickets.command()
    async def viewmessages(self, ctx: commands.Context, panel_name: str):
        """View/Delete a ticket message for a support ticket panel"""
        panel_name = panel_name.lower()
        panels = await self.config.guild(ctx.guild).panels()
        if not panels:
            return await ctx.send(
                _("There are no panels available!\nUse ")
                + f"`{ctx.clean_prefix}tset addpanel` "
                + _("to create one.")
            )
        if panel_name not in panels:
            valid = _("Valid panels are: ") + f"`{', '.join(list(panels.keys()))}`"
            return await ctx.send(_("Panel does not exist!") + "\n" + valid)
        messages = panels[panel_name]["ticket_messages"]
        if not messages:
            return await ctx.send(_("This panel does not have any messages added!"))
        embeds = []
        for i, msg in enumerate(messages):
            desc = _("**Title**\n") + box(msg["title"]) + "\n"
            desc += _("**Description**\n") + box(msg["desc"]) + "\n"
            desc += _("**Footer**\n") + box(msg["footer"])
            em = Embed(
                title=_("Ticket Messages for: ") + panel_name,
                description=desc,
                color=ctx.author.color,
            )
            em.set_footer(text=_("Page") + f" {i + 1}/{len(messages)}")
            embeds.append(em)

        controls = SMALL_CONTROLS.copy()
        controls["\N{WASTEBASKET}\N{VARIATION SELECTOR-16}"] = self.delete_panel_message
        await menu(ctx, embeds, controls)

    async def delete_panel_message(self, instance, interaction: discord.Interaction):
        index = instance.view.page
        panel_name = instance.view.pages[index].title.replace(
            _("Ticket Messages for: "), ""
        )
        async with self.config.guild(interaction.guild).panels() as panels:
            del panels[panel_name]["ticket_messages"][index]
            em = Embed(
                description=_("Ticket message has been deleted from ")
                + f"{panel_name}!"
            )
            await interaction.response.send_message(embed=em, ephemeral=True)
            del instance.view.pages[index]
            if not len(instance.view.pages):
                em = Embed(description="There are no more messages for this panel")
                return await interaction.followup.send(embed=em, ephemeral=True)
            instance.view.page += 1
            instance.view.page %= len(instance.view.pages)
            for i, embed in enumerate(instance.view.pages):
                embed.set_footer(text=f"{i + 1}/{len(instance.view.pages)}")
            await instance.view.handle_page(interaction.response.edit_message)

    @tickets.command()
    async def panels(self, ctx: commands.Context):
        """View/Delete currently configured support ticket panels"""
        panels = await self.config.guild(ctx.guild).panels()
        if not panels:
            return await ctx.send(
                _("There are no panels available!\nUse ")
                + f"`{ctx.clean_prefix}tset addpanel` "
                + _("to create one.")
            )
        embeds = []
        pages = len(panels.keys())
        page = 1
        for panel_name, info in panels.items():
            cat = (
                self.bot.get_channel(info["category_id"])
                if info["category_id"]
                else "None"
            )
            channel = (
                self.bot.get_channel(info["channel_id"])
                if info["channel_id"]
                else "None"
            )
            extra = ""
            if alt := info.get("alt_channel"):
                if alt := self.bot.get_channel(alt):
                    channel = alt
                    extra = _("(alt)")
            logchannel = (
                self.bot.get_channel(info["log_channel"])
                if info["log_channel"]
                else "None"
            )

            panel_roles = ""
            for role_id, mention_toggle in info.get("roles", []):
                role = ctx.guild.get_role(role_id)
                if not role:
                    continue
                panel_roles += f"{role.mention}({mention_toggle})\n"

            open_roles = ""
            for role_id in info.get("required_roles", []):
                role = ctx.guild.get_role(role_id)
                if not role:
                    continue
                open_roles += f"{role.mention}\n"

            desc = _("`Disabled:       `") + f"{info.get('disabled', False)}\n"
            desc += _("`Category:       `") + f"{cat}\n"
            desc += _("`Channel:        `") + f"{channel}{extra}\n"
            desc += _("`MessageID:      `") + f"{info['message_id']}\n"
            desc += _("`ButtonText:     `") + f"{info['button_text']}\n"
            desc += _("`ButtonColor:    `") + f"{info['button_color']}\n"
            desc += _("`ButtonEmoji:    `") + f"{info['button_emoji']}\n"
            desc += _("`TicketNum:      `") + f"{info['ticket_num']}\n"
            desc += _("`Use Threads:    `") + f"{info.get('threads', False)}\n"
            desc += _("`TicketMessages: `") + f"{len(info['ticket_messages'])}\n"
            desc += _("`TicketName:     `") + f"{info['ticket_name']}\n"
            desc += _("`Modal Fields:   `") + f"{len(info.get('modal', {}))}\n"
            desc += _("`Modal Title:    `") + f"{info.get('modal_title', 'None')}\n"
            desc += _("`LogChannel:     `") + f"{logchannel}\n"
            desc += _("`Priority:       `") + f"{info.get('priority', 1)}\n"
            desc += _("`Button Row:     `") + f"{info.get('row')}\n"
            desc += _("`Reason Modal:   `") + f"{info.get('close_reason', False)}\n"
            desc += _("`Max Claims:     `") + f"{info.get('max_claims', 0)}"

            em = Embed(
                title=panel_name,
                description=desc,
                color=ctx.author.color,
            )
            if panel_roles:
                em.add_field(name=_("Panel Roles(Mention)"), value=panel_roles)
            if open_roles:
                em.add_field(name=_("Required Roles to Open"), value=open_roles)
            em.set_footer(text=_("Page ") + f"{page}/{pages}")
            page += 1
            embeds.append(em)
        controls = SMALL_CONTROLS.copy()
        controls["\N{WASTEBASKET}\N{VARIATION SELECTOR-16}"] = self.delete_panel
        await menu(ctx, embeds, controls)

    async def delete_panel(self, instance, interaction: discord.Interaction):
        index = instance.view.page
        panel_name = instance.view.pages[index].title
        async with self.config.guild(interaction.guild).panels() as panels:
            del panels[panel_name]
            em = Embed(description=panel_name + _(" panel has been deleted!"))
            await interaction.response.send_message(embed=em, ephemeral=True)
            del instance.view.pages[index]
            instance.view.page += 1
            instance.view.page %= len(instance.view.pages)
            for i, embed in enumerate(instance.view.pages):
                embed.set_footer(text=f"{i + 1}/{len(instance.view.pages)}")
            if not instance.view.pages:
                em = Embed(description=_("There are no more panels configured!"))
                await interaction.response.edit_message(embed=em, view=None)
                await interaction.response.defer()
                instance.view.stop()

    @tickets.command(name="view")
    async def view_settings(self, ctx: commands.Context):
        """View support ticket settings"""
        conf = await self.config.guild(ctx.guild).all()
        inactive = conf["inactive"]
        plural = _("hours")
        singular = _("hour")
        no_resp = f"{inactive} {singular if inactive == 1 else plural}"
        if not inactive:
            no_resp = _("Disabled")

        detailed = conf.get("detailed_transcript", False)
        transcript_type = _("Detailed") if detailed else _("Simple")

        msg = _("`Max Tickets:      `") + f"{conf['max_tickets']}\n"
        msg += _("`DM Alerts:        `") + f"{conf['dm']}\n"
        msg += _("`Users can Rename: `") + f"{conf['user_can_rename']}\n"
        msg += _("`Users can Close:  `") + f"{conf['user_can_close']}\n"
        msg += _("`Users can Manage: `") + f"{conf['user_can_manage']}\n"
        msg += _("`Save Transcripts: `") + f"{conf['transcript']} ({transcript_type})\n"
        msg += _("`Auto Close:       `") + (_("On") if inactive else _("Off")) + "\n"
        msg += _("`NoResponseDelete: `") + no_resp

        support = conf["support_roles"]
        suproles = ""
        if support:
            for role_id, mention_toggle in support:
                role = ctx.guild.get_role(role_id)
                if role:
                    suproles += f"{role.mention}({mention_toggle})\n"
        blacklist = conf["blacklist"]
        blacklisted = ""
        if blacklist:
            for uid_or_rid in blacklist:
                user_or_role = ctx.guild.get_member(uid_or_rid) or ctx.guild.get_role(
                    uid_or_rid
                )
                if user_or_role:
                    blacklisted += f"{user_or_role.mention}-{user_or_role.id}\n"
                else:
                    blacklisted += _("Invalid") + f"-{uid_or_rid}\n"
        embed = Embed(
            title=_("Tickets Core Settings"),
            description=msg,
            color=discord.Color.random(),
        )
        if suproles:
            embed.add_field(
                name=_("Support Roles(Mention)"), value=suproles, inline=False
            )
        if blacklisted:
            embed.add_field(name=_("Blacklist"), value=blacklisted, inline=False)

        if conf["thread_close"]:
            txt = _("Thread tickets will be closed/archived rather than deleted")
        else:
            txt = _("Thread tickets will be deleted instead of closed/archived")
        embed.add_field(name=_("Thread Tickets"), value=txt, inline=False)

        embed.add_field(
            name=_("Thread Ticket Auto-Add"),
            value=_(
                "Auto-add support and panel roles to tickets that use threads: **{}**"
            ).format(str(conf["auto_add"])),
        )
        if conf["suspended_msg"]:
            embed.add_field(
                name=_("Suspended Message"),
                value=_(
                    "Tickets are currently suspended, users will be met with the following message\n{}"
                ).format(box(conf["suspended_msg"])),
                inline=False,
            )
        await ctx.send(embed=embed)

    @tickets.command()
    async def maxtickets(self, ctx: commands.Context, amount: int):
        """Set the max tickets a user can have open at one time of any kind"""
        if not amount:
            return await ctx.send(_("Max ticket amount must be greater than 0!"))
        await self.config.guild(ctx.guild).max_tickets.set(amount)
        await ctx.tick()

    @tickets.command()
    async def supportrole(
        self,
        ctx: commands.Context,
        role: discord.Role,
        mention: Optional[bool] = False,
    ):
        """
        Add/Remove ticket support roles (one at a time)

        **Optional**: include `true` for mention to have that role mentioned when a ticket is opened

        To remove a role, simply run this command with it again to remove it
        """
        entry = [role.id, mention]
        async with self.config.guild(ctx.guild).support_roles() as roles:
            for i in roles.copy():
                if i[0] == role.id:
                    roles.remove(i)
                    await ctx.send(
                        _("{} has been removed from support roles").format(role.name)
                    )
                    break
            else:
                roles.append(entry)
                await ctx.send(role.name + _(" has been added to support roles"))
        await self.initialize(ctx.guild)

    @tickets.command()
    async def panelrole(
        self,
        ctx: commands.Context,
        panel_name: str,
        role: discord.Role,
        mention: Optional[bool] = False,
    ):
        """
        Add/Remove roles for a specific panel

        To remove a role, simply run this command with it again to remove it

        **Optional**: include `true` for mention to have that role mentioned when a ticket is opened

        These roles are a specialized subset of the main support roles.
        Use this role type if you want to isolate specific groups to a certain panel.
        """
        panel_name = panel_name.lower()
        entry = [role.id, mention]
        async with self.config.guild(ctx.guild).panels() as panels:
            if panel_name not in panels:
                return await ctx.send(_("Panel does not exist!"))
            if "roles" not in panels[panel_name]:
                panels[panel_name]["roles"] = []
            for i in panels[panel_name]["roles"].copy():
                if i[0] == role.id:
                    panels[panel_name]["roles"].remove(i)
                    await ctx.send(
                        _("{} has been removed from the {} panel roles").format(
                            role.name, panel_name
                        )
                    )
                    break
            else:
                panels[panel_name]["roles"].append(entry)
                await ctx.send(
                    role.name
                    + _(" has been added to the {} panel roles").format(panel_name)
                )
        await self.initialize(ctx.guild)

    @tickets.command()
    async def maxclaims(
        self, ctx: commands.Context, panel_name: str, amount: commands.positive_int
    ):
        """Set how many staff members can claim/join a ticket before the join button is disabled (If using threads)"""
        panel_name = panel_name.lower()
        async with self.config.guild(ctx.guild).panels() as panels:
            if panel_name not in panels:
                return await ctx.send(_("Panel does not exist!"))
            panels[panel_name]["max_claims"] = amount

        await ctx.send(
            _("Up to {} staff member(s) can claim a single ticket").format(amount)
        )
        await self.initialize(ctx.guild)

    @tickets.command()
    async def openrole(
        self, ctx: commands.Context, panel_name: str, *, role: discord.Role
    ):
        """
        Add/Remove roles required to open a ticket for a specific panel

        Specify the same role to remove it
        """
        panel_name = panel_name.lower()
        async with self.config.guild(ctx.guild).panels() as panels:
            if panel_name not in panels:
                return await ctx.send(_("Panel does not exist!"))
            if "required_roles" not in panels[panel_name]:
                panels[panel_name]["required_roles"] = []

            if role.id in panels[panel_name]["required_roles"]:
                panels[panel_name]["required_roles"].remove(role.id)
                await ctx.send(
                    _(
                        "{} has been removed from the {} panel's required open roles"
                    ).format(role.name, panel_name)
                )
            else:
                panels[panel_name]["required_roles"].append(role.id)
                await ctx.send(
                    role.name
                    + _(" has been added to the {} panel's required open roles").format(
                        panel_name
                    )
                )
            await self.initialize(ctx.guild)

    @tickets.command()
    async def altchannel(
        self,
        ctx: commands.Context,
        panel_name: str,
        *,
        channel: Union[discord.TextChannel, discord.CategoryChannel],
    ):
        """
        Set an alternate channel that tickets will be opened under for a panel

        If the panel uses threads, this needs to be a normal text channel.
        If the panel uses channels, this needs to be a category.

        If the panel is a channel type and a channel is used, the bot will use the category associated with the channel.

        To remove the alt channel, specify the existing one
        """
        panel_name = panel_name.lower()
        async with self.config.guild(ctx.guild).panels() as panels:
            if panel_name not in panels:
                return await ctx.send(_("Panel does not exist!"))
            panel = panels[panel_name]
            if panel.get("alt_channel", 0) == channel.id:
                panel["alt_channel"] = 0
                return await ctx.send(_("Alt channel has been removed for this panel!"))
            panel["alt_channel"] = channel.id
            await ctx.send(_("Alt channel has been set to {}!").format(channel.name))
        await self.initialize(ctx.guild)

    @tickets.command()
    async def priority(self, ctx: commands.Context, panel_name: str, priority: int):
        """Set the priority order of a panel's button"""
        if priority < 1 or priority > 25:
            return await ctx.send(_("Priority needs to be between 1 and 25"))
        panel_name = panel_name.lower()
        async with self.config.guild(ctx.guild).panels() as panels:
            if panel_name not in panels:
                return await ctx.send(_("Panel does not exist!"))
            panels[panel_name]["priority"] = priority
            await ctx.send(
                _("Priority for this panel has been set to {}!").format(priority)
            )
        await self.initialize(ctx.guild)

    @tickets.command()
    async def row(self, ctx: commands.Context, panel_name: str, row: int):
        """Set the row of a panel's button (0 - 4)"""
        if row < 0 or row > 4:
            return await ctx.send(_("Row needs to be between 0 and 4"))
        panel_name = panel_name.lower()
        async with self.config.guild(ctx.guild).panels() as panels:
            if panel_name not in panels:
                return await ctx.send(_("Panel does not exist!"))

            panel = panels[panel_name]
            panel_key = f"{panel['channel_id']}{panel['message_id']}"
            count = 0
            for i in panels.values():
                panel_key2 = f"{i['channel_id']}{i['message_id']}"
                if panel_key != panel_key2:
                    continue
                if not i["row"]:
                    continue
                if i["row"] == row:
                    count += 1

            if count > 4:
                return await ctx.send(
                    _(
                        "This panel message already has the max amount of buttons for that specific row"
                    )
                )
            panels[panel_name]["row"] = row
            await ctx.send(
                _("The row number for this panel has been set to {}!").format(row)
            )
        await self.initialize(ctx.guild)

    @tickets.command()
    async def noresponse(self, ctx: commands.Context, hours: int):
        """
        Auto-close ticket if opener doesn't say anything after X hours of opening

        Set to 0 to disable this

        If using thread tickets, this translates to the thread's "Hide after inactivity" setting.
        Your options are:
        - 1 hour
        - 24 hours (1 day)
        - 72 hours (3 days)
        - 168 hours (1 week)
        Tickets will default to the closest value you select.
        """
        await self.config.guild(ctx.guild).inactive.set(hours)
        await ctx.tick()

    @tickets.command()
    async def overview(
        self,
        ctx: commands.Context,
        *,
        channel: Optional[discord.TextChannel] = None,
    ):
        """
        Set a channel for the live overview message

        The overview message shows all active tickets across all configured panels for a server.
        """
        if not channel:
            await ctx.send(_("Overview channel has been **Disabled**"))
            await self.config.guild(ctx.guild).overview_channel.set(0)
        else:
            await ctx.send(
                _("Overview channel has been set to {}").format(channel.mention)
            )
            await self.config.guild(ctx.guild).overview_channel.set(channel.id)
            conf = await self.config.guild(ctx.guild).all()
            new_id = await update_active_overview(ctx.guild, conf)
            if new_id:
                await self.config.guild(ctx.guild).overview_msg.set(new_id)

    @tickets.command()
    async def overviewmention(self, ctx: commands.Context):
        """Toggle whether channels are mentioned in the active ticket overview"""
        toggle = await self.config.guild(ctx.guild).overview_mention()
        if toggle:
            await self.config.guild(ctx.guild).overview_mention.set(False)
            txt = _(
                "Ticket channels will no longer be mentioned in the active ticket channel"
            )
        else:
            await self.config.guild(ctx.guild).overview_mention.set(True)
            txt = _("Ticket channels now be mentioned in the active ticket channel")
        await ctx.send(txt)

    @tickets.command()
    async def cleanup(self, ctx: commands.Context):
        """Cleanup tickets that no longer exist"""
        async with ctx.typing():
            conf = await self.config.guild(ctx.guild).all()
            await prune_invalid_tickets(ctx.guild, conf, self.config, ctx)

    @tickets.command()
    async def getlink(self, ctx: commands.Context, message: discord.Message):
        """Refetch the transcript link for a ticket"""
        notrans = _("This message does not have a transcript attached!")
        if not message.attachments:
            return await ctx.send(notrans)
        attachment = message.attachments[0]
        if not attachment.filename.endswith(".html"):
            return await ctx.send(notrans)
        user_id = attachment.filename.split("-")[-1].split(".")[0]
        if not user_id.isdigit():
            return await ctx.send(notrans)
        url = f"https://mahto.id/chat-exporter?url={attachment.url}"
        with suppress(discord.HTTPException):
            await ctx.channel.send(url, delete_after=3600)

    # TOGGLES --------------------------------------------------------------------------------
    @tickets.command()
    async def dm(self, ctx: commands.Context):
        """(Toggle) The bot sending DM's for ticket alerts"""
        toggle = await self.config.guild(ctx.guild).dm()
        if toggle:
            await self.config.guild(ctx.guild).dm.set(False)
            await ctx.send(_("DM alerts have been **Disabled**"))
        else:
            await self.config.guild(ctx.guild).dm.set(True)
            await ctx.send(_("DM alerts have been **Enabled**"))

    @tickets.command()
    async def threadclose(self, ctx: commands.Context):
        """(Toggle) Thread tickets being closed & archived instead of deleted"""
        toggle = await self.config.guild(ctx.guild).thread_close()
        if toggle:
            await self.config.guild(ctx.guild).thread_close.set(False)
            await ctx.send(_("Closed ticket threads will be **Deleted**"))
        else:
            await self.config.guild(ctx.guild).thread_close.set(True)
            await ctx.send(_("Closed ticket threads will be **Closed & Archived**"))

    @tickets.command()
    async def selfrename(self, ctx: commands.Context):
        """(Toggle) If users can rename their own tickets"""
        toggle = await self.config.guild(ctx.guild).user_can_rename()
        if toggle:
            await self.config.guild(ctx.guild).user_can_rename.set(False)
            await ctx.send(_("User can no longer rename their support channel"))
        else:
            await self.config.guild(ctx.guild).user_can_rename.set(True)
            await ctx.send(_("User can now rename their support channel"))

    @tickets.command()
    async def selfclose(self, ctx: commands.Context):
        """(Toggle) If users can close their own tickets"""
        toggle = await self.config.guild(ctx.guild).user_can_close()
        if toggle:
            await self.config.guild(ctx.guild).user_can_close.set(False)
            await ctx.send(_("User can no longer close their support ticket channel"))
        else:
            await self.config.guild(ctx.guild).user_can_close.set(True)
            await ctx.send(_("User can now close their support ticket channel"))

    @tickets.command()
    async def selfmanage(self, ctx: commands.Context):
        """
        (Toggle) If users can manage their own tickets

        Users will be able to add/remove others to their support ticket
        """
        toggle = await self.config.guild(ctx.guild).user_can_manage()
        if toggle:
            await self.config.guild(ctx.guild).user_can_manage.set(False)
            await ctx.send(_("User can no longer manage their support ticket channel"))
        else:
            await self.config.guild(ctx.guild).user_can_manage.set(True)
            await ctx.send(_("User can now manage their support ticket channel"))

    @tickets.command()
    async def autoadd(self, ctx: commands.Context):
        """
        (Toggle) Auto-add support and panel roles to thread tickets

        Adding a user to a thread pings them, so this is off by default
        """
        toggle = await self.config.guild(ctx.guild).auto_add()
        if toggle:
            await self.config.guild(ctx.guild).auto_add.set(False)
            await ctx.send(
                _(
                    "Support and panel roles will no longer be auto-added to thread tickets"
                )
            )
        else:
            await self.config.guild(ctx.guild).auto_add.set(True)
            await ctx.send(
                _("Support and panel roles will be auto-added to thread tickets")
            )

    @tickets.command(name="transcripts")
    async def transcripts_toggle(self, ctx: commands.Context):
        """
        (Toggle) Ticket transcripts

        Closed tickets will have their transcripts uploaded to the log channel
        """
        toggle = await self.config.guild(ctx.guild).transcript()
        if toggle:
            await self.config.guild(ctx.guild).transcript.set(False)
            await ctx.send(_("Transcripts of closed tickets will no longer be saved"))
        else:
            await self.config.guild(ctx.guild).transcript.set(True)
            await ctx.send(_("Transcripts of closed tickets will now be saved"))

    @tickets.command(aliases=["intertrans", "itrans", "itranscript"])
    async def interactivetranscript(self, ctx: commands.Context):
        """
        (Toggle) Interactive transcripts

        Transcripts will be an interactive html file to visualize the conversation from your browser.
        """
        toggle = await self.config.guild(ctx.guild).detailed_transcript()
        if toggle:
            await self.config.guild(ctx.guild).detailed_transcript.set(False)
            await ctx.send(
                _("Transcripts of closed tickets will no longer be interactive")
            )
        else:
            await self.config.guild(ctx.guild).detailed_transcript.set(True)
            await ctx.send(_("Transcripts of closed tickets will now be interactive"))

    @tickets.command()
    async def updatemessage(
        self,
        ctx: commands.Context,
        source: discord.Message,
        target: discord.Message,
    ):
        """Update a message with another message (Target gets updated using the source)"""
        try:
            await target.edit(
                embeds=source.embeds,
                content=target.content,
                attachments=target.attachments,
            )
            await ctx.tick()
        except discord.HTTPException as e:
            if txt := e.text:
                await ctx.send(txt)
            else:
                await ctx.send(_("Failed to update message!"))

    @tickets.command()
    async def embed(
        self,
        ctx: commands.Context,
        color: Optional[discord.Color],
        channel: Optional[discord.TextChannel],
        title: str,
        *,
        description: str,
    ):
        """Create an embed for ticket panel buttons to be added to"""
        foot = _("type 'cancel' to cancel")
        channel = channel or ctx.channel
        color = color or ctx.author.color
        # FOOTER
        em = Embed(
            description=_("Would you like this embed to have a footer?"),
            color=color,
        )
        msg = await ctx.send(embed=em)
        yes = await confirm(ctx, msg)
        if yes:
            em = Embed(description=_("Enter the desired footer"), color=color)
            em.set_footer(text=foot)
            await msg.edit(embed=em)
            footer = await wait_reply(ctx, 300)
            if footer and footer.lower().strip() == _("cancel"):
                em = Embed(description=_("Embed creation cancelled"))
                return await msg.edit(embed=em)
        else:
            footer = None

        # Thumbnail
        em = Embed(
            description=_("Would you like this embed to have a thumbnail?"),
            color=color,
        )
        try:
            await msg.edit(embed=em)
        except discord.NotFound:
            # Message was deleted. Just cancel.
            return
        yes = await confirm(ctx, msg)
        if yes is None:
            return

        if yes:
            em = Embed(description=_("Enter a url for the thumbnail"), color=color)
            em.set_footer(text=foot)
            await msg.edit(embed=em)
            thumbnail = await wait_reply(ctx, 300)
            if thumbnail and thumbnail.lower().strip() == _("cancel"):
                em = Embed(description=_("Embed creation cancelled"))
                return await msg.edit(embed=em)
        else:
            thumbnail = None

        # Image
        em = Embed(
            description=_("Would you like this embed to have an image?"),
            color=color,
        )
        await msg.edit(embed=em)
        yes = await confirm(ctx, msg)
        if yes:
            em = Embed(description=_("Enter a url for the image"), color=color)
            em.set_footer(text=foot)
            await msg.edit(embed=em)
            image = await wait_reply(ctx, 300)
            if image and image.lower().strip() == _("cancel"):
                em = Embed(description=_("Embed creation cancelled"))
                return await msg.edit(embed=em)
        else:
            image = None

        embed = discord.Embed(title=title, description=description, color=color)
        if footer:
            embed.set_footer(text=footer)
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        if image:
            embed.set_image(url=image)

        fields = 0
        while fields < 25:
            if not fields:
                em = Embed(
                    description=_("Would you like to add a field to this embed?"),
                    color=color,
                )
            else:
                em = Embed(
                    description=_(
                        "Would you like to add another field to this embed?\n*There are currently {} fields*"
                    ).format(fields),
                    color=color,
                )
            await msg.edit(embed=em)
            yes = await confirm(ctx, msg)
            if yes:
                em = Embed(description=_("Enter the name of the field"), color=color)
                em.set_footer(text=foot)
                await msg.edit(embed=em)
                name = await wait_reply(ctx, 300)
                if name and name.lower().strip() == "cancel":
                    break
                em = Embed(description=_("Enter the value of the field"), color=color)
                em.set_footer(text=foot)
                await msg.edit(embed=em)
                value = await wait_reply(ctx, 300)
                if value and value.lower().strip() == "cancel":
                    break
                em = Embed(
                    description=_("Do you want this field to be inline?"),
                    color=color,
                )
                await msg.edit(embed=em)
                yes = await confirm(ctx, msg)
                inline = True if yes else False
                embed.add_field(name=name, value=value, inline=inline)
                fields += 1
            else:
                break

        try:
            await channel.send(embed=embed)
            await msg.edit(content=_("Your embed has been sent!"), embed=None)
        except Exception as e:
            await ctx.send(
                _("Failed to send embed!\nException: {}").format(box(str(e), "py"))
            )

    @commands.hybrid_command(name="openfor")
    @commands.mod_or_permissions(manage_messages=True)
    async def openfor(
        self, ctx: commands.Context, user: discord.Member, *, panel_name: str
    ):
        """Open a ticket for another user"""
        conf = await self.config.guild(ctx.guild).all()
        panel_name = panel_name.lower()
        if panel_name not in conf["panels"]:
            return await ctx.send(_("Panel does not exist!"))
        panel = conf["panels"][panel_name]
        # Create a custom temp view by manipulting the panel
        view = PanelView(self.bot, ctx.guild, self.config, [panel], mock_user=user)
        desc = _(
            "Click the button below to open a {} ticket for {}\nThis message will self-cleanup in 2 minutes."
        ).format(panel_name, user.name)
        embed = discord.Embed(
            description=desc, color=await self.bot.get_embed_color(ctx)
        )
        await ctx.send(embed=embed, view=view, delete_after=120)

    # ============================================================================
    # Anti-Spam / Control de Abuso
    # ============================================================================

    @tickets.group(name="cooldown")
    async def ticket_cooldown(self, ctx: commands.Context):
        """Manage ticket creation cooldowns"""
        pass

    @ticket_cooldown.command(name="set")
    async def cooldown_set(self, ctx: commands.Context, seconds: int):
        """
        Set the cooldown between ticket creations per user
        
        Set to 0 to disable
        """
        if seconds < 0:
            return await ctx.send(_("Cooldown must be 0 or greater"))
        
        await self.config.guild(ctx.guild).ticket_cooldown.set(seconds)
        if seconds == 0:
            await ctx.send(_("Ticket cooldown disabled"))
        else:
            await ctx.send(_("Users must now wait {} seconds between creating tickets").format(seconds))

    @ticket_cooldown.command(name="view")
    async def cooldown_view(self, ctx: commands.Context):
        """View the current cooldown settings"""
        conf = await self.config.guild(ctx.guild).all()
        cooldown = conf.get("ticket_cooldown", 0)
        rate_limit = conf.get("global_rate_limit", 0)
        
        embed = discord.Embed(
            title=_("Cooldown Settings"),
            color=ctx.author.color,
        )
        embed.add_field(
            name=_("Per-User Cooldown"),
            value=_("{} seconds").format(cooldown) if cooldown else _("Disabled"),
        )
        embed.add_field(
            name=_("Global Rate Limit"),
            value=_("{} tickets/hour").format(rate_limit) if rate_limit else _("Disabled"),
        )
        await ctx.send(embed=embed)

    @tickets.command(name="ratelimit")
    async def ticket_ratelimit(self, ctx: commands.Context, tickets_per_hour: int):
        """
        Set the global rate limit for ticket creation (tickets per hour)
        
        Set to 0 to disable
        """
        if tickets_per_hour < 0:
            return await ctx.send(_("Rate limit must be 0 or greater"))
        
        await self.config.guild(ctx.guild).global_rate_limit.set(tickets_per_hour)
        if tickets_per_hour == 0:
            await ctx.send(_("Global rate limit disabled"))
        else:
            await ctx.send(_("Maximum {} tickets can now be created per hour").format(tickets_per_hour))

    @tickets.group(name="agegate")
    async def age_gate(self, ctx: commands.Context):
        """Set account or server membership age requirements"""
        pass

    @age_gate.command(name="account")
    async def age_account(self, ctx: commands.Context, days: int):
        """
        Set minimum account age in days to open tickets
        
        Set to 0 to disable
        """
        if days < 0:
            return await ctx.send(_("Days must be 0 or greater"))
        
        await self.config.guild(ctx.guild).min_account_age.set(days)
        if days == 0:
            await ctx.send(_("Account age requirement disabled"))
        else:
            await ctx.send(_("Users must now have accounts at least {} days old to open tickets").format(days))

    @age_gate.command(name="server")
    async def age_server(self, ctx: commands.Context, days: int):
        """
        Set minimum server membership age in days to open tickets
        
        Set to 0 to disable
        """
        if days < 0:
            return await ctx.send(_("Days must be 0 or greater"))
        
        await self.config.guild(ctx.guild).min_server_age.set(days)
        if days == 0:
            await ctx.send(_("Server membership age requirement disabled"))
        else:
            await ctx.send(_("Users must now be server members for at least {} days to open tickets").format(days))

    # ============================================================================
    # Blacklist Avanzado
    # ============================================================================

    @tickets.group(name="blacklist")
    async def blacklist_cmd(self, ctx: commands.Context):
        """Manage the ticket blacklist (advanced)"""
        pass

    @blacklist_cmd.command(name="add")
    async def blacklist_add(
        self,
        ctx: commands.Context,
        user: discord.Member,
        duration: Optional[str] = None,
        *,
        reason: Optional[str] = None,
    ):
        """
        Add a user to the ticket blacklist
        
        Duration can be: 1h, 2d, 1w, 30d, permanent
        If no duration is specified, the ban is permanent
        
        Examples:
        - `[p]tickets blacklist add @user` - permanent ban
        - `[p]tickets blacklist add @user 7d spamming` - 7 day ban with reason
        """
        expires_at = None
        if duration and duration.lower() != "permanent":
            parsed = TimeParser.parse(duration)
            if parsed:
                expires_at = datetime.now() + parsed
            else:
                return await ctx.send(_("Invalid duration format. Use: 1h, 2d, 1w, 30d, or permanent"))
        
        success, message = await add_to_blacklist(
            guild=ctx.guild,
            user=user,
            moderator=ctx.author,
            reason=reason,
            expires_at=expires_at,
            config=self.config,
        )
        
        if success:
            # Log the action
            conf = await self.config.guild(ctx.guild).all()
            await log_audit_action(
                guild=ctx.guild,
                action="blacklist_add",
                user=user,
                moderator=ctx.author,
                details=f"Duration: {duration or 'permanent'}, Reason: {reason or 'None'}",
                config=self.config,
                conf=conf,
            )
        
        await ctx.send(message)

    @blacklist_cmd.command(name="remove")
    async def blacklist_remove(self, ctx: commands.Context, user: discord.Member):
        """Remove a user from the ticket blacklist"""
        success, message = await remove_from_blacklist(
            guild=ctx.guild,
            user=user,
            config=self.config,
        )
        
        if success:
            conf = await self.config.guild(ctx.guild).all()
            await log_audit_action(
                guild=ctx.guild,
                action="blacklist_remove",
                user=user,
                moderator=ctx.author,
                details="User removed from blacklist",
                config=self.config,
                conf=conf,
            )
        
        await ctx.send(message)

    @blacklist_cmd.command(name="list")
    async def blacklist_list(self, ctx: commands.Context):
        """View the ticket blacklist"""
        conf = await self.config.guild(ctx.guild).all()
        
        # Combine simple blacklist and advanced blacklist
        simple_bl = conf.get("blacklist", [])
        advanced_bl = conf.get("blacklist_advanced", {})
        
        if not simple_bl and not advanced_bl:
            return await ctx.send(_("The blacklist is empty"))
        
        embed = discord.Embed(
            title=_("Ticket Blacklist"),
            color=ctx.author.color,
        )
        
        lines = []
        now = datetime.now()
        
        # Simple blacklist entries
        for uid in simple_bl:
            member = ctx.guild.get_member(uid)
            name = member.display_name if member else f"Unknown ({uid})"
            lines.append(f"• **{name}** - Permanent (legacy)")
        
        # Advanced blacklist entries
        for uid, data in advanced_bl.items():
            member = ctx.guild.get_member(int(uid))
            name = member.display_name if member else f"Unknown ({uid})"
            
            expires = data.get("expires_at")
            if expires:
                expires_dt = datetime.fromisoformat(expires)
                if expires_dt <= now:
                    remaining = "Expired"
                else:
                    remaining = f"<t:{int(expires_dt.timestamp())}:R>"
            else:
                remaining = "Permanent"
            
            reason = data.get("reason", "No reason")[:50]
            lines.append(f"• **{name}** - {remaining}\n  └ {reason}")
        
        if lines:
            description = "\n".join(lines[:20])  # Limit to 20 entries
            if len(lines) > 20:
                description += _("\n\n... and {} more").format(len(lines) - 20)
            embed.description = description
        
        await ctx.send(embed=embed)

    # ============================================================================
    # Auto-Close Inteligente
    # ============================================================================

    @tickets.group(name="autoclose")
    async def auto_close_settings(self, ctx: commands.Context):
        """Configure smart auto-close settings"""
        pass

    @auto_close_settings.command(name="user")
    async def autoclose_user(self, ctx: commands.Context, hours: int):
        """
        Set hours to auto-close if user doesn't respond after staff reply
        
        Set to 0 to disable
        """
        if hours < 0:
            return await ctx.send(_("Hours must be 0 or greater"))
        
        await self.config.guild(ctx.guild).auto_close_user_hours.set(hours)
        if hours == 0:
            await ctx.send(_("User inactivity auto-close disabled"))
        else:
            await ctx.send(
                _("Tickets will auto-close after {} hours if user doesn't respond to staff").format(hours)
            )

    @auto_close_settings.command(name="staff")
    async def autoclose_staff(self, ctx: commands.Context, hours: int):
        """
        Set hours to auto-close if no staff responds
        
        Set to 0 to disable
        """
        if hours < 0:
            return await ctx.send(_("Hours must be 0 or greater"))
        
        await self.config.guild(ctx.guild).auto_close_staff_hours.set(hours)
        if hours == 0:
            await ctx.send(_("Staff inactivity auto-close disabled"))
        else:
            await ctx.send(
                _("Tickets will auto-close after {} hours if no staff responds").format(hours)
            )

    @auto_close_settings.command(name="warning")
    async def autoclose_warning(self, ctx: commands.Context, hours: int):
        """
        Set hours before auto-close to send warning
        
        Set to 0 to disable warnings
        """
        if hours < 0:
            return await ctx.send(_("Hours must be 0 or greater"))
        
        await self.config.guild(ctx.guild).auto_close_warning_hours.set(hours)
        if hours == 0:
            await ctx.send(_("Auto-close warnings disabled"))
        else:
            await ctx.send(
                _("Users will be warned {} hours before ticket auto-closes").format(hours)
            )

    @auto_close_settings.command(name="reopen")
    async def autoclose_reopen(self, ctx: commands.Context, hours: int):
        """
        Set hours after close during which user can reopen ticket
        
        Set to 0 to disable reopening
        """
        if hours < 0:
            return await ctx.send(_("Hours must be 0 or greater"))
        
        await self.config.guild(ctx.guild).reopen_hours.set(hours)
        if hours == 0:
            await ctx.send(_("Ticket reopening disabled"))
        else:
            await ctx.send(
                _("Users can reopen tickets within {} hours of closing").format(hours)
            )

    @auto_close_settings.command(name="view")
    async def autoclose_view(self, ctx: commands.Context):
        """View current auto-close settings"""
        conf = await self.config.guild(ctx.guild).all()
        
        embed = discord.Embed(
            title=_("Auto-Close Settings"),
            color=ctx.author.color,
        )
        
        embed.add_field(
            name=_("Legacy Inactive Hours"),
            value=str(conf.get("inactive", 0)) or _("Disabled"),
        )
        embed.add_field(
            name=_("User Inactivity"),
            value=_("{} hours").format(conf.get("auto_close_user_hours", 0)) or _("Disabled"),
        )
        embed.add_field(
            name=_("Staff Inactivity"),
            value=_("{} hours").format(conf.get("auto_close_staff_hours", 0)) or _("Disabled"),
        )
        embed.add_field(
            name=_("Warning Before Close"),
            value=_("{} hours").format(conf.get("auto_close_warning_hours", 0)) or _("Disabled"),
        )
        embed.add_field(
            name=_("Reopen Window"),
            value=_("{} hours").format(conf.get("reopen_hours", 0)) or _("Disabled"),
        )
        
        await ctx.send(embed=embed)

    # ============================================================================
    # Claim Settings
    # ============================================================================

    @tickets.group(name="claim")
    async def claim_settings(self, ctx: commands.Context):
        """Configure ticket claim settings"""
        pass

    @claim_settings.command(name="maxperstaff")
    async def claim_max(self, ctx: commands.Context, max_claims: int):
        """
        Set maximum tickets a staff member can claim at once
        
        Set to 0 for unlimited
        """
        if max_claims < 0:
            return await ctx.send(_("Must be 0 or greater"))
        
        await self.config.guild(ctx.guild).max_claims_per_staff.set(max_claims)
        if max_claims == 0:
            await ctx.send(_("Staff members can now claim unlimited tickets"))
        else:
            await ctx.send(
                _("Staff members can now claim a maximum of {} tickets").format(max_claims)
            )

    @claim_settings.command(name="view")
    async def claim_view(self, ctx: commands.Context):
        """View current claim settings"""
        conf = await self.config.guild(ctx.guild).all()
        
        embed = discord.Embed(
            title=_("Claim Settings"),
            color=ctx.author.color,
        )
        
        max_claims = conf.get("max_claims_per_staff", 0)
        embed.add_field(
            name=_("Max Claims Per Staff"),
            value=str(max_claims) if max_claims else _("Unlimited"),
        )
        
        # Count current claims per staff
        opened = conf.get("opened", {})
        claims = {}
        for uid, tickets in opened.items():
            for cid, ticket in tickets.items():
                claimed_by = ticket.get("claimed_by")
                if claimed_by:
                    claims[claimed_by] = claims.get(claimed_by, 0) + 1
        
        if claims:
            claims_text = "\n".join([
                f"<@{uid}>: {count}" for uid, count in sorted(
                    claims.items(), key=lambda x: x[1], reverse=True
                )[:10]
            ])
            embed.add_field(
                name=_("Current Claims"),
                value=claims_text,
                inline=False,
            )
        
        await ctx.send(embed=embed)

    # ============================================================================
    # Escalation Settings
    # ============================================================================

    @tickets.group(name="escalation")
    async def escalation_settings(self, ctx: commands.Context):
        """Configure ticket escalation settings"""
        pass

    @escalation_settings.command(name="channel")
    async def escalation_channel(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Set the channel for escalation alerts (leave empty to disable)"""
        if channel:
            await self.config.guild(ctx.guild).escalation_channel.set(channel.id)
            await ctx.send(_("Escalation alerts will be sent to {}").format(channel.mention))
        else:
            await self.config.guild(ctx.guild).escalation_channel.set(0)
            await ctx.send(_("Escalation channel disabled"))

    @escalation_settings.command(name="role")
    async def escalation_role(self, ctx: commands.Context, role: Optional[discord.Role] = None):
        """Set the role to ping for escalations (leave empty to disable)"""
        if role:
            await self.config.guild(ctx.guild).escalation_role.set(role.id)
            await ctx.send(_("Escalation alerts will mention {}").format(role.mention))
        else:
            await self.config.guild(ctx.guild).escalation_role.set(0)
            await ctx.send(_("Escalation role disabled"))

    @escalation_settings.command(name="minutes")
    async def escalation_minutes(self, ctx: commands.Context, minutes: int):
        """
        Set minutes of inactivity before escalating an unclaimed ticket
        
        Set to 0 to disable
        """
        if minutes < 0:
            return await ctx.send(_("Minutes must be 0 or greater"))
        
        await self.config.guild(ctx.guild).escalation_minutes.set(minutes)
        if minutes == 0:
            await ctx.send(_("Automatic escalation disabled"))
        else:
            await ctx.send(
                _("Tickets will be escalated after {} minutes without a claim").format(minutes)
            )

    @escalation_settings.command(name="view")
    async def escalation_view(self, ctx: commands.Context):
        """View current escalation settings"""
        conf = await self.config.guild(ctx.guild).all()
        
        embed = discord.Embed(
            title=_("Escalation Settings"),
            color=ctx.author.color,
        )
        
        channel_id = conf.get("escalation_channel", 0)
        channel = ctx.guild.get_channel(channel_id) if channel_id else None
        embed.add_field(
            name=_("Channel"),
            value=channel.mention if channel else _("Not set"),
        )
        
        role_id = conf.get("escalation_role", 0)
        role = ctx.guild.get_role(role_id) if role_id else None
        embed.add_field(
            name=_("Role"),
            value=role.mention if role else _("Not set"),
        )
        
        minutes = conf.get("escalation_minutes", 0)
        embed.add_field(
            name=_("Minutes"),
            value=str(minutes) if minutes else _("Disabled"),
        )
        
        await ctx.send(embed=embed)

    # ============================================================================
    # Quick Replies
    # ============================================================================

    @tickets.group(name="quickreply", aliases=["qr"])
    async def quick_reply(self, ctx: commands.Context):
        """Manage quick reply templates"""
        pass

    @quick_reply.command(name="add")
    async def qr_add(self, ctx: commands.Context, name: str, *, content: str):
        """
        Add a quick reply template
        
        Example: `[p]tickets quickreply add greeting Hello! How can I help you today?`
        """
        name = name.lower()
        
        async with self.config.guild(ctx.guild).quick_replies() as replies:
            if name in replies:
                return await ctx.send(_("A quick reply with that name already exists"))
            
            replies[name] = {
                "title": "",
                "content": content,
                "close_after": False,
                "delay_close": 0,
            }
        
        await ctx.send(_("Quick reply '{}' added!").format(name))

    @quick_reply.command(name="addadvanced")
    async def qr_add_advanced(
        self,
        ctx: commands.Context,
        name: str,
        close_after: bool = False,
        delay_seconds: int = 0,
    ):
        """
        Add an advanced quick reply with more options
        
        You will be prompted for title and content
        """
        name = name.lower()
        
        conf = await self.config.guild(ctx.guild).all()
        if name in conf.get("quick_replies", {}):
            return await ctx.send(_("A quick reply with that name already exists"))
        
        # Get title
        await ctx.send(_("Enter the title for this quick reply (or 'skip' for no title):"))
        title_msg = await wait_reply(ctx, timeout=120)
        title = "" if title_msg.lower() == "skip" else title_msg
        
        # Get content
        await ctx.send(_("Enter the content/message for this quick reply:"))
        content = await wait_reply(ctx, timeout=300)
        if not content:
            return await ctx.send(_("Cancelled - no content provided"))
        
        async with self.config.guild(ctx.guild).quick_replies() as replies:
            replies[name] = {
                "title": title,
                "content": content,
                "close_after": close_after,
                "delay_close": delay_seconds,
            }
        
        await ctx.send(_("Advanced quick reply '{}' added!").format(name))

    @quick_reply.command(name="remove")
    async def qr_remove(self, ctx: commands.Context, name: str):
        """Remove a quick reply template"""
        name = name.lower()
        
        async with self.config.guild(ctx.guild).quick_replies() as replies:
            if name not in replies:
                return await ctx.send(_("Quick reply not found"))
            del replies[name]
        
        await ctx.send(_("Quick reply '{}' removed!").format(name))

    @quick_reply.command(name="list")
    async def qr_list(self, ctx: commands.Context):
        """List all quick reply templates"""
        conf = await self.config.guild(ctx.guild).all()
        replies = conf.get("quick_replies", {})
        
        if not replies:
            return await ctx.send(_("No quick replies configured"))
        
        embed = discord.Embed(
            title=_("Quick Replies"),
            color=ctx.author.color,
        )
        
        for name, data in list(replies.items())[:25]:
            content_preview = data.get("content", "")[:100]
            if len(data.get("content", "")) > 100:
                content_preview += "..."
            
            extras = []
            if data.get("title"):
                extras.append(f"Title: {data['title'][:30]}")
            if data.get("close_after"):
                delay = data.get("delay_close", 0)
                extras.append(f"Closes after {delay}s" if delay else "Closes immediately")
            
            value = content_preview
            if extras:
                value += f"\n*{', '.join(extras)}*"
            
            embed.add_field(name=name, value=value, inline=False)
        
        await ctx.send(embed=embed)

    # ============================================================================
    # Audit Log
    # ============================================================================

    @tickets.command(name="auditlog")
    async def audit_log_channel(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Set the audit log channel for ticket actions (leave empty to disable)"""
        if channel:
            await self.config.guild(ctx.guild).audit_log_channel.set(channel.id)
            await ctx.send(_("Audit logs will be sent to {}").format(channel.mention))
        else:
            await self.config.guild(ctx.guild).audit_log_channel.set(0)
            await ctx.send(_("Audit logging disabled"))

    # ============================================================================
    # Export/Import Config
    # ============================================================================

    @tickets.command(name="export")
    async def export_cmd(self, ctx: commands.Context):
        """Export ticket configuration to a JSON file"""
        export_data = await export_config(ctx.guild, self.config)
        
        # Create file
        json_str = json.dumps(export_data, indent=2, default=str)
        
        file = discord.File(
            fp=__import__("io").BytesIO(json_str.encode()),
            filename=f"tickets_config_{ctx.guild.id}.json"
        )
        
        await ctx.send(
            _("Here's your ticket configuration export:"),
            file=file,
        )

    @tickets.command(name="import")
    async def import_cmd(self, ctx: commands.Context):
        """Import ticket configuration from a JSON file"""
        if not ctx.message.attachments:
            return await ctx.send(_("Please attach a JSON file to import"))
        
        attachment = ctx.message.attachments[0]
        if not attachment.filename.endswith(".json"):
            return await ctx.send(_("Please attach a JSON file"))
        
        try:
            content = await attachment.read()
            import_data = json.loads(content.decode())
        except json.JSONDecodeError:
            return await ctx.send(_("Invalid JSON file"))
        except Exception as e:
            return await ctx.send(_("Failed to read file: {}").format(str(e)))
        
        # Confirm
        embed = discord.Embed(
            title=_("⚠️ Import Configuration"),
            description=_(
                "This will **overwrite** the following settings:\n"
                "• Support roles\n"
                "• Panel configurations\n"
                "• Quick replies\n"
                "• Blacklist\n"
                "• All other ticket settings\n\n"
                "**This action cannot be undone!**\n"
                "Are you sure you want to continue?"
            ),
            color=discord.Color.orange(),
        )
        msg = await ctx.send(embed=embed)
        yes = await confirm(ctx, msg)
        
        if not yes:
            return await ctx.send(_("Import cancelled"))
        
        success, message = await import_config(
            guild=ctx.guild,
            config=self.config,
            import_data=import_data,
        )
        
        if success:
            await log_audit_action(
                guild=ctx.guild,
                action="config_import",
                user=ctx.author,
                moderator=ctx.author,
                details="Configuration imported",
                config=self.config,
                conf=await self.config.guild(ctx.guild).all(),
            )
            await self.initialize(ctx.guild)
        
        await ctx.send(message)

    # ============================================================================
    # Preflight Check
    # ============================================================================

    @tickets.command(name="preflight")
    async def preflight_cmd(self, ctx: commands.Context, panel_name: Optional[str] = None):
        """
        Run preflight checks on panel configurations
        
        Checks permissions, channel validity, and other potential issues
        """
        conf = await self.config.guild(ctx.guild).all()
        
        if panel_name:
            panel_name = panel_name.lower()
            if panel_name not in conf.get("panels", {}):
                return await ctx.send(_("Panel not found"))
            
            panel = conf["panels"][panel_name]
            issues = await preflight_check_panel(ctx.guild, panel_name, panel, self.bot)
            
            if not issues:
                embed = discord.Embed(
                    title=_("✅ Panel Check Passed"),
                    description=_("No issues found with panel '{}'").format(panel_name),
                    color=discord.Color.green(),
                )
            else:
                embed = discord.Embed(
                    title=_("⚠️ Panel Issues Found"),
                    description="\n".join([f"• {issue}" for issue in issues]),
                    color=discord.Color.orange(),
                )
        else:
            # Check all panels
            all_issues = await preflight_check_all_panels(ctx.guild, conf, self.bot)
            
            if not all_issues:
                embed = discord.Embed(
                    title=_("✅ All Panels OK"),
                    description=_("No issues found with any panels"),
                    color=discord.Color.green(),
                )
            else:
                embed = discord.Embed(
                    title=_("⚠️ Issues Found"),
                    color=discord.Color.orange(),
                )
                for panel_name, issues in all_issues.items():
                    if issues:
                        embed.add_field(
                            name=panel_name,
                            value="\n".join([f"• {i}" for i in issues[:5]]),
                            inline=False,
                        )
        
        await ctx.send(embed=embed)

    # ============================================================================
    # Enhanced Embed Wizard
    # ============================================================================

    @tickets.command(name="embedwizard")
    async def embed_wizard(self, ctx: commands.Context):
        """
        Interactive embed creation wizard with buttons
        
        Create embeds visually with live preview
        """
        view = EmbedWizardView(ctx)
        
        embed = discord.Embed(
            title=_("(No title)"),
            description=_("(No description)"),
            color=ctx.author.color,
        )
        embed.set_author(name=_("Preview"))
        
        msg = await ctx.send(
            _("Use the buttons below to build your embed:"),
            embed=embed,
            view=view,
        )
        
        await view.wait()
        
        if view.cancelled:
            await msg.edit(view=None)
        elif view.channel:
            await msg.edit(
                content=_("Embed sent to {}!").format(view.channel.mention),
                embed=None,
                view=None,
            )
        else:
            await msg.edit(view=None)

    # ============================================================================
    # Enhanced Overview
    # ============================================================================

    @tickets.command(name="overviewpro")
    async def overview_pro(self, ctx: commands.Context):
        """
        Enhanced ticket overview with pagination, filters, and stats
        """
        conf = await self.config.guild(ctx.guild).all()
        
        view = OverviewView(
            bot=self.bot,
            guild=ctx.guild,
            config=self.config,
            conf=conf,
        )
        
        # Initial render
        from ..common.utils import prep_overview_text_paginated
        text, page, total_pages = prep_overview_text_paginated(
            ctx.guild,
            conf.get("opened", {}),
            mention=conf.get("overview_mention", False),
        )
        
        embed = discord.Embed(
            title=_("Ticket Overview"),
            description=text,
            color=discord.Color.greyple(),
            timestamp=datetime.now(),
        )
        if total_pages > 0:
            embed.set_footer(text=_("Page {}/{}").format(1, total_pages))
        
        await ctx.send(embed=embed, view=view)

    # ============================================================================
    # Statistics
    # ============================================================================

    @tickets.command(name="stats")
    async def ticket_stats(self, ctx: commands.Context):
        """View ticket statistics and KPIs"""
        conf = await self.config.guild(ctx.guild).all()
        stats = get_overview_stats(ctx.guild, conf.get("opened", {}), conf)
        
        embed = discord.Embed(
            title=_("📊 Ticket Statistics"),
            color=ctx.author.color,
            timestamp=datetime.now(),
        )
        
        # Current status
        status_text = []
        status_text.append(_("**Total Open:** {}").format(stats["total_open"]))
        for status, emoji in TICKET_STATUSES.items():
            count = stats["by_status"].get(status, 0)
            if count > 0:
                status_text.append(f"{emoji} {status.replace('_', ' ').title()}: {count}")
        
        embed.add_field(
            name=_("Current Tickets"),
            value="\n".join(status_text) or _("No open tickets"),
            inline=True,
        )
        
        # All time stats
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
        
        # By staff
        if stats["by_staff"]:
            staff_text = "\n".join([
                f"<@{uid}>: {count}" 
                for uid, count in sorted(
                    stats["by_staff"].items(), 
                    key=lambda x: x[1], 
                    reverse=True
                )[:10]
            ])
            embed.add_field(name=_("Claims by Staff"), value=staff_text, inline=False)
        
        await ctx.send(embed=embed)

    # ============================================================================
    # Transcript Settings
    # ============================================================================

    @tickets.group(name="transcript")
    async def transcript_settings(self, ctx: commands.Context):
        """Configure transcript settings"""
        pass

    @transcript_settings.command(name="retention")
    async def transcript_retention(self, ctx: commands.Context, days: int):
        """
        Set how many days to keep transcript logs
        
        Set to 0 for unlimited retention
        """
        if days < 0:
            return await ctx.send(_("Days must be 0 or greater"))
        
        await self.config.guild(ctx.guild).transcript_retention_days.set(days)
        if days == 0:
            await ctx.send(_("Transcript retention set to unlimited"))
        else:
            await ctx.send(_("Transcripts will be kept for {} days").format(days))

    @transcript_settings.command(name="formats")
    async def transcript_formats(self, ctx: commands.Context, *formats: str):
        """
        Set transcript export formats
        
        Available formats: html, txt, json
        Example: `[p]tickets transcript formats html txt`
        """
        valid_formats = ["html", "txt", "json"]
        selected = []
        
        for fmt in formats:
            fmt = fmt.lower()
            if fmt in valid_formats and fmt not in selected:
                selected.append(fmt)
        
        if not selected:
            return await ctx.send(_("Please specify at least one valid format: html, txt, json"))
        
        await self.config.guild(ctx.guild).transcript_formats.set(selected)
        await ctx.send(_("Transcript formats set to: {}").format(", ".join(selected)))

    @transcript_settings.command(name="view")
    async def transcript_view(self, ctx: commands.Context):
        """View current transcript settings"""
        conf = await self.config.guild(ctx.guild).all()
        
        embed = discord.Embed(
            title=_("Transcript Settings"),
            color=ctx.author.color,
        )
        
        retention = conf.get("transcript_retention_days", 0)
        embed.add_field(
            name=_("Retention"),
            value=_("{} days").format(retention) if retention else _("Unlimited"),
        )
        
        formats = conf.get("transcript_formats", ["html"])
        embed.add_field(
            name=_("Formats"),
            value=", ".join(formats) if formats else "html",
        )
        
        await ctx.send(embed=embed)
        await asyncio.sleep(120)
        if not ctx.interaction:
            await ctx.tick()
