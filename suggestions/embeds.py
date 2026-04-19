"""
Embed builders for SimpleSuggestions.
Handles all embed creation and formatting.
"""
import discord # pyright: ignore[reportMissingImports]
from redbot.core.i18n import Translator
from typing import Optional, TYPE_CHECKING
from datetime import datetime

from .storage import SuggestionData, SuggestionStatus, STATUS_CONFIG

if TYPE_CHECKING:
    from redbot.core.bot import Red

_ = Translator("SimpleSuggestions", __file__)


def create_suggestion_embed(
    suggestion: SuggestionData,
    author: Optional[discord.Member] = None,
    show_votes: bool = True
) -> discord.Embed:
    """Create an embed for a suggestion."""
    status_info = STATUS_CONFIG.get(suggestion.status, STATUS_CONFIG[SuggestionStatus.PENDING])
    
    embed = discord.Embed(
        title=_("Suggestion #{suggestion_id}").format(suggestion_id=suggestion.suggestion_id),
        description=suggestion.content,
        color=status_info["color"],
        timestamp=datetime.fromisoformat(suggestion.created_at) if suggestion.created_at else datetime.utcnow()
    )
    
    if author:
        embed.set_author(name=author.display_name, icon_url=author.display_avatar.url)
    
    # Status field
    label = _(status_info['label'])
    status_text = f"{status_info['emoji']} {label}"
    if suggestion.reason:
        status_text += f"\n📝 *{suggestion.reason}*"
    embed.add_field(name=_("Status"), value=status_text, inline=True)
    
    # Votes field
    if show_votes:
        votes_text = f"👍 {suggestion.upvotes}  |  👎 {suggestion.downvotes}"
        if suggestion.score != 0:
            score_emoji = "📈" if suggestion.score > 0 else "📉"
            votes_text += f"  |  {score_emoji} {suggestion.score:+d}"
        embed.add_field(name=_("Votes"), value=votes_text, inline=True)
    
    # Footer with status
    embed.set_footer(text=_("ID: {suggestion_id} • {label}").format(
        suggestion_id=suggestion.suggestion_id, label=label
    ))
    
    return embed


def create_vote_result_embed(
    suggestion: SuggestionData,
    action: str,
    vote_type: str,
    user: discord.Member
) -> discord.Embed:
    """Create an embed showing vote result (ephemeral response)."""
    emoji = "👍" if vote_type == "up" else "👎"
    
    if action == "added":
        title = _("{emoji} Vote registered").format(emoji=emoji)
        if vote_type == "up":
            description = _("You voted in favor of suggestion #{suggestion_id}").format(suggestion_id=suggestion.suggestion_id)
        else:
            description = _("You voted against suggestion #{suggestion_id}").format(suggestion_id=suggestion.suggestion_id)
        color = discord.Color.green() if vote_type == "up" else discord.Color.red()
    elif action == "removed":
        title = _("🔄 Vote withdrawn")
        description = _("You withdrew your vote from suggestion #{suggestion_id}").format(suggestion_id=suggestion.suggestion_id)
        color = discord.Color.light_grey()
    else:  # switched
        title = _("{emoji} Vote changed").format(emoji=emoji)
        if vote_type == "up":
            description = _("You changed your vote to in favor of suggestion #{suggestion_id}").format(suggestion_id=suggestion.suggestion_id)
        else:
            description = _("You changed your vote to against suggestion #{suggestion_id}").format(suggestion_id=suggestion.suggestion_id)
        color = discord.Color.gold()
    
    embed = discord.Embed(
        title=title,
        description=description,
        color=color
    )
    embed.add_field(
        name=_("Current votes"),
        value=f"👍 {suggestion.upvotes}  |  👎 {suggestion.downvotes}",
        inline=False
    )
    
    return embed


def create_status_change_embed(
    suggestion: SuggestionData,
    old_status: SuggestionStatus,
    changed_by: discord.Member,
    reason: Optional[str] = None
) -> discord.Embed:
    """Create an embed for status change notification (DM to author)."""
    old_info = STATUS_CONFIG.get(old_status, STATUS_CONFIG[SuggestionStatus.PENDING])
    new_info = STATUS_CONFIG.get(suggestion.status, STATUS_CONFIG[SuggestionStatus.PENDING])
    
    embed = discord.Embed(
        title=_("📬 Update on your suggestion"),
        description=_("**Suggestion #{suggestion_id}** has changed status.").format(suggestion_id=suggestion.suggestion_id),
        color=new_info["color"]
    )
    
    embed.add_field(
        name=_("Your suggestion"),
        value=suggestion.content[:200] + ("..." if len(suggestion.content) > 200 else ""),
        inline=False
    )
    
    embed.add_field(
        name=_("Status change"),
        value=f"{old_info['emoji']} {_(old_info['label'])} → {new_info['emoji']} {_(new_info['label'])}",
        inline=False
    )
    
    if reason:
        embed.add_field(name=_("Reason"), value=reason, inline=False)
    
    embed.set_footer(text=_("Updated by {name}").format(name=changed_by.display_name))
    embed.timestamp = datetime.utcnow()
    
    return embed


