"""
Views para GameServerMonitor - Botones interactivos y UI Components.
Implementa botones persistentes para embeds de servidores.
By Killerbite95
"""

import discord
from discord import ui
from discord.ext import commands
import asyncio
import logging
from typing import Optional, Dict, Any, TYPE_CHECKING
from datetime import datetime, timedelta
from collections import defaultdict
from redbot.core.i18n import Translator

if TYPE_CHECKING:
    from .gameservermonitor import GameServerMonitor

logger = logging.getLogger("red.killerbite95.gameservermonitor.views")

# Internacionalización
_ = Translator("GameServerMonitor", __file__)


# ==================== Cooldown Manager ====================

class CooldownManager:
    """Gestiona cooldowns por usuario y acción."""
    
    def __init__(self, default_cooldown: float = 5.0):
        self.default_cooldown = default_cooldown
        self._cooldowns: Dict[str, datetime] = {}
    
    def _get_key(self, user_id: int, action: str, server_id: str) -> str:
        """Genera la clave única para el cooldown."""
        return f"{user_id}:{action}:{server_id}"
    
    def is_on_cooldown(self, user_id: int, action: str, server_id: str) -> tuple[bool, float]:
        """
        Verifica si un usuario está en cooldown.
        
        Returns:
            Tupla (está_en_cooldown, segundos_restantes)
        """
        key = self._get_key(user_id, action, server_id)
        if key not in self._cooldowns:
            return False, 0.0
        
        elapsed = (datetime.utcnow() - self._cooldowns[key]).total_seconds()
        if elapsed >= self.default_cooldown:
            del self._cooldowns[key]
            return False, 0.0
        
        remaining = self.default_cooldown - elapsed
        return True, remaining
    
    def set_cooldown(self, user_id: int, action: str, server_id: str) -> None:
        """Establece el cooldown para un usuario/acción."""
        key = self._get_key(user_id, action, server_id)
        self._cooldowns[key] = datetime.utcnow()
    
    def cleanup(self) -> None:
        """Limpia cooldowns expirados."""
        now = datetime.utcnow()
        expired = [
            key for key, timestamp in self._cooldowns.items()
            if (now - timestamp).total_seconds() >= self.default_cooldown * 2
        ]
        for key in expired:
            del self._cooldowns[key]


# Instancia global del cooldown manager
cooldown_manager = CooldownManager(default_cooldown=5.0)


# ==================== Server Actions View ====================

class ServerActionsView(ui.View):
    """
    View persistente con botones de acción para servidores.
    
    Botones:
    - 👥 Players: Muestra lista de jugadores conectados
    - 📈 Stats: Muestra estadísticas del servidor
    - 📊 History: Muestra historial de jugadores
    
    Los botones usan server_id estable en el custom_id para
    funcionar incluso después de reinicios del bot.
    """
    
    def __init__(self, server_id: str, cog: Optional["GameServerMonitor"] = None):
        """
        Inicializa la view.
        
        Args:
            server_id: ID único y estable del servidor
            cog: Referencia al cog (opcional, se obtiene del bot en callbacks)
        """
        super().__init__(timeout=None)  # Persistente
        self.server_id = server_id
        self._cog = cog
        
        # Crear botones con custom_id que incluye server_id
        self.add_item(PlayersButton(server_id))
        self.add_item(StatsButton(server_id))
        self.add_item(HistoryButton(server_id))
    
    @classmethod
    def from_custom_id(cls, custom_id: str) -> Optional[str]:
        """
        Extrae el server_id de un custom_id de botón.
        
        Args:
            custom_id: El custom_id del botón (formato: gsm:action:server_id)
            
        Returns:
            El server_id o None si el formato es inválido
        """
        parts = custom_id.split(":")
        if len(parts) >= 3 and parts[0] == "gsm":
            return parts[2]
        return None


class PlayersButton(ui.Button):
    """Botón para ver jugadores conectados."""
    
    def __init__(self, server_id: str):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label="Players",
            emoji="👥",
            custom_id=f"gsm:players:{server_id}"
        )
        self.server_id = server_id
    
    async def callback(self, interaction: discord.Interaction):
        await handle_button_callback(interaction, self.server_id, "players")


class StatsButton(ui.Button):
    """Botón para ver estadísticas del servidor."""
    
    def __init__(self, server_id: str):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="Stats",
            emoji="📈",
            custom_id=f"gsm:stats:{server_id}"
        )
        self.server_id = server_id
    
    async def callback(self, interaction: discord.Interaction):
        await handle_button_callback(interaction, self.server_id, "stats")


class HistoryButton(ui.Button):
    """Botón para ver historial de jugadores."""
    
    def __init__(self, server_id: str):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="History",
            emoji="📊",
            custom_id=f"gsm:history:{server_id}"
        )
        self.server_id = server_id
    
    async def callback(self, interaction: discord.Interaction):
        await handle_button_callback(interaction, self.server_id, "history")


# ==================== Callback Handler ====================

