import asyncio
import json
import logging
import zipfile
from collections import defaultdict
from contextlib import suppress
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import quote  # IMPORTACIÓN PARA CODIFICAR LA URL

import chat_exporter
import discord
from discord.utils import escape_markdown
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list, pagify, text_to_file
from redbot.core.utils.mod import is_admin_or_superior

from .models import (
    AuditLogEntry,
    BlacklistEntry,
    PermissionChecker,
    PanelSchedule,
    TicketStats,
    TimeParser,
)
from .constants import SCHEMA_VERSION, TICKET_STATUSES

LOADING = "https://i.imgur.com/l3p6EMX.gif"
log = logging.getLogger("red.killerbite95.tickets.utils")
_ = Translator("Tickets", __file__)


# ============================================================================
# Schema Migration
# ============================================================================

async def migrate_schema(guild: discord.Guild, conf: dict, config: Config) -> dict:
    """
    Migrate configuration to the latest schema version.
    Returns the updated config.
    """
    current_version = conf.get("schema_version", 1)
    
    if current_version >= SCHEMA_VERSION:
        return conf
    
    log.info(f"Migrating schema for {guild.name} from v{current_version} to v{SCHEMA_VERSION}")
    
    async with config.guild(guild).all() as data:
        # Migration from v1 to v2
        if current_version < 2:
            # Initialize new fields
            if "blacklist_advanced" not in data:
                data["blacklist_advanced"] = {}
            if "ticket_cooldown" not in data:
                data["ticket_cooldown"] = 0
            if "global_rate_limit" not in data:
                data["global_rate_limit"] = 0
            if "min_account_age" not in data:
                data["min_account_age"] = 0
            if "min_server_age" not in data:
                data["min_server_age"] = 0
            if "auto_close_user_hours" not in data:
                data["auto_close_user_hours"] = data.get("inactive", 0)
            if "auto_close_staff_hours" not in data:
                data["auto_close_staff_hours"] = 0
            if "auto_close_warning_hours" not in data:
                data["auto_close_warning_hours"] = [24, 1]
            if "reopen_hours" not in data:
                data["reopen_hours"] = 0
            if "max_claims_per_staff" not in data:
                data["max_claims_per_staff"] = 0
            if "escalation_channel" not in data:
                data["escalation_channel"] = 0
            if "escalation_role" not in data:
                data["escalation_role"] = 0
            if "escalation_minutes" not in data:
                data["escalation_minutes"] = 0
            if "second_escalation_minutes" not in data:
                data["second_escalation_minutes"] = 0
            if "transcript_retention_days" not in data:
                data["transcript_retention_days"] = 0
            if "transcript_formats" not in data:
                data["transcript_formats"] = ["html"]
            if "quick_replies" not in data:
                data["quick_replies"] = {}
            if "audit_log_channel" not in data:
                data["audit_log_channel"] = 0
            if "stats" not in data:
                data["stats"] = {
                    "total_opened": 0,
                    "total_closed": 0,
                    "avg_claim_time": 0,
                    "avg_close_time": 0,
                }
            if "user_cooldowns" not in data:
                data["user_cooldowns"] = {}
            
            # Migrate existing tickets to new schema
            for uid, tickets in data.get("opened", {}).items():
                for cid, ticket in tickets.items():
                    if "status" not in ticket:
                        ticket["status"] = "open"
                    if "claimed_by" not in ticket:
                        ticket["claimed_by"] = None
                    if "claimed_at" not in ticket:
                        ticket["claimed_at"] = None
                    if "last_user_message" not in ticket:
                        ticket["last_user_message"] = ticket.get("opened")
                    if "last_staff_message" not in ticket:
                        ticket["last_staff_message"] = None
                    if "close_warnings_sent" not in ticket:
                        ticket["close_warnings_sent"] = []
                    if "escalated" not in ticket:
                        ticket["escalated"] = False
                    if "escalation_level" not in ticket:
                        ticket["escalation_level"] = 0
                    if "transferred_from" not in ticket:
                        ticket["transferred_from"] = None
                    if "notes" not in ticket:
                        ticket["notes"] = []
                    if "summary" not in ticket:
                        ticket["summary"] = None
            
            # Migrate panels
            for panel_name, panel in data.get("panels", {}).items():
                if "cooldown" not in panel:
                    panel["cooldown"] = 0
                if "rate_limit" not in panel:
                    panel["rate_limit"] = 0
                if "max_open" not in panel:
                    panel["max_open"] = 0
                if "schedule" not in panel:
                    panel["schedule"] = None
                if "welcome_sections" not in panel:
                    panel["welcome_sections"] = None
                if "fallback_mode" not in panel:
                    panel["fallback_mode"] = "none"
        
        data["schema_version"] = SCHEMA_VERSION
        return data


# ============================================================================
# Audit Logging
# ============================================================================

async def log_audit_action(
    guild: discord.Guild,
    config: Config,
    action: str,
    user: Union[discord.Member, discord.User],
    details: Optional[Dict[str, Any]] = None,
    target_user: Optional[Union[discord.Member, discord.User]] = None,
    ticket_channel: Optional[Union[discord.TextChannel, discord.Thread]] = None,
    panel_name: Optional[str] = None,
) -> None:
    """Log an action to the audit log channel if configured"""
    conf = await config.guild(guild).all()
    audit_channel_id = conf.get("audit_log_channel", 0)
    
    if not audit_channel_id:
        return
    
    audit_channel = guild.get_channel(audit_channel_id)
    if not audit_channel or not audit_channel.permissions_for(guild.me).send_messages:
        return
    
    entry = AuditLogEntry.create(
        action=action,
        user_id=user.id,
        details=details,
        target_user_id=target_user.id if target_user else None,
        ticket_channel_id=ticket_channel.id if ticket_channel else None,
        panel_name=panel_name,
    )
    
    # Format the embed
    action_emojis = {
        "ticket_open": "🎫",
        "ticket_close": "🔒",
        "ticket_reopen": "🔓",
        "ticket_rename": "✏️",
        "ticket_add_user": "➕",
        "ticket_remove_user": "➖",
        "ticket_claim": "🙋",
        "ticket_unclaim": "🚫",
        "ticket_transfer": "🔄",
        "ticket_escalate": "⚠️",
        "config_change": "⚙️",
        "blacklist_add": "🚷",
        "blacklist_remove": "✅",
        "note_add": "📝",
    }
    
    emoji = action_emojis.get(action, "📋")
    action_display = action.replace("_", " ").title()
    
    embed = discord.Embed(
        title=f"{emoji} {action_display}",
        color=discord.Color.blue(),
        timestamp=datetime.now(),
    )
    
    embed.add_field(name="User", value=f"{user.mention} ({user.id})", inline=True)
    
    if target_user:
        embed.add_field(name="Target", value=f"{target_user.mention} ({target_user.id})", inline=True)
    
    if ticket_channel:
        embed.add_field(name="Ticket", value=ticket_channel.mention, inline=True)
    
    if panel_name:
        embed.add_field(name="Panel", value=panel_name, inline=True)
    
    if details:
        details_str = "\n".join([f"**{k}:** {v}" for k, v in details.items()])
        if len(details_str) <= 1024:
            embed.add_field(name="Details", value=details_str, inline=False)
    
    try:
        await audit_channel.send(embed=embed)
    except discord.HTTPException:
        log.warning(f"Failed to send audit log to {guild.name}")


