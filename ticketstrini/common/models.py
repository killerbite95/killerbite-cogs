"""
Data models and helper classes for TicketsTrini
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union
import re


@dataclass
class TicketStats:
    """Statistics for a guild's ticket system"""
    total_opened: int = 0
    total_closed: int = 0
    avg_claim_time: float = 0.0  # In seconds
    avg_close_time: float = 0.0  # In seconds
    tickets_by_panel: Dict[str, int] = field(default_factory=dict)
    tickets_by_staff: Dict[int, int] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: dict) -> "TicketStats":
        return cls(
            total_opened=data.get("total_opened", 0),
            total_closed=data.get("total_closed", 0),
            avg_claim_time=data.get("avg_claim_time", 0.0),
            avg_close_time=data.get("avg_close_time", 0.0),
            tickets_by_panel=data.get("tickets_by_panel", {}),
            tickets_by_staff=data.get("tickets_by_staff", {}),
        )
    
    def to_dict(self) -> dict:
        return {
            "total_opened": self.total_opened,
            "total_closed": self.total_closed,
            "avg_claim_time": self.avg_claim_time,
            "avg_close_time": self.avg_close_time,
            "tickets_by_panel": self.tickets_by_panel,
            "tickets_by_staff": self.tickets_by_staff,
        }
    
    def update_avg_claim_time(self, new_time: float):
        """Update rolling average for claim time"""
        if self.total_opened == 0:
            self.avg_claim_time = new_time
        else:
            self.avg_claim_time = (
                (self.avg_claim_time * (self.total_opened - 1) + new_time) 
                / self.total_opened
            )
    
    def update_avg_close_time(self, new_time: float):
        """Update rolling average for close time"""
        if self.total_closed == 0:
            self.avg_close_time = new_time
        else:
            self.avg_close_time = (
                (self.avg_close_time * (self.total_closed - 1) + new_time) 
                / self.total_closed
            )


@dataclass
class BlacklistEntry:
    """Represents an advanced blacklist entry"""
    user_or_role_id: int
    reason: Optional[str] = None
    added_by: Optional[int] = None
    added_at: Optional[str] = None
    expires_at: Optional[str] = None
    
    @property
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        try:
            expires = datetime.fromisoformat(self.expires_at)
            return datetime.now().astimezone() > expires
        except (ValueError, TypeError):
            return False
    
    @property
    def time_remaining(self) -> Optional[timedelta]:
        if not self.expires_at:
            return None
        try:
            expires = datetime.fromisoformat(self.expires_at)
            remaining = expires - datetime.now().astimezone()
            return remaining if remaining.total_seconds() > 0 else timedelta(0)
        except (ValueError, TypeError):
            return None
    
    @classmethod
    def from_dict(cls, user_or_role_id: int, data: dict) -> "BlacklistEntry":
        return cls(
            user_or_role_id=user_or_role_id,
            reason=data.get("reason"),
            added_by=data.get("added_by"),
            added_at=data.get("added_at"),
            expires_at=data.get("expires_at"),
        )
    
    def to_dict(self) -> dict:
        return {
            "reason": self.reason,
            "added_by": self.added_by,
            "added_at": self.added_at,
            "expires_at": self.expires_at,
        }


@dataclass
class TicketNote:
    """Internal staff note on a ticket"""
    author_id: int
    content: str
    timestamp: str
    
    @classmethod
    def from_dict(cls, data: dict) -> "TicketNote":
        return cls(
            author_id=data["author_id"],
            content=data["content"],
            timestamp=data["timestamp"],
        )
    
    def to_dict(self) -> dict:
        return {
            "author_id": self.author_id,
            "content": self.content,
            "timestamp": self.timestamp,
        }


@dataclass
class QuickReply:
    """Quick reply template for staff"""
    name: str
    title: str
    content: str
    close_after: bool = False
    delay_close: int = 0
    
    @classmethod
    def from_dict(cls, name: str, data: dict) -> "QuickReply":
        return cls(
            name=name,
            title=data.get("title", ""),
            content=data.get("content", ""),
            close_after=data.get("close_after", False),
            delay_close=data.get("delay_close", 0),
        )
    
    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "content": self.content,
            "close_after": self.close_after,
            "delay_close": self.delay_close,
        }


