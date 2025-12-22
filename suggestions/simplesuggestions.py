"""
SimpleSuggestions - A comprehensive suggestion system for Discord.
By Killerbite95

Features:
- Interactive buttons for voting and management
- Persistent views (buttons work after bot restart)
- Atomic counter (no duplicate IDs)
- Multiple status states with history tracking
- Staff notifications and author DMs
- Dashboard integration
"""
import discord
from redbot.core import commands, Config, checks, app_commands
from redbot.core.bot import Red
from typing import Optional, Union
import logging
import re
from datetime import datetime

from .storage import (
    SuggestionStorage,
    SuggestionStatus,
    STATUS_CONFIG,
    CURRENT_SCHEMA_VERSION,
    migrate_schema,
)
from .embeds import (
    create_suggestion_embed,
    create_status_change_embed,
    create_suggestion_list_embed,
    create_history_embed,
)
from .views import (
    SuggestionView,
    StaffActionsView,
    SuggestionModal,
    SuggestionListView,
    setup_persistent_views,
    cleanup_persistent_views,
)
from .dashboard_integration import DashboardIntegration, dashboard_page

logger = logging.getLogger("red.killerbite95.suggestions")


class SimpleSuggestions(DashboardIntegration, commands.Cog):
    """
    Sistema de sugerencias completo con botones interactivos, votaciones persistentes,
    múltiples estados y panel de control web.
    
    By Killerbite95
    """
    __author__ = "Killerbite95"
    __version__ = "2.0.0"
    
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        
        default_guild = {
            # Channels
            "suggestion_channel": None,
            "log_channel": None,
            
            # Features
            "use_buttons": True,  # True = buttons, False = reactions
            "suggestion_threads": False,
            "thread_auto_archive": False,
            "thread_archive_duration": 1440,  # minutes: 60, 1440, 4320, 10080
            "thread_on_votes": 0,  # Create thread when reaching X votes (0 = always)
            
            # Notifications
            "notify_author": True,
            "notify_channel": None,  # Alternative to DM
            
            # Permissions
            "staff_role": None,
            
            # Data
            "suggestion_counter": 0,
            "suggestions": {},
            "schema_version": CURRENT_SCHEMA_VERSION,
            
            # Legacy (for migration)
            "suggestion_id": 0,
        }
        self.config.register_guild(**default_guild)
        
        # Initialize storage handler
        self.storage = SuggestionStorage(bot, self.config)
        
        # Persistent view handler reference
        self._persistent_view_handler = None
    
    async def cog_load(self):
        """Called when cog is loaded."""
        await setup_persistent_views(self.bot, self)
        logger.info(f"SimpleSuggestions v{self.__version__} loaded")
    
    async def cog_unload(self):
        """Called when cog is unloaded."""
        await cleanup_persistent_views(self.bot, self)
        logger.info("SimpleSuggestions unloaded")
    
    # ==================== HELPER METHODS ====================
    
    async def _ensure_migrated(self, guild: discord.Guild):
        """Ensure guild data is migrated to latest schema."""
        await migrate_schema(self.config, guild)
    
    async def _get_suggestion_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Get the configured suggestion channel."""
        channel_id = await self.config.guild(guild).suggestion_channel()
        if channel_id:
            return guild.get_channel(channel_id)
        return None
    
    async def _parse_suggestion_reference(
        self,
        guild: discord.Guild,
        reference: str
    ) -> Optional[int]:
        """
        Parse a suggestion reference which can be:
        - #123 (suggestion ID)
        - 1234567890 (message ID)
        - https://discord.com/channels/.../... (message URL)
        
        Returns the suggestion_id or None.
        """
        reference = reference.strip()
        
        # Check for #ID format
        if reference.startswith("#"):
            try:
                return int(reference[1:])
            except ValueError:
                pass
        
        # Check for message URL
        url_pattern = r"https?://(?:ptb\.|canary\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)"
        match = re.match(url_pattern, reference)
        if match:
            message_id = int(match.group(3))
            suggestion = await self.storage.get_suggestion_by_message(guild, message_id)
            if suggestion:
                return suggestion.suggestion_id
            return None
        
        # Try as raw number (could be suggestion_id or message_id)
        try:
            num = int(reference)
            # First try as suggestion_id
            suggestion = await self.storage.get_suggestion(guild, num)
            if suggestion:
                return num
            # Then try as message_id
            suggestion = await self.storage.get_suggestion_by_message(guild, num)
            if suggestion:
                return suggestion.suggestion_id
        except ValueError:
            pass
        
        return None
    
    async def _notify_author(
        self,
        guild: discord.Guild,
        suggestion,
        old_status: SuggestionStatus,
        changed_by: discord.Member,
        reason: Optional[str] = None
    ):
        """Notify the suggestion author about status change."""
        if not await self.config.guild(guild).notify_author():
            return
        
        author = guild.get_member(suggestion.author_id)
        if not author:
            return
        
        embed = create_status_change_embed(suggestion, old_status, changed_by, reason)
        
        # Try DM first
        try:
            await author.send(embed=embed)
            return
        except (discord.Forbidden, discord.HTTPException):
            pass
        
        # Fallback to notification channel
        notify_channel_id = await self.config.guild(guild).notify_channel()
        if notify_channel_id:
            channel = guild.get_channel(notify_channel_id)
            if channel:
                try:
                    await channel.send(f"{author.mention}", embed=embed)
                except discord.HTTPException:
                    pass
    
    async def _handle_thread_archive(self, guild: discord.Guild, suggestion):
        """Handle thread archiving when suggestion is resolved."""
        if not await self.config.guild(guild).thread_auto_archive():
            return
        
        if suggestion.status not in [
            SuggestionStatus.APPROVED,
            SuggestionStatus.DENIED,
            SuggestionStatus.IMPLEMENTED,
            SuggestionStatus.WONT_DO,
            SuggestionStatus.DUPLICATE,
        ]:
            return
        
        if not suggestion.thread_id:
            return
        
        thread = guild.get_thread(suggestion.thread_id)
        if thread:
            try:
                await thread.edit(archived=True, locked=True)
            except discord.HTTPException:
                pass
    
    async def _create_suggestion_message(
        self,
        channel: discord.TextChannel,
        suggestion,
        author: discord.Member
    ) -> discord.Message:
        """Create the suggestion message with embed and view."""
        embed = create_suggestion_embed(suggestion, author)
        
        use_buttons = await self.config.guild(channel.guild).use_buttons()
        
        if use_buttons:
            # Create view with buttons
            view = SuggestionView(self, suggestion.suggestion_id)
            view.update_vote_counts(0, 0)
            
            # Add staff buttons
            staff_view = StaffActionsView(self, suggestion.suggestion_id)
            
            # Combine views (add staff buttons to user view)
            for item in staff_view.children:
                view.add_item(item)
            
            message = await channel.send(embed=embed, view=view)
        else:
            # Legacy: use reactions
            message = await channel.send(embed=embed)
            await message.add_reaction("👍")
            await message.add_reaction("👎")
        
        return message
    
    # ==================== USER COMMANDS ====================
    
    @commands.hybrid_command(name="suggest")
    @app_commands.describe(suggestion="Tu sugerencia")
    async def suggest(self, ctx: commands.Context, *, suggestion: Optional[str] = None):
        """
        Envía una nueva sugerencia.
        
        Puedes escribir la sugerencia directamente o usar el modal interactivo.
        
        **Ejemplos:**
        - `[p]suggest Añadir más emojis al servidor`
        - `[p]suggest` (abre un modal para escribir)
        """
        await self._ensure_migrated(ctx.guild)
        
        channel = await self._get_suggestion_channel(ctx.guild)
        if not channel:
            await ctx.send("❌ El canal de sugerencias no ha sido configurado.", ephemeral=True)
            return
        
        # If no suggestion provided, show modal (only works with slash commands)
        if not suggestion:
            if ctx.interaction:
                modal = SuggestionModal()
                await ctx.interaction.response.send_modal(modal)
                if await modal.wait():
                    return
                suggestion = modal.value
                # Use followup since we already responded with modal
                respond = modal.interaction.followup.send
            else:
                await ctx.send("❌ Por favor, incluye tu sugerencia: `[p]suggest <tu sugerencia>`")
                return
        else:
            respond = ctx.send
        
        # Create suggestion in storage
        suggestion_data = await self.storage.create_suggestion(
            ctx.guild,
            message_id=0,  # Will be updated after message is sent
            content=suggestion,
            author_id=ctx.author.id
        )
        
        # Create message
        message = await self._create_suggestion_message(channel, suggestion_data, ctx.author)
        
        # Update with correct message_id
        suggestion_data.message_id = message.id
        
        # Handle thread creation
        create_thread = await self.config.guild(ctx.guild).suggestion_threads()
        threshold = await self.config.guild(ctx.guild).thread_on_votes()
        
        if create_thread and threshold == 0:
            try:
                duration = await self.config.guild(ctx.guild).thread_archive_duration()
                thread = await message.create_thread(
                    name=f"Sugerencia #{suggestion_data.suggestion_id}",
                    auto_archive_duration=duration
                )
                suggestion_data.thread_id = thread.id
            except discord.HTTPException as e:
                logger.warning(f"Could not create thread: {e}")
        
        await self.storage.update_suggestion(ctx.guild, suggestion_data)
        
        await respond(
            f"✅ Tu sugerencia **#{suggestion_data.suggestion_id}** ha sido enviada en {channel.mention}",
            ephemeral=True
        )
    
    @commands.hybrid_command(name="editsuggest")
    @app_commands.describe(
        reference="ID de sugerencia (#123), ID de mensaje, o link del mensaje",
        new_content="Nuevo contenido de la sugerencia"
    )
    async def edit_suggestion(
        self,
        ctx: commands.Context,
        reference: str,
        *,
        new_content: str
    ):
        """
        Edita tu propia sugerencia (solo si está pendiente).
        
        **Ejemplos:**
        - `[p]editsuggest #123 Nuevo texto de mi sugerencia`
        - `[p]editsuggest 1234567890 Nuevo texto`
        """
        await self._ensure_migrated(ctx.guild)
        
        suggestion_id = await self._parse_suggestion_reference(ctx.guild, reference)
        if not suggestion_id:
            await ctx.send("❌ No se encontró esa sugerencia.", ephemeral=True)
            return
        
        suggestion = await self.storage.get_suggestion(ctx.guild, suggestion_id)
        if not suggestion:
            await ctx.send("❌ Sugerencia no encontrada.", ephemeral=True)
            return
        
        if suggestion.author_id != ctx.author.id:
            await ctx.send("❌ Solo puedes editar tus propias sugerencias.", ephemeral=True)
            return
        
        if suggestion.status != SuggestionStatus.PENDING:
            status_info = STATUS_CONFIG.get(suggestion.status, {})
            await ctx.send(
                f"❌ No puedes editar una sugerencia con estado: {status_info.get('label', suggestion.status.value)}",
                ephemeral=True
            )
            return
        
        # Update content
        suggestion.content = new_content
        await self.storage.update_suggestion(ctx.guild, suggestion)
        
        # Update message
        channel = await self._get_suggestion_channel(ctx.guild)
        if channel:
            try:
                message = await channel.fetch_message(suggestion.message_id)
                author = ctx.guild.get_member(suggestion.author_id)
                embed = create_suggestion_embed(suggestion, author)
                await message.edit(embed=embed)
            except discord.NotFound:
                pass
        
        await ctx.send("✅ Tu sugerencia ha sido editada.", ephemeral=True)
    
    @commands.hybrid_command(name="mysuggestions")
    async def my_suggestions(self, ctx: commands.Context):
        """Ver tus propias sugerencias."""
        await self._ensure_migrated(ctx.guild)
        
        suggestions = await self.storage.get_all_suggestions(
            ctx.guild,
            author_filter=ctx.author.id
        )
        
        if not suggestions:
            await ctx.send("No tienes sugerencias.", ephemeral=True)
            return
        
        view = SuggestionListView(self, suggestions)
        embed = create_suggestion_list_embed(
            view.get_current_page_items(),
            view.page,
            view.total_pages
        )
        await ctx.send(embed=embed, view=view, ephemeral=True)
    
    # ==================== STAFF COMMANDS ====================
    
    @commands.hybrid_command(name="approve")
    @checks.admin_or_permissions(manage_guild=True)
    @app_commands.describe(
        reference="ID de sugerencia (#123), ID de mensaje, o link",
        reason="Motivo de la aprobación (opcional)"
    )
    async def approve_suggestion(
        self,
        ctx: commands.Context,
        reference: str,
        *,
        reason: Optional[str] = None
    ):
        """
        Aprueba una sugerencia.
        
        **Ejemplos:**
        - `[p]approve #123`
        - `[p]approve #123 Buena idea, lo implementaremos`
        """
        await self._change_suggestion_status(
            ctx, reference, SuggestionStatus.APPROVED, reason
        )
    
    @commands.hybrid_command(name="deny")
    @checks.admin_or_permissions(manage_guild=True)
    @app_commands.describe(
        reference="ID de sugerencia (#123), ID de mensaje, o link",
        reason="Motivo del rechazo (opcional)"
    )
    async def deny_suggestion(
        self,
        ctx: commands.Context,
        reference: str,
        *,
        reason: Optional[str] = None
    ):
        """
        Rechaza una sugerencia.
        
        **Ejemplos:**
        - `[p]deny #123`
        - `[p]deny #123 No es viable actualmente`
        """
        await self._change_suggestion_status(
            ctx, reference, SuggestionStatus.DENIED, reason
        )
    
    @commands.hybrid_command(name="setstatus")
    @checks.admin_or_permissions(manage_guild=True)
    @app_commands.describe(
        reference="ID de sugerencia (#123), ID de mensaje, o link",
        status="Nuevo estado",
        reason="Motivo del cambio (opcional)"
    )
    @app_commands.choices(status=[
        app_commands.Choice(name="Pendiente", value="pending"),
        app_commands.Choice(name="En revisión", value="in_review"),
        app_commands.Choice(name="Planeado", value="planned"),
        app_commands.Choice(name="En progreso", value="in_progress"),
        app_commands.Choice(name="Aprobado", value="approved"),
        app_commands.Choice(name="Implementado", value="implemented"),
        app_commands.Choice(name="Rechazado", value="denied"),
        app_commands.Choice(name="Duplicado", value="duplicate"),
        app_commands.Choice(name="No se hará", value="wont_do"),
    ])
    async def set_status(
        self,
        ctx: commands.Context,
        reference: str,
        status: str,
        *,
        reason: Optional[str] = None
    ):
        """
        Cambia el estado de una sugerencia.
        
        **Estados disponibles:**
        pending, in_review, planned, in_progress, approved, implemented, denied, duplicate, wont_do
        """
        try:
            new_status = SuggestionStatus(status)
        except ValueError:
            await ctx.send(f"❌ Estado inválido: {status}", ephemeral=True)
            return
        
        await self._change_suggestion_status(ctx, reference, new_status, reason)
    
    async def _change_suggestion_status(
        self,
        ctx: commands.Context,
        reference: str,
        new_status: SuggestionStatus,
        reason: Optional[str]
    ):
        """Helper to change suggestion status."""
        await self._ensure_migrated(ctx.guild)
        
        suggestion_id = await self._parse_suggestion_reference(ctx.guild, reference)
        if not suggestion_id:
            await ctx.send("❌ No se encontró esa sugerencia.", ephemeral=True)
            return
        
        suggestion = await self.storage.get_suggestion(ctx.guild, suggestion_id)
        if not suggestion:
            await ctx.send("❌ Sugerencia no encontrada.", ephemeral=True)
            return
        
        old_status = suggestion.status
        
        # Update status
        suggestion = await self.storage.update_status(
            ctx.guild,
            suggestion_id,
            new_status,
            ctx.author.id,
            reason
        )
        
        # Update message
        channel = await self._get_suggestion_channel(ctx.guild)
        if channel:
            try:
                message = await channel.fetch_message(suggestion.message_id)
                author = ctx.guild.get_member(suggestion.author_id)
                embed = create_suggestion_embed(suggestion, author)
                
                use_buttons = await self.config.guild(ctx.guild).use_buttons()
                if use_buttons:
                    view = SuggestionView(self, suggestion_id)
                    view.update_vote_counts(suggestion.upvotes, suggestion.downvotes)
                    if suggestion.status != SuggestionStatus.PENDING:
                        view.edit_button.disabled = True
                    
                    staff_view = StaffActionsView(self, suggestion_id)
                    for item in staff_view.children:
                        view.add_item(item)
                    
                    await message.edit(embed=embed, view=view)
                else:
                    await message.edit(embed=embed)
            except discord.NotFound:
                pass
        
        # Handle thread
        await self._handle_thread_archive(ctx.guild, suggestion)
        
        # Notify author
        await self._notify_author(ctx.guild, suggestion, old_status, ctx.author, reason)
        
        status_info = STATUS_CONFIG.get(new_status, {})
        await ctx.send(
            f"✅ Sugerencia #{suggestion_id} actualizada a: {status_info.get('emoji', '')} {status_info.get('label', new_status.value)}",
            ephemeral=True
        )
    
    @commands.hybrid_command(name="suggestions")
    @checks.admin_or_permissions(manage_guild=True)
    @app_commands.describe(status="Filtrar por estado")
    @app_commands.choices(status=[
        app_commands.Choice(name="Todos", value="all"),
        app_commands.Choice(name="Pendiente", value="pending"),
        app_commands.Choice(name="En revisión", value="in_review"),
        app_commands.Choice(name="Planeado", value="planned"),
        app_commands.Choice(name="En progreso", value="in_progress"),
        app_commands.Choice(name="Aprobado", value="approved"),
        app_commands.Choice(name="Implementado", value="implemented"),
        app_commands.Choice(name="Rechazado", value="denied"),
    ])
    async def list_suggestions(
        self,
        ctx: commands.Context,
        status: Optional[str] = "all"
    ):
        """Lista las sugerencias del servidor."""
        await self._ensure_migrated(ctx.guild)
        
        status_filter = None
        if status and status != "all":
            try:
                status_filter = SuggestionStatus(status)
            except ValueError:
                pass
        
        suggestions = await self.storage.get_all_suggestions(
            ctx.guild,
            status_filter=status_filter
        )
        
        if not suggestions:
            await ctx.send("No hay sugerencias.", ephemeral=True)
            return
        
        view = SuggestionListView(self, suggestions, status_filter=status_filter)
        embed = create_suggestion_list_embed(
            view.get_current_page_items(),
            view.page,
            view.total_pages,
            status_filter
        )
        await ctx.send(embed=embed, view=view)
    
    @commands.hybrid_command(name="suggestioninfo")
    @app_commands.describe(reference="ID de sugerencia (#123), ID de mensaje, o link")
    async def suggestion_info(self, ctx: commands.Context, reference: str):
        """Ver información detallada de una sugerencia."""
        await self._ensure_migrated(ctx.guild)
        
        suggestion_id = await self._parse_suggestion_reference(ctx.guild, reference)
        if not suggestion_id:
            await ctx.send("❌ No se encontró esa sugerencia.", ephemeral=True)
            return
        
        suggestion = await self.storage.get_suggestion(ctx.guild, suggestion_id)
        if not suggestion:
            await ctx.send("❌ Sugerencia no encontrada.", ephemeral=True)
            return
        
        author = ctx.guild.get_member(suggestion.author_id)
        embed = create_suggestion_embed(suggestion, author)
        
        # Add extra info
        embed.add_field(
            name="📝 Información adicional",
            value=f"**Message ID:** {suggestion.message_id}\n"
                  f"**Thread:** {'Sí' if suggestion.thread_id else 'No'}\n"
                  f"**Cambios:** {len(suggestion.history)}",
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name="suggestionhistory")
    @checks.admin_or_permissions(manage_guild=True)
    @app_commands.describe(reference="ID de sugerencia (#123), ID de mensaje, o link")
    async def suggestion_history(self, ctx: commands.Context, reference: str):
        """Ver el historial de cambios de una sugerencia."""
        await self._ensure_migrated(ctx.guild)
        
        suggestion_id = await self._parse_suggestion_reference(ctx.guild, reference)
        if not suggestion_id:
            await ctx.send("❌ No se encontró esa sugerencia.", ephemeral=True)
            return
        
        suggestion = await self.storage.get_suggestion(ctx.guild, suggestion_id)
        if not suggestion:
            await ctx.send("❌ Sugerencia no encontrada.", ephemeral=True)
            return
        
        embed = create_history_embed(suggestion, self.bot)
        await ctx.send(embed=embed)
    
    # ==================== MAINTENANCE COMMANDS ====================
    
    @commands.group(name="suggestadmin", aliases=["sadmin"])
    @checks.admin_or_permissions(administrator=True)
    async def suggest_admin(self, ctx: commands.Context):
        """Comandos de administración de sugerencias."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)
    
    @suggest_admin.command(name="resync")
    async def suggest_resync(self, ctx: commands.Context):
        """
        Sincroniza las sugerencias verificando qué mensajes aún existen.
        Marca como eliminadas las sugerencias cuyo mensaje ya no existe.
        """
        await self._ensure_migrated(ctx.guild)
        
        channel = await self._get_suggestion_channel(ctx.guild)
        if not channel:
            await ctx.send("❌ No hay canal de sugerencias configurado.")
            return
        
        await ctx.send("🔄 Sincronizando sugerencias...")
        
        suggestions = await self.storage.get_all_suggestions(ctx.guild)
        deleted_count = 0
        valid_count = 0
        
        for suggestion in suggestions:
            try:
                await channel.fetch_message(suggestion.message_id)
                valid_count += 1
            except discord.NotFound:
                await self.storage.mark_deleted(ctx.guild, suggestion.suggestion_id)
                deleted_count += 1
            except discord.HTTPException:
                pass
        
        await ctx.send(
            f"✅ Sincronización completada:\n"
            f"• Sugerencias válidas: {valid_count}\n"
            f"• Marcadas como eliminadas: {deleted_count}"
        )
    
    @suggest_admin.command(name="repost")
    async def suggest_repost(self, ctx: commands.Context, reference: str):
        """
        Re-publica una sugerencia eliminada manteniendo su ID original.
        
        **Uso:** `[p]suggestadmin repost #123`
        """
        await self._ensure_migrated(ctx.guild)
        
        suggestion_id = await self._parse_suggestion_reference(ctx.guild, reference)
        if not suggestion_id:
            await ctx.send("❌ No se encontró esa sugerencia.")
            return
        
        # Get suggestion including deleted
        suggestions = await self.config.guild(ctx.guild).suggestions()
        data = suggestions.get(str(suggestion_id))
        if not data:
            await ctx.send("❌ Sugerencia no encontrada.")
            return
        
        from .storage import SuggestionData
        suggestion = SuggestionData(data)
        
        channel = await self._get_suggestion_channel(ctx.guild)
        if not channel:
            await ctx.send("❌ No hay canal de sugerencias configurado.")
            return
        
        # Re-create message
        author = ctx.guild.get_member(suggestion.author_id)
        message = await self._create_suggestion_message(channel, suggestion, author)
        
        # Update message_id
        await self.storage.update_message_id(ctx.guild, suggestion_id, message.id)
        
        await ctx.send(f"✅ Sugerencia #{suggestion_id} republicada: {message.jump_url}")
    
    @suggest_admin.command(name="purge")
    async def suggest_purge(self, ctx: commands.Context, what: str = "deleted"):
        """
        Elimina permanentemente sugerencias del registro.
        
        **Opciones:**
        - `deleted`: Elimina sugerencias marcadas como eliminadas
        
        **Uso:** `[p]suggestadmin purge deleted`
        """
        if what == "deleted":
            await ctx.send(
                "⚠️ Esto eliminará permanentemente todas las sugerencias marcadas como eliminadas.\n"
                "¿Estás seguro? Responde `confirmar` en 30 segundos."
            )
            
            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel
            
            try:
                msg = await self.bot.wait_for("message", check=check, timeout=30)
                if msg.content.lower() != "confirmar":
                    await ctx.send("❌ Operación cancelada.")
                    return
            except:
                await ctx.send("❌ Tiempo agotado.")
                return
            
            count = await self.storage.purge_deleted(ctx.guild)
            await ctx.send(f"✅ {count} sugerencias eliminadas permanentemente.")
        else:
            await ctx.send("❌ Opción no válida. Usa: `deleted`")
    
    # ==================== CONFIGURATION COMMANDS ====================
    
    @commands.group(name="suggestset", aliases=["sset"])
    @checks.admin_or_permissions(administrator=True)
    async def suggest_set(self, ctx: commands.Context):
        """Configuración del sistema de sugerencias."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)
    
    @suggest_set.command(name="channel")
    async def set_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Establece el canal de sugerencias."""
        await self.config.guild(ctx.guild).suggestion_channel.set(channel.id)
        await ctx.send(f"✅ Canal de sugerencias: {channel.mention}")
    
    @suggest_set.command(name="logchannel")
    async def set_log_channel(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Establece el canal de logs (o desactiva con ningún argumento)."""
        if channel:
            await self.config.guild(ctx.guild).log_channel.set(channel.id)
            await ctx.send(f"✅ Canal de logs: {channel.mention}")
        else:
            await self.config.guild(ctx.guild).log_channel.set(None)
            await ctx.send("✅ Canal de logs desactivado.")
    
    @suggest_set.command(name="notifychannel")
    async def set_notify_channel(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Canal alternativo para notificaciones (si DM falla)."""
        if channel:
            await self.config.guild(ctx.guild).notify_channel.set(channel.id)
            await ctx.send(f"✅ Canal de notificaciones: {channel.mention}")
        else:
            await self.config.guild(ctx.guild).notify_channel.set(None)
            await ctx.send("✅ Canal de notificaciones desactivado.")
    
    @suggest_set.command(name="staffrole")
    async def set_staff_role(self, ctx: commands.Context, role: Optional[discord.Role] = None):
        """Establece el rol de staff que puede gestionar sugerencias."""
        if role:
            await self.config.guild(ctx.guild).staff_role.set(role.id)
            await ctx.send(f"✅ Rol de staff: {role.mention}")
        else:
            await self.config.guild(ctx.guild).staff_role.set(None)
            await ctx.send("✅ Rol de staff eliminado.")
    
    @suggest_set.command(name="buttons")
    async def toggle_buttons(self, ctx: commands.Context):
        """Alterna entre botones y reacciones."""
        current = await self.config.guild(ctx.guild).use_buttons()
        await self.config.guild(ctx.guild).use_buttons.set(not current)
        mode = "botones" if not current else "reacciones"
        await ctx.send(f"✅ Modo de interacción: **{mode}**")
    
    @suggest_set.command(name="threads")
    async def toggle_threads(self, ctx: commands.Context):
        """Activa/desactiva hilos automáticos."""
        current = await self.config.guild(ctx.guild).suggestion_threads()
        await self.config.guild(ctx.guild).suggestion_threads.set(not current)
        state = "activados" if not current else "desactivados"
        await ctx.send(f"✅ Hilos automáticos: **{state}**")
    
    @suggest_set.command(name="autoarchive")
    async def toggle_auto_archive(self, ctx: commands.Context):
        """Activa/desactiva archivado automático de hilos."""
        current = await self.config.guild(ctx.guild).thread_auto_archive()
        await self.config.guild(ctx.guild).thread_auto_archive.set(not current)
        state = "activado" if not current else "desactivado"
        await ctx.send(f"✅ Archivado automático de hilos: **{state}**")
    
    @suggest_set.command(name="notify")
    async def toggle_notify(self, ctx: commands.Context):
        """Activa/desactiva notificaciones al autor."""
        current = await self.config.guild(ctx.guild).notify_author()
        await self.config.guild(ctx.guild).notify_author.set(not current)
        state = "activadas" if not current else "desactivadas"
        await ctx.send(f"✅ Notificaciones al autor: **{state}**")
    
    @suggest_set.command(name="settings")
    async def show_settings(self, ctx: commands.Context):
        """Muestra la configuración actual."""
        guild_config = await self.config.guild(ctx.guild).all()
        
        channel = ctx.guild.get_channel(guild_config["suggestion_channel"])
        log_channel = ctx.guild.get_channel(guild_config["log_channel"]) if guild_config["log_channel"] else None
        notify_channel = ctx.guild.get_channel(guild_config["notify_channel"]) if guild_config["notify_channel"] else None
        staff_role = ctx.guild.get_role(guild_config["staff_role"]) if guild_config["staff_role"] else None
        
        embed = discord.Embed(
            title="⚙️ Configuración de Sugerencias",
            color=discord.Color.blurple()
        )
        
        embed.add_field(
            name="📢 Canales",
            value=f"**Sugerencias:** {channel.mention if channel else 'No configurado'}\n"
                  f"**Logs:** {log_channel.mention if log_channel else 'Desactivado'}\n"
                  f"**Notificaciones:** {notify_channel.mention if notify_channel else 'DM'}",
            inline=False
        )
        
        embed.add_field(
            name="🔧 Opciones",
            value=f"**Modo:** {'Botones' if guild_config['use_buttons'] else 'Reacciones'}\n"
                  f"**Hilos automáticos:** {'✅' if guild_config['suggestion_threads'] else '❌'}\n"
                  f"**Archivado de hilos:** {'✅' if guild_config['thread_auto_archive'] else '❌'}\n"
                  f"**Notificar autor:** {'✅' if guild_config['notify_author'] else '❌'}",
            inline=False
        )
        
        embed.add_field(
            name="👥 Permisos",
            value=f"**Rol staff:** {staff_role.mention if staff_role else 'Solo admins'}",
            inline=False
        )
        
        embed.add_field(
            name="📊 Estadísticas",
            value=f"**Total sugerencias:** {len(guild_config['suggestions'])}\n"
                  f"**Contador actual:** #{guild_config['suggestion_counter']}",
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    # ==================== LEGACY COMMANDS (compatibility) ====================
    
    @commands.command(name="setsuggestionchannel", hidden=True)
    @checks.admin_or_permissions(administrator=True)
    async def legacy_set_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """[Legacy] Usa [p]suggestset channel"""
        await self.set_channel(ctx, channel)
    
    @commands.command(name="setlogchannel", hidden=True)
    @checks.admin_or_permissions(administrator=True)
    async def legacy_set_log(self, ctx: commands.Context, channel: discord.TextChannel):
        """[Legacy] Usa [p]suggestset logchannel"""
        await self.set_log_channel(ctx, channel)
    
    @commands.command(name="togglesuggestionthreads", hidden=True)
    @checks.admin_or_permissions(administrator=True)
    async def legacy_toggle_threads(self, ctx: commands.Context):
        """[Legacy] Usa [p]suggestset threads"""
        await self.toggle_threads(ctx)
    
    @commands.command(name="togglethreadarchive", hidden=True)
    @checks.admin_or_permissions(administrator=True)
    async def legacy_toggle_archive(self, ctx: commands.Context):
        """[Legacy] Usa [p]suggestset autoarchive"""
        await self.toggle_auto_archive(ctx)


# Red setup function is in __init__.py