# ============================================================================
# Cooldown & Rate Limiting
# ============================================================================

async def check_cooldown(
    guild: discord.Guild,
    user: discord.Member,
    panel: dict,
    conf: dict,
    config: Config,
) -> Tuple[bool, Optional[int]]:
    """
    Check if user is on cooldown for opening tickets.
    Returns (can_open, seconds_remaining)
    """
    # Check panel-specific cooldown first, then global
    cooldown = panel.get("cooldown", 0) or conf.get("ticket_cooldown", 0)
    
    if not cooldown:
        return True, None
    
    user_cooldowns = conf.get("user_cooldowns", {})
    user_id = str(user.id)
    
    if user_id not in user_cooldowns:
        return True, None
    
    last_ticket = user_cooldowns.get(user_id)
    if not last_ticket:
        return True, None
    
    try:
        last_time = datetime.fromisoformat(last_ticket)
        elapsed = (datetime.now().astimezone() - last_time).total_seconds()
        
        if elapsed < cooldown:
            remaining = int(cooldown - elapsed)
            return False, remaining
        
        return True, None
    except (ValueError, TypeError):
        return True, None


async def update_user_cooldown(
    guild: discord.Guild,
    user: discord.Member,
    config: Config,
) -> None:
    """Update user's last ticket timestamp for cooldown tracking"""
    async with config.guild(guild).user_cooldowns() as cooldowns:
        cooldowns[str(user.id)] = datetime.now().astimezone().isoformat()


async def check_rate_limit(
    guild: discord.Guild,
    panel: dict,
    conf: dict,
) -> Tuple[bool, Optional[str]]:
    """
    Check if panel/global rate limit has been reached.
    Returns (can_open, error_message)
    """
    rate_limit = panel.get("rate_limit", 0) or conf.get("global_rate_limit", 0)
    
    if not rate_limit:
        return True, None
    
    # Count tickets opened in the last hour
    opened = conf.get("opened", {})
    one_hour_ago = datetime.now().astimezone() - timedelta(hours=1)
    panel_name = panel.get("name")
    
    count = 0
    for uid, tickets in opened.items():
        for cid, ticket in tickets.items():
            try:
                opened_time = datetime.fromisoformat(ticket.get("opened", ""))
                if opened_time > one_hour_ago:
                    if not panel_name or ticket.get("panel") == panel_name:
                        count += 1
            except (ValueError, TypeError):
                continue
    
    if count >= rate_limit:
        return False, _("Rate limit reached. Please try again later.")
    
    return True, None


async def check_panel_max_open(
    guild: discord.Guild,
    panel: dict,
    conf: dict,
) -> Tuple[bool, Optional[str]]:
    """
    Check if panel has reached max open tickets.
    Returns (can_open, error_message)
    """
    max_open = panel.get("max_open", 0)
    
    if not max_open:
        return True, None
    
    panel_name = panel.get("name")
    opened = conf.get("opened", {})
    
    count = 0
    for uid, tickets in opened.items():
        for cid, ticket in tickets.items():
            if ticket.get("panel") == panel_name:
                count += 1
    
    if count >= max_open:
        return False, _("This panel has reached its maximum open ticket limit.")
    
    return True, None


# ============================================================================
# Account/Server Age Gates
# ============================================================================

async def check_account_age(
    user: discord.Member,
    conf: dict,
) -> Tuple[bool, Optional[str]]:
    """Check if user's account meets minimum age requirement"""
    min_days = conf.get("min_account_age", 0)
    
    if not min_days:
        return True, None
    
    account_age = (datetime.now(user.created_at.tzinfo) - user.created_at).days
    
    if account_age < min_days:
        return False, _("Your account must be at least {} days old to open tickets.").format(min_days)
    
    return True, None


async def check_server_age(
    user: discord.Member,
    conf: dict,
) -> Tuple[bool, Optional[str]]:
    """Check if user has been in server long enough"""
    min_days = conf.get("min_server_age", 0)
    
    if not min_days or not user.joined_at:
        return True, None
    
    server_age = (datetime.now(user.joined_at.tzinfo) - user.joined_at).days
    
    if server_age < min_days:
        return False, _("You must be a member for at least {} days to open tickets.").format(min_days)
    
    return True, None


# ============================================================================
# Blacklist Functions
# ============================================================================

async def check_blacklist(
    user: discord.Member,
    conf: dict,
    config: Config,
    guild: discord.Guild,
) -> Tuple[bool, Optional[str]]:
    """
    Check if user or any of their roles is blacklisted.
    Returns (is_allowed, reason_if_blocked)
    Also cleans up expired blacklist entries.
    """
    user_roles = [r.id for r in user.roles]
    
    # Check simple blacklist (backward compatibility)
    simple_blacklist = conf.get("blacklist", [])
    if user.id in simple_blacklist:
        return False, _("You have been blacklisted from creating tickets.")
    
    for role_id in user_roles:
        if role_id in simple_blacklist:
            return False, _("You have a role that is blacklisted from creating tickets.")
    
    # Check advanced blacklist
    advanced_blacklist = conf.get("blacklist_advanced", {})
    expired_entries = []
    
    for id_str, entry_data in advanced_blacklist.items():
        entry = BlacklistEntry.from_dict(int(id_str), entry_data)
        
        if entry.is_expired:
            expired_entries.append(id_str)
            continue
        
        if entry.user_or_role_id == user.id:
            reason = entry.reason or _("No reason provided")
            return False, _("You have been blacklisted: {}").format(reason)
        
        if entry.user_or_role_id in user_roles:
            reason = entry.reason or _("No reason provided")
            return False, _("You have a blacklisted role: {}").format(reason)
    
    # Clean up expired entries
    if expired_entries:
        async with config.guild(guild).blacklist_advanced() as bl:
            for entry_id in expired_entries:
                if entry_id in bl:
                    del bl[entry_id]
    
    return True, None


async def add_to_blacklist(
    guild: discord.Guild,
    target: Union[discord.Member, discord.Role],
    config: Config,
    added_by: discord.Member,
    reason: Optional[str] = None,
    duration: Optional[timedelta] = None,
) -> BlacklistEntry:
    """Add a user or role to the advanced blacklist"""
    now = datetime.now().astimezone()
    expires_at = (now + duration).isoformat() if duration else None
    
    entry = BlacklistEntry(
        user_or_role_id=target.id,
        reason=reason,
        added_by=added_by.id,
        added_at=now.isoformat(),
        expires_at=expires_at,
    )
    
    async with config.guild(guild).blacklist_advanced() as bl:
        bl[str(target.id)] = entry.to_dict()
    
    # Log the action
    await log_audit_action(
        guild=guild,
        config=config,
        action="blacklist_add",
        user=added_by,
        target_user=target if isinstance(target, discord.Member) else None,
        details={
            "reason": reason,
            "duration": str(duration) if duration else "permanent",
            "target_type": "user" if isinstance(target, discord.Member) else "role",
        },
    )
    
    return entry


