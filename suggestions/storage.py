"""
Storage module for SimpleSuggestions.
Handles Config schema, atomic operations, and data migrations.
"""
import asyncio
import discord
from redbot.core import Config
from typing import Dict, List, Optional, Any, TYPE_CHECKING
from datetime import datetime
from enum import Enum
import logging

if TYPE_CHECKING:
    from redbot.core.bot import Red

logger = logging.getLogger("red.killerbite95.suggestions.storage")

# Schema version for migrations
CURRENT_SCHEMA_VERSION = 2


class SuggestionStatus(Enum):
    """Possible states for a suggestion."""
    PENDING = "pending"
    IN_REVIEW = "in_review"
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    IMPLEMENTED = "implemented"
    DENIED = "denied"
    DUPLICATE = "duplicate"
    WONT_DO = "wont_do"


# Status display configuration
STATUS_CONFIG = {
    SuggestionStatus.PENDING: {"color": discord.Color.blue(), "emoji": "🔵", "label": "Pendiente"},
    SuggestionStatus.IN_REVIEW: {"color": discord.Color.gold(), "emoji": "🟡", "label": "En revisión"},
    SuggestionStatus.PLANNED: {"color": discord.Color.purple(), "emoji": "🟣", "label": "Planeado"},
    SuggestionStatus.IN_PROGRESS: {"color": discord.Color.orange(), "emoji": "🟠", "label": "En progreso"},
    SuggestionStatus.APPROVED: {"color": discord.Color.green(), "emoji": "🟢", "label": "Aprobado"},
    SuggestionStatus.IMPLEMENTED: {"color": discord.Color.dark_green(), "emoji": "✅", "label": "Implementado"},
    SuggestionStatus.DENIED: {"color": discord.Color.red(), "emoji": "🔴", "label": "Rechazado"},
    SuggestionStatus.DUPLICATE: {"color": discord.Color.greyple(), "emoji": "🔄", "label": "Duplicado"},
    SuggestionStatus.WONT_DO: {"color": discord.Color.dark_grey(), "emoji": "⛔", "label": "No se hará"},
}


class SuggestionData:
    """Data class for a suggestion."""
    
    def __init__(self, data: Dict[str, Any]):
        self.suggestion_id: int = data.get("suggestion_id", 0)
        self.message_id: int = data.get("message_id", 0)
        self.content: str = data.get("content", "")
        self.author_id: int = data.get("author_id", 0)
        self.status: SuggestionStatus = SuggestionStatus(data.get("status", "pending"))
        self.created_at: str = data.get("created_at", datetime.utcnow().isoformat())
        self.thread_id: Optional[int] = data.get("thread_id")
        self.voters_up: List[int] = data.get("voters_up", [])
        self.voters_down: List[int] = data.get("voters_down", [])
        self.reason: Optional[str] = data.get("reason")
        self.history: List[Dict[str, Any]] = data.get("history", [])
        self.deleted: bool = data.get("deleted", False)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "suggestion_id": self.suggestion_id,
            "message_id": self.message_id,
            "content": self.content,
            "author_id": self.author_id,
            "status": self.status.value,
            "created_at": self.created_at,
            "thread_id": self.thread_id,
            "voters_up": self.voters_up,
            "voters_down": self.voters_down,
            "reason": self.reason,
            "history": self.history,
            "deleted": self.deleted,
        }
    
    @property
    def upvotes(self) -> int:
        return len(self.voters_up)
    
    @property
    def downvotes(self) -> int:
        return len(self.voters_down)
    
    @property
    def score(self) -> int:
        return self.upvotes - self.downvotes
    
    def add_history_entry(self, changed_by: int, old_status: str, new_status: str, reason: Optional[str] = None):
        """Add an entry to the history log."""
        self.history.append({
            "changed_by": changed_by,
            "changed_at": datetime.utcnow().isoformat(),
            "old_status": old_status,
            "new_status": new_status,
            "reason": reason,
        })


