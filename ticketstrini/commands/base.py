import asyncio
import datetime
import logging
from typing import Optional

import discord
from discord import app_commands
from redbot.core import commands
from redbot.core.commands import parse_timedelta
from redbot.core.i18n import Translator
import pathlib
from redbot.core.utils.mod import is_admin_or_superior

from ..abc import MixinMeta
from ..common.utils import (
    can_close,
    close_ticket,
    get_ticket_owner,
    claim_ticket,
    unclaim_ticket,
    transfer_ticket,
    add_ticket_note,
)
from ..common.views import QuickReplyView, NoteModal, TransferView

LOADING = "https://i.imgur.com/l3p6EMX.gif"
log = logging.getLogger("red.vrt.tickets.base")
_ = Translator("Tickets", pathlib.Path(__file__).parent.parent)


class BaseCommands(MixinMeta):
    @commands.hybrid_command(name="add", description="Add a user to your ticket")
    @app_commands.describe(user="The Discord user you want to add to your ticket")
    @commands.guild_only()
    async def add_user_to_ticket(self, ctx: commands.Context, *, user: discord.Member):
        """Add a user to your ticket"""
        conf = await self.config.guild(ctx.guild).all()
        opened = conf["opened"]
        owner_id = get_ticket_owner(opened, str(ctx.channel.id))
        if not owner_id:
            return await ctx.send(_("This is not a ticket channel, or it has been removed from config"))

        panel_name = opened[owner_id][str(ctx.channel.id)]["panel"]
        panel_roles = conf["panels"][panel_name]["roles"]
        user_roles = [r.id for r in ctx.author.roles]

        support_roles = [i[0] for i in conf["support_roles"]]
        support_roles.extend([i[0] for i in panel_roles])

        # If a mod tries
        can_add = False
        if any(i in support_roles for i in user_roles):
            can_add = True
        elif ctx.author.id == ctx.guild.owner_id:
            can_add = True
        elif await is_admin_or_superior(self.bot, ctx.author):
            can_add = True
        elif owner_id == str(ctx.author.id) and conf["user_can_manage"]:
            can_add = True

        if not can_add:
            return await ctx.send(_("You do not have permissions to add users to this ticket"))

        channel = ctx.channel
        try:
            if isinstance(channel, discord.TextChannel):
                await ctx.channel.set_permissions(user, read_messages=True, send_messages=True)
            else:
                await channel.add_user(user)
        except Exception as e:
            log.exception(f"Failed to add {user.name} to ticket", exc_info=e)
            txt = _("Failed to add user to ticket: {}").format(str(e))
            return await ctx.send(txt)
        await ctx.send(f"**{user.name}** " + _("has been added to this ticket!"))

    @commands.hybrid_command(name="renameticket", description="Rename your ticket")
    @app_commands.describe(new_name="The new name for your ticket")
    @commands.guild_only()
    async def rename_ticket(self, ctx: commands.Context, *, new_name: str):
        """Rename your ticket channel"""
        conf = await self.config.guild(ctx.guild).all()
        opened = conf["opened"]
        owner_id = get_ticket_owner(opened, str(ctx.channel.id))
        if not owner_id:
            return await ctx.send(_("This is not a ticket channel, or it has been removed from config"))

        panel_name = opened[owner_id][str(ctx.channel.id)]["panel"]
        panel_roles = conf["panels"][panel_name]["roles"]
        user_roles = [r.id for r in ctx.author.roles]

        support_roles = [i[0] for i in conf["support_roles"]]
        support_roles.extend([i[0] for i in panel_roles])

        can_rename = False
        if any(i in support_roles for i in user_roles):
            can_rename = True
        elif ctx.author.id == ctx.guild.owner_id:
            can_rename = True
        elif await is_admin_or_superior(self.bot, ctx.author):
            can_rename = True
        elif owner_id == str(ctx.author.id) and conf["user_can_rename"]:
            can_rename = True

        if not can_rename:
            return await ctx.send(_("You do not have permissions to rename this ticket"))
        if not ctx.channel.permissions_for(ctx.me).manage_channels:
            return await ctx.send(_("I no longer have permission to edit this channel"))

        if isinstance(ctx.channel, discord.TextChannel):
            txt = _("Renaming channel to {}").format(f"**{new_name}**")
            if ctx.interaction:
                await ctx.interaction.response.send_message(txt)
            else:
                await ctx.send(txt)
        else:
            # Threads already alert to name changes
            await ctx.tick()

        await ctx.channel.edit(name=new_name)

    @commands.hybrid_command(name="close", description="Close your ticket")
    @app_commands.describe(reason="Reason for closing the ticket")
    @commands.guild_only()
    async def close_a_ticket(self, ctx: commands.Context, *, reason: Optional[str] = None):
        """
        Close your ticket

        **Examples**
        `[p]close` - closes ticket with no reason attached
        `[p]close thanks for helping!` - closes with reason "thanks for helping!"
        `[p]close 1h` - closes in 1 hour with no reason attached
        `[p]close 1m thanks for helping!` - closes in 1 minute with reason "thanks for helping!"
        """
        conf = await self.config.guild(ctx.guild).all()
        owner_id = get_ticket_owner(conf["opened"], str(ctx.channel.id))
        if not owner_id:
            return await ctx.send(
                _(
                    "Cannot find the owner of this ticket! Maybe it is not a ticket channel or was cleaned from the config?"
                )
            )

        user_can_close = await can_close(self.bot, ctx.guild, ctx.channel, ctx.author, owner_id, conf)
        if not user_can_close:
            return await ctx.send(_("You do not have permissions to close this ticket"))
        else:
            owner = ctx.guild.get_member(int(owner_id))
            if not owner:
                owner = await self.bot.fetch_user(int(owner_id))

        if reason:
            timestring = reason.split(" ")[0]
            if td := parse_timedelta(timestring):

                def check(m: discord.Message):
                    return m.channel.id == ctx.channel.id and not m.author.bot

                reason = reason.replace(timestring, "")
                if not reason.strip():
                    # User provided delayed close with no reason attached
                    reason = None
                closing_in = int((datetime.datetime.now() + td).timestamp())
                closemsg = _("This ticket will close {}").format(f"<t:{closing_in}:R>")
                msg = await ctx.send(f"{owner.mention}, {closemsg}")
                await asyncio.sleep(1.5)
                try:
                    await ctx.bot.wait_for("message", check=check, timeout=td.total_seconds())
                except asyncio.TimeoutError:
                    pass
                else:
                    cancelled = _("Closing cancelled!")
                    await msg.edit(content=cancelled)
                    return

                conf = await self.config.guild(ctx.guild).all()
                owner_id = get_ticket_owner(conf["opened"], str(ctx.channel.id))
                if not owner_id:
                    # Ticket already closed...
                    return

        if ctx.interaction:
            await ctx.interaction.response.send_message(_("Closing..."), ephemeral=True, delete_after=4)
        await close_ticket(
            bot=self.bot,
            member=owner,
            guild=ctx.guild,
            channel=ctx.channel,
            conf=conf,
            reason=reason,
            closedby=ctx.author.name,
            config=self.config,
        )

    # ============================================================================
    # Claim / Unclaim / Transfer Commands
    # ============================================================================

    @commands.hybrid_command(name="claim", description="Claim this ticket")
    @commands.guild_only()
    async def claim_cmd(self, ctx: commands.Context):
        """Claim this ticket as your own to handle"""
        conf = await self.config.guild(ctx.guild).all()
        owner_id = get_ticket_owner(conf["opened"], str(ctx.channel.id))
        if not owner_id:
            return await ctx.send(_("This is not a ticket channel"))
        
        # Check if user is support staff
        panel_name = conf["opened"][owner_id][str(ctx.channel.id)]["panel"]
        panel_roles = conf["panels"][panel_name]["roles"] if panel_name in conf["panels"] else []
        user_roles = [r.id for r in ctx.author.roles]
        
        support_roles = [i[0] for i in conf["support_roles"]]
        support_roles.extend([i[0] for i in panel_roles])
        
        is_staff = any(i in support_roles for i in user_roles)
        if not is_staff and ctx.author.id != ctx.guild.owner_id:
            if not await is_admin_or_superior(self.bot, ctx.author):
                return await ctx.send(_("Only support staff can claim tickets"))
        
        success, message = await claim_ticket(
            guild=ctx.guild,
            channel=ctx.channel,
            staff=ctx.author,
            config=self.config,
            conf=conf,
        )
        
        await ctx.send(message)

    @commands.hybrid_command(name="unclaim", description="Unclaim this ticket")
    @commands.guild_only()
    async def unclaim_cmd(self, ctx: commands.Context):
        """Unclaim this ticket so others can claim it"""
        conf = await self.config.guild(ctx.guild).all()
        owner_id = get_ticket_owner(conf["opened"], str(ctx.channel.id))
        if not owner_id:
            return await ctx.send(_("This is not a ticket channel"))
        
        success, message = await unclaim_ticket(
            guild=ctx.guild,
            channel=ctx.channel,
            staff=ctx.author,
            config=self.config,
            conf=conf,
        )
        
        await ctx.send(message)

    @commands.hybrid_command(name="transfer", description="Transfer this ticket to another staff member")
    @app_commands.describe(new_staff="The staff member to transfer the ticket to")
    @commands.guild_only()
    async def transfer_cmd(self, ctx: commands.Context, new_staff: discord.Member):
        """Transfer this ticket to another staff member"""
        conf = await self.config.guild(ctx.guild).all()
        owner_id = get_ticket_owner(conf["opened"], str(ctx.channel.id))
        if not owner_id:
            return await ctx.send(_("This is not a ticket channel"))
        
        # Check if user is support staff or current claimant
        ticket_data = conf["opened"][owner_id][str(ctx.channel.id)]
        claimed_by = ticket_data.get("claimed_by")
        
        panel_name = ticket_data.get("panel")
        panel_roles = conf["panels"][panel_name]["roles"] if panel_name in conf["panels"] else []
        user_roles = [r.id for r in ctx.author.roles]
        
        support_roles = [i[0] for i in conf["support_roles"]]
        support_roles.extend([i[0] for i in panel_roles])
        
        is_staff = any(i in support_roles for i in user_roles)
        is_claimant = claimed_by == ctx.author.id
        is_admin = ctx.author.id == ctx.guild.owner_id or await is_admin_or_superior(self.bot, ctx.author)
        
        if not (is_staff or is_claimant or is_admin):
            return await ctx.send(_("Only staff or the current claimant can transfer tickets"))
        
        # Check if target is staff
        new_staff_roles = [r.id for r in new_staff.roles]
        if not any(i in support_roles for i in new_staff_roles):
            if new_staff.id != ctx.guild.owner_id and not await is_admin_or_superior(self.bot, new_staff):
                return await ctx.send(_("The target user must be a support staff member"))
        
        success, message = await transfer_ticket(
            guild=ctx.guild,
            channel=ctx.channel,
            from_staff=ctx.author,
            to_staff=new_staff,
            config=self.config,
            conf=conf,
        )
        
        await ctx.send(message)

    # ============================================================================
    # Notes Command
    # ============================================================================

    @commands.hybrid_command(name="note", description="Add an internal note to this ticket")
    @app_commands.describe(note="The note to add (optional, will prompt if not provided)")
    @commands.guild_only()
    async def note_cmd(self, ctx: commands.Context, *, note: Optional[str] = None):
        """
        Add an internal staff note to this ticket
        
        Notes are only visible to staff and stored with the ticket
        """
        conf = await self.config.guild(ctx.guild).all()
        owner_id = get_ticket_owner(conf["opened"], str(ctx.channel.id))
        if not owner_id:
            return await ctx.send(_("This is not a ticket channel"))
        
        # Check if user is support staff
        panel_name = conf["opened"][owner_id][str(ctx.channel.id)]["panel"]
        panel_roles = conf["panels"][panel_name]["roles"] if panel_name in conf["panels"] else []
        user_roles = [r.id for r in ctx.author.roles]
        
        support_roles = [i[0] for i in conf["support_roles"]]
        support_roles.extend([i[0] for i in panel_roles])
        
        is_staff = any(i in support_roles for i in user_roles)
        if not is_staff and ctx.author.id != ctx.guild.owner_id:
            if not await is_admin_or_superior(self.bot, ctx.author):
                return await ctx.send(_("Only support staff can add notes"))
        
        if not note:
            # Use modal for input
            if ctx.interaction:
                modal = NoteModal()
                await ctx.interaction.response.send_modal(modal)
                await modal.wait()
                note = modal.note_content
                if not note:
                    return
            else:
                return await ctx.send(_("Please provide a note: `{}note Your note here`").format(ctx.prefix))
        
        success = await add_ticket_note(
            guild=ctx.guild,
            channel=ctx.channel,
            staff=ctx.author,
            content=note,
            config=self.config,
            conf=conf,
        )
        
        if success:
            if ctx.interaction and not ctx.interaction.response.is_done():
                await ctx.interaction.response.send_message(_("📝 Note added!"), ephemeral=True)
            else:
                await ctx.send(_("📝 Note added!"))
        else:
            await ctx.send(_("Failed to add note"))

    @commands.hybrid_command(name="notes", description="View notes for this ticket")
    @commands.guild_only()
    async def notes_list(self, ctx: commands.Context):
        """View all internal notes for this ticket"""
        conf = await self.config.guild(ctx.guild).all()
        owner_id = get_ticket_owner(conf["opened"], str(ctx.channel.id))
        if not owner_id:
            return await ctx.send(_("This is not a ticket channel"))
        
        # Check if user is support staff
        panel_name = conf["opened"][owner_id][str(ctx.channel.id)]["panel"]
        panel_roles = conf["panels"][panel_name]["roles"] if panel_name in conf["panels"] else []
        user_roles = [r.id for r in ctx.author.roles]
        
        support_roles = [i[0] for i in conf["support_roles"]]
        support_roles.extend([i[0] for i in panel_roles])
        
        is_staff = any(i in support_roles for i in user_roles)
        if not is_staff and ctx.author.id != ctx.guild.owner_id:
            if not await is_admin_or_superior(self.bot, ctx.author):
                return await ctx.send(_("Only support staff can view notes"))
        
        ticket_data = conf["opened"][owner_id][str(ctx.channel.id)]
        notes = ticket_data.get("notes", [])
        
        if not notes:
            return await ctx.send(_("No notes for this ticket"))
        
        embed = discord.Embed(
            title=_("📝 Ticket Notes"),
            color=ctx.author.color,
        )
        
        for i, note in enumerate(notes[-10:], 1):  # Last 10 notes
            staff_id = note.get("staff_id")
            staff = ctx.guild.get_member(staff_id) if staff_id else None
            staff_name = staff.display_name if staff else "Unknown"
            
            timestamp = note.get("timestamp", "Unknown")
            content = note.get("content", "")[:200]
            
            embed.add_field(
                name=f"#{i} - {staff_name}",
                value=f"{content}\n*{timestamp}*",
                inline=False,
            )
        
        await ctx.send(embed=embed, ephemeral=True if ctx.interaction else False)

    # ============================================================================
    # Quick Reply Command
    # ============================================================================

    @commands.hybrid_command(name="quickreply", aliases=["qr"], description="Send a quick reply template")
    @app_commands.describe(template_name="Name of the quick reply template (optional)")
    @commands.guild_only()
    async def quick_reply_cmd(self, ctx: commands.Context, template_name: Optional[str] = None):
        """
        Send a quick reply template in this ticket
        
        Use without arguments to see a dropdown of available templates
        """
        conf = await self.config.guild(ctx.guild).all()
        owner_id = get_ticket_owner(conf["opened"], str(ctx.channel.id))
        if not owner_id:
            return await ctx.send(_("This is not a ticket channel"))
        
        # Check if user is support staff
        panel_name = conf["opened"][owner_id][str(ctx.channel.id)]["panel"]
        panel_roles = conf["panels"][panel_name]["roles"] if panel_name in conf["panels"] else []
        user_roles = [r.id for r in ctx.author.roles]
        
        support_roles = [i[0] for i in conf["support_roles"]]
        support_roles.extend([i[0] for i in panel_roles])
        
        is_staff = any(i in support_roles for i in user_roles)
        if not is_staff and ctx.author.id != ctx.guild.owner_id:
            if not await is_admin_or_superior(self.bot, ctx.author):
                return await ctx.send(_("Only support staff can use quick replies"))
        
        templates = conf.get("quick_replies", {})
        if not templates:
            return await ctx.send(_("No quick reply templates configured"))
        
        if template_name:
            # Send specific template
            template_name = template_name.lower()
            if template_name not in templates:
                return await ctx.send(_("Template '{}' not found").format(template_name))
            
            template = templates[template_name]
            title = template.get("title", "")
            content = template.get("content", "")
            
            if title:
                embed = discord.Embed(
                    title=title,
                    description=content,
                    color=discord.Color.blue(),
                )
                await ctx.channel.send(embed=embed)
            else:
                await ctx.channel.send(content)
            
            if ctx.interaction:
                await ctx.interaction.response.send_message(_("Quick reply sent!"), ephemeral=True)
            else:
                # Delete the command message
                try:
                    await ctx.message.delete()
                except discord.HTTPException:
                    pass
            
            # Handle close_after
            if template.get("close_after"):
                delay = template.get("delay_close", 0)
                if delay > 0:
                    await asyncio.sleep(delay)
                
                owner = ctx.guild.get_member(int(owner_id))
                if not owner:
                    owner = await self.bot.fetch_user(int(owner_id))
                
                await close_ticket(
                    bot=self.bot,
                    member=owner,
                    guild=ctx.guild,
                    channel=ctx.channel,
                    conf=conf,
                    reason=f"Quick reply: {template_name}",
                    closedby=ctx.author.name,
                    config=self.config,
                )
        else:
            # Show dropdown
            view = QuickReplyView(templates, self.config, ctx.channel)
            await ctx.send(_("Select a quick reply:"), view=view, ephemeral=True)

    # ============================================================================
    # Ticket Info Command
    # ============================================================================

    @commands.hybrid_command(name="ticketinfo", description="View information about this ticket")
    @commands.guild_only()
    async def ticket_info(self, ctx: commands.Context):
        """View detailed information about this ticket"""
        conf = await self.config.guild(ctx.guild).all()
        owner_id = get_ticket_owner(conf["opened"], str(ctx.channel.id))
        if not owner_id:
            return await ctx.send(_("This is not a ticket channel"))
        
        ticket_data = conf["opened"][owner_id][str(ctx.channel.id)]
        
        owner = ctx.guild.get_member(int(owner_id))
        owner_name = owner.display_name if owner else f"Unknown ({owner_id})"
        
        embed = discord.Embed(
            title=_("🎫 Ticket Information"),
            color=ctx.author.color,
        )
        
        # Basic info
        embed.add_field(name=_("Owner"), value=owner.mention if owner else owner_name, inline=True)
        embed.add_field(name=_("Panel"), value=ticket_data.get("panel", "Unknown"), inline=True)
        
        # Status
        from ..common.constants import TICKET_STATUSES
        status = ticket_data.get("status", "open")
        status_emoji = TICKET_STATUSES.get(status, "❓")
        embed.add_field(name=_("Status"), value=f"{status_emoji} {status.replace('_', ' ').title()}", inline=True)
        
        # Claim info
        claimed_by = ticket_data.get("claimed_by")
        if claimed_by:
            claimer = ctx.guild.get_member(claimed_by)
            claimer_name = claimer.mention if claimer else f"Unknown ({claimed_by})"
            embed.add_field(name=_("Claimed By"), value=claimer_name, inline=True)
            
            claimed_at = ticket_data.get("claimed_at")
            if claimed_at:
                embed.add_field(name=_("Claimed At"), value=f"<t:{int(datetime.datetime.fromisoformat(claimed_at).timestamp())}:R>", inline=True)
        
        # Timestamps
        opened_at = ticket_data.get("opened")
        if opened_at:
            embed.add_field(
                name=_("Opened"),
                value=f"<t:{int(datetime.datetime.fromisoformat(opened_at).timestamp())}:R>",
                inline=True,
            )
        
        last_user = ticket_data.get("last_user_message")
        if last_user:
            embed.add_field(
                name=_("Last User Message"),
                value=f"<t:{int(datetime.datetime.fromisoformat(last_user).timestamp())}:R>",
                inline=True,
            )
        
        last_staff = ticket_data.get("last_staff_message")
        if last_staff:
            embed.add_field(
                name=_("Last Staff Message"),
                value=f"<t:{int(datetime.datetime.fromisoformat(last_staff).timestamp())}:R>",
                inline=True,
            )
        
        # Notes count
        notes = ticket_data.get("notes", [])
        if notes:
            embed.add_field(name=_("Notes"), value=str(len(notes)), inline=True)
        
        # Escalation
        if ticket_data.get("escalated"):
            embed.add_field(name=_("Escalated"), value="⚠️ Yes", inline=True)
        
        await ctx.send(embed=embed)