async def remove_from_blacklist(
    guild: discord.Guild,
    target: Union[discord.Member, discord.Role, int],
    config: Config,
    removed_by: discord.Member,
) -> bool:
    """Remove a user or role from the blacklist (both simple and advanced)"""
    target_id = target if isinstance(target, int) else target.id
    removed = False
    
    # Remove from simple blacklist
    async with config.guild(guild).blacklist() as bl:
        if target_id in bl:
            bl.remove(target_id)
            removed = True
    
    # Remove from advanced blacklist
    async with config.guild(guild).blacklist_advanced() as bl:
        if str(target_id) in bl:
            del bl[str(target_id)]
            removed = True
    
    if removed:
        await log_audit_action(
            guild=guild,
            config=config,
            action="blacklist_remove",
            user=removed_by,
            target_user=target if isinstance(target, discord.Member) else None,
            details={"target_id": target_id},
        )
    
    return removed


# ============================================================================
# Ticket Status & Claim Functions
# ============================================================================

async def claim_ticket(
    guild: discord.Guild,
    channel: Union[discord.TextChannel, discord.Thread],
    staff: discord.Member,
    config: Config,
    conf: dict,
) -> Tuple[bool, str]:
    """
    Claim a ticket for a staff member.
    Returns (success, message)
    """
    # Find the ticket
    ticket_data = None
    owner_id = None
    
    for uid, tickets in conf.get("opened", {}).items():
        if str(channel.id) in tickets:
            ticket_data = tickets[str(channel.id)]
            owner_id = uid
            break
    
    if not ticket_data:
        return False, _("This is not a ticket channel.")
    
    # Check if already claimed
    if ticket_data.get("claimed_by"):
        claimer = guild.get_member(ticket_data["claimed_by"])
        claimer_name = claimer.display_name if claimer else "Unknown"
        return False, _("This ticket is already claimed by {}.").format(claimer_name)
    
    # Check max claims per staff
    max_claims = conf.get("max_claims_per_staff", 0)
    if max_claims:
        staff_claims = 0
        for uid, tickets in conf.get("opened", {}).items():
            for cid, ticket in tickets.items():
                if ticket.get("claimed_by") == staff.id:
                    staff_claims += 1
        
        if staff_claims >= max_claims:
            return False, _("You have reached your maximum claim limit of {} tickets.").format(max_claims)
    
    # Claim the ticket
    now = datetime.now().astimezone()
    
    async with config.guild(guild).opened() as opened:
        if owner_id in opened and str(channel.id) in opened[owner_id]:
            opened[owner_id][str(channel.id)]["claimed_by"] = staff.id
            opened[owner_id][str(channel.id)]["claimed_at"] = now.isoformat()
            opened[owner_id][str(channel.id)]["status"] = "claimed"
    
    # Calculate claim time for stats
    try:
        opened_at = datetime.fromisoformat(ticket_data["opened"])
        claim_time = (now - opened_at).total_seconds()
        await update_stats_claim_time(guild, config, claim_time)
    except (ValueError, TypeError):
        pass
    
    # Log the action
    await log_audit_action(
        guild=guild,
        config=config,
        action="ticket_claim",
        user=staff,
        ticket_channel=channel,
        panel_name=ticket_data.get("panel"),
    )
    
    return True, _("Ticket claimed successfully!")


async def unclaim_ticket(
    guild: discord.Guild,
    channel: Union[discord.TextChannel, discord.Thread],
    staff: discord.Member,
    config: Config,
    conf: dict,
) -> Tuple[bool, str]:
    """
    Unclaim a ticket.
    Returns (success, message)
    """
    ticket_data = None
    owner_id = None
    
    for uid, tickets in conf.get("opened", {}).items():
        if str(channel.id) in tickets:
            ticket_data = tickets[str(channel.id)]
            owner_id = uid
            break
    
    if not ticket_data:
        return False, _("This is not a ticket channel.")
    
    if not ticket_data.get("claimed_by"):
        return False, _("This ticket is not claimed.")
    
    if ticket_data["claimed_by"] != staff.id:
        # Check if user is admin
        if not await is_admin_or_superior(None, staff):
            return False, _("You can only unclaim tickets you have claimed.")
    
    async with config.guild(guild).opened() as opened:
        if owner_id in opened and str(channel.id) in opened[owner_id]:
            opened[owner_id][str(channel.id)]["claimed_by"] = None
            opened[owner_id][str(channel.id)]["claimed_at"] = None
            opened[owner_id][str(channel.id)]["status"] = "open"
    
    await log_audit_action(
        guild=guild,
        config=config,
        action="ticket_unclaim",
        user=staff,
        ticket_channel=channel,
        panel_name=ticket_data.get("panel"),
    )
    
    return True, _("Ticket unclaimed successfully!")


async def transfer_ticket(
    guild: discord.Guild,
    channel: Union[discord.TextChannel, discord.Thread],
    from_staff: discord.Member,
    to_staff: discord.Member,
    config: Config,
    conf: dict,
) -> Tuple[bool, str]:
    """
    Transfer a ticket from one staff member to another.
    Returns (success, message)
    """
    ticket_data = None
    owner_id = None
    
    for uid, tickets in conf.get("opened", {}).items():
        if str(channel.id) in tickets:
            ticket_data = tickets[str(channel.id)]
            owner_id = uid
            break
    
    if not ticket_data:
        return False, _("This is not a ticket channel.")
    
    current_claimer = ticket_data.get("claimed_by")
    if current_claimer and current_claimer != from_staff.id:
        if not await is_admin_or_superior(None, from_staff):
            return False, _("You can only transfer tickets you have claimed.")
    
    now = datetime.now().astimezone()
    
    async with config.guild(guild).opened() as opened:
        if owner_id in opened and str(channel.id) in opened[owner_id]:
            opened[owner_id][str(channel.id)]["transferred_from"] = current_claimer
            opened[owner_id][str(channel.id)]["claimed_by"] = to_staff.id
            opened[owner_id][str(channel.id)]["claimed_at"] = now.isoformat()
            opened[owner_id][str(channel.id)]["status"] = "claimed"
    
    await log_audit_action(
        guild=guild,
        config=config,
        action="ticket_transfer",
        user=from_staff,
        target_user=to_staff,
        ticket_channel=channel,
        panel_name=ticket_data.get("panel"),
        details={"from": from_staff.id, "to": to_staff.id},
    )
    
    return True, _("Ticket transferred to {}.").format(to_staff.display_name)


async def update_ticket_status(
    guild: discord.Guild,
    channel_id: str,
    owner_id: str,
    status: str,
    config: Config,
) -> None:
    """Update a ticket's status"""
    async with config.guild(guild).opened() as opened:
        if owner_id in opened and channel_id in opened[owner_id]:
            opened[owner_id][channel_id]["status"] = status


async def update_last_message(
    guild: discord.Guild,
    channel_id: str,
    owner_id: str,
    is_staff: bool,
    config: Config,
) -> None:
    """Update the last message timestamp for a ticket"""
    now = datetime.now().astimezone().isoformat()
    field = "last_staff_message" if is_staff else "last_user_message"
    
    async with config.guild(guild).opened() as opened:
        if owner_id in opened and channel_id in opened[owner_id]:
            opened[owner_id][channel_id][field] = now
            # Update status based on who sent the message
            if is_staff:
                opened[owner_id][channel_id]["status"] = "awaiting_user"
            else:
                if opened[owner_id][channel_id].get("claimed_by"):
                    opened[owner_id][channel_id]["status"] = "awaiting_staff"


