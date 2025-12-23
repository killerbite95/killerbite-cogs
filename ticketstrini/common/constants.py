# Schema version for migrations
SCHEMA_VERSION = 2

DEFAULT_GUILD = {
    # Settings
    "schema_version": SCHEMA_VERSION,
    "support_roles": [],  # Role ids that have access to all tickets
    "blacklist": [],  # User ids that cannot open any tickets - simple list for backward compat
    "blacklist_advanced": {},  # Advanced blacklist: {user_or_role_id: {reason, added_by, added_at, expires_at}}
    "max_tickets": 1,  # Max amount of tickets a user can have open at a time of any kind
    "inactive": 0,  # Auto close tickets with X hours of inactivity (0 = disabled)
    "overview_channel": 0,  # Overview of open tickets across panels
    "overview_msg": 0,  # Message id of the overview info
    "overview_mention": False,  # Whether the channel names are displayed or the name
    # Ticket data
    "opened": {},  # All opened tickets {user_id: {channel_id: panel_data_dict}}
    "panels": {},  # All ticket panels
    # Toggles
    "dm": False,  # Whether to DM the user when their ticket is closed
    "user_can_rename": False,  # Ticket opener can rename their ticket channel
    "user_can_close": True,  # Ticket opener can close their own ticket
    "user_can_manage": False,  # Ticket opener can add other users to their ticket
    "transcript": False,  # Save a transcript of the ticket conversation on close
    "detailed_transcript": False,  # Save transcript to interactive html file
    "auto_add": False,  # Auto-add support/subroles to thread tickets
    "thread_close": True,  # Whether to close/lock the thread instead of deleting it
    "suspended_msg": None,  # If not None, user will be presented with this message when trying to open a ticket
    # Anti-spam settings
    "ticket_cooldown": 0,  # Cooldown in seconds between tickets per user (0 = disabled)
    "global_rate_limit": 0,  # Max tickets per hour globally (0 = disabled)
    "min_account_age": 0,  # Minimum account age in days to open tickets (0 = disabled)
    "min_server_age": 0,  # Minimum server membership age in days (0 = disabled)
    # Auto-close settings
    "auto_close_user_hours": 0,  # Auto-close if user doesn't respond (0 = disabled)
    "auto_close_staff_hours": 0,  # Auto-close if staff doesn't respond (0 = disabled)
    "auto_close_warning_hours": [24, 1],  # Warning intervals before auto-close
    "reopen_hours": 0,  # Allow reopening for X hours after close (0 = disabled)
    # Staff settings
    "max_claims_per_staff": 0,  # Max tickets a single staff can claim (0 = unlimited)
    "escalation_channel": 0,  # Channel to ping for unclaimed tickets
    "escalation_role": 0,  # Role to ping for escalation
    "escalation_minutes": 0,  # Minutes before escalating unclaimed ticket (0 = disabled)
    "second_escalation_minutes": 0,  # Second escalation timing (0 = disabled)
    # Transcript settings
    "transcript_retention_days": 0,  # Days to keep transcripts (0 = forever)
    "transcript_formats": ["html"],  # Formats to save: html, txt, json
    # Quick reply templates
    "quick_replies": {},  # {name: {title, content, close_after}}
    # Audit log
    "audit_log_channel": 0,  # Channel for audit logs
    # Stats/KPIs
    "stats": {
        "total_opened": 0,
        "total_closed": 0,
        "avg_claim_time": 0,
        "avg_close_time": 0,
    },
    # User cooldowns cache
    "user_cooldowns": {},  # {user_id: last_ticket_timestamp}
}

