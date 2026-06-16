"""
RustMapsVote - Map voting COG for Red-DiscordBot
By Killerbite95

Lets a guild create an embed-based vote over rustmaps.com maps. Users vote with
numbered buttons; each user has a configurable number of votes per session
(default 1, so in a 3-map vote everyone picks a single map).
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import aiohttp
import discord
from discord import app_commands
from redbot.core import Config, checks, commands
from redbot.core.bot import Red

from .models import (
    DEFAULT_MAX_VOTES_PER_USER,
    MAX_MAPS,
    MIN_MAPS,
    MapInfo,
    VoteSession,
)
from .views import VoteView

logger = logging.getLogger("red.killerbite95.rustmaps_vote")

URL_PATTERN = re.compile(r"rustmaps\.com/map/(\d+)_(\d+)")
API_BASE = "https://api.rustmaps.com"


class RustMapsVote(commands.Cog):
    """Votación de mapas de Rust usando rustmaps.com. By Killerbite95"""

    __author__ = "Killerbite95"
    __version__ = "1.0.0"

    def __init__(self, bot: Red) -> None:
        self.bot: Red = bot
        self.config: Config = Config.get_conf(
            self, identifier=7890123456, force_registration=True
        )
        self.config.register_global(api_key="")
        self.config.register_guild(
            vote_session_active=False,
            vote_session_data={},
            vote_channel_id=None,
            max_votes_per_user=DEFAULT_MAX_VOTES_PER_USER,
            session_counter=0,
        )
        self.session: Optional[aiohttp.ClientSession] = None
        self._locks: Dict[int, asyncio.Lock] = {}

    async def cog_load(self) -> None:
        self.session = aiohttp.ClientSession()
        logger.info(f"RustMapsVote v{self.__version__} loaded")

    async def cog_unload(self) -> None:
        if self.session:
            await self.session.close()

    def _get_lock(self, guild_id: int) -> asyncio.Lock:
        return self._locks.setdefault(guild_id, asyncio.Lock())

    # ==================== API CLIENT ====================

    def parse_rustmaps_url(self, url: str) -> Tuple[int, int]:
        """Extract (size, seed) from a rustmaps.com map URL."""
        match = URL_PATTERN.search(url)
        if not match:
            raise ValueError(
                "URL no válida. Debe tener el formato "
                "`https://rustmaps.com/map/<size>_<seed>`."
            )
        return int(match.group(1)), int(match.group(2))

    async def fetch_map_data(self, size: int, seed: int) -> Dict[str, Any]:
        """Fetch raw map data from the RustMaps API v4."""
        api_key = await self.config.api_key()
        if not api_key:
            raise ValueError("La API key de RustMaps no está configurada.")
        if self.session is None:
            self.session = aiohttp.ClientSession()

        headers = {"x-api-key": api_key}
        url = f"{API_BASE}/v4/maps/{size}/{seed}?staging=false"
        try:
            async with self.session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    return await response.json()
                if response.status == 401:
                    raise ValueError("API key inválida.")
                if response.status == 404:
                    raise ValueError("Mapa no encontrado.")
                if response.status == 409:
                    raise ValueError("El mapa todavía se está generando, inténtalo más tarde.")
                raise ValueError(f"Error de la API de RustMaps (HTTP {response.status}).")
        except asyncio.TimeoutError:
            raise ValueError("Tiempo de espera agotado al contactar con RustMaps.")
        except aiohttp.ClientError as exc:
            raise ValueError(f"Error de red al contactar con RustMaps: {exc}")

    async def fetch_map_from_url(self, url: str) -> MapInfo:
        """Resolve a rustmaps URL into a MapInfo (map_id is assigned later)."""
        size, seed = self.parse_rustmaps_url(url)
        data = await self.fetch_map_data(size, seed)
        info = MapInfo.from_api_response(data, 0, url)
        # Fall back to URL-parsed values if the API omitted them.
        if not info.size:
            info.size = size
        if not info.seed:
            info.seed = seed
        return info

    # ==================== CONFIG UTILITIES ====================

    async def save_session(self, guild: discord.Guild, session: VoteSession) -> None:
        await self.config.guild(guild).vote_session_data.set(session.to_dict())

    async def load_session(self, guild: discord.Guild) -> Optional[VoteSession]:
        data = await self.config.guild(guild).vote_session_data()
        if not data:
            return None
        try:
            return VoteSession.from_dict(data)
        except Exception as exc:  # corrupt/old data — treat as no session
            logger.warning(f"Could not load vote session for guild {guild.id}: {exc}")
            return None

    async def clear_session(self, guild: discord.Guild) -> None:
        await self.config.guild(guild).vote_session_data.set({})
        await self.config.guild(guild).vote_session_active.set(False)

    # ==================== EMBED BUILDERS ====================

    def build_vote_embed(self, map_info: MapInfo, total_maps: int) -> discord.Embed:
        embed = discord.Embed(
            title=f"🗺️ Mapa {map_info.map_id}",
            color=discord.Color.blue(),
        )
        if map_info.map_type:
            embed.description = f"**Tipo:** {map_info.map_type}"

        embed.add_field(name="🌱 Seed", value=f"`{map_info.seed}`", inline=True)
        embed.add_field(name="📏 Size", value=f"`{map_info.size}`", inline=True)
        if map_info.total_monuments:
            embed.add_field(
                name="🏛️ Monumentos", value=str(map_info.total_monuments), inline=True
            )

        biomes = map_info.biomes_display()
        if biomes:
            embed.add_field(name="🌍 Biomas", value=biomes, inline=False)

        terrain = map_info.terrain_display()
        if terrain:
            embed.add_field(name="🏔️ Terreno", value=terrain, inline=False)

        if map_info.land_percentage is not None:
            embed.add_field(
                name="🗺️ Tierra firme", value=f"{map_info.land_percentage}%", inline=True
            )

        if map_info.monument_names:
            names = ", ".join(map_info.monument_names[:8])
            if len(map_info.monument_names) > 8:
                names += f" (+{len(map_info.monument_names) - 8})"
            embed.add_field(name="📍 Monumentos destacados", value=names, inline=False)

        embed.add_field(
            name="🔗 Ver mapa completo",
            value=f"[rustmaps.com]({map_info.url})",
            inline=False,
        )

        # The thumbnailUrl render is the good one -> show it big; imageUrl as the small icon.
        if map_info.thumbnail_url:
            embed.set_image(url=map_info.thumbnail_url)
            if map_info.image_url:
                embed.set_thumbnail(url=map_info.image_url)
        elif map_info.image_url:
            embed.set_image(url=map_info.image_url)

        embed.set_footer(text=f"RustMaps Vote • {total_maps} mapas en esta votación")
        return embed

    def build_results_embed(self, session: VoteSession) -> discord.Embed:
        embed = discord.Embed(
            title="🗳️ Votación de mapas de Rust",
            description="Pulsa el botón con el número del mapa que prefieras.",
            color=discord.Color.blurple(),
        )
        for m in session.maps:
            embed.add_field(
                name=f"Mapa {m.map_id}",
                value=(
                    f"🌱 Seed: `{m.seed}` • 📏 Size: `{m.size}`\n"
                    f"🗳️ **{m.vote_count}** voto(s) • [Ver mapa]({m.url})"
                ),
                inline=False,
            )
        votes = session.max_votes_per_user
        embed.set_footer(
            text=(
                f"Tienes {votes} voto(s) por persona • "
                f"{session.total_voters} votante(s) hasta ahora"
            )
        )
        return embed

    def build_winner_embed(self, session: VoteSession) -> discord.Embed:
        ranking = session.get_ranking()
        winner = ranking[0] if ranking else None
        embed = discord.Embed(color=discord.Color.gold())
        if not winner or session.total_votes == 0:
            embed.title = "🏁 Votación finalizada"
            embed.description = "No se registró ningún voto."
            return embed

        embed.title = f"🏆 ¡Gana el Mapa {winner.map_id}!"
        embed.add_field(
            name="🥇 Ganador",
            value=(
                f"**Mapa {winner.map_id}** — Seed `{winner.seed}`, Size `{winner.size}`\n"
                f"🗳️ {winner.vote_count} voto(s)\n[Ver mapa]({winner.url})"
            ),
            inline=False,
        )
        medals = ["🥈 2º lugar", "🥉 3er lugar"]
        for medal, m in zip(medals, ranking[1:3]):
            embed.add_field(
                name=medal,
                value=f"Mapa {m.map_id} — {m.vote_count} voto(s)",
                inline=False,
            )
        embed.set_footer(
            text=f"{session.total_votes} voto(s) de {session.total_voters} votante(s)"
        )
        return embed

    def build_add_confirm_embed(self, map_info: MapInfo, map_count: int) -> discord.Embed:
        embed = discord.Embed(
            title="✅ Mapa añadido",
            color=discord.Color.green(),
        )
        lines = [
            f"🌱 Seed: `{map_info.seed}`",
            f"📏 Size: `{map_info.size}`",
        ]
        if map_info.map_type:
            lines.append(f"🏷️ Tipo: {map_info.map_type}")
        if map_info.total_monuments:
            lines.append(f"🏛️ Monumentos: {map_info.total_monuments}")
        lines.append(f"🗺️ Mapas en la sesión: **{map_count}/{MAX_MAPS}**")
        embed.add_field(
            name=f"Mapa {map_info.map_id} añadido correctamente",
            value="\n".join(lines),
            inline=False,
        )
        if map_info.thumbnail_url:
            embed.set_thumbnail(url=map_info.thumbnail_url)
        return embed

    async def _update_voting_message(
        self, guild: discord.Guild, session: VoteSession
    ) -> None:
        """Refresh the live voting message embed with current counts."""
        if not session.channel_id or not session.voting_message_id:
            return
        channel = guild.get_channel(session.channel_id)
        if channel is None:
            return
        try:
            message = await channel.fetch_message(session.voting_message_id)
            await message.edit(embed=self.build_results_embed(session))
        except discord.NotFound:
            pass
        except discord.HTTPException as exc:
            logger.debug(f"Could not update voting message: {exc}")

    # ==================== COMMANDS ====================

    @commands.guild_only()
    @commands.hybrid_group(name="votemap")
    async def votemap(self, ctx: commands.Context) -> None:
        """Votaciones de mapas de Rust usando rustmaps.com."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @votemap.command(name="setapi")
    @checks.admin_or_permissions(administrator=True)
    @app_commands.describe(key="Tu API key de RustMaps (v4)")
    async def setapi(self, ctx: commands.Context, key: str) -> None:
        """Configura la API key global de RustMaps."""
        await self.config.api_key.set(key.strip())
        # Try to remove the message so the key isn't left visible in chat.
        if ctx.message and ctx.guild:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass
        await ctx.send("✅ API key de RustMaps configurada.", ephemeral=True)

    @votemap.command(name="maxvotes")
    @checks.admin_or_permissions(administrator=True)
    @app_commands.describe(amount="Número de votos por persona (mínimo 1)")
    async def maxvotes(self, ctx: commands.Context, amount: int) -> None:
        """Define cuántos mapas puede votar cada persona por votación (por defecto 1)."""
        if amount < 1:
            await ctx.send("❌ El número de votos debe ser al menos 1.", ephemeral=True)
            return
        if amount > MAX_MAPS:
            await ctx.send(
                f"❌ El número de votos no puede superar el máximo de mapas ({MAX_MAPS}).",
                ephemeral=True,
            )
            return
        await self.config.guild(ctx.guild).max_votes_per_user.set(amount)
        # Apply to an in-progress session too, if there is one.
        session = await self.load_session(ctx.guild)
        if session:
            session.max_votes_per_user = amount
            await self.save_session(ctx.guild, session)
            if await self.config.guild(ctx.guild).vote_session_active():
                await self._update_voting_message(ctx.guild, session)
        await ctx.send(
            f"✅ Cada persona podrá votar **{amount}** mapa(s) por votación.",
            ephemeral=True,
        )

    @votemap.command(name="add")
    @checks.admin_or_permissions(administrator=True)
    @app_commands.describe(url="URL del mapa en rustmaps.com")
    async def add(self, ctx: commands.Context, url: str) -> None:
        """Añade un mapa a la votación actual."""
        if await self.config.guild(ctx.guild).vote_session_active():
            await ctx.send(
                "❌ Ya hay una votación en curso. Termínala con `[p]votemap end` "
                "antes de añadir más mapas.",
                ephemeral=True,
            )
            return

        if not await self.config.api_key():
            await ctx.send(
                "❌ Configura primero la API key con `[p]votemap setapi <key>`.",
                ephemeral=True,
            )
            return

        async with ctx.typing():
            try:
                map_info = await self.fetch_map_from_url(url)
            except ValueError as exc:
                await ctx.send(f"❌ {exc}", ephemeral=True)
                return

        session = await self.load_session(ctx.guild)
        if session is None:
            counter = await self.config.guild(ctx.guild).session_counter()
            counter += 1
            await self.config.guild(ctx.guild).session_counter.set(counter)
            session = VoteSession(
                session_id=counter,
                max_votes_per_user=await self.config.guild(ctx.guild).max_votes_per_user(),
            )

        if session.has_duplicate(map_info.size, map_info.seed):
            await ctx.send("❌ Ese mapa ya está en la votación.", ephemeral=True)
            return

        if not session.add_map(map_info):
            await ctx.send(
                f"❌ Has alcanzado el máximo de {MAX_MAPS} mapas por votación.",
                ephemeral=True,
            )
            return

        await self.save_session(ctx.guild, session)
        await ctx.send(embed=self.build_add_confirm_embed(map_info, len(session.maps)))

    @votemap.command(name="remove")
    @checks.admin_or_permissions(administrator=True)
    @app_commands.describe(map_id="Número del mapa a quitar")
    async def remove(self, ctx: commands.Context, map_id: int) -> None:
        """Quita un mapa de la votación actual (antes de empezar)."""
        if await self.config.guild(ctx.guild).vote_session_active():
            await ctx.send(
                "❌ No puedes quitar mapas con una votación en curso. Usa `[p]votemap end`.",
                ephemeral=True,
            )
            return

        session = await self.load_session(ctx.guild)
        if session is None or not session.maps:
            await ctx.send("❌ No hay ninguna votación en preparación.", ephemeral=True)
            return

        if not session.remove_map(map_id):
            await ctx.send(f"❌ No existe el mapa número {map_id}.", ephemeral=True)
            return

        if not session.maps:
            await self.clear_session(ctx.guild)
            await ctx.send("✅ Mapa quitado. La votación quedó vacía y se canceló.")
            return

        await self.save_session(ctx.guild, session)
        await ctx.send(
            f"✅ Mapa quitado. Quedan **{len(session.maps)}** mapa(s) "
            "(renumerados del 1 en adelante)."
        )

    @votemap.command(name="list")
    async def list_maps(self, ctx: commands.Context) -> None:
        """Muestra los mapas de la votación actual."""
        session = await self.load_session(ctx.guild)
        if session is None or not session.maps:
            await ctx.send("ℹ️ No hay ninguna votación activa o en preparación.", ephemeral=True)
            return

        active = await self.config.guild(ctx.guild).vote_session_active()
        embed = discord.Embed(
            title="🗺️ Mapas en la votación",
            color=discord.Color.blue(),
        )
        for m in session.maps:
            value = f"🌱 Seed: `{m.seed}` • 📏 Size: `{m.size}` • [Ver mapa]({m.url})"
            if active:
                value += f"\n🗳️ {m.vote_count} voto(s)"
            embed.add_field(name=f"Mapa {m.map_id}", value=value, inline=False)
        state = "En curso" if active else "En preparación"
        embed.set_footer(
            text=f"Estado: {state} • {len(session.maps)}/{MAX_MAPS} mapas "
            f"• {session.max_votes_per_user} voto(s) por persona"
        )
        await ctx.send(embed=embed)

    @votemap.command(name="start")
    @checks.admin_or_permissions(administrator=True)
    async def start(self, ctx: commands.Context) -> None:
        """Inicia la votación con embeds y botones."""
        if await self.config.guild(ctx.guild).vote_session_active():
            await ctx.send("❌ Ya hay una votación en curso.", ephemeral=True)
            return

        session = await self.load_session(ctx.guild)
        if session is None or len(session.maps) < MIN_MAPS:
            await ctx.send(
                f"❌ Necesitas al menos {MIN_MAPS} mapas para empezar. "
                "Añádelos con `[p]votemap add <url>`.",
                ephemeral=True,
            )
            return

        channel_id = await self.config.guild(ctx.guild).vote_channel_id()
        channel = ctx.guild.get_channel(channel_id) if channel_id else ctx.channel
        if channel is None:
            channel = ctx.channel

        # Reset any stale votes and snapshot the configured votes-per-user.
        session.votes = {}
        session._apply_counts()
        session.started_at = datetime.utcnow()
        session.channel_id = channel.id
        session.max_votes_per_user = await self.config.guild(ctx.guild).max_votes_per_user()

        # Post one embed per map for visual context...
        for m in session.maps:
            await channel.send(embed=self.build_vote_embed(m, len(session.maps)))

        # ...then the single voting message holding all the buttons.
        view = VoteView(
            session_id=session.session_id,
            map_ids=[m.map_id for m in session.maps],
            channel_id=channel.id,
        )
        voting_message = await channel.send(
            embed=self.build_results_embed(session), view=view
        )
        session.voting_message_id = voting_message.id

        await self.save_session(ctx.guild, session)
        await self.config.guild(ctx.guild).vote_session_active.set(True)

        if channel.id != ctx.channel.id:
            await ctx.send(f"✅ ¡Votación iniciada en {channel.mention}!", ephemeral=True)
        else:
            await ctx.send("✅ ¡Votación iniciada!", ephemeral=True)

    @votemap.command(name="end")
    @checks.admin_or_permissions(administrator=True)
    async def end(self, ctx: commands.Context) -> None:
        """Termina la votación y anuncia al ganador."""
        async with self._get_lock(ctx.guild.id):
            session = await self.load_session(ctx.guild)
            active = await self.config.guild(ctx.guild).vote_session_active()
            if session is None or not active:
                await ctx.send("❌ No hay ninguna votación en curso.", ephemeral=True)
                return

            session.ended_at = datetime.utcnow()
            embed = self.build_winner_embed(session)

            # Disable the buttons on the original voting message.
            await self._disable_voting_message(ctx.guild, session)
            await self.clear_session(ctx.guild)

        channel = ctx.guild.get_channel(session.channel_id) if session.channel_id else ctx.channel
        if channel is None:
            channel = ctx.channel
        await channel.send(embed=embed)
        if channel.id != ctx.channel.id:
            await ctx.send("✅ Votación finalizada.", ephemeral=True)

    async def _disable_voting_message(
        self, guild: discord.Guild, session: VoteSession
    ) -> None:
        if not session.channel_id or not session.voting_message_id:
            return
        channel = guild.get_channel(session.channel_id)
        if channel is None:
            return
        view = VoteView(
            session_id=session.session_id,
            map_ids=[m.map_id for m in session.maps],
            channel_id=session.channel_id,
        )
        for item in view.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        try:
            message = await channel.fetch_message(session.voting_message_id)
            await message.edit(embed=self.build_results_embed(session), view=view)
        except discord.NotFound:
            pass
        except discord.HTTPException as exc:
            logger.debug(f"Could not disable voting message: {exc}")

    @votemap.command(name="cancel")
    @checks.admin_or_permissions(administrator=True)
    async def cancel(self, ctx: commands.Context) -> None:
        """Cancela la votación o la preparación actual sin anunciar ganador."""
        session = await self.load_session(ctx.guild)
        if session is None:
            await ctx.send("ℹ️ No hay ninguna votación que cancelar.", ephemeral=True)
            return
        if await self.config.guild(ctx.guild).vote_session_active():
            await self._disable_voting_message(ctx.guild, session)
        await self.clear_session(ctx.guild)
        await ctx.send("🗑️ Votación cancelada.")

    @votemap.command(name="settings")
    @checks.admin_or_permissions(administrator=True)
    async def settings(self, ctx: commands.Context) -> None:
        """Muestra la configuración de las votaciones."""
        guild_conf = await self.config.guild(ctx.guild).all()
        api_set = bool(await self.config.api_key())
        session = await self.load_session(ctx.guild)

        channel = (
            ctx.guild.get_channel(guild_conf["vote_channel_id"])
            if guild_conf["vote_channel_id"]
            else None
        )

        embed = discord.Embed(title="⚙️ Configuración de RustMaps Vote", color=discord.Color.blurple())
        embed.add_field(name="🔑 API key", value="✅ Configurada" if api_set else "❌ Sin configurar", inline=True)
        embed.add_field(
            name="🗳️ Votos por persona",
            value=str(guild_conf["max_votes_per_user"]),
            inline=True,
        )
        embed.add_field(
            name="📢 Canal de votación",
            value=channel.mention if channel else "Canal donde se usa `start`",
            inline=True,
        )
        if session:
            state = "En curso" if guild_conf["vote_session_active"] else "En preparación"
            embed.add_field(
                name="📊 Sesión actual",
                value=(
                    f"Estado: **{state}**\n"
                    f"Mapas: **{len(session.maps)}/{MAX_MAPS}**\n"
                    f"Votantes: **{session.total_voters}**"
                ),
                inline=False,
            )
        else:
            embed.add_field(name="📊 Sesión actual", value="Ninguna", inline=False)
        await ctx.send(embed=embed)

    @votemap.command(name="setchannel")
    @checks.admin_or_permissions(administrator=True)
    @app_commands.describe(channel="Canal donde se publicarán las votaciones (vacío para usar el actual)")
    async def setchannel(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None
    ) -> None:
        """Define el canal por defecto de las votaciones."""
        if channel:
            await self.config.guild(ctx.guild).vote_channel_id.set(channel.id)
            await ctx.send(f"✅ Las votaciones se publicarán en {channel.mention}.", ephemeral=True)
        else:
            await self.config.guild(ctx.guild).vote_channel_id.set(None)
            await ctx.send(
                "✅ Las votaciones se publicarán en el canal donde se ejecute `start`.",
                ephemeral=True,
            )

    # ==================== INTERACTION HANDLER ====================

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        """Handle vote button clicks (works across restarts)."""
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = (interaction.data or {}).get("custom_id", "")
        if not custom_id.startswith("rustmaps_vote:vote:"):
            return

        parts = custom_id.split(":")
        if len(parts) != 4:
            return
        try:
            session_id = int(parts[2])
            map_id = int(parts[3])
        except ValueError:
            return

        guild = interaction.guild
        if guild is None:
            return

        async with self._get_lock(guild.id):
            session = await self.load_session(guild)
            active = await self.config.guild(guild).vote_session_active()
            if session is None or not active or session.session_id != session_id:
                await interaction.response.send_message(
                    "⚠️ Esta votación ya ha terminado.", ephemeral=True
                )
                return

            action = session.toggle_vote(interaction.user.id, map_id)

            if action == "invalid":
                await interaction.response.send_message("❌ Mapa no válido.", ephemeral=True)
                return
            if action == "limit":
                await interaction.response.send_message(
                    f"⚠️ Ya has usado todos tus votos ({session.max_votes_per_user}). "
                    "Pulsa de nuevo un mapa que ya votaste para liberar un voto.",
                    ephemeral=True,
                )
                return

            await self.save_session(guild, session)
            await self._update_voting_message(guild, session)

        if action == "added":
            await interaction.response.send_message(
                f"✅ Has votado por el **Mapa {map_id}**.", ephemeral=True
            )
        else:  # removed
            await interaction.response.send_message(
                f"↩️ Has retirado tu voto del **Mapa {map_id}**.", ephemeral=True
            )