# ============================================================================
# Stats Functions
# ============================================================================

async def update_stats_claim_time(
    guild: discord.Guild,
    config: Config,
    claim_time_seconds: float,
) -> None:
    """Update average claim time statistic"""
    async with config.guild(guild).stats() as stats:
        total = stats.get("total_opened", 0)
        if total == 0:
            stats["avg_claim_time"] = claim_time_seconds
        else:
            current_avg = stats.get("avg_claim_time", 0)
            stats["avg_claim_time"] = (current_avg * (total - 1) + claim_time_seconds) / total


async def update_stats_close_time(
    guild: discord.Guild,
    config: Config,
    close_time_seconds: float,
) -> None:
    """Update average close time statistic"""
    async with config.guild(guild).stats() as stats:
        total = stats.get("total_closed", 0)
        stats["total_closed"] = total + 1
        if total == 0:
            stats["avg_close_time"] = close_time_seconds
        else:
            current_avg = stats.get("avg_close_time", 0)
            stats["avg_close_time"] = (current_avg * total + close_time_seconds) / (total + 1)


async def increment_stats_opened(
    guild: discord.Guild,
    config: Config,
) -> None:
    """Increment total opened tickets stat"""
    async with config.guild(guild).stats() as stats:
        stats["total_opened"] = stats.get("total_opened", 0) + 1


# ============================================================================
# Escalation Functions
# ============================================================================

async def escalate_ticket(
    guild: discord.Guild,
    channel: Union[discord.TextChannel, discord.Thread],
    ticket_data: dict,
    owner_id: str,
    config: Config,
    conf: dict,
    level: int = 1,
) -> None:
    """Escalate an unclaimed ticket"""
    escalation_channel_id = conf.get("escalation_channel", 0)
    escalation_role_id = conf.get("escalation_role", 0)
    panel_name = ticket_data.get("panel")
    
    # Update ticket escalation status
    async with config.guild(guild).opened() as opened:
        if owner_id in opened and str(channel.id) in opened[owner_id]:
            opened[owner_id][str(channel.id)]["escalated"] = True
            opened[owner_id][str(channel.id)]["escalation_level"] = level
    
    # Build notification message
    role_mention = ""
    if escalation_role_id:
        role = guild.get_role(escalation_role_id)
        if role:
            role_mention = role.mention
    
    escalation_msg = _("⚠️ **Ticket Escalation (Level {})**\n").format(level)
    escalation_msg += _("Ticket {} has been unclaimed for too long!\n").format(channel.mention)
    escalation_msg += _("Panel: {}\n").format(panel_name)
    escalation_msg += _("Please claim and assist the user.")
    
    if role_mention:
        escalation_msg = f"{role_mention}\n{escalation_msg}"
    
    # Send to escalation channel or ticket channel
    if escalation_channel_id:
        esc_channel = guild.get_channel(escalation_channel_id)
        if esc_channel and esc_channel.permissions_for(guild.me).send_messages:
            await esc_channel.send(escalation_msg, allowed_mentions=discord.AllowedMentions(roles=True))
    else:
        await channel.send(escalation_msg, allowed_mentions=discord.AllowedMentions(roles=True))
    
    await log_audit_action(
        guild=guild,
        config=config,
        action="ticket_escalate",
        user=guild.me,
        ticket_channel=channel,
        panel_name=panel_name,
        details={"level": level},
    )


# ============================================================================
# Ticket Notes
# ============================================================================

async def add_ticket_note(
    guild: discord.Guild,
    channel: Union[discord.TextChannel, discord.Thread],
    author: discord.Member,
    content: str,
    config: Config,
    conf: dict,
) -> Tuple[bool, str]:
    """Add an internal staff note to a ticket"""
    owner_id = None
    
    for uid, tickets in conf.get("opened", {}).items():
        if str(channel.id) in tickets:
            owner_id = uid
            break
    
    if not owner_id:
        return False, _("This is not a ticket channel.")
    
    note = {
        "author_id": author.id,
        "content": content,
        "timestamp": datetime.now().astimezone().isoformat(),
    }
    
    async with config.guild(guild).opened() as opened:
        if owner_id in opened and str(channel.id) in opened[owner_id]:
            if "notes" not in opened[owner_id][str(channel.id)]:
                opened[owner_id][str(channel.id)]["notes"] = []
            opened[owner_id][str(channel.id)]["notes"].append(note)
    
    await log_audit_action(
        guild=guild,
        config=config,
        action="note_add",
        user=author,
        ticket_channel=channel,
    )
    
    return True, _("Note added successfully!")


# ============================================================================
# Export/Import Config
# ============================================================================

async def export_config(
    guild: discord.Guild,
    config: Config,
) -> dict:
    """Export guild configuration for backup"""
    conf = await config.guild(guild).all()
    
    # Remove transient data
    export_data = conf.copy()
    export_data.pop("opened", None)  # Don't export open tickets
    export_data.pop("user_cooldowns", None)
    export_data.pop("overview_msg", None)
    
    return {
        "version": SCHEMA_VERSION,
        "guild_id": guild.id,
        "guild_name": guild.name,
        "exported_at": datetime.now().astimezone().isoformat(),
        "config": export_data,
    }


async def import_config(
    guild: discord.Guild,
    config: Config,
    import_data: dict,
) -> Tuple[bool, str]:
    """Import guild configuration from backup"""
    if "config" not in import_data:
        return False, _("Invalid import data format.")
    
    conf_data = import_data["config"]
    
    # Validate version
    if import_data.get("version", 1) > SCHEMA_VERSION:
        return False, _("Import data is from a newer version. Please update the cog first.")
    
    try:
        async with config.guild(guild).all() as current:
            # Preserve certain fields
            preserve_fields = ["opened", "user_cooldowns", "overview_msg", "overview_channel"]
            preserved = {k: current.get(k) for k in preserve_fields}
            
            # Update with imported data
            current.update(conf_data)
            
            # Restore preserved fields
            for k, v in preserved.items():
                if v is not None:
                    current[k] = v
        
        return True, _("Configuration imported successfully!")
    except Exception as e:
        log.error(f"Failed to import config for {guild.name}", exc_info=e)
        return False, _("Failed to import configuration: {}").format(str(e))


# ============================================================================
# Original Utility Functions (Updated)
# ============================================================================


async def can_close(
    bot: Red,
    guild: discord.Guild,
    channel: Union[discord.TextChannel, discord.Thread],
    author: discord.Member,
    owner_id: int,
    conf: dict,
):
    if str(owner_id) not in conf["opened"]:
        return False
    if str(channel.id) not in conf["opened"][str(owner_id)]:
        return False

    panel_name = conf["opened"][str(owner_id)][str(channel.id)]["panel"]
    panel_roles = conf["panels"][panel_name]["roles"]
    user_roles = [r.id for r in author.roles]

    support_roles = [i[0] for i in conf["support_roles"]]
    support_roles.extend([i[0] for i in panel_roles])

    can_close_flag = False
    if any(i in support_roles for i in user_roles):
        can_close_flag = True
    elif author.id == guild.owner_id:
        can_close_flag = True
    elif await is_admin_or_superior(bot, author):
        can_close_flag = True
    elif str(owner_id) == str(author.id) and conf["user_can_close"]:
        can_close_flag = True
    return can_close_flag


