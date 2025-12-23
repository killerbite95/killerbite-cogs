"""
Embed builders for SimpleSuggestions.
Handles all embed creation and formatting.
"""
import discord # pyright: ignore[reportMissingImports]
from typing import Optional, TYPE_CHECKING
from datetime import datetime

from .storage import SuggestionData, SuggestionStatus, STATUS_CONFIG

if TYPE_CHECKING:
    from redbot.core.bot import Red


def create_suggestion_embed(
    suggestion: SuggestionData,
    author: Optional[discord.Member] = None,
    show_votes: bool = True
) -> discord.Embed:
    """Create an embed for a suggestion."""
    status_info = STATUS_CONFIG.get(suggestion.status, STATUS_CONFIG[SuggestionStatus.PENDING])
    
    embed = discord.Embed(
        title=f"Sugerencia #{suggestion.suggestion_id}",
        description=suggestion.content,
        color=status_info["color"],
        timestamp=datetime.fromisoformat(suggestion.created_at) if suggestion.created_at else datetime.utcnow()
    )
    
    if author:
        embed.set_author(name=author.display_name, icon_url=author.display_avatar.url)
    
    # Status field
    status_text = f"{status_info['emoji']} {status_info['label']}"
    if suggestion.reason:
        status_text += f"\n📝 *{suggestion.reason}*"
    embed.add_field(name="Estado", value=status_text, inline=True)
    
    # Votes field
    if show_votes:
        votes_text = f"👍 {suggestion.upvotes}  |  👎 {suggestion.downvotes}"
        if suggestion.score != 0:
            score_emoji = "📈" if suggestion.score > 0 else "📉"
            votes_text += f"  |  {score_emoji} {suggestion.score:+d}"
        embed.add_field(name="Votos", value=votes_text, inline=True)
    
    # Footer with status
    embed.set_footer(text=f"ID: {suggestion.suggestion_id} • {status_info['label']}")
    
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
        title = f"{emoji} Voto registrado"
        description = f"Has votado {'a favor' if vote_type == 'up' else 'en contra'} de la sugerencia #{suggestion.suggestion_id}"
        color = discord.Color.green() if vote_type == "up" else discord.Color.red()
    elif action == "removed":
        title = "🔄 Voto retirado"
        description = f"Has retirado tu voto de la sugerencia #{suggestion.suggestion_id}"
        color = discord.Color.light_grey()
    else:  # switched
        title = f"{emoji} Voto cambiado"
        description = f"Has cambiado tu voto a {'a favor' if vote_type == 'up' else 'en contra'} de la sugerencia #{suggestion.suggestion_id}"
        color = discord.Color.gold()
    
    embed = discord.Embed(
        title=title,
        description=description,
        color=color
    )
    embed.add_field(
        name="Votos actuales",
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
        title="📬 Actualización de tu sugerencia",
        description=f"**Sugerencia #{suggestion.suggestion_id}** ha cambiado de estado.",
        color=new_info["color"]
    )
    
    embed.add_field(
        name="Tu sugerencia",
        value=suggestion.content[:200] + ("..." if len(suggestion.content) > 200 else ""),
        inline=False
    )
    
    embed.add_field(
        name="Cambio de estado",
        value=f"{old_info['emoji']} {old_info['label']} → {new_info['emoji']} {new_info['label']}",
        inline=False
    )
    
    if reason:
        embed.add_field(name="Motivo", value=reason, inline=False)
    
    embed.set_footer(text=f"Actualizado por {changed_by.display_name}")
    embed.timestamp = datetime.utcnow()
    
    return embed


def create_votes_detail_embed(suggestion: SuggestionData, bot: "Red") -> discord.Embed:
    """Create a detailed votes embed."""
    embed = discord.Embed(
        title=f"📊 Votos - Sugerencia #{suggestion.suggestion_id}",
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
            name="Resumen",
            value=f"**Total:** {total} votos\n"
                  f"**A favor:** {suggestion.upvotes} ({up_pct:.1f}%)\n"
                  f"**En contra:** {suggestion.downvotes} ({down_pct:.1f}%)\n\n"
                  f"{bar}",
            inline=False
        )
    else:
        embed.add_field(
            name="Resumen",
            value="Aún no hay votos",
            inline=False
        )
    
    # Score
    score_emoji = "📈" if suggestion.score > 0 else ("📉" if suggestion.score < 0 else "➖")
    embed.add_field(
        name="Puntuación",
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
    title = "📋 Lista de Sugerencias"
    if status_filter:
        status_info = STATUS_CONFIG.get(status_filter)
        title += f" - {status_info['emoji']} {status_info['label']}"
    
    embed = discord.Embed(
        title=title,
        color=discord.Color.blurple()
    )
    
    if not suggestions:
        embed.description = "No hay sugerencias que mostrar."
    else:
        lines = []
        for s in suggestions:
            status_info = STATUS_CONFIG.get(s.status, STATUS_CONFIG[SuggestionStatus.PENDING])
            votes = f"[👍{s.upvotes}/👎{s.downvotes}]"
            preview = s.content[:50] + ("..." if len(s.content) > 50 else "")
            lines.append(f"{status_info['emoji']} **#{s.suggestion_id}** {votes} - {preview}")
        
        embed.description = "\n".join(lines)
    
    embed.set_footer(text=f"Página {page}/{total_pages}")
    
    return embed


def create_history_embed(suggestion: SuggestionData, bot: "Red") -> discord.Embed:
    """Create an embed showing suggestion history."""
    embed = discord.Embed(
        title=f"📜 Historial - Sugerencia #{suggestion.suggestion_id}",
        color=discord.Color.blurple()
    )
    
    if not suggestion.history:
        embed.description = "No hay cambios registrados."
    else:
        lines = []
        for entry in suggestion.history[-10:]:  # Last 10 entries
            user = bot.get_user(entry.get("changed_by", 0))
            user_name = user.display_name if user else "Desconocido"
            
            old_status = entry.get("old_status", "?")
            new_status = entry.get("new_status", "?")
            
            try:
                old_info = STATUS_CONFIG.get(SuggestionStatus(old_status), {"emoji": "?"})
                new_info = STATUS_CONFIG.get(SuggestionStatus(new_status), {"emoji": "?"})
            except ValueError:
                old_info = {"emoji": "?"}
                new_info = {"emoji": "?"}
            
            line = f"• {old_info['emoji']} → {new_info['emoji']} por **{user_name}**"
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
