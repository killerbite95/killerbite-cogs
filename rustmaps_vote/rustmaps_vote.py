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
from .dashboard_integration import DashboardIntegration
from redbot.core.i18n import Translator, cog_i18n, set_contextual_locales_from_guild

_ = Translator("RustMapsVote", __file__)

logger = logging.getLogger("red.killerbite95.rustmaps_vote")

URL_PATTERN = re.compile(r"rustmaps\.com/map/(\d+)_(\d+)")
API_BASE = "https://api.rustmaps.com"


@cog_i18n(_)
class RustMapsVote(DashboardIntegration, commands.Cog):
    """Rust map voting using rustmaps.com. By Killerbite95"""

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


    # ------------------------------------------------------------------
    # Protocolo de La Trini: TriniProfiles (export/import) y TriniBackups
    # ------------------------------------------------------------------

    # Datos de funcionamiento (no son configuracion): ni se exportan ni se pisan.
    _TRINI_RUNTIME_KEYS = ('vote_session_active', 'vote_session_data', 'session_counter')
    # Configuracion que solo tiene sentido en el mismo servidor.
    _TRINI_LOCAL_KEYS = ()

    async def trini_export(self, guild):
        conf = await self.config.guild(guild).all()
        return {k: v for k, v in conf.items() if k not in self._TRINI_RUNTIME_KEYS}

    async def trini_import(self, guild, data, *, same_guild):
        skip = set(self._TRINI_RUNTIME_KEYS)
        if not same_guild:
            skip |= set(self._TRINI_LOCAL_KEYS)
        data = {k: v for k, v in data.items() if k not in skip}
        group = self.config.guild(guild)
        current = await group.all()
        for key, value in data.items():
            if key in current:
                await group.set_raw(key, value=value)
        return []

    async def cog_load(self) -> None:
        self._dashboard_register()
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
                _("Invalid URL. It must look like `https://rustmaps.com/map/<size>_<seed>`.")
            )
        return int(match.group(1)), int(match.group(2))

    async def fetch_map_data(self, size: int, seed: int) -> Dict[str, Any]:
        """Fetch raw map data from the RustMaps API v4."""
        api_key = await self.config.api_key()
        if not api_key:
            raise ValueError(_("The RustMaps API key is not set."))
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
                    raise ValueError(_("Invalid API key."))
                if response.status == 404:
                    raise ValueError(_("Map not found."))
                if response.status == 409:
                    raise ValueError(_("The map is still being generated, try again later."))
                raise ValueError(_("RustMaps API error (HTTP {status}).").format(status=response.status))
        except asyncio.TimeoutError:
            raise ValueError(_("Timed out while contacting RustMaps."))
        except aiohttp.ClientError as exc:
            raise ValueError(_("Network error while contacting RustMaps: {exc}").format(exc=exc))

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
            title=_("🗺️ Map {map_id}").format(map_id=map_info.map_id),
            color=discord.Color.blue(),
        )
        if map_info.map_type:
            embed.description = _("**Type:** {map_type}").format(map_type=map_info.map_type)

        embed.add_field(name=_("🌱 Seed"), value=f"`{map_info.seed}`", inline=True)
        embed.add_field(name=_("📏 Size"), value=f"`{map_info.size}`", inline=True)
        if map_info.total_monuments:
            embed.add_field(
                name=_("🏛️ Monuments"), value=str(map_info.total_monuments), inline=True
            )

        biomes = map_info.biomes_display()
        if biomes:
            embed.add_field(name=_("🌍 Biomes"), value=biomes, inline=False)

        terrain = map_info.terrain_display()
        if terrain:
            embed.add_field(name=_("🏔️ Terrain"), value=terrain, inline=False)

        if map_info.land_percentage is not None:
            embed.add_field(
                name=_("🗺️ Land"), value=f"{map_info.land_percentage}%", inline=True
            )

        monuments = map_info.relevant_monuments_display()
        if monuments:
            embed.add_field(name=_("📍 Monuments"), value=monuments, inline=False)

        embed.add_field(
            name=_("🔗 See full map"),
            value=_("[rustmaps.com]({url})").format(url=map_info.url),
            inline=False,
        )

        # The thumbnailUrl render is the good one -> show it big; imageUrl as the small icon.
        if map_info.thumbnail_url:
            embed.set_image(url=map_info.thumbnail_url)
            if map_info.image_url:
                embed.set_thumbnail(url=map_info.image_url)
        elif map_info.image_url:
            embed.set_image(url=map_info.image_url)

        embed.set_footer(text=_("RustMaps Vote • {total_maps} maps in this vote").format(total_maps=total_maps))
        return embed

    def build_results_embed(self, session: VoteSession) -> discord.Embed:
        embed = discord.Embed(
            title=_("🗳️ Rust map vote"),
            description=_("Press the button with the number of the map you prefer."),
            color=discord.Color.blurple(),
        )
        for m in session.maps:
            embed.add_field(
                name=_("Map {map_id}").format(map_id=m.map_id),
                value=_("🌱 Seed: `{seed}` • 📏 Size: `{size}`\n🗳️ **{vote_count}** vote(s) • [See map]({url})").format(seed=m.seed, size=m.size, vote_count=m.vote_count, url=m.url),
                inline=False,
            )
        votes = session.max_votes_per_user
        embed.set_footer(
            text=_("{votes} vote(s) per person • {total_voters} voter(s) so far").format(votes=votes, total_voters=session.total_voters)
        )
        return embed

    def build_winner_embed(self, session: VoteSession) -> discord.Embed:
        ranking = session.get_ranking()
        winner = ranking[0] if ranking else None
        embed = discord.Embed(color=discord.Color.gold())
        if not winner or session.total_votes == 0:
            embed.title = _("🏁 Vote finished")
            embed.description = _("No votes were cast.")
            return embed

        embed.title = _("🏆 Map {map_id} wins!").format(map_id=winner.map_id)
        embed.add_field(
            name=_("🥇 Winner"),
            value=_("**Map {map_id}** — Seed `{seed}`, Size `{size}`\n🗳️ {vote_count} vote(s)\n[See map]({url})").format(map_id=winner.map_id, seed=winner.seed, size=winner.size, vote_count=winner.vote_count, url=winner.url),
            inline=False,
        )
        medals = [_("🥈 2nd place"), _("🥉 3rd place")]
        for medal, m in zip(medals, ranking[1:3]):
            embed.add_field(
                name=medal,
                value=_("Map {map_id} — {vote_count} vote(s)").format(map_id=m.map_id, vote_count=m.vote_count),
                inline=False,
            )
        embed.set_footer(
            text=_("{total_votes} vote(s) from {total_voters} voter(s)").format(total_votes=session.total_votes, total_voters=session.total_voters)
        )
        return embed

    def build_add_confirm_embed(self, map_info: MapInfo, map_count: int) -> discord.Embed:
        embed = discord.Embed(
            title=_("✅ Map added"),
            color=discord.Color.green(),
        )
        lines = [
            _("🌱 Seed: `{seed}`").format(seed=map_info.seed),
            _("📏 Size: `{size}`").format(size=map_info.size),
        ]
        if map_info.map_type:
            lines.append(_("🏷️ Type: {map_type}").format(map_type=map_info.map_type))
        if map_info.total_monuments:
            lines.append(_("🏛️ Monuments: {total_monuments}").format(total_monuments=map_info.total_monuments))
        lines.append(_("🗺️ Maps in the session: **{map_count}/{MAX_MAPS}**").format(map_count=map_count, MAX_MAPS=MAX_MAPS))
        embed.add_field(
            name=_("Map {map_id} added").format(map_id=map_info.map_id),
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
        """Rust map votes using rustmaps.com."""
        # Sin subcomando Red ya muestra la ayuda (autohelp); enviarla aqui la duplicaba.

    @votemap.command(name="setapi")
    @checks.admin_or_permissions(administrator=True)
    @app_commands.describe(key="Tu API key de RustMaps (v4)")
    async def setapi(self, ctx: commands.Context, key: str) -> None:
        """Set the global RustMaps API key."""
        await self.config.api_key.set(key.strip())
        # Try to remove the message so the key isn't left visible in chat.
        if ctx.message and ctx.guild:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass
        await ctx.send(_("✅ RustMaps API key set."), ephemeral=True)

    @votemap.command(name="maxvotes")
    @checks.admin_or_permissions(administrator=True)
    @app_commands.describe(amount="Número de votos por persona (mínimo 1)")
    async def maxvotes(self, ctx: commands.Context, amount: int) -> None:
        """Set how many maps each person can vote for per vote (default 1)."""
        if amount < 1:
            await ctx.send(_("❌ The number of votes must be at least 1."), ephemeral=True)
            return
        if amount > MAX_MAPS:
            await ctx.send(
                _("❌ The number of votes can't exceed the maximum number of maps ({MAX_MAPS}).").format(MAX_MAPS=MAX_MAPS),
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
            _("✅ Each person can vote for **{amount}** map(s) per vote.").format(amount=amount),
            ephemeral=True,
        )

    @votemap.command(name="add")
    @checks.admin_or_permissions(administrator=True)
    @app_commands.describe(url="URL del mapa en rustmaps.com")
    async def add(self, ctx: commands.Context, url: str) -> None:
        """Add a map to the current vote."""
        if await self.config.guild(ctx.guild).vote_session_active():
            await ctx.send(
                _("❌ A vote is already running. End it with `[p]votemap end` before adding more maps."),
                ephemeral=True,
            )
            return

        if not await self.config.api_key():
            await ctx.send(
                _("❌ Set the API key first with `[p]votemap setapi <key>`."),
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
            await ctx.send(_("❌ That map is already in the vote."), ephemeral=True)
            return

        if not session.add_map(map_info):
            await ctx.send(
                _("❌ You reached the maximum of {MAX_MAPS} maps per vote.").format(MAX_MAPS=MAX_MAPS),
                ephemeral=True,
            )
            return

        await self.save_session(ctx.guild, session)
        await ctx.send(embed=self.build_add_confirm_embed(map_info, len(session.maps)))

    @votemap.command(name="remove")
    @checks.admin_or_permissions(administrator=True)
    @app_commands.describe(map_id="Número del mapa a quitar")
    async def remove(self, ctx: commands.Context, map_id: int) -> None:
        """Remove a map from the current vote (before it starts)."""
        if await self.config.guild(ctx.guild).vote_session_active():
            await ctx.send(
                _("❌ You can't remove maps while a vote is running. Use `[p]votemap end`."),
                ephemeral=True,
            )
            return

        session = await self.load_session(ctx.guild)
        if session is None or not session.maps:
            await ctx.send(_("❌ No vote is being prepared."), ephemeral=True)
            return

        if not session.remove_map(map_id):
            await ctx.send(_("❌ Map number {map_id} does not exist.").format(map_id=map_id), ephemeral=True)
            return

        if not session.maps:
            await self.clear_session(ctx.guild)
            await ctx.send(_("✅ Map removed. The vote was empty and has been cancelled."))
            return

        await self.save_session(ctx.guild, session)
        await ctx.send(
            _("✅ Map removed. **{count}** map(s) left (renumbered from 1).").format(count=len(session.maps))
        )

    @votemap.command(name="list")
    async def list_maps(self, ctx: commands.Context) -> None:
        """Show the maps of the current vote."""
        session = await self.load_session(ctx.guild)
        if session is None or not session.maps:
            await ctx.send(_("ℹ️ There is no active or prepared vote."), ephemeral=True)
            return

        active = await self.config.guild(ctx.guild).vote_session_active()
        embed = discord.Embed(
            title=_("🗺️ Maps in the vote"),
            color=discord.Color.blue(),
        )
        for m in session.maps:
            value = _("🌱 Seed: `{seed}` • 📏 Size: `{size}` • [See map]({url})").format(seed=m.seed, size=m.size, url=m.url)
            if active:
                value += _("\n🗳️ {vote_count} vote(s)").format(vote_count=m.vote_count)
            embed.add_field(name=_("Map {map_id}").format(map_id=m.map_id), value=value, inline=False)
        state = _("Running") if active else _("Being prepared")
        embed.set_footer(
            text=_("Status: {state} • {count}/{MAX_MAPS} maps • {max_votes_per_user} vote(s) per person").format(state=state, count=len(session.maps), MAX_MAPS=MAX_MAPS, max_votes_per_user=session.max_votes_per_user)
        )
        await ctx.send(embed=embed)

    @votemap.command(name="start")
    @checks.admin_or_permissions(administrator=True)
    async def start(self, ctx: commands.Context) -> None:
        """Start the vote with embeds and buttons."""
        if await self.config.guild(ctx.guild).vote_session_active():
            await ctx.send(_("❌ A vote is already running."), ephemeral=True)
            return

        session = await self.load_session(ctx.guild)
        if session is None or len(session.maps) < MIN_MAPS:
            await ctx.send(
                _("❌ You need at least {MIN_MAPS} maps to start. Add them with `[p]votemap add <url>`.").format(MIN_MAPS=MIN_MAPS),
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
        map_embed_ids: list[int] = []
        for m in session.maps:
            msg = await channel.send(embed=self.build_vote_embed(m, len(session.maps)))
            map_embed_ids.append(msg.id)
        session.map_embed_message_ids = map_embed_ids

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
            await ctx.send(_("✅ Vote started in {channel}!").format(channel=channel.mention), ephemeral=True)
        else:
            await ctx.send(_("✅ Vote started!"), ephemeral=True)

    @votemap.command(name="end")
    @checks.admin_or_permissions(administrator=True)
    async def end(self, ctx: commands.Context) -> None:
        """End the vote, clean up the previous messages and announce the winner."""
        async with self._get_lock(ctx.guild.id):
            session = await self.load_session(ctx.guild)
            active = await self.config.guild(ctx.guild).vote_session_active()
            if session is None or not active:
                await ctx.send(_("❌ No vote is running."), ephemeral=True)
                return

            session.ended_at = datetime.utcnow()
            embed = self.build_winner_embed(session)

            channel = ctx.guild.get_channel(session.channel_id) if session.channel_id else ctx.channel
            if channel is None:
                channel = ctx.channel

            # Delete the individual map embeds.
            for msg_id in session.map_embed_message_ids:
                try:
                    msg = await channel.fetch_message(msg_id)
                    await msg.delete()
                except (discord.NotFound, discord.HTTPException):
                    pass

            # Delete the voting message (buttons and status embed) instead of disabling it.
            if session.voting_message_id:
                try:
                    msg = await channel.fetch_message(session.voting_message_id)
                    await msg.delete()
                except (discord.NotFound, discord.HTTPException):
                    pass

            await self.clear_session(ctx.guild)

        await channel.send(embed=embed)
        if channel.id != ctx.channel.id:
            await ctx.send(_("✅ Vote finished."), ephemeral=True)

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
        """Cancel the current vote or preparation without announcing a winner."""
        session = await self.load_session(ctx.guild)
        if session is None:
            await ctx.send(_("ℹ️ There is no vote to cancel."), ephemeral=True)
            return
        if await self.config.guild(ctx.guild).vote_session_active():
            await self._disable_voting_message(ctx.guild, session)
        await self.clear_session(ctx.guild)
        await ctx.send(_("🗑️ Vote cancelled."))

    @votemap.command(name="settings")
    @checks.admin_or_permissions(administrator=True)
    async def settings(self, ctx: commands.Context) -> None:
        """Show the vote settings."""
        guild_conf = await self.config.guild(ctx.guild).all()
        api_set = bool(await self.config.api_key())
        session = await self.load_session(ctx.guild)

        channel = (
            ctx.guild.get_channel(guild_conf["vote_channel_id"])
            if guild_conf["vote_channel_id"]
            else None
        )

        embed = discord.Embed(title=_("⚙️ RustMaps Vote settings"), color=discord.Color.blurple())
        embed.add_field(name=_("🔑 API key"), value=_("✅ Set") if api_set else _("❌ Not set"), inline=True)
        embed.add_field(
            name=_("🗳️ Votes per person"),
            value=str(guild_conf["max_votes_per_user"]),
            inline=True,
        )
        embed.add_field(
            name=_("📢 Vote channel"),
            value=channel.mention if channel else _("Channel where `start` is used"),
            inline=True,
        )
        if session:
            state = _("Running") if guild_conf["vote_session_active"] else _("Being prepared")
            embed.add_field(
                name=_("📊 Current session"),
                value=_("Status: **{state}**\nMaps: **{count}/{MAX_MAPS}**\nVoters: **{total_voters}**").format(state=state, count=len(session.maps), MAX_MAPS=MAX_MAPS, total_voters=session.total_voters),
                inline=False,
            )
        else:
            embed.add_field(name=_("📊 Current session"), value=_("None"), inline=False)
        await ctx.send(embed=embed)

    @votemap.command(name="setchannel")
    @checks.admin_or_permissions(administrator=True)
    @app_commands.describe(channel="Canal donde se publicarán las votaciones (vacío para usar el actual)")
    async def setchannel(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None
    ) -> None:
        """Set the default channel for votes."""
        if channel:
            await self.config.guild(ctx.guild).vote_channel_id.set(channel.id)
            await ctx.send(_("✅ Votes will be posted in {channel}.").format(channel=channel.mention), ephemeral=True)
        else:
            await self.config.guild(ctx.guild).vote_channel_id.set(None)
            await ctx.send(
                _("✅ Votes will be posted in the channel where `start` is run."),
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
        await set_contextual_locales_from_guild(self.bot, interaction.guild)

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
                    _("⚠️ This vote has already ended."), ephemeral=True
                )
                return

            action = session.toggle_vote(interaction.user.id, map_id)

            if action == "invalid":
                await interaction.response.send_message(_("❌ Invalid map."), ephemeral=True)
                return
            if action == "limit":
                await interaction.response.send_message(
                    _("⚠️ You already used all your votes ({max_votes_per_user}). Press a map you already voted for again to free a vote.").format(max_votes_per_user=session.max_votes_per_user),
                    ephemeral=True,
                )
                return

            await self.save_session(guild, session)
            await self._update_voting_message(guild, session)

        if action == "added":
            await interaction.response.send_message(
                _("✅ You voted for **Map {map_id}**.").format(map_id=map_id), ephemeral=True
            )
        else:  # removed
            await interaction.response.send_message(
                _("↩️ You removed your vote from **Map {map_id}**.").format(map_id=map_id), ephemeral=True
            )