async def fetch_channel_history(channel: discord.TextChannel, limit: int | None = None) -> List[discord.Message]:
    history = []
    async for msg in channel.history(oldest_first=True, limit=limit):
        history.append(msg)
    return history


async def ticket_owner_hastyped(channel: discord.TextChannel, user: discord.Member) -> bool:
    async for msg in channel.history(limit=50, oldest_first=True):
        if msg.author.id == user.id:
            return True
    return False


def get_ticket_owner(opened: dict, channel_id: str) -> Optional[str]:
    for uid, tickets in opened.items():
        if channel_id in tickets:
            return uid


async def close_ticket(
    bot: Red,
    member: Union[discord.Member, discord.User],
    guild: discord.Guild,
    channel: Union[discord.TextChannel, discord.Thread],
    conf: dict,
    reason: str | None,
    closedby: str,
    config: Config,
) -> None:
    opened = conf["opened"]
    if not opened:
        return
    uid = str(member.id)
    cid = str(channel.id)
    if uid not in opened:
        return
    if cid not in opened[uid]:
        return

    ticket = opened[uid][cid]
    pfp = ticket["pfp"]
    panel_name = ticket["panel"]
    panel = conf["panels"][panel_name]
    panel.get("threads")

    if not channel.permissions_for(guild.me).manage_channels and isinstance(channel, discord.TextChannel):
        await channel.send(_("I am missing the `Manage Channels` permission to close this ticket!"))
        return
    if not channel.permissions_for(guild.me).manage_threads and isinstance(channel, discord.Thread):
        await channel.send(_("I am missing the `Manage Threads` permission to close this ticket!"))
        return

    opened_ts = int(datetime.fromisoformat(ticket["opened"]).timestamp())
    closed_ts = int(datetime.now().timestamp())
    closer_name = escape_markdown(closedby)

    desc = _(
        "Ticket created by **{}-{}** has been closed.\n"
        "`PanelType: `{}\n"
        "`Opened on: `<t:{}:F>\n"
        "`Closed on: `<t:{}:F>\n"
        "`Closed by: `{}\n"
        "`Reason:    `{}\n"
    ).format(
        member.name,
        member.id,
        panel_name,
        opened_ts,
        closed_ts,
        closer_name,
        str(reason),
    )
    if isinstance(channel, discord.Thread) and conf["thread_close"]:
        desc += _("`Thread:    `{}\n").format(channel.mention)

    backup_text = _("Ticket Closed\n{}\nCurrently missing permissions to send embeds to this channel!").format(desc)
    embed_title = _("Ticket Closed")
    embed = discord.Embed(
        title=embed_title,
        description=desc,
        color=discord.Color.green(),
    )
    embed.set_thumbnail(url=pfp)
    log_chan = guild.get_channel(panel["log_channel"]) if panel["log_channel"] else None

    text = ""
    files: List[dict] = []
    filename = (
        f"{member.name}-{member.id}.html" if conf.get("detailed_transcript") else f"{member.name}-{member.id}.txt"
    )
    filename = filename.replace("/", "")

    # Prep embed in case we're exporting a transcript
    em = discord.Embed(color=member.color)
    em.set_author(name=_("Archiving Ticket..."), icon_url=LOADING)

    use_exporter = conf.get("detailed_transcript", False)
    is_thread = isinstance(channel, discord.Thread)
    exporter_success = False

    if conf["transcript"]:
        temp_message = await channel.send(embed=em)

        if use_exporter:
            try:
                text = await chat_exporter.export(
                    channel=channel,
                    limit=None,
                    tz_info="UTC",
                    guild=guild,
                    bot=bot,
                    military_time=True,
                    fancy_times=True,
                    support_dev=False,
                )
                exporter_success = True
            except AttributeError:
                pass

        answers = ticket.get("answers")
        if answers and not use_exporter:
            for q, a in answers.items():
                text += _("Question: {}\nResponse: {}\n").format(q, a)

        history = await fetch_channel_history(channel)
        filenames = defaultdict(int)
        for msg in history:
            if msg.author.bot:
                continue
            if not msg:
                continue

            att = []
            for i in msg.attachments:
                att.append(i.filename)
                if i.size < guild.filesize_limit and (not is_thread or conf["thread_close"]):
                    filenames[i.filename] += 1
                    if filenames[i.filename] > 1:
                        # Increment filename count to avoid overwriting
                        p = Path(i.filename)
                        i.filename = f"{p.stem}_{filenames[i.filename]}{p.suffix}"
                    files.append({"filename": i.filename, "content": await i.read()})

            if not use_exporter:
                if msg.content:
                    text += f"{msg.author.name}: {msg.content}\n"
                if att:
                    text += _("Files uploaded: ") + humanize_list(att) + "\n"

        with suppress(discord.HTTPException):
            await temp_message.delete()

    else:
        history = await fetch_channel_history(channel, limit=1)

    def zip_files():
        if files:
            # Create a zip archive in memory
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zip_file:
                for file_dict in files:
                    zip_file.writestr(
                        file_dict["filename"],
                        file_dict["content"],
                        compress_type=zipfile.ZIP_DEFLATED,
                        compresslevel=9,
                    )
            zip_buffer.seek(0)
            return zip_buffer.getvalue()

    zip_bytes = await asyncio.to_thread(zip_files)

    # Send off new messages
    view = None
    if history and is_thread and conf["thread_close"]:
        jump_url = history[0].jump_url
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label="View Thread",
                style=discord.ButtonStyle.link,
                url=jump_url,
            )
        )

    view_label = _("View Transcript")

    if log_chan and ticket["logmsg"]:
        text_file = text_to_file(text, filename) if text else None
        zip_file = discord.File(BytesIO(zip_bytes), filename="attachments.zip") if zip_bytes else None

        perms = [
            log_chan.permissions_for(guild.me).embed_links,
            log_chan.permissions_for(guild.me).attach_files,
        ]

        attachments = []
        text_file_size = 0
        if text_file:
            text_file_size = text_file.__sizeof__()
            attachments.append(text_file)
        if zip_file and ((zip_file.__sizeof__() + text_file_size) < guild.filesize_limit):
            attachments.append(zip_file)

        log_msg: discord.Message = None
        try:
            if all(perms):
                log_msg = await log_chan.send(embed=embed, files=attachments or None, view=view)
            elif perms[0]:
                log_msg = await log_chan.send(embed=embed, view=view)
            elif perms[1]:
                log_msg = await log_chan.send(backup_text, files=attachments or None, view=view)
        except discord.HTTPException as e:
            if "Payload Too Large" in str(e) or "Request entity too large" in str(e):
                text_file = text_to_file(text, filename) if text else None
                zip_file = discord.File(BytesIO(zip_bytes), filename="attachments.zip") if zip_bytes else None
                attachments = []
                text_file_size = 0
                if text_file:
                    text_file_size = text_file.__sizeof__()
                    attachments.append(text_file)
                if zip_file and ((zip_file.__sizeof__() + text_file_size) < guild.filesize_limit):
                    attachments.append(zip_file)

                # Pop last element and try again
                if text_file:
                    attachments.pop(-1)
                else:
                    attachments = None
                if all(perms):
                    log_msg = await log_chan.send(embed=embed, files=attachments or None, view=view)
                elif perms[0]:
                    log_msg = await log_chan.send(embed=embed, view=view)
                elif perms[1]:
                    log_msg = await log_chan.send(backup_text, files=attachments or None, view=view)
            else:
                raise

        if log_msg and exporter_success:
            # Codificar la URL del attachment antes de construir la URL final
            encoded_attachment_url = quote(log_msg.attachments[0].url, safe='')
            url = f"https://ticketview.alienhost.ovh/index.php?url={encoded_attachment_url}"
            view = discord.ui.View()
            view.add_item(discord.ui.Button(label=view_label, style=discord.ButtonStyle.link, url=url))
            await log_msg.edit(view=view)

        # Delete old log msg
        log_msg_id = ticket["logmsg"]
        try:
            log_msg = await log_chan.fetch_message(log_msg_id)
        except discord.HTTPException:
            log.warning("Failed to get log channel message")
            log_msg = None
        if log_msg:
            try:
                await log_msg.delete()
            except Exception as e:
                log.warning(f"Failed to auto-delete log message: {e}")

    if conf["dm"]:
        try:
            if text:
                text_file = text_to_file(text, filename) if text else None
                dm_msg = await member.send(embed=embed, file=text_file)
                # Codificar la URL del attachment del mensaje directo
                encoded_attachment_url = quote(dm_msg.attachments[0].url, safe='')
                url = f"https://ticketview.alienhost.ovh/index.php?url={encoded_attachment_url}"
                view = discord.ui.View()
                view.add_item(discord.ui.Button(label=view_label, style=discord.ButtonStyle.link, url=url))
                await dm_msg.edit(view=view)
            else:
                await member.send(embed=embed)

        except discord.Forbidden:
            pass

    # Delete/close ticket channel
    if is_thread and conf["thread_close"]:
        try:
            await channel.edit(archived=True, locked=True)
        except Exception as e:
            log.error("Failed to archive thread ticket", exc_info=e)
    else:
        try:
            await channel.delete()
        except discord.DiscordServerError:
            await asyncio.sleep(3)
            try:
                await channel.delete()
            except Exception as e:
                log.error("Failed to delete ticket channel", exc_info=e)

    # Calculate close time for stats
    try:
        opened_at = datetime.fromisoformat(ticket["opened"])
        close_time = (datetime.now().astimezone() - opened_at).total_seconds()
        await update_stats_close_time(guild, config, close_time)
    except (ValueError, TypeError):
        pass

    async with config.guild(guild).all() as conf:
        tickets = conf["opened"]
        if uid not in tickets:
            return
        if cid not in tickets[uid]:
            return
        del tickets[uid][cid]
        # If user has no more tickets, clean up their key from the config
        if not tickets[uid]:
            del tickets[uid]

        new_id = await update_active_overview(guild, conf)
        if new_id:
            conf["overview_msg"] = new_id

    # Log the close action
    await log_audit_action(
        guild=guild,
        config=config,
        action="ticket_close",
        user=guild.get_member(int(closedby)) if closedby.isdigit() else guild.me,
        target_user=member,
        ticket_channel=channel,
        panel_name=panel_name,
        details={"reason": reason},
    )