async def handle_button_callback(
    interaction: discord.Interaction,
    server_id: str,
    action: str
) -> None:
    """
    Manejador centralizado para callbacks de botones.
    
    Args:
        interaction: La interacción de Discord
        server_id: ID del servidor
        action: Acción a realizar (players/stats/history)
    """
    # Verificar cooldown
    on_cooldown, remaining = cooldown_manager.is_on_cooldown(
        interaction.user.id, action, server_id
    )
    
    if on_cooldown:
        await interaction.response.send_message(
            _("Please wait **{seconds:.1f}s** before using this button again.").format(seconds=remaining),
            ephemeral=True
        )
        return
    
    # Defer la respuesta (ephemeral y thinking)
    await interaction.response.defer(ephemeral=True, thinking=True)
    
    try:
        # Obtener el cog
        cog = interaction.client.get_cog("GameServerMonitor")
        if not cog:
            await interaction.followup.send(
                f"❌ {_('The GameServerMonitor module is not available.')}",
                ephemeral=True
            )
            return
        
        # Obtener guild
        guild = interaction.guild
        if not guild:
            await interaction.followup.send(
                f"❌ {_('This command only works in servers.')}",
                ephemeral=True
            )
            return
        
        # Resolver server_key desde server_id
        server_key = await cog._resolve_server_key_by_id(guild, server_id)
        if not server_key:
            await interaction.followup.send(
                f"❌ {_('Server not found (ID: `{server_id}`).\nThe server may have been deleted.').format(server_id=server_id)}",
                ephemeral=True
            )
            return
        
        # Establecer cooldown
        cooldown_manager.set_cooldown(interaction.user.id, action, server_id)
        
        # Ejecutar acción correspondiente
        if action == "players":
            payload = await cog._build_players_payload(guild, server_key)
        elif action == "stats":
            payload = await cog._build_stats_payload(guild, server_key)
        elif action == "history":
            # Usar horas por defecto de la config
            interaction_config = await cog.config.guild(guild).interaction_features()
            hours = interaction_config.get("history_default_hours", 24)
            payload = await cog._build_history_payload(guild, server_key, hours)
        else:
            payload = {"error": _("Unknown action: {action}").format(action=action)}
        
        # Enviar respuesta
        if "error" in payload:
            await interaction.followup.send(
                f"❌ {payload['error']}",
                ephemeral=True
            )
        else:
            # Construir kwargs solo con valores no-None para evitar
            # AttributeError: 'NoneType' object has no attribute 'to_dict'
            send_kwargs = {"ephemeral": True}
            if payload.get("content"):
                send_kwargs["content"] = payload["content"]
            if payload.get("embed"):
                send_kwargs["embed"] = payload["embed"]
            if payload.get("file"):
                send_kwargs["file"] = payload["file"]
            
            await interaction.followup.send(**send_kwargs)
    
    except Exception as e:
        logger.error(f"Error en callback de botón {action}: {e!r}")
        await interaction.followup.send(
            f"❌ {_('An error occurred while processing the request.')}\n"
            f"```{type(e).__name__}: {str(e)[:100]}```",
            ephemeral=True
        )


# ==================== View Registration ====================

def setup_persistent_views(bot: commands.Bot, cog: "GameServerMonitor") -> None:
    """
    Registra las views persistentes en el bot.
    Debe llamarse al cargar el cog.
    
    Args:
        bot: Instancia del bot
        cog: Instancia del cog GameServerMonitor
    """
    # Registrar un view "template" para cada tipo de botón
    # Discord usa el custom_id prefix para rutear las interacciones
    
    # No podemos registrar views sin server_id conocido, pero podemos
    # usar un interaction handler personalizado
    
    # En su lugar, usamos add_view con views que tengan custom_id parcial
    # o manejamos via on_interaction
    
    async def interaction_check(interaction: discord.Interaction) -> bool:
        """Handler global para interacciones de botones GSM."""
        if interaction.type != discord.InteractionType.component:
            return True
        
        custom_id = interaction.data.get("custom_id", "")
        if not custom_id.startswith("gsm:"):
            return True
        
        # Parsear custom_id: gsm:action:server_id
        parts = custom_id.split(":")
        if len(parts) < 3:
            return True
        
        action = parts[1]
        server_id = parts[2]
        
        # El callback ya fue manejado por los botones si la view está activa
        # Este es un fallback para views que no están en memoria
        if not interaction.response.is_done():
            await handle_button_callback(interaction, server_id, action)
        
        return False
    
    # Registrar el listener
    @bot.listen("on_interaction")
    async def on_gsm_interaction(interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        
        custom_id = interaction.data.get("custom_id", "")
        if not custom_id.startswith("gsm:"):
            return
        
        # Ya manejado por el botón si está en memoria
        if interaction.response.is_done():
            return
        
        parts = custom_id.split(":")
        if len(parts) >= 3:
            action = parts[1]
            server_id = parts[2]
            await handle_button_callback(interaction, server_id, action)
    
    logger.info("Views persistentes de GSM registradas correctamente")


def create_server_view(server_id: str) -> ServerActionsView:
    """
    Crea una nueva instancia de ServerActionsView para un servidor.
    
    Args:
        server_id: ID único del servidor
        
    Returns:
        ServerActionsView configurada
    """
    return ServerActionsView(server_id=server_id)