@dataclass
class PanelSchedule:
    """Schedule configuration for a panel"""
    start: str  # HH:MM format
    end: str  # HH:MM format
    timezone: str = "UTC"
    message: str = "This support panel is currently closed."
    
    @property
    def is_open(self) -> bool:
        """Check if the panel is currently open based on schedule"""
        from datetime import timezone as tz
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        
        try:
            panel_tz = ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, KeyError):
            panel_tz = tz.utc
        
        now = datetime.now(panel_tz)
        current_time = now.strftime("%H:%M")
        
        # Simple comparison (works for same-day schedules)
        if self.start <= self.end:
            return self.start <= current_time <= self.end
        else:
            # Overnight schedule (e.g., 22:00 - 06:00)
            return current_time >= self.start or current_time <= self.end
    
    @classmethod
    def from_dict(cls, data: Optional[dict]) -> Optional["PanelSchedule"]:
        if not data:
            return None
        return cls(
            start=data.get("start", "00:00"),
            end=data.get("end", "23:59"),
            timezone=data.get("timezone", "UTC"),
            message=data.get("message", "This support panel is currently closed."),
        )
    
    def to_dict(self) -> dict:
        return {
            "start": self.start,
            "end": self.end,
            "timezone": self.timezone,
            "message": self.message,
        }


@dataclass
class WelcomeSections:
    """Welcome message sections for enhanced ticket opening"""
    what_we_need: str = ""
    steps: str = ""
    sla: str = ""
    rules: str = ""
    
    @classmethod
    def from_dict(cls, data: Optional[dict]) -> Optional["WelcomeSections"]:
        if not data:
            return None
        return cls(
            what_we_need=data.get("what_we_need", ""),
            steps=data.get("steps", ""),
            sla=data.get("sla", ""),
            rules=data.get("rules", ""),
        )
    
    def to_dict(self) -> dict:
        return {
            "what_we_need": self.what_we_need,
            "steps": self.steps,
            "sla": self.sla,
            "rules": self.rules,
        }
    
    def to_embed_fields(self) -> List[tuple]:
        """Convert sections to embed field tuples (name, value)"""
        fields = []
        if self.what_we_need:
            fields.append(("📋 What We Need", self.what_we_need))
        if self.steps:
            fields.append(("📝 Steps", self.steps))
        if self.sla:
            fields.append(("⏰ Response Time", self.sla))
        if self.rules:
            fields.append(("📜 Rules", self.rules))
        return fields


@dataclass
class AuditLogEntry:
    """Audit log entry for tracking actions"""
    action: str
    user_id: int
    timestamp: str
    details: Dict[str, Any] = field(default_factory=dict)
    target_user_id: Optional[int] = None
    ticket_channel_id: Optional[int] = None
    panel_name: Optional[str] = None
    
    @classmethod
    def create(
        cls,
        action: str,
        user_id: int,
        details: Optional[Dict[str, Any]] = None,
        target_user_id: Optional[int] = None,
        ticket_channel_id: Optional[int] = None,
        panel_name: Optional[str] = None,
    ) -> "AuditLogEntry":
        return cls(
            action=action,
            user_id=user_id,
            timestamp=datetime.now().astimezone().isoformat(),
            details=details or {},
            target_user_id=target_user_id,
            ticket_channel_id=ticket_channel_id,
            panel_name=panel_name,
        )
    
    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "user_id": self.user_id,
            "timestamp": self.timestamp,
            "details": self.details,
            "target_user_id": self.target_user_id,
            "ticket_channel_id": self.ticket_channel_id,
            "panel_name": self.panel_name,
        }