async def prune_invalid_tickets(
    guild: discord.Guild,
    conf: dict,
    config: Config,
    ctx: Optional[commands.Context] = None,
) -> bool:
    opened_tickets = conf["opened"]
    if not opened_tickets:
        if ctx:
            await ctx.send(_("There are no tickets stored in the database."))
        return False

    users_to_remove = []
    tickets_to_remove = []
    count = 0
    for user_id, tickets in opened_tickets.items():
        member = guild.get_member(int(user_id))
        if not member:
            count += len(list(tickets.keys()))
            users_to_remove.append(user_id)
            log.info(f"Cleaning up user {user_id}'s tickets for leaving")
            continue

        if not tickets:
            count += 1
            users_to_remove.append(user_id)
            log.info(f"Cleaning member {member} for having no tickets opened")
            continue

        for channel_id, ticket in tickets.items():
            if guild.get_channel_or_thread(int(channel_id)):
                continue

            count += 1
            log.info(f"Ticket channel {channel_id} no longer exists for {member}")
            tickets_to_remove.append((user_id, channel_id))

            panel = conf["panels"].get(ticket["panel"])
            if not panel:
                # Panel has been deleted
                continue
            log_message_id = ticket["logmsg"]
            log_channel_id = panel["log_channel"]
            if log_channel_id and log_message_id:
                log_channel = guild.get_channel(log_channel_id)
                try:
                    log_message = await log_channel.fetch_message(log_message_id)
                    await log_message.delete()
                except (discord.NotFound, discord.Forbidden):
                    pass

    if users_to_remove or tickets_to_remove:
        async with config.guild(guild).opened() as opened:
            for uid in users_to_remove:
                del opened[uid]
            for uid, cid in tickets_to_remove:
                if uid not in opened:
                    continue
                if cid not in opened[uid]:
                    continue
                del opened[uid][cid]

    grammar = _("ticket") if count == 1 else _("tickets")
    if count and ctx:
        txt = _("Pruned `{}` invalid {}").format(count, grammar)
        await ctx.send(txt)
    elif not count and ctx:
        await ctx.send(_("There are no tickets to prune"))
    elif count and not ctx:
        log.info(f"{count} {grammar} pruned from {guild.name}")

    return True if count else False


def prep_overview_text(
    guild: discord.Guild,
    opened: dict,
    mention: bool = False,
    filter_panel: Optional[str] = None,
    filter_status: Optional[str] = None,
    filter_staff: Optional[int] = None,
) -> str:
    """
    Prepare overview text with optional filters.
    """
    active = []
    for uid, opened_tickets in opened.items():
        member = guild.get_member(int(uid))
        if not member:
            continue
        for ticket_channel_id, ticket_info in opened_tickets.items():
            # Apply filters
            if filter_panel and ticket_info.get("panel") != filter_panel:
                continue
            if filter_status and ticket_info.get("status", "open") != filter_status:
                continue
            if filter_staff and ticket_info.get("claimed_by") != filter_staff:
                continue
            
            channel = guild.get_channel_or_thread(int(ticket_channel_id))
            if not channel:
                continue

            open_time_obj = datetime.fromisoformat(ticket_info["opened"])
            panel_name = ticket_info["panel"]
            status = ticket_info.get("status", "open")
            status_emoji = TICKET_STATUSES.get(status, "").split()[0] if status in TICKET_STATUSES else "🔘"
            claimed_by = ticket_info.get("claimed_by")

            entry = {
                "channel": channel.mention if mention else channel.name,
                "panel": panel_name,
                "timestamp": int(open_time_obj.timestamp()),
                "username": member.name,
                "status": status,
                "status_emoji": status_emoji,
                "claimed_by": claimed_by,
            }
            active.append(entry)

    if not active:
        return _("There are no active tickets.")

    sorted_active = sorted(active, key=lambda x: x["timestamp"])

    desc = ""
    for index, entry in enumerate(sorted_active):
        claimer_text = ""
        if entry["claimed_by"]:
            claimer = guild.get_member(entry["claimed_by"])
            claimer_text = f" 👤 {claimer.display_name if claimer else 'Unknown'}"
        
        desc += (
            f"{index + 1}. {entry['status_emoji']} {entry['channel']} "
            f"({entry['panel']}) <t:{entry['timestamp']}:R> - {entry['username']}{claimer_text}\n"
        )
    return desc


