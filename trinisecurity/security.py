"""
Trini Security - capa defensiva de La Trini.

Auditoria de permisos, modelo de autoridad propio, roles protegidos,
whitelists, Security Watch, Anti-Nuke con risk score y quarantine,
Emergency Lockdown, timeline, reconstruccion de incidentes, Health Score,
digest semanal y registro de cambios de configuracion.

By Killerbite95
"""

from __future__ import annotations

import copy
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import discord
from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.bot import Red

from .audit import AuditReport, run_guild_audit
from .commands import CommandsMixin
from .constants import (
    DEFAULT_LEVELS,
    DEFAULT_SCORES,
    DEFAULT_THRESHOLDS,
    WHITELIST_TYPES,
)
from .engine import EngineMixin
from .views import DYNAMIC_ITEMS

log = logging.getLogger("red.killerbite95.trinisecurity")

DEFAULT_ANTINUKE = {
    "enabled": False,
    "thresholds": DEFAULT_THRESHOLDS,
    "scores": DEFAULT_SCORES,
    "levels": DEFAULT_LEVELS,
    "window": 600,
    "trusted_immune": True,
    "quarantine_role": None,
    "bot_policy": "kick",
}

MAX_SETTINGS_LOG = 500


class TriniSecurity(CommandsMixin, EngineMixin, commands.Cog):
    """Capa defensiva de La Trini: auditoria, autoridad, roles protegidos, anti-nuke e incidentes."""

    __author__ = "Killerbite95"
    __version__ = "1.0.0"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0x7121A5EC, force_registration=True)
        self.config.register_guild(
            log_channel=None,
            alert_role=None,
            authority={"extra_owners": [], "trusted_admins": []},
            watch={"enabled": False, "level": "normal"},
            protected_roles={},
            whitelists={t: [] for t in WHITELIST_TYPES},
            temp_whitelist=[],
            antinuke=copy.deepcopy(DEFAULT_ANTINUKE),
            lockdown={"active": False, "by": None, "at": None, "invites_disabled_by_us": False, "disable_invites": True},
            quarantined={},
            events=[],
            next_event_id=1,
            incidents={},
            next_incident_id=1,
            settings_log=[],
            health_history=[],
            last_health=None,
            last_findings=[],
            digest={"enabled": False, "channel": None, "last_sent": 0},
        )
        self._engine_init()

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre = super().format_help_for_context(ctx)
        return f"{pre}\n\nVersion: {self.__version__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int) -> None:
        for guild_id, data in (await self.config.all_guilds()).items():
            group = self.config.guild_from_id(guild_id)
            auth = data.get("authority", {})
            if user_id in auth.get("extra_owners", []) or user_id in auth.get("trusted_admins", []):
                async with group.authority() as a:
                    for key in ("extra_owners", "trusted_admins"):
                        if user_id in a.get(key, []):
                            a[key].remove(user_id)
            async with group.events() as events:
                for e in events:
                    if e.get("actor") == user_id:
                        e["actor"] = None
                    if e.get("target") == user_id:
                        e["target"] = None
                        e["target_name"] = "usuario eliminado"

    async def cog_load(self) -> None:
        self.bot.add_dynamic_items(*DYNAMIC_ITEMS)
        self.maintenance_loop.start()

    async def cog_unload(self) -> None:
        self.maintenance_loop.cancel()
        try:
            self.bot.remove_dynamic_items(*DYNAMIC_ITEMS)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Helpers de configuracion
    # ------------------------------------------------------------------

    @staticmethod
    def _merged_antinuke(stored: Dict[str, Any]) -> Dict[str, Any]:
        merged = copy.deepcopy(DEFAULT_ANTINUKE)
        for key, value in (stored or {}).items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = {**merged[key], **value}
            else:
                merged[key] = value
        return merged

    async def _get_whitelists(self, guild: discord.Guild) -> Dict[str, List[Any]]:
        stored = await self.config.guild(guild).whitelists()
        return {t: list(stored.get(t, [])) for t in WHITELIST_TYPES}

    async def _settings_log(self, guild: discord.Guild, actor: Optional[discord.abc.User], action: str, detail: str, module: str = "Security") -> None:
        async with self.config.guild(guild).settings_log() as entries:
            entries.append(
                {
                    "ts": int(time.time()),
                    "actor": actor.id if actor else None,
                    "module": module,
                    "action": action,
                    "detail": detail[:300],
                }
            )
            del entries[:-MAX_SETTINGS_LOG]
        watch = await self.config.guild(guild).watch()
        if watch.get("enabled") and module == "Security":
            embed = discord.Embed(
                title="⚙️ Cambio en la configuracion de Security",
                color=discord.Color.blurple(),
                description=f"**{action}**\n{detail[:1000]}",
                timestamp=discord.utils.utcnow(),
            )
            embed.add_field(name="Por", value=actor.mention if actor else "sistema")
            await self._send_log(guild, embed)

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    async def get_authority_level(self, member: discord.Member) -> str:
        """owner | extra_owner | trusted_admin | admin | member"""
        guild = member.guild
        if member.id == guild.owner_id:
            return "owner"
        auth = await self.config.guild(guild).authority()
        if member.id in auth.get("extra_owners", []) or member.id in getattr(self.bot, "owner_ids", set()):
            return "extra_owner"
        if member.id in auth.get("trusted_admins", []):
            return "trusted_admin"
        if member.guild_permissions.administrator or member.guild_permissions.manage_guild or await self.bot.is_admin(member):
            return "admin"
        return "member"

    async def is_trusted(self, member: discord.Member) -> bool:
        return await self.get_authority_level(member) in ("owner", "extra_owner", "trusted_admin")

    async def compute_health(self, guild: discord.Guild, *, fetch_remote: bool = True) -> AuditReport:
        g = self.config.guild(guild)
        protected = await g.protected_roles()
        antinuke = self._merged_antinuke(await g.antinuke())
        watch = await g.watch()
        bonuses: List[Tuple[int, str]] = []
        if protected:
            bonuses.append((5, f"Protected Roles activo ({len(protected)})"))
        if antinuke.get("enabled"):
            bonuses.append((5, "Anti-Nuke activo"))
        if watch.get("enabled"):
            bonuses.append((3, "Security Watch activo"))
        backups = self.bot.get_cog("TriniBackups")
        if backups is not None and hasattr(backups, "is_scheduled"):
            try:
                if await backups.is_scheduled(guild):
                    bonuses.append((2, "Backups automaticos programados"))
            except Exception:
                pass
        hints: List[str] = []
        profiles = self.bot.get_cog("TriniProfiles")
        if profiles is not None and hasattr(profiles, "get_profile"):
            try:
                hints = (await profiles.get_profile(guild)).get("hints", [])
            except Exception:
                hints = []
        extra: List[Dict[str, Any]] = []
        for cog in list(self.bot.cogs.values()):
            if cog is self:
                continue
            hook = getattr(cog, "trini_security_findings", None)
            if hook is None:
                continue
            try:
                extra.extend(await hook(guild))
            except Exception:
                log.exception("Error en trini_security_findings de %s", cog.qualified_name)
        return await run_guild_audit(
            guild,
            whitelists=await self._get_whitelists(guild),
            protected_roles=[int(r) for r in protected],
            config_bonus=bonuses,
            profile_hints=hints,
            extra_findings=extra,
            fetch_remote=fetch_remote,
        )

    async def compare_with_backup(self, guild: discord.Guild, before_ts: Optional[float]) -> Tuple[List[discord.Embed], Optional[str]]:
        backups = self.bot.get_cog("TriniBackups")
        if backups is None:
            return [], "Trini Backups no esta cargado."
        if before_ts:
            meta = await backups.latest_snapshot_before(guild, before_ts)
        else:
            meta = await backups.latest_snapshot_before(guild, time.time() + 1)
        if meta is None:
            return [], "No hay ningun backup previo con el que comparar."
        embeds = await backups.diff_current_embeds(guild, meta["id"])
        return embeds, None

    # ------------------------------------------------------------------
    # Integracion con otros modulos Trini
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_trini_settings_change(self, guild: discord.Guild, module: str, actor, action: str, detail: str) -> None:
        if module == "Security":
            return
        try:
            await self._settings_log(guild, actor, action, detail, module=module)
        except Exception:
            log.exception("Error registrando cambio de %s", module)

    @commands.Cog.listener()
    async def on_trini_profile_applied(self, guild: discord.Guild, profile_key: str, actor) -> None:
        profiles = self.bot.get_cog("TriniProfiles")
        if profiles is None:
            return
        try:
            data = await profiles.get_profile(guild)
            if "security" not in data.get("modules", {}):
                return
            level = data.get("security_level", "standard")
            changes = []
            if level in ("high", "strict"):
                async with self.config.guild(guild).watch() as watch:
                    if not watch.get("enabled"):
                        watch["enabled"] = True
                        changes.append("Security Watch activado")
            if level == "strict":
                async with self.config.guild(guild).antinuke() as an:
                    if not an.get("enabled"):
                        an["enabled"] = True
                        changes.append("Anti-Nuke activado")
            if changes:
                await self._settings_log(guild, actor, "profile_security_level", f"{profile_key}/{level}: " + ", ".join(changes))
        except Exception:
            log.exception("Error aplicando nivel de seguridad del perfil")

    async def trini_export(self, guild: discord.Guild) -> Dict[str, Any]:
        data = await self.config.guild(guild).all()
        keep = ("log_channel", "alert_role", "authority", "watch", "protected_roles", "whitelists", "antinuke", "digest")
        return {k: data[k] for k in keep}

    async def trini_import(self, guild: discord.Guild, data: Dict[str, Any], *, same_guild: bool) -> List[str]:
        warnings = []
        g = self.config.guild(guild)
        for key in ("log_channel", "alert_role", "watch", "protected_roles", "whitelists", "antinuke", "digest"):
            if key in data:
                await g.set_raw(key, value=data[key])
        if same_guild and "authority" in data:
            await g.authority.set(data["authority"])
        elif "authority" in data:
            warnings.append("Security: la autoridad (Extra Owners/Trusted Admins) no se importa entre servidores distintos.")
        prot = await g.protected_roles()
        cleaned = {k: v for k, v in prot.items() if k.isdigit() and guild.get_role(int(k))}
        if len(cleaned) != len(prot):
            await g.protected_roles.set(cleaned)
            warnings.append(f"Security: {len(prot) - len(cleaned)} roles protegidos no existen en este servidor.")
        await self._settings_log(guild, None, "import", "Configuracion importada via Profiles")
        return warnings

    # ------------------------------------------------------------------
    # Mantenimiento: whitelist temporal, health diario y digest semanal
    # ------------------------------------------------------------------

    @tasks.loop(hours=1)
    async def maintenance_loop(self) -> None:
        now = time.time()
        for guild_id in list(self._restricted):
            self._restricted[guild_id] = {u: t for u, t in self._restricted[guild_id].items() if t > now}
        for guild in list(self.bot.guilds):
            try:
                g = self.config.guild(guild)
                temp = await g.temp_whitelist()
                if temp:
                    alive = [t for t in temp if t["expires"] > now]
                    if len(alive) != len(temp):
                        await g.temp_whitelist.set(alive)
                log_channel = await g.log_channel()
                digest = await g.digest()
                if not log_channel and not digest.get("enabled"):
                    continue
                history = await g.health_history()
                if not history or now - history[-1]["ts"] >= 86400 - 300:
                    report = await self.compute_health(guild, fetch_remote=True)
                    history.append({"ts": int(now), "score": report.score, "findings": [f.title for f in report.findings if f.severity in ("critical", "warning")]})
                    await g.health_history.set(history[-90:])
                    await g.last_health.set(report.score)
                if digest.get("enabled") and now - digest.get("last_sent", 0) >= 7 * 86400 - 600:
                    embed = await self.build_digest(guild, days=7)
                    channel = guild.get_channel_or_thread(digest.get("channel") or log_channel)
                    if channel is not None:
                        await channel.send(embed=embed)
                    async with g.digest() as d:
                        d["last_sent"] = int(now)
            except Exception:
                log.exception("Error en mantenimiento de Security para %s", guild.id)

    @maintenance_loop.before_loop
    async def _before_maintenance(self) -> None:
        await self.bot.wait_until_red_ready()

    async def build_digest(self, guild: discord.Guild, *, days: int = 7) -> discord.Embed:
        now = time.time()
        start = now - days * 86400
        events = [e for e in await self.config.guild(guild).events() if e["ts"] >= start]
        incidents = [i for i in (await self.config.guild(guild).incidents()).values() if i["start"] >= start]
        settings = [s for s in await self.config.guild(guild).settings_log() if s["ts"] >= start]

        def count(*types):
            return sum(1 for e in events if e["type"] in types)

        admin_types = ("role_update", "role_create", "role_delete", "admin_grant", "dangerous_permission",
                       "everyone_change", "overwrite_update", "channel_delete", "channel_create", "webhook_create",
                       "bot_add", "guild_update", "member_role_update")
        embed = discord.Embed(
            title="🔐 Security Digest",
            color=discord.Color.blurple(),
            description=f"**Periodo:** <t:{int(start)}:d> — <t:{int(now)}:d>",
        )
        embed.add_field(
            name="Actividad",
            value=(
                f"Cambios administrativos: **{count(*admin_types)}**\n"
                f"Cambios criticos: **{sum(1 for e in events if e['severity'] == 'critical')}**\n"
                f"Roles modificados: **{count('role_update', 'admin_grant', 'dangerous_permission', 'everyone_change')}**\n"
                f"Bots añadidos: **{count('bot_add')}**\n"
                f"Webhooks creados: **{count('webhook_create')}**\n"
                f"Cambios de configuracion: **{len(settings)}**"
            ),
            inline=False,
        )
        embed.add_field(
            name="Anti-Nuke",
            value=f"{len(incidents)} activacion(es)" + (
                f" · {sum(1 for i in incidents if i['level'] == 'quarantine')} quarantine" if incidents else ""
            ),
            inline=True,
        )
        embed.add_field(name="Protected Roles", value=f"{count('protected_role_violation')} intento(s) bloqueados", inline=True)
        history = [h for h in await self.config.guild(guild).health_history() if h["ts"] >= start - 86400]
        if history:
            first, last = history[0], history[-1]
            embed.add_field(name="Security Health", value=f"{first['score']} → **{last['score']}**", inline=False)
            resolved = [f for f in first.get("findings", []) if f not in last.get("findings", [])]
            new = [f for f in last.get("findings", []) if f not in first.get("findings", [])]
            if resolved:
                embed.add_field(name="Principales mejoras", value="\n".join(f"• {f}" for f in resolved[:6])[:1024], inline=False)
            if new:
                embed.add_field(name="Nuevos riesgos", value="\n".join(f"• {f}" for f in new[:6])[:1024], inline=False)
        return embed