class SuggestionStorage:
    """Handles all storage operations for suggestions."""
    
    def __init__(self, bot: "Red", config: Config):
        self.bot = bot
        self.config = config
        self._locks: Dict[int, asyncio.Lock] = {}  # guild_id -> Lock
    
    def _get_lock(self, guild_id: int) -> asyncio.Lock:
        """Get or create a lock for a guild."""
        if guild_id not in self._locks:
            self._locks[guild_id] = asyncio.Lock()
        return self._locks[guild_id]
    
    async def get_next_suggestion_id(self, guild: discord.Guild) -> int:
        """
        Atomically get and increment the suggestion counter.
        Uses a lock to prevent race conditions.
        """
        async with self._get_lock(guild.id):
            current_id = await self.config.guild(guild).suggestion_counter()
            next_id = current_id + 1
            await self.config.guild(guild).suggestion_counter.set(next_id)
            return next_id
    
    async def create_suggestion(
        self,
        guild: discord.Guild,
        message_id: int,
        content: str,
        author_id: int,
        thread_id: Optional[int] = None
    ) -> SuggestionData:
        """Create a new suggestion atomically."""
        suggestion_id = await self.get_next_suggestion_id(guild)
        
        data = SuggestionData({
            "suggestion_id": suggestion_id,
            "message_id": message_id,
            "content": content,
            "author_id": author_id,
            "status": SuggestionStatus.PENDING.value,
            "created_at": datetime.utcnow().isoformat(),
            "thread_id": thread_id,
            "voters_up": [],
            "voters_down": [],
            "reason": None,
            "history": [],
            "deleted": False,
        })
        
        async with self._get_lock(guild.id):
            suggestions = await self.config.guild(guild).suggestions()
            suggestions[str(suggestion_id)] = data.to_dict()
            await self.config.guild(guild).suggestions.set(suggestions)
        
        logger.info(f"Created suggestion #{suggestion_id} in guild {guild.id}")
        return data
    
    async def get_suggestion(self, guild: discord.Guild, suggestion_id: int) -> Optional[SuggestionData]:
        """Get a suggestion by its ID."""
        suggestions = await self.config.guild(guild).suggestions()
        data = suggestions.get(str(suggestion_id))
        if data:
            return SuggestionData(data)
        return None
    
    async def get_suggestion_by_message(self, guild: discord.Guild, message_id: int) -> Optional[SuggestionData]:
        """Get a suggestion by its message ID."""
        suggestions = await self.config.guild(guild).suggestions()
        for data in suggestions.values():
            if data.get("message_id") == message_id:
                return SuggestionData(data)
        return None
    
    async def update_suggestion(self, guild: discord.Guild, suggestion: SuggestionData) -> bool:
        """Update a suggestion in storage."""
        async with self._get_lock(guild.id):
            suggestions = await self.config.guild(guild).suggestions()
            if str(suggestion.suggestion_id) in suggestions:
                suggestions[str(suggestion.suggestion_id)] = suggestion.to_dict()
                await self.config.guild(guild).suggestions.set(suggestions)
                return True
        return False
    
    async def update_status(
        self,
        guild: discord.Guild,
        suggestion_id: int,
        new_status: SuggestionStatus,
        changed_by: int,
        reason: Optional[str] = None
    ) -> Optional[SuggestionData]:
        """Update the status of a suggestion with history tracking."""
        suggestion = await self.get_suggestion(guild, suggestion_id)
        if not suggestion:
            return None
        
        old_status = suggestion.status.value
        suggestion.status = new_status
        suggestion.reason = reason
        suggestion.add_history_entry(changed_by, old_status, new_status.value, reason)
        
        await self.update_suggestion(guild, suggestion)
        logger.info(f"Updated suggestion #{suggestion_id} status: {old_status} -> {new_status.value}")
        return suggestion
    
    async def add_vote(
        self,
        guild: discord.Guild,
        suggestion_id: int,
        user_id: int,
        vote_type: str  # "up" or "down"
    ) -> Optional[tuple]:
        """
        Add a vote to a suggestion.
        Returns (suggestion, action) where action is "added", "removed", or "switched".
        Handles toggle and switch logic.
        """
        suggestion = await self.get_suggestion(guild, suggestion_id)
        if not suggestion:
            return None
        
        action = None
        
        if vote_type == "up":
            if user_id in suggestion.voters_up:
                # Toggle off
                suggestion.voters_up.remove(user_id)
                action = "removed"
            else:
                # Add upvote
                suggestion.voters_up.append(user_id)
                action = "added"
                # Remove downvote if exists
                if user_id in suggestion.voters_down:
                    suggestion.voters_down.remove(user_id)
                    action = "switched"
        else:  # down
            if user_id in suggestion.voters_down:
                # Toggle off
                suggestion.voters_down.remove(user_id)
                action = "removed"
            else:
                # Add downvote
                suggestion.voters_down.append(user_id)
                action = "added"
                # Remove upvote if exists
                if user_id in suggestion.voters_up:
                    suggestion.voters_up.remove(user_id)
                    action = "switched"
        
        await self.update_suggestion(guild, suggestion)
        return (suggestion, action)
    
    async def get_all_suggestions(
        self,
        guild: discord.Guild,
        status_filter: Optional[SuggestionStatus] = None,
        author_filter: Optional[int] = None,
        include_deleted: bool = False
    ) -> List[SuggestionData]:
        """Get all suggestions with optional filters."""
        suggestions = await self.config.guild(guild).suggestions()
        result = []
        
        for data in suggestions.values():
            suggestion = SuggestionData(data)
            
            if not include_deleted and suggestion.deleted:
                continue
            if status_filter and suggestion.status != status_filter:
                continue
            if author_filter and suggestion.author_id != author_filter:
                continue
            
            result.append(suggestion)
        
        # Sort by suggestion_id descending (newest first)
        result.sort(key=lambda s: s.suggestion_id, reverse=True)
        return result
    
    async def mark_deleted(self, guild: discord.Guild, suggestion_id: int) -> bool:
        """Mark a suggestion as deleted (soft delete)."""
        suggestion = await self.get_suggestion(guild, suggestion_id)
        if not suggestion:
            return False
        
        suggestion.deleted = True
        return await self.update_suggestion(guild, suggestion)
    
    async def purge_deleted(self, guild: discord.Guild) -> int:
        """Permanently remove all deleted suggestions. Returns count removed."""
        async with self._get_lock(guild.id):
            suggestions = await self.config.guild(guild).suggestions()
            original_count = len(suggestions)
            
            suggestions = {
                k: v for k, v in suggestions.items()
                if not v.get("deleted", False)
            }
            
            await self.config.guild(guild).suggestions.set(suggestions)
            return original_count - len(suggestions)
    
    async def update_message_id(
        self,
        guild: discord.Guild,
        suggestion_id: int,
        new_message_id: int
    ) -> bool:
        """Update the message ID for a suggestion (for repost)."""
        suggestion = await self.get_suggestion(guild, suggestion_id)
        if not suggestion:
            return False
        
        suggestion.message_id = new_message_id
        suggestion.deleted = False
        return await self.update_suggestion(guild, suggestion)