def prep_overview_text_paginated(
    guild: discord.Guild,
    opened: dict,
    mention: bool = False,
    page: int = 0,
    per_page: int = 10,
    filter_panel: Optional[str] = None,
    filter_status: Optional[str] = None,
    filter_staff: Optional[int] = None,
) -> Tuple[str, int, int]:
    """
    Prepare paginated overview text.
    Returns (text, current_page, total_pages)
    """
    active = []
    for uid, opened_tickets in opened.items():
        member = guild.get_member(int(uid))
        if not member:
            continue
        for ticket_channel_id, ticket_info in opened_tickets.items():
            # Apply filters
            if filter_panel and ticket_info.get("panel") != filter_panel:
                continue
            if filter_status and ticket_info.get("status", "open") != filter_status:
                continue
            if filter_staff and ticket_info.get("claimed_by") != filter_staff:
                continue
            
            channel = guild.get_channel_or_thread(int(ticket_channel_id))
            if not channel:
                continue

            open_time_obj = datetime.fromisoformat(ticket_info["opened"])
            panel_name = ticket_info["panel"]
            status = ticket_info.get("status", "open")
            status_emoji = TICKET_STATUSES.get(status, "").split()[0] if status in TICKET_STATUSES else "🔘"
            claimed_by = ticket_info.get("claimed_by")

            entry = {
                "channel": channel.mention if mention else channel.name,
                "channel_id": ticket_channel_id,
                "panel": panel_name,
                "timestamp": int(open_time_obj.timestamp()),
                "username": member.name,
                "user_id": uid,
                "status": status,
                "status_emoji": status_emoji,
                "claimed_by": claimed_by,
            }
            active.append(entry)

    if not active:
        return _("There are no active tickets."), 0, 0

    sorted_active = sorted(active, key=lambda x: x["timestamp"])
    total_pages = (len(sorted_active) + per_page - 1) // per_page
    page = max(0, min(page, total_pages - 1))
    
    start_idx = page * per_page
    end_idx = start_idx + per_page
    page_entries = sorted_active[start_idx:end_idx]

    desc = ""
    for index, entry in enumerate(page_entries, start=start_idx + 1):
        claimer_text = ""
        if entry["claimed_by"]:
            claimer = guild.get_member(entry["claimed_by"])
            claimer_text = f" 👤 {claimer.display_name if claimer else 'Unknown'}"
        
        desc += (
            f"{index}. {entry['status_emoji']} {entry['channel']} "
            f"({entry['panel']}) <t:{entry['timestamp']}:R> - {entry['username']}{claimer_text}\n"
        )
    
    return desc, page, total_pages


def get_overview_stats(guild: discord.Guild, opened: dict, conf: dict) -> Dict[str, Any]:
    """Get KPI statistics for the overview"""
    stats = conf.get("stats", {})
    
    # Count tickets by status
    status_counts = defaultdict(int)
    panel_counts = defaultdict(int)
    staff_counts = defaultdict(int)
    
    for uid, tickets in opened.items():
        for cid, ticket in tickets.items():
            status = ticket.get("status", "open")
            panel = ticket.get("panel", "unknown")
            claimed_by = ticket.get("claimed_by")
            
            status_counts[status] += 1
            panel_counts[panel] += 1
            if claimed_by:
                staff_counts[claimed_by] += 1
    
    avg_claim = stats.get("avg_claim_time", 0)
    avg_close = stats.get("avg_close_time", 0)
    
    return {
        "total_open": sum(status_counts.values()),
        "by_status": dict(status_counts),
        "by_panel": dict(panel_counts),
        "by_staff": dict(staff_counts),
        "avg_claim_time": TimeParser.format_duration(avg_claim) if avg_claim else "N/A",
        "avg_close_time": TimeParser.format_duration(avg_close) if avg_close else "N/A",
        "total_opened_all_time": stats.get("total_opened", 0),
        "total_closed_all_time": stats.get("total_closed", 0),
    }


async def update_active_overview(guild: discord.Guild, conf: dict) -> Optional[int]:
    """Update active ticket overview

    Args:
        guild (discord.Guild): discord server
        conf (dict): settings for the guild

    Returns:
        int: Message ID of the overview panel
    """
    if not conf["overview_channel"]:
        return
    channel: discord.TextChannel = guild.get_channel(conf["overview_channel"])
    if not channel:
        return
    if not channel.permissions_for(guild.me).send_messages:
        return

    txt = prep_overview_text(guild, conf["opened"], conf.get("overview_mention", False))
    title = _("Ticket Overview")
    embeds = []
    attachments = []
    if len(txt) < 4000:
        embed = discord.Embed(
            title=title,
            description=txt,
            color=discord.Color.greyple(),
            timestamp=datetime.now(),
        )
        embeds.append(embed)
    elif len(txt) < 5500:
        for p in pagify(txt, page_length=3900):
            embed = discord.Embed(
                title=title,
                description=p,
                color=discord.Color.greyple(),
                timestamp=datetime.now(),
            )
            embeds.append(embed)
    else:
        embed = discord.Embed(
            title=title,
            description=_("Too many active tickets to include in message!"),
            color=discord.Color.red(),
            timestamp=datetime.now(),
        )
        embeds.append(embed)
        filename = _("Active Tickets") + ".txt"
        file = text_to_file(txt, filename=filename)
        attachments = [file]

    message = None
    if msg_id := conf["overview_msg"]:
        try:
            message = await channel.fetch_message(msg_id)
        except (discord.NotFound, discord.HTTPException):
            pass

    if message:
        try:
            await message.edit(content=None, embeds=embeds, attachments=attachments)
        except discord.Forbidden:
            message = await channel.send(embeds=embeds, files=attachments)
            return message.id
    else:
        try:
            message = await channel.send(embeds=embeds, files=attachments)
            return message.id
        except discord.Forbidden:
            message = await channel.send(_("Failed to send overview message due to missing permissions"))


# ============================================================================
# Smart Auto-Close Functions
# ============================================================================

