"""
Views module for SimpleSuggestions.
Handles buttons, modals, and persistent views.
"""
import discord
from discord import ui
from typing import Optional, TYPE_CHECKING
import logging

from .storage import SuggestionStorage, SuggestionStatus, STATUS_CONFIG
from .embeds import (
    create_suggestion_embed,
    create_vote_result_embed,
    create_votes_detail_embed,
    create_status_change_embed,
)

if TYPE_CHECKING:
    from redbot.core.bot import Red
    from redbot.core import Config

logger = logging.getLogger("red.killerbite95.suggestions.views")


# ==================== MODALS ====================

class SuggestionModal(ui.Modal, title="Nueva Sugerencia"):
    """Modal for creating a new suggestion."""
    
    suggestion_text = ui.TextInput(
        label="Tu sugerencia",
        style=discord.TextStyle.paragraph,
        placeholder="Describe tu sugerencia con detalle...",
        min_length=10,
        max_length=2000,
        required=True
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        # This will be handled by the cog
        self.interaction = interaction
        self.value = self.suggestion_text.value
        self.stop()


class EditSuggestionModal(ui.Modal, title="Editar Sugerencia"):
    """Modal for editing an existing suggestion."""
    
    def __init__(self, current_content: str, suggestion_id: int):
        super().__init__()
        self.suggestion_id = suggestion_id
        self.new_content = ui.TextInput(
            label="Contenido de la sugerencia",
            style=discord.TextStyle.paragraph,
            default=current_content,
            min_length=1,
            max_length=2000,
            required=True
        )
        self.add_item(self.new_content)
    
    async def on_submit(self, interaction: discord.Interaction):
        self.interaction = interaction
        self.value = self.new_content.value
        self.stop()


class StatusChangeModal(ui.Modal, title="Cambiar Estado"):
    """Modal for changing suggestion status with reason."""
    
    reason = ui.TextInput(
        label="Motivo (opcional)",
        style=discord.TextStyle.paragraph,
        placeholder="Explica el motivo del cambio de estado...",
        max_length=500,
        required=False
    )
    
    def __init__(self, new_status: SuggestionStatus):
        super().__init__()
        self.new_status = new_status
        status_info = STATUS_CONFIG.get(new_status, {})
        self.title = f"Cambiar a: {status_info.get('label', new_status.value)}"
    
    async def on_submit(self, interaction: discord.Interaction):
        self.interaction = interaction
        self.value = self.reason.value or None
        self.stop()


# ==================== PERSISTENT VIEWS ====================

class SuggestionView(ui.View):
    """
    Persistent view for suggestion interactions.
    Attached to each suggestion message.
    """
    
    def __init__(self, cog: "SimpleSuggestions", suggestion_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.suggestion_id = suggestion_id
        
        # Create buttons manually to guarantee order
        # Row 0: Upvote, Downvote, Ver votos, Editar
        self.upvote_button = ui.Button(
            label="0",
            emoji="👍",
            style=discord.ButtonStyle.success,
            custom_id=f"suggestion:upvote:{suggestion_id}",
            row=0
        )
        self.upvote_button.callback = self._upvote_callback
        self.add_item(self.upvote_button)
        
        self.downvote_button = ui.Button(
            label="0",
            emoji="👎",
            style=discord.ButtonStyle.danger,
            custom_id=f"suggestion:downvote:{suggestion_id}",
            row=0
        )
        self.downvote_button.callback = self._downvote_callback
        self.add_item(self.downvote_button)
        
        self.votes_button = ui.Button(
            label="Ver votos",
            emoji="📊",
            style=discord.ButtonStyle.secondary,
            custom_id=f"suggestion:votes:{suggestion_id}",
            row=0
        )
        self.votes_button.callback = self._votes_callback
        self.add_item(self.votes_button)
        
        self.edit_button = ui.Button(
            label="Editar",
            emoji="✏️",
            style=discord.ButtonStyle.secondary,
            custom_id=f"suggestion:edit:{suggestion_id}",
            row=0
        )
        self.edit_button.callback = self._edit_callback
        self.add_item(self.edit_button)
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if the interaction is valid."""
        if not interaction.guild:
            return False
        return True
    
    async def _upvote_callback(self, interaction: discord.Interaction):
        """Handle upvote."""
        await self._handle_vote(interaction, "up")
    
    async def _downvote_callback(self, interaction: discord.Interaction):
        """Handle downvote."""
        await self._handle_vote(interaction, "down")
    
    async def _votes_callback(self, interaction: discord.Interaction):
        """Show detailed votes."""
        suggestion = await self.cog.storage.get_suggestion(interaction.guild, self.suggestion_id)
        if not suggestion:
            await interaction.response.send_message("❌ Sugerencia no encontrada.", ephemeral=True)
            return
        
        embed = create_votes_detail_embed(suggestion, self.cog.bot)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def _edit_callback(self, interaction: discord.Interaction):
        """Edit suggestion (author only, pending only)."""
        suggestion = await self.cog.storage.get_suggestion(interaction.guild, self.suggestion_id)
        if not suggestion:
            await interaction.response.send_message("❌ Sugerencia no encontrada.", ephemeral=True)
            return
        
        if suggestion.author_id != interaction.user.id:
            await interaction.response.send_message("❌ Solo el autor puede editar esta sugerencia.", ephemeral=True)
            return
        
        if suggestion.status != SuggestionStatus.PENDING:
            status_info = STATUS_CONFIG.get(suggestion.status, {})
            await interaction.response.send_message(
                f"❌ No puedes editar una sugerencia con estado: {status_info.get('label', suggestion.status.value)}",
                ephemeral=True
            )
            return
        
        modal = EditSuggestionModal(suggestion.content, self.suggestion_id)
        await interaction.response.send_modal(modal)
        
        if await modal.wait():
            return
        
        # Update content
        suggestion.content = modal.value
        await self.cog.storage.update_suggestion(interaction.guild, suggestion)
        
        # Update message
        author = interaction.guild.get_member(suggestion.author_id)
        embed = create_suggestion_embed(suggestion, author)
        await interaction.message.edit(embed=embed)
        
        await modal.interaction.response.send_message("✅ Sugerencia editada.", ephemeral=True)
    
    async def _handle_vote(self, interaction: discord.Interaction, vote_type: str):
        """Handle vote button press."""
        # Defer the response first
        await interaction.response.defer(ephemeral=True)
        
        result = await self.cog.storage.add_vote(
            interaction.guild,
            self.suggestion_id,
            interaction.user.id,
            vote_type
        )
        
        if not result:
            await interaction.followup.send("❌ Sugerencia no encontrada.", ephemeral=True)
            return
        
        suggestion, action = result
        
        # Create a fresh view with correct vote counts
        new_view = SuggestionView(self.cog, self.suggestion_id)
        new_view.update_vote_counts(suggestion.upvotes, suggestion.downvotes)
        
        # Disable edit if not pending
        if suggestion.status != SuggestionStatus.PENDING:
            new_view.edit_button.disabled = True
        
        # Add staff buttons
        staff_view = StaffActionsView(self.cog, self.suggestion_id)
        for item in staff_view.children:
            new_view.add_item(item)
        
        # Update message embed
        author = interaction.guild.get_member(suggestion.author_id)
        embed = create_suggestion_embed(suggestion, author)
        await interaction.message.edit(embed=embed, view=new_view)
        
        # Send ephemeral response
        response_embed = create_vote_result_embed(suggestion, action, vote_type, interaction.user)
        await interaction.followup.send(embed=response_embed, ephemeral=True)
    
    def update_vote_counts(self, upvotes: int, downvotes: int):
        """Update the vote count labels."""
        self.upvote_button.label = str(upvotes)
        self.downvote_button.label = str(downvotes)


class StaffActionsView(ui.View):
    """
    Staff-only actions view.
    Added as a second row for staff members.
    """
    
    def __init__(self, cog: "SimpleSuggestions", suggestion_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.suggestion_id = suggestion_id
        
        # Create buttons manually to guarantee order (row 1)
        self.approve_button = ui.Button(
            label="Aprobar",
            emoji="✅",
            style=discord.ButtonStyle.success,
            custom_id=f"suggestion:approve:{suggestion_id}",
            row=1
        )
        self.approve_button.callback = self._approve_callback
        self.add_item(self.approve_button)
        
        self.deny_button = ui.Button(
            label="Rechazar",
            emoji="❌",
            style=discord.ButtonStyle.danger,
            custom_id=f"suggestion:deny:{suggestion_id}",
            row=1
        )
        self.deny_button.callback = self._deny_callback
        self.add_item(self.deny_button)
        
        self.status_button = ui.Button(
            label="Cambiar estado",
            emoji="📋",
            style=discord.ButtonStyle.secondary,
            custom_id=f"suggestion:status:{suggestion_id}",
            row=1
        )
        self.status_button.callback = self._status_callback
        self.add_item(self.status_button)
    
    async def _check_staff_permission(self, interaction: discord.Interaction) -> bool:
        """Check if user has staff permissions."""
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ Este comando solo puede usarse en un servidor.",
                ephemeral=True
            )
            return False
        
        # Get the member object - interaction.user may be User or Member
        member = interaction.guild.get_member(interaction.user.id)
        
        if not member:
            # Try to fetch if not in cache
            try:
                member = await interaction.guild.fetch_member(interaction.user.id)
            except Exception:
                await interaction.response.send_message(
                    "❌ No se pudo verificar tu membresía en el servidor.",
                    ephemeral=True
                )
                return False
        
        # Check for admin permission
        if member.guild_permissions.administrator:
            return True
        
        # Check for manage_guild permission
        if member.guild_permissions.manage_guild:
            return True
        
        # Check for configured staff role
        staff_role_id = await self.cog.config.guild(interaction.guild).staff_role()
        if staff_role_id:
            member_role_ids = [r.id for r in member.roles]
            if staff_role_id in member_role_ids:
                return True
        
        await interaction.response.send_message(
            "❌ No tienes permisos para realizar esta acción.\n"
            "Necesitas ser **Administrador**, tener permiso de **Gestionar servidor**, "
            "o tener el rol de staff configurado.",
            ephemeral=True
        )
        return False
    
    async def _approve_callback(self, interaction: discord.Interaction):
        """Approve the suggestion."""
        if not await self._check_staff_permission(interaction):
            return
        await self._change_status(interaction, SuggestionStatus.APPROVED)
    
    async def _deny_callback(self, interaction: discord.Interaction):
        """Deny the suggestion."""
        if not await self._check_staff_permission(interaction):
            return
        await self._change_status(interaction, SuggestionStatus.DENIED)
    
    async def _status_callback(self, interaction: discord.Interaction):
        """Show status selection menu."""
        if not await self._check_staff_permission(interaction):
            return
        view = StatusSelectView(self.cog, self.suggestion_id)
        await interaction.response.send_message(
            "Selecciona el nuevo estado:",
            view=view,
            ephemeral=True
        )
    
    async def _change_status(self, interaction: discord.Interaction, new_status: SuggestionStatus):
        """Change suggestion status with optional reason."""
        suggestion = await self.cog.storage.get_suggestion(interaction.guild, self.suggestion_id)
        if not suggestion:
            await interaction.response.send_message("❌ Sugerencia no encontrada.", ephemeral=True)
            return
        
        old_status = suggestion.status
        
        # Show modal for reason
        modal = StatusChangeModal(new_status)
        await interaction.response.send_modal(modal)
        
        if await modal.wait():
            return
        
        # Update status
        suggestion = await self.cog.storage.update_status(
            interaction.guild,
            self.suggestion_id,
            new_status,
            interaction.user.id,
            modal.value
        )
        
        if not suggestion:
            await modal.interaction.response.send_message("❌ Error al actualizar.", ephemeral=True)
            return
        
        # Update message
        author = interaction.guild.get_member(suggestion.author_id)
        embed = create_suggestion_embed(suggestion, author)
        
        # Create new view with updated state
        user_view = SuggestionView(self.cog, self.suggestion_id)
        user_view.update_vote_counts(suggestion.upvotes, suggestion.downvotes)
        
        # Disable edit button if not pending
        if suggestion.status != SuggestionStatus.PENDING:
            user_view.edit_button.disabled = True
        
        await interaction.message.edit(embed=embed, view=user_view)
        
        # Handle thread archiving
        await self.cog._handle_thread_archive(interaction.guild, suggestion)
        
        # Notify author
        await self.cog._notify_author(interaction.guild, suggestion, old_status, interaction.user, modal.value)
        
        status_info = STATUS_CONFIG.get(new_status, {})
        await modal.interaction.response.send_message(
            f"✅ Estado cambiado a: {status_info.get('emoji', '')} {status_info.get('label', new_status.value)}",
            ephemeral=True
        )


class StatusSelectView(ui.View):
    """View with dropdown to select status."""
    
    def __init__(self, cog: "SimpleSuggestions", suggestion_id: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.suggestion_id = suggestion_id
        
        # Create options for each status
        options = []
        for status in SuggestionStatus:
            info = STATUS_CONFIG.get(status, {})
            options.append(discord.SelectOption(
                label=info.get("label", status.value),
                value=status.value,
                emoji=info.get("emoji", "")
            ))
        
        self.select = ui.Select(
            placeholder="Selecciona un estado...",
            options=options
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)
    
    async def _check_staff_permission(self, interaction: discord.Interaction) -> bool:
        """Check if user has staff permissions."""
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ Este comando solo puede usarse en un servidor.",
                ephemeral=True
            )
            return False
        
        # Get the member object - interaction.user may be User or Member
        member = interaction.guild.get_member(interaction.user.id)
        if not member:
            # Try to fetch if not in cache
            try:
                member = await interaction.guild.fetch_member(interaction.user.id)
            except Exception:
                await interaction.response.send_message(
                    "❌ No se pudo verificar tu membresía en el servidor.",
                    ephemeral=True
                )
                return False
        
        # Check for admin permission
        if member.guild_permissions.administrator:
            return True
        
        # Check for manage_guild permission
        if member.guild_permissions.manage_guild:
            return True
        
        # Check for configured staff role
        staff_role_id = await self.cog.config.guild(interaction.guild).staff_role()
        if staff_role_id:
            member_role_ids = [r.id for r in member.roles]
            if staff_role_id in member_role_ids:
                return True
        
        await interaction.response.send_message(
            "❌ No tienes permisos para realizar esta acción.\n"
            "Necesitas ser **Administrador**, tener permiso de **Gestionar servidor**, "
            "o tener el rol de staff configurado.",
            ephemeral=True
        )
        return False
    
    async def select_callback(self, interaction: discord.Interaction):
        """Handle status selection."""
        # Check permissions first
        if not await self._check_staff_permission(interaction):
            return
        
        selected_value = self.select.values[0]
        new_status = SuggestionStatus(selected_value)
        
        suggestion = await self.cog.storage.get_suggestion(interaction.guild, self.suggestion_id)
        if not suggestion:
            await interaction.response.send_message("❌ Sugerencia no encontrada.", ephemeral=True)
            return
        
        old_status = suggestion.status
        
        # Show modal for reason
        modal = StatusChangeModal(new_status)
        await interaction.response.send_modal(modal)
        
        if await modal.wait():
            return
        
        # Update status
        suggestion = await self.cog.storage.update_status(
            interaction.guild,
            self.suggestion_id,
            new_status,
            interaction.user.id,
            modal.value
        )
        
        if suggestion:
            # Notify author
            await self.cog._notify_author(interaction.guild, suggestion, old_status, interaction.user, modal.value)
            
            status_info = STATUS_CONFIG.get(new_status, {})
            await modal.interaction.response.send_message(
                f"✅ Estado cambiado a: {status_info.get('emoji', '')} {status_info.get('label', new_status.value)}",
                ephemeral=True
            )
        else:
            await modal.interaction.response.send_message("❌ Error al actualizar.", ephemeral=True)


# ==================== PAGINATION VIEW ====================

class SuggestionListView(ui.View):
    """Paginated view for listing suggestions."""
    
    def __init__(
        self,
        cog: "SimpleSuggestions",
        suggestions: list,
        page: int = 1,
        per_page: int = 10,
        status_filter: Optional[SuggestionStatus] = None
    ):
        super().__init__(timeout=120)
        self.cog = cog
        self.all_suggestions = suggestions
        self.page = page
        self.per_page = per_page
        self.status_filter = status_filter
        self.total_pages = max(1, (len(suggestions) + per_page - 1) // per_page)
        
        self._update_buttons()
    
    def _update_buttons(self):
        self.prev_button.disabled = self.page <= 1
        self.next_button.disabled = self.page >= self.total_pages
        self.page_label.label = f"{self.page}/{self.total_pages}"
    
    def get_current_page_items(self) -> list:
        start = (self.page - 1) * self.per_page
        end = start + self.per_page
        return self.all_suggestions[start:end]
    
    @ui.button(emoji="⬅️", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: ui.Button):
        self.page = max(1, self.page - 1)
        self._update_buttons()
        await self._update_message(interaction)
    
    @ui.button(label="1/1", style=discord.ButtonStyle.secondary, disabled=True)
    async def page_label(self, interaction: discord.Interaction, button: ui.Button):
        pass
    
    @ui.button(emoji="➡️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: ui.Button):
        self.page = min(self.total_pages, self.page + 1)
        self._update_buttons()
        await self._update_message(interaction)
    
    async def _update_message(self, interaction: discord.Interaction):
        from .embeds import create_suggestion_list_embed
        
        current_items = self.get_current_page_items()
        embed = create_suggestion_list_embed(
            current_items,
            self.page,
            self.total_pages,
            self.status_filter
        )
        await interaction.response.edit_message(embed=embed, view=self)


# ==================== SETUP FUNCTIONS ====================

async def setup_persistent_views(bot: "Red", cog: "SimpleSuggestions"):
    """
    Register all persistent views for the cog.
    Called on cog load to restore button functionality.
    """
    logger.info("Setting up persistent views for SimpleSuggestions")
    # Nothing to do here anymore - the handler is in the cog itself
    logger.info("Persistent views setup complete")


async def cleanup_persistent_views(bot: "Red", cog: "SimpleSuggestions"):
    """Remove the persistent view handler on cog unload."""
    # Nothing to do here anymore - the handler is in the cog itself
    logger.info("Persistent views cleaned up")


async def handle_suggestion_interaction(cog: "SimpleSuggestions", interaction: discord.Interaction):
    """
    Handle suggestion button interactions.
    This is called from the cog's on_interaction listener.
    """
    if interaction.type != discord.InteractionType.component:
        return False
    
    custom_id = interaction.data.get("custom_id", "")
    if not custom_id.startswith("suggestion:"):
        return False
    
    parts = custom_id.split(":")
    if len(parts) < 3:
        return False
    
    action = parts[1]
    try:
        suggestion_id = int(parts[2])
    except ValueError:
        return False
    
    # Check if interaction was already responded to
    if interaction.response.is_done():
        logger.warning(f"Interaction already responded to for action {action}")
        return True
    
    try:
        # Create the appropriate view and handle the interaction
        if action in ["upvote", "downvote", "votes", "edit"]:
            view = SuggestionView(cog, suggestion_id)
            if action == "upvote":
                await view._handle_vote(interaction, "up")
            elif action == "downvote":
                await view._handle_vote(interaction, "down")
            elif action == "votes":
                await view.votes_button.callback(interaction)
            elif action == "edit":
                await view.edit_button.callback(interaction)
        
        elif action in ["approve", "deny", "status"]:
            view = StaffActionsView(cog, suggestion_id)
            
            # Check staff permission first
            if not await view._check_staff_permission(interaction):
                return True  # Handled, but denied
            
            if action == "approve":
                await view._change_status(interaction, SuggestionStatus.APPROVED)
            elif action == "deny":
                await view._change_status(interaction, SuggestionStatus.DENIED)
            elif action == "status":
                # Permission already checked, show the status select menu
                status_view = StatusSelectView(cog, suggestion_id)
                await interaction.response.send_message(
                    "Selecciona el nuevo estado:",
                    view=status_view,
                    ephemeral=True
                )
        
        return True  # Interaction handled
        
    except discord.errors.HTTPException as e:
        if e.code == 40060:  # Interaction already acknowledged
            logger.warning(f"Interaction already acknowledged for {action}")
            return True
        raise