class TimeParser:
    """Utility class for parsing time strings"""
    
    TIME_UNITS = {
        's': 1,
        'sec': 1,
        'second': 1,
        'seconds': 1,
        'm': 60,
        'min': 60,
        'minute': 60,
        'minutes': 60,
        'h': 3600,
        'hr': 3600,
        'hour': 3600,
        'hours': 3600,
        'd': 86400,
        'day': 86400,
        'days': 86400,
        'w': 604800,
        'week': 604800,
        'weeks': 604800,
    }
    
    @classmethod
    def parse(cls, time_string: str) -> Optional[timedelta]:
        """
        Parse a time string like '1h', '30m', '2d', '1h30m' into a timedelta.
        Returns None if parsing fails.
        """
        if not time_string:
            return None
        
        time_string = time_string.lower().strip()
        
        # Try simple format first (e.g., "1h", "30m")
        pattern = r'(\d+)\s*([a-zA-Z]+)'
        matches = re.findall(pattern, time_string)
        
        if not matches:
            # Try pure number (assume minutes)
            try:
                return timedelta(minutes=int(time_string))
            except ValueError:
                return None
        
        total_seconds = 0
        for amount, unit in matches:
            unit = unit.lower()
            if unit in cls.TIME_UNITS:
                total_seconds += int(amount) * cls.TIME_UNITS[unit]
            else:
                return None
        
        return timedelta(seconds=total_seconds) if total_seconds > 0 else None
    
    @classmethod
    def format_duration(cls, seconds: float) -> str:
        """Format seconds into a human-readable duration string"""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f"{minutes}m"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            minutes = int((seconds % 3600) / 60)
            if minutes:
                return f"{hours}h {minutes}m"
            return f"{hours}h"
        else:
            days = int(seconds / 86400)
            hours = int((seconds % 86400) / 3600)
            if hours:
                return f"{days}d {hours}h"
            return f"{days}d"


class PermissionChecker:
    """Utility class for checking bot permissions"""
    
    THREAD_PERMISSIONS = [
        "create_private_threads",
        "send_messages_in_threads",
        "manage_threads",
    ]
    
    CHANNEL_PERMISSIONS = [
        "manage_channels",
        "manage_permissions",
        "view_channel",
        "send_messages",
        "read_message_history",
        "embed_links",
        "attach_files",
    ]
    
    @classmethod
    def check_thread_permissions(cls, channel, bot_member) -> List[str]:
        """Check thread-related permissions and return list of missing ones"""
        perms = channel.permissions_for(bot_member)
        missing = []
        
        perm_names = {
            "create_private_threads": "Create Private Threads",
            "send_messages_in_threads": "Send Messages in Threads",
            "manage_threads": "Manage Threads",
        }
        
        for perm in cls.THREAD_PERMISSIONS:
            if not getattr(perms, perm, False):
                missing.append(perm_names.get(perm, perm))
        
        return missing
    
    @classmethod
    def check_channel_permissions(cls, category, bot_member) -> List[str]:
        """Check channel-related permissions and return list of missing ones"""
        perms = category.permissions_for(bot_member)
        missing = []
        
        perm_names = {
            "manage_channels": "Manage Channels",
            "manage_permissions": "Manage Permissions",
            "view_channel": "View Channel",
            "send_messages": "Send Messages",
            "read_message_history": "Read Message History",
            "embed_links": "Embed Links",
            "attach_files": "Attach Files",
        }
        
        for perm in cls.CHANNEL_PERMISSIONS:
            if not getattr(perms, perm, False):
                missing.append(perm_names.get(perm, perm))
        
        return missing
    
    @classmethod
    def preflight_check(cls, guild, panel: dict, bot_member) -> Dict[str, Any]:
        """
        Perform a comprehensive permission check for a panel.
        Returns a dict with status and any issues found.
        """
        issues = []
        warnings = []
        
        # Check category
        category_id = panel.get("category_id")
        if category_id:
            category = guild.get_channel(category_id)
            if not category:
                issues.append("Category not found")
            else:
                missing = cls.check_channel_permissions(category, bot_member)
                if missing:
                    issues.append(f"Missing in category: {', '.join(missing)}")
        else:
            if not panel.get("threads"):
                issues.append("No category set for channel-based tickets")
        
        # Check channel
        channel_id = panel.get("channel_id")
        if channel_id:
            channel = guild.get_channel(channel_id)
            if not channel:
                issues.append("Panel channel not found")
            else:
                perms = channel.permissions_for(bot_member)
                if not perms.view_channel:
                    issues.append("Cannot view panel channel")
                if not perms.send_messages:
                    issues.append("Cannot send messages in panel channel")
                
                # Thread-specific checks
                if panel.get("threads"):
                    missing = cls.check_thread_permissions(channel, bot_member)
                    if missing:
                        issues.append(f"Missing thread permissions: {', '.join(missing)}")
        else:
            issues.append("No panel channel set")
        
        # Check log channel
        log_channel_id = panel.get("log_channel")
        if log_channel_id:
            log_channel = guild.get_channel(log_channel_id)
            if not log_channel:
                warnings.append("Log channel not found")
            else:
                perms = log_channel.permissions_for(bot_member)
                if not perms.send_messages or not perms.embed_links:
                    warnings.append("Missing permissions in log channel")
        
        return {
            "ok": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
        }