async def check_auto_close_warnings(
    guild: discord.Guild,
    channel: Union[discord.TextChannel, discord.Thread],
    ticket: dict,
    owner_id: str,
    conf: dict,
    config: Config,
) -> Optional[str]:
    """
    Check if auto-close warnings should be sent.
    Returns the warning type if a warning was sent, None otherwise.
    """
    warning_hours = conf.get("auto_close_warning_hours", [24, 1])
    user_hours = conf.get("auto_close_user_hours", 0)
    staff_hours = conf.get("auto_close_staff_hours", 0)
    
    now = datetime.now().astimezone()
    warnings_sent = ticket.get("close_warnings_sent", [])
    
    # Determine which inactivity type to check
    status = ticket.get("status", "open")
    
    if status in ["open", "awaiting_staff"]:
        # Check staff inactivity
        if not staff_hours:
            return None
        last_activity = ticket.get("last_staff_message") or ticket.get("opened")
        inactive_hours = staff_hours
        inactivity_type = "staff"
    else:
        # Check user inactivity
        if not user_hours:
            return None
        last_activity = ticket.get("last_user_message") or ticket.get("opened")
        inactive_hours = user_hours
        inactivity_type = "user"
    
    try:
        last_time = datetime.fromisoformat(last_activity)
    except (ValueError, TypeError):
        return None
    
    hours_inactive = (now - last_time).total_seconds() / 3600
    
    # Check each warning threshold
    for warning_hour in sorted(warning_hours, reverse=True):
        threshold = inactive_hours - warning_hour
        
        if hours_inactive >= threshold and warning_hour not in warnings_sent:
            # Send warning
            if inactivity_type == "user":
                member = guild.get_member(int(owner_id))
                mention = member.mention if member else f"<@{owner_id}>"
                warning_msg = _(
                    "⚠️ {mention}, this ticket will be automatically closed in **{hours} hours** "
                    "due to inactivity. Please respond if you still need assistance."
                ).format(mention=mention, hours=warning_hour)
            else:
                warning_msg = _(
                    "⚠️ **Staff Notice:** This ticket has been awaiting staff response. "
                    "It will be automatically closed in **{hours} hours** if not addressed."
                ).format(hours=warning_hour)
            
            try:
                await channel.send(warning_msg)
            except discord.HTTPException:
                pass
            
            # Record warning sent
            async with config.guild(guild).opened() as opened:
                if owner_id in opened and str(channel.id) in opened[owner_id]:
                    if "close_warnings_sent" not in opened[owner_id][str(channel.id)]:
                        opened[owner_id][str(channel.id)]["close_warnings_sent"] = []
                    opened[owner_id][str(channel.id)]["close_warnings_sent"].append(warning_hour)
            
            return inactivity_type
    
    return None


async def should_auto_close(
    guild: discord.Guild,
    ticket: dict,
    conf: dict,
) -> Tuple[bool, str]:
    """
    Check if a ticket should be auto-closed.
    Returns (should_close, reason)
    """
    user_hours = conf.get("auto_close_user_hours", 0)
    staff_hours = conf.get("auto_close_staff_hours", 0)
    
    # Fallback to legacy inactive setting
    if not user_hours and not staff_hours:
        legacy_hours = conf.get("inactive", 0)
        if legacy_hours:
            user_hours = legacy_hours
    
    now = datetime.now().astimezone()
    status = ticket.get("status", "open")
    
    # Check user inactivity
    if user_hours and status in ["claimed", "awaiting_user"]:
        last_user = ticket.get("last_user_message") or ticket.get("opened")
        try:
            last_time = datetime.fromisoformat(last_user)
            hours_inactive = (now - last_time).total_seconds() / 3600
            if hours_inactive >= user_hours:
                return True, _("Auto-closed: No response from user for {} hours").format(user_hours)
        except (ValueError, TypeError):
            pass
    
    # Check staff inactivity
    if staff_hours and status in ["open", "awaiting_staff"]:
        last_staff = ticket.get("last_staff_message")
        last_activity = last_staff or ticket.get("opened")
        try:
            last_time = datetime.fromisoformat(last_activity)
            hours_inactive = (now - last_time).total_seconds() / 3600
            if hours_inactive >= staff_hours:
                return True, _("Auto-closed: No staff response for {} hours").format(staff_hours)
        except (ValueError, TypeError):
            pass
    
    return False, ""


# ============================================================================
# Reopen Functions
# ============================================================================

async def can_reopen_ticket(
    guild: discord.Guild,
    channel_id: int,
    conf: dict,
) -> Tuple[bool, Optional[str]]:
    """
    Check if a ticket can be reopened (within the reopen window).
    This is mainly used for thread tickets that are archived but not deleted.
    Returns (can_reopen, error_message)
    """
    reopen_hours = conf.get("reopen_hours", 0)
    
    if not reopen_hours:
        return False, _("Ticket reopening is not enabled.")
    
    # For this to work, we need to track closed tickets temporarily
    # This would require additional config storage
    # For now, return False with a message to create a new ticket
    return False, _("Please open a new ticket and reference the previous one.")


# ============================================================================
# Preflight Permission Check
# ============================================================================

async def preflight_check_panel(
    guild: discord.Guild,
    panel_name: str,
    panel: dict,
) -> Dict[str, Any]:
    """
    Perform a comprehensive permission check for a panel.
    Returns a detailed status dict.
    """
    return PermissionChecker.preflight_check(guild, panel, guild.me)


async def preflight_check_all_panels(
    guild: discord.Guild,
    conf: dict,
) -> Dict[str, Dict[str, Any]]:
    """Check all panels and return status for each"""
    results = {}
    for panel_name, panel in conf.get("panels", {}).items():
        panel["name"] = panel_name
        results[panel_name] = await preflight_check_panel(guild, panel_name, panel)
    return results


# ============================================================================
# Transcript Export Formats
# ============================================================================

async def export_transcript_json(
    channel: Union[discord.TextChannel, discord.Thread],
    ticket: dict,
    member: Union[discord.Member, discord.User],
) -> str:
    """Export transcript as JSON for auditing"""
    history = await fetch_channel_history(channel)
    
    messages = []
    for msg in history:
        messages.append({
            "id": str(msg.id),
            "author": {
                "id": str(msg.author.id),
                "name": msg.author.name,
                "bot": msg.author.bot,
            },
            "content": msg.content,
            "timestamp": msg.created_at.isoformat(),
            "attachments": [{"filename": a.filename, "url": a.url} for a in msg.attachments],
            "embeds": [e.to_dict() for e in msg.embeds],
        })
    
    export_data = {
        "ticket": {
            "channel_id": str(channel.id),
            "channel_name": channel.name,
            "panel": ticket.get("panel"),
            "opened": ticket.get("opened"),
            "owner_id": str(member.id),
            "owner_name": member.name,
            "claimed_by": ticket.get("claimed_by"),
            "status": ticket.get("status"),
            "answers": ticket.get("answers", {}),
            "notes": ticket.get("notes", []),
        },
        "messages": messages,
        "exported_at": datetime.now().astimezone().isoformat(),
    }
    
    return json.dumps(export_data, indent=2, ensure_ascii=False)


async def export_transcript_txt(
    channel: Union[discord.TextChannel, discord.Thread],
    ticket: dict,
    member: Union[discord.Member, discord.User],
) -> str:
    """Export transcript as plain text"""
    history = await fetch_channel_history(channel)
    
    lines = [
        f"=== Ticket Transcript ===",
        f"Channel: {channel.name} ({channel.id})",
        f"Owner: {member.name} ({member.id})",
        f"Panel: {ticket.get('panel')}",
        f"Opened: {ticket.get('opened')}",
        f"Status: {ticket.get('status')}",
        "=" * 30,
        "",
    ]
    
    # Add answers if any
    answers = ticket.get("answers", {})
    if answers:
        lines.append("=== Form Responses ===")
        for q, a in answers.items():
            lines.append(f"Q: {q}")
            lines.append(f"A: {a}")
            lines.append("")
        lines.append("=" * 30)
        lines.append("")
    
    # Add messages
    lines.append("=== Messages ===")
    for msg in history:
        timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"[{timestamp}] {msg.author.name}: {msg.content}")
        for att in msg.attachments:
            lines.append(f"  [Attachment: {att.filename}]")
    
    return "\n".join(lines)