def create_votes_detail_embed(suggestion: SuggestionData, bot: "Red") -> discord.Embed:
    """Create a detailed votes embed."""
    embed = discord.Embed(
        title=_("📊 Votes - Suggestion #{suggestion_id}").format(suggestion_id=suggestion.suggestion_id),
        color=discord.Color.blurple()
    )
    
    # Summary
    total = suggestion.upvotes + suggestion.downvotes
    if total > 0:
        up_pct = (suggestion.upvotes / total) * 100
        down_pct = (suggestion.downvotes / total) * 100
        
        # Visual bar
        bar_length = 20
        up_bars = int(bar_length * (up_pct / 100))
        down_bars = bar_length - up_bars
        bar = "🟩" * up_bars + "🟥" * down_bars
        
        embed.add_field(
            name=_("Summary"),
            value=_("**Total:** {total} votes\n"
                  "**In favor:** {upvotes} ({up_pct:.1f}%)\n"
                  "**Against:** {downvotes} ({down_pct:.1f}%)\n\n"
                  "{bar}").format(
                      total=total, upvotes=suggestion.upvotes, up_pct=up_pct,
                      downvotes=suggestion.downvotes, down_pct=down_pct, bar=bar
                  ),
            inline=False
        )
    else:
        embed.add_field(
            name=_("Summary"),
            value=_("No votes yet"),
            inline=False
        )
    
    # Score
    score_emoji = "📈" if suggestion.score > 0 else ("📉" if suggestion.score < 0 else "➖")
    embed.add_field(
        name=_("Score"),
        value=f"{score_emoji} **{suggestion.score:+d}**",
        inline=True
    )
    
    return embed


def create_suggestion_list_embed(
    suggestions: list,
    page: int,
    total_pages: int,
    status_filter: Optional[SuggestionStatus] = None
) -> discord.Embed:
    """Create an embed listing multiple suggestions."""
    title = _("📋 Suggestion List")
    if status_filter:
        status_info = STATUS_CONFIG.get(status_filter)
        title += f" - {status_info['emoji']} {_(status_info['label'])}"
    
    embed = discord.Embed(
        title=title,
        color=discord.Color.blurple()
    )
    
    if not suggestions:
        embed.description = _("No suggestions to show.")
    else:
        lines = []
        for s in suggestions:
            status_info = STATUS_CONFIG.get(s.status, STATUS_CONFIG[SuggestionStatus.PENDING])
            votes = f"[👍{s.upvotes}/👎{s.downvotes}]"
            preview = s.content[:50] + ("..." if len(s.content) > 50 else "")
            lines.append(f"{status_info['emoji']} **#{s.suggestion_id}** {votes} - {preview}")
        
        embed.description = "\n".join(lines)
    
    embed.set_footer(text=_("Page {page}/{total_pages}").format(page=page, total_pages=total_pages))
    
    return embed


def create_history_embed(suggestion: SuggestionData, bot: "Red") -> discord.Embed:
    """Create an embed showing suggestion history."""
    embed = discord.Embed(
        title=_("📜 History - Suggestion #{suggestion_id}").format(suggestion_id=suggestion.suggestion_id),
        color=discord.Color.blurple()
    )
    
    if not suggestion.history:
        embed.description = _("No changes recorded.")
    else:
        lines = []
        for entry in suggestion.history[-10:]:  # Last 10 entries
            user = bot.get_user(entry.get("changed_by", 0))
            user_name = user.display_name if user else _("Unknown")
            
            old_status = entry.get("old_status", "?")
            new_status = entry.get("new_status", "?")
            
            try:
                old_info = STATUS_CONFIG.get(SuggestionStatus(old_status), {"emoji": "?"})
                new_info = STATUS_CONFIG.get(SuggestionStatus(new_status), {"emoji": "?"})
            except ValueError:
                old_info = {"emoji": "?"}
                new_info = {"emoji": "?"}
            
            line = _("• {old_emoji} → {new_emoji} by **{user_name}**").format(
                old_emoji=old_info['emoji'], new_emoji=new_info['emoji'], user_name=user_name
            )
            if entry.get("reason"):
                line += f"\n  └ *{entry['reason'][:50]}*"
            
            # Parse and format timestamp
            try:
                timestamp = datetime.fromisoformat(entry.get("changed_at", ""))
                line += f"\n  └ <t:{int(timestamp.timestamp())}:R>"
            except:
                pass
            
            lines.append(line)
        
        embed.description = "\n".join(lines)
    
    return embed