async def migrate_schema(config: Config, guild: discord.Guild) -> bool:
    """
    Migrate data from old schema to new schema if needed.
    Returns True if migration was performed.
    """
    current_version = await config.guild(guild).schema_version()
    
    if current_version >= CURRENT_SCHEMA_VERSION:
        return False
    
    logger.info(f"Migrating guild {guild.id} from schema v{current_version} to v{CURRENT_SCHEMA_VERSION}")
    
    if current_version < 2:
        # Migrate from v1 to v2
        # v1 used message_id as key, v2 uses suggestion_id as key
        old_suggestions = await config.guild(guild).suggestions()
        new_suggestions = {}
        
        for msg_id, data in old_suggestions.items():
            suggestion_id = data.get("suggestion_id", 0)
            if suggestion_id == 0:
                continue
            
            # Convert old status format
            old_status = data.get("status", "Pendiente")
            status_map = {
                "Pendiente": "pending",
                "Aprobado": "approved",
                "Rechazado": "denied",
            }
            new_status = status_map.get(old_status, "pending")
            
            new_suggestions[str(suggestion_id)] = {
                "suggestion_id": suggestion_id,
                "message_id": int(msg_id),
                "content": data.get("content", ""),
                "author_id": data.get("author", 0),
                "status": new_status,
                "created_at": datetime.utcnow().isoformat(),
                "thread_id": None,
                "voters_up": [],
                "voters_down": [],
                "reason": None,
                "history": [],
                "deleted": False,
            }
        
        await config.guild(guild).suggestions.set(new_suggestions)
        
        # Migrate counter
        old_counter = await config.guild(guild).suggestion_id()
        await config.guild(guild).suggestion_counter.set(old_counter)
    
    await config.guild(guild).schema_version.set(CURRENT_SCHEMA_VERSION)
    logger.info(f"Migration complete for guild {guild.id}")
    return True