TICKET_PANEL_SCHEMA = {  # "panel_name" will be the key for the schema
    # Panel settings
    "category_id": 0,  # <Required>
    "channel_id": 0,  # <Required>
    "message_id": 0,  # <Required>
    "disabled": False,  # Whether panel is disabled
    "alt_channel": 0,  # (Optional) Open tickets from another channel/category
    "required_roles": [],  # (Optional) list of role IDs, empty list if anyone can open
    "close_reason": True,  # Throw a modal for closing reason on the ticket close button
    # Button settings
    "button_text": "Open a Ticket",  # (Optional)
    "button_color": "blue",  # (Optional)
    "button_emoji": None,  # (Optional) Either None or an emoji for the button
    "priority": 1,  # (Optional) Button order
    "row": None,  # Row for the button to be placed
    # Ticket settings
    "ticket_messages": [],  # (Optional) A list of messages to be sent
    "ticket_name": None,  # (Optional) Name format for the ticket channel
    "log_channel": 0,  # (Optional) Log open/closed tickets
    "modal": {},  # (Optional) Modal fields to fill out before ticket is opened
    "modal_title": "",  # (Optional) Modal title
    "threads": False,  # Whether this panel makes a thread or channel
    "roles": [],  # Sub-support roles
    "max_claims": 0,  # How many cooks in the kitchen (default infinite if 0)
    # Ticker
    "ticket_num": 1,
    # v4.0.0 - Panel-specific settings
    "cooldown": 0,  # Panel-specific cooldown (0 = use global)
    "rate_limit": 0,  # Max tickets per hour for this panel (0 = unlimited)
    "max_open": 0,  # Max simultaneous tickets for this panel (0 = unlimited)
    "schedule": None,  # {"start": "10:00", "end": "22:00", "timezone": "UTC", "message": "..."}
    "welcome_sections": None,  # {"what_we_need": "", "steps": "", "sla": "", "rules": ""}
    "fallback_mode": "none",  # "none", "channel", "thread" - fallback if primary fails
}

# v1.3.10 schema update (Modals)
MODAL_SCHEMA = {
    "label": "",  # <Required>
    "style": "short",  # <Required>
    "placeholder": None,  # (Optional)
    "default": None,  # (Optional)
    "required": True,  # (Optional)
    "min_length": None,  # (Optional)
    "max_length": None,  # (Optional)
    "answer": None,  # (Optional)
}

OPENED_TICKET_SCHEMA = {
    "panel": str,
    "opened": "datetime",
    "pfp": "url or None",
    "logmsg": "message ID or None",
    "answers": {"question": "answer"},
    "has_response": bool,
    "message_id": "Message ID of first message in the ticket sent from the bot",
    "max_claims": int,
    "overview_msg": "Ticket overview message ID (Optional)",
    # v4.0.0 - New fields
    "status": "open",  # open, claimed, awaiting_user, awaiting_staff, closed
    "claimed_by": None,  # User ID of staff who claimed
    "claimed_at": None,  # ISO timestamp
    "last_user_message": None,  # ISO timestamp
    "last_staff_message": None,  # ISO timestamp
    "close_warnings_sent": [],  # List of warning timestamps sent
    "escalated": False,  # Whether ticket has been escalated
    "escalation_level": 0,  # 0 = not escalated, 1 = first escalation, 2 = second
    "transferred_from": None,  # Previous claimer if transferred
    "notes": [],  # Internal staff notes: [{author_id, content, timestamp}]
    "summary": None,  # Auto-generated or manual summary on close
}

# Blacklist entry schema
BLACKLIST_ENTRY_SCHEMA = {
    "reason": None,
    "added_by": None,  # User ID
    "added_at": None,  # ISO timestamp
    "expires_at": None,  # ISO timestamp or None for permanent
}

# Quick reply template schema
QUICK_REPLY_SCHEMA = {
    "title": "",
    "content": "",
    "close_after": False,
    "delay_close": 0,  # Seconds to wait before closing (0 = immediate)
}

# Audit log action types
AUDIT_ACTIONS = [
    "ticket_open",
    "ticket_close",
    "ticket_reopen",
    "ticket_rename",
    "ticket_add_user",
    "ticket_remove_user",
    "ticket_claim",
    "ticket_unclaim",
    "ticket_transfer",
    "ticket_escalate",
    "config_change",
    "blacklist_add",
    "blacklist_remove",
    "note_add",
]

# Ticket statuses
TICKET_STATUSES = {
    "open": "🟢 Open",
    "claimed": "🔵 Claimed",
    "awaiting_user": "🟡 Awaiting User",
    "awaiting_staff": "🟠 Awaiting Staff",
    "closed": "🔴 Closed",
}
