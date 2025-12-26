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
        # Note: No callbacks assigned - all handled by handle_suggestion_interaction
        self.upvote_button = ui.Button(
            label="0",
            emoji="👍",
            style=discord.ButtonStyle.success,
            custom_id=f"suggestion:upvote:{suggestion_id}",
            row=0
        )
        self.add_item(self.upvote_button)
        
        self.downvote_button = ui.Button(
            label="0",
            emoji="👎",
            style=discord.ButtonStyle.danger,
            custom_id=f"suggestion:downvote:{suggestion_id}",
            row=0
        )
        self.add_item(self.downvote_button)
        
        self.votes_button = ui.Button(
            label="Ver votos",
            emoji="📊",
            style=discord.ButtonStyle.secondary,
            custom_id=f"suggestion:votes:{suggestion_id}",
            row=0
        )
        self.add_item(self.votes_button)
        
        self.edit_button = ui.Button(
            label="Editar",
            emoji="✏️",
            style=discord.ButtonStyle.secondary,
            custom_id=f"suggestion:edit:{suggestion_id}",
            row=0
        )
        self.add_item(self.edit_button)
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if the interaction is valid."""
        if not interaction.guild:
            return False
        return True
    
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
        # Note: No callbacks assigned - all handled by handle_suggestion_interaction
        self.approve_button = ui.Button(
            label="Aprobar",
            emoji="✅",
            style=discord.ButtonStyle.success,
            custom_id=f"suggestion:approve:{suggestion_id}",
            row=1
        )
        self.add_item(self.approve_button)
        
        self.deny_button = ui.Button(
            label="Rechazar",
            emoji="❌",
            style=discord.ButtonStyle.danger,
            custom_id=f"suggestion:deny:{suggestion_id}",
            row=1
        )
        self.add_item(self.deny_button)
        
        self.status_button = ui.Button(
            label="Cambiar estado",
            emoji="📋",
            style=discord.ButtonStyle.secondary,
            custom_id=f"suggestion:status:{suggestion_id}",
            row=1
        )
        self.add_item(self.status_button)


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
            options=options,
            custom_id=f"suggestion:select_status:{suggestion_id}"
        )
        self.select.callback = self.on_select
        self.add_item(self.select)
    
    async def on_select(self, interaction: discord.Interaction):
        """Handle status selection from dropdown."""
        # Direct print to ensure we see this even if logger fails
        print(f"[DEBUG] StatusSelectView.on_select called! suggestion_id={self.suggestion_id}")
        logger.info(f"StatusSelectView.on_select called for suggestion #{self.suggestion_id}")
        logger.info(f"Selected values: {self.select.values}")
        
        # Check staff permission
        if not await _check_staff_permission_standalone(self.cog, interaction):
            logger.info("Staff permission check failed")
            return
        
        selected_value = self.select.values[0]
        new_status = SuggestionStatus(selected_value)
        
        suggestion = await self.cog.storage.get_suggestion(interaction.guild, self.suggestion_id)
        if not suggestion:
            await interaction.response.send_message("❌ Sugerencia no encontrada.", ephemeral=True)
            return
        
        old_status = suggestion.status
        
        # Check if trying to set the same status
        if old_status == new_status:
            status_info = STATUS_CONFIG.get(new_status, {})
            await interaction.response.send_message(
                f"ℹ️ La sugerencia ya tiene el estado: {status_info.get('emoji', '')} {status_info.get('label', new_status.value)}",
                ephemeral=True
            )
            return
        
        # Show modal for reason
        modal = StatusChangeModal(new_status)
        await interaction.response.send_modal(modal)
        
        if await modal.wait():
            logger.info(f"Modal timed out for suggestion #{self.suggestion_id}")
            return
        
        # Update status
        print(f"[DEBUG] About to update status for #{self.suggestion_id}")
        logger.info(f"Updating status for suggestion #{self.suggestion_id} to {new_status.value}")
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
        
        print(f"[DEBUG] Status updated, now updating embed for #{self.suggestion_id}")
        # Update the original suggestion message embed
        logger.info(f"Updating embed for suggestion #{self.suggestion_id}")
        try:
            channel_id = await self.cog.config.guild(interaction.guild).suggestion_channel()
            print(f"[DEBUG] Channel ID: {channel_id}")
            logger.info(f"Channel ID from config: {channel_id}")
            if channel_id:
                channel = interaction.guild.get_channel(channel_id)
                print(f"[DEBUG] Channel: {channel}, message_id: {suggestion.message_id}")
                logger.info(f"Channel object: {channel}, message_id: {suggestion.message_id}")
                if channel and suggestion.message_id:
                    try:
                        original_message = await channel.fetch_message(suggestion.message_id)
                        print(f"[DEBUG] Fetched message: {original_message.id}")
                        logger.info(f"Fetched original message: {original_message.id}")
                        
                        author = interaction.guild.get_member(suggestion.author_id)
                        embed = create_suggestion_embed(suggestion, author)
                        print(f"[DEBUG] Created embed, color: {embed.color}")
                        logger.info(f"Created embed with color: {embed.color}")
                        
                        user_view = SuggestionView(self.cog, self.suggestion_id)
                        user_view.update_vote_counts(suggestion.upvotes, suggestion.downvotes)
                        if suggestion.status != SuggestionStatus.PENDING:
                            user_view.edit_button.disabled = True
                        
                        staff_view = StaffActionsView(self.cog, self.suggestion_id)
                        for item in staff_view.children:
                            user_view.add_item(item)
                        
                        print(f"[DEBUG] About to edit message {original_message.id}")
                        logger.info(f"About to edit message {original_message.id}")
                        await original_message.edit(embed=embed, view=user_view)
                        print(f"[DEBUG] SUCCESS! Embed updated for #{self.suggestion_id}")
                        logger.info(f"Successfully updated embed for suggestion #{self.suggestion_id}")
                    except discord.NotFound:
                        print(f"[DEBUG] ERROR: Message not found")
                        logger.warning(f"Original message not found for suggestion #{self.suggestion_id}")
                    except discord.Forbidden:
                        print(f"[DEBUG] ERROR: No permission")
                        logger.warning(f"No permission to edit message for suggestion #{self.suggestion_id}")
                    except Exception as inner_e:
                        print(f"[DEBUG] ERROR editing: {inner_e}")
                        logger.error(f"Error editing message: {inner_e}", exc_info=True)
                else:
                    print(f"[DEBUG] Channel or message_id missing")
                    logger.warning(f"Channel or message_id missing: channel={channel}, message_id={suggestion.message_id}")
            else:
                print(f"[DEBUG] No suggestion channel configured")
                logger.warning(f"No suggestion channel configured for guild {interaction.guild.id}")
        except Exception as e:
            print(f"[DEBUG] EXCEPTION: {e}")
            logger.error(f"Error updating suggestion message: {e}", exc_info=True)
        
        # Handle thread archiving
        await self.cog._handle_thread_archive(interaction.guild, suggestion)
        
        # Notify author
        await self.cog._notify_author(interaction.guild, suggestion, old_status, interaction.user, modal.value)
        
        status_info = STATUS_CONFIG.get(new_status, {})
        await modal.interaction.response.send_message(
            f"✅ Estado cambiado a: {status_info.get('emoji', '')} {status_info.get('label', new_status.value)}",
            ephemeral=True
        )


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


async def _check_staff_permission_standalone(cog: "SimpleSuggestions", interaction: discord.Interaction) -> bool:
    """Check if user has staff permissions without using a View."""
    if not interaction.guild:
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "❌ Este comando solo puede usarse en un servidor.",
                ephemeral=True
            )
        return False
    
    member = interaction.guild.get_member(interaction.user.id)
    if not member:
        try:
            member = await interaction.guild.fetch_member(interaction.user.id)
        except Exception:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ No se pudo verificar tu membresía en el servidor.",
                    ephemeral=True
                )
            return False
    
    # Check for admin or manage_guild permission
    if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
        return True
    
    # Check for configured staff role
    staff_role_id = await cog.config.guild(interaction.guild).staff_role()
    if staff_role_id:
        member_role_ids = [r.id for r in member.roles]
        if staff_role_id in member_role_ids:
            return True
    
    if not interaction.response.is_done():
        await interaction.response.send_message(
            "❌ No tienes permisos para realizar esta acción.\n"
            "Necesitas ser **Administrador**, tener permiso de **Gestionar servidor**, "
            "o tener el rol de staff configurado.",
            ephemeral=True
        )
    return False


async def _handle_status_change(cog: "SimpleSuggestions", interaction: discord.Interaction, suggestion_id: int, new_status: SuggestionStatus):
    """Handle status change with modal for reason."""
    suggestion = await cog.storage.get_suggestion(interaction.guild, suggestion_id)
    if not suggestion:
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Sugerencia no encontrada.", ephemeral=True)
        return
    
    old_status = suggestion.status
    
    # Show modal for reason
    modal = StatusChangeModal(new_status)
    if not interaction.response.is_done():
        await interaction.response.send_modal(modal)
    else:
        logger.warning(f"Cannot show modal - interaction already done")
        return
    
    if await modal.wait():
        return
    
    # Update status
    suggestion = await cog.storage.update_status(
        interaction.guild,
        suggestion_id,
        new_status,
        interaction.user.id,
        modal.value
    )
    
    if not suggestion:
        await modal.interaction.response.send_message("❌ Error al actualizar.", ephemeral=True)
        return
    
    # Update message embed
    try:
        channel_id = await cog.config.guild(interaction.guild).suggestion_channel()
        if channel_id:
            channel = interaction.guild.get_channel(channel_id)
            if channel and suggestion.message_id:
                try:
                    original_message = await channel.fetch_message(suggestion.message_id)
                    author = interaction.guild.get_member(suggestion.author_id)
                    embed = create_suggestion_embed(suggestion, author)
                    
                    user_view = SuggestionView(cog, suggestion_id)
                    user_view.update_vote_counts(suggestion.upvotes, suggestion.downvotes)
                    if suggestion.status != SuggestionStatus.PENDING:
                        user_view.edit_button.disabled = True
                    
                    staff_view = StaffActionsView(cog, suggestion_id)
                    for item in staff_view.children:
                        user_view.add_item(item)
                    
                    await original_message.edit(embed=embed, view=user_view)
                    logger.info(f"Updated embed for suggestion #{suggestion_id}")
                except discord.NotFound:
                    logger.warning(f"Original message not found for suggestion #{suggestion_id}")
                except discord.Forbidden:
                    logger.warning(f"No permission to edit message for suggestion #{suggestion_id}")
    except Exception as e:
        logger.error(f"Error updating suggestion message: {e}", exc_info=True)
    
    # Handle thread archiving
    await cog._handle_thread_archive(interaction.guild, suggestion)
    
    # Notify author
    await cog._notify_author(interaction.guild, suggestion, old_status, interaction.user, modal.value)
    
    status_info = STATUS_CONFIG.get(new_status, {})
    await modal.interaction.response.send_message(
        f"✅ Estado cambiado a: {status_info.get('emoji', '')} {status_info.get('label', new_status.value)}",
        ephemeral=True
    )


async def handle_suggestion_interaction(cog: "SimpleSuggestions", interaction: discord.Interaction):
    """
    Handle suggestion button interactions.
    This is called from the cog's on_interaction listener.
    """
    if interaction.type != discord.InteractionType.component:
        return False
    
    custom_id = interaction.data.get("custom_id", "")
    logger.debug(f"Received interaction with custom_id: {custom_id}")
    
    if not custom_id.startswith("suggestion:"):
        return False
    
    parts = custom_id.split(":")
    if len(parts) < 3:
        return False
    
    action = parts[1]
    
    # select_status is handled by StatusSelectView.on_select callback
    # Return False to let Discord.py handle it via the View
    if action == "select_status":
        logger.debug(f"Ignoring select_status - handled by View callback")
        return False
    
    try:
        suggestion_id = int(parts[2])
    except ValueError:
        return False
    
    logger.info(f"Processing suggestion interaction: action={action}, suggestion_id={suggestion_id}")
    
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
                await view._votes_callback(interaction)
            elif action == "edit":
                await view._edit_callback(interaction)
        
        elif action in ["approve", "deny", "status"]:
            # Check staff permission first
            if not await _check_staff_permission_standalone(cog, interaction):
                return True  # Handled, but denied
            
            logger.info(f"Staff permission OK for {action}, is_done={interaction.response.is_done()}")
            
            if action == "approve":
                await _handle_status_change(cog, interaction, suggestion_id, SuggestionStatus.APPROVED)
            elif action == "deny":
                await _handle_status_change(cog, interaction, suggestion_id, SuggestionStatus.DENIED)
            elif action == "status":
                # Show the status select menu
                logger.info(f"Showing status select menu for suggestion #{suggestion_id}")
                status_view = StatusSelectView(cog, suggestion_id)
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "Selecciona el nuevo estado:",
                        view=status_view,
                        ephemeral=True
                    )
                    logger.info(f"Status select menu sent successfully")
                else:
                    logger.warning(f"Cannot send status menu - interaction already done")
        
        # Note: select_status is handled by StatusSelectView.on_select callback
        
        return True  # Interaction handled
        
    except discord.errors.HTTPException as e:
        if e.code == 40060:  # Interaction already acknowledged
            logger.warning(f"Interaction already acknowledged for {action}")
            return True
        raise
