"""
TriniProfiles - Configuracion por perfiles para La Trini.

By Killerbite95
"""

from __future__ import annotations

import io
import json
import logging
import time
from typing import Any, Dict, List, Optional

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, humanize_list, pagify

from .dashboard_integration import DashboardIntegration
from .portable import collect_references, export_cog, import_cog, remap_references
from .registry import (
    LEVEL_LABELS,
    MODULES,
    ON,
    OPTIONAL,
    PROFILES,
    RECOMMENDED,
    ProfileInfo,
    dependents_of,
    resolve_cog,
    resolve_dependencies,
    resolve_qualified_name,
)
from redbot.core.i18n import Translator, cog_i18n, set_contextual_locales_from_guild

_ = Translator("TriniProfiles", __file__)


def N_(text: str) -> str:
    """Marca un texto de una constante para traducirlo al usarlo con ``_()``."""
    return text

log = logging.getLogger("red.killerbite95.triniprofiles")

EXPORT_VERSION = 1
MAX_HISTORY = 200
COLOR = discord.Color.from_rgb(88, 101, 242)


# Estado real de cada modulo en un servidor (ver ``TriniProfiles.effective_states``).
STATE_ON = "on"            # cargado y habilitado en este servidor: funciona
STATE_OFF = "off"          # cargado pero desactivado en este servidor (disablecog)
STATE_MISSING_ON = "missing_on"  # Profiles lo quiere activo, pero el cog no esta cargado
STATE_MISSING = "missing"  # no cargado y sin activar en Profiles
STATE_ICON = {STATE_ON: "🟢", STATE_OFF: "🔴", STATE_MISSING_ON: "🟠", STATE_MISSING: "⚫"}
STATE_LEGEND = N_("🟢 running · 🔴 disabled in this server · 🟠 enabled but not loaded · ⚫ not loaded")


def _clean_name(name: str) -> str:
    """Normaliza el nombre de un preset (sin comillas ni espacios sobrantes)."""
    return name.strip().strip('"').strip("'").strip()[:60]


def _join_capped(lines: List[str], limit: int = 1024) -> str:
    """Une ``lines`` con saltos de linea sin superar ``limit``, cortando por
    lineas completas (nunca a mitad de una) y avisando cuantas faltan."""
    out: List[str] = []
    used = 0
    for i, line in enumerate(lines):
        extra = len(line) + (1 if out else 0)
        remaining = len(lines) - i
        marker = _("… and {remaining} more").format(remaining=remaining) if remaining else ""
        if used + extra + (len(marker) + 1 if marker else 0) > limit:
            if marker:
                out.append(marker)
            break
        out.append(line)
        used += extra
    return "\n".join(out) or "—"


class AuthorView(discord.ui.View):
    """Vista que solo puede usar quien ejecuto el comando."""

    def __init__(self, author: discord.abc.User, *, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.author = author
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        await set_contextual_locales_from_guild(interaction.client, interaction.guild)
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                _("Only whoever ran the command can use these controls."), ephemeral=True
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class ProfileSelect(discord.ui.Select):
    def __init__(self, view: "SetupView"):
        options = [
            discord.SelectOption(
                label=_(p.name), value=p.key, emoji=p.emoji, description=_(p.description)[:100]
            )
            for p in PROFILES.values()
        ]
        super().__init__(placeholder=_("How is this Discord used?"), options=options)
        self.setup_view = view
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Los callbacks no pasan por un comando: se usa el idioma del servidor.
        await set_contextual_locales_from_guild(interaction.client, interaction.guild)
        return await super().interaction_check(interaction)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.setup_view.selected = self.values[0]
        for item in self.setup_view.children:
            if isinstance(item, discord.ui.Button) and item.custom_id != "cancel":
                item.disabled = False
        embed = await self.setup_view.cog.build_profile_preview(
            interaction.guild, PROFILES[self.values[0]]
        )
        await interaction.response.edit_message(embed=embed, view=self.setup_view)


class SetupView(AuthorView):
    def __init__(self, cog: "TriniProfiles", ctx: commands.Context):
        super().__init__(ctx.author)
        self.cog = cog
        self.ctx = ctx
        self.selected: Optional[str] = None
        self.add_item(ProfileSelect(self))
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Los callbacks no pasan por un comando: se usa el idioma del servidor.
        await set_contextual_locales_from_guild(interaction.client, interaction.guild)
        return await super().interaction_check(interaction)

    async def _apply(self, interaction: discord.Interaction, *, recommended: bool, exact: bool):
        if self.selected is None:
            return await interaction.response.send_message(_("Pick a profile first."), ephemeral=True)
        await interaction.response.defer()
        result = await self.cog.apply_profile(
            interaction.guild,
            PROFILES[self.selected],
            actor=interaction.user,
            include_recommended=recommended,
            exact=exact,
        )
        self.stop()
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(embed=result, view=self)

    @discord.ui.button(label=_("Apply"), style=discord.ButtonStyle.green, emoji="✅", disabled=True, row=1)
    async def apply_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._apply(interaction, recommended=False, exact=False)

    @discord.ui.button(label=_("Apply + recommended"), style=discord.ButtonStyle.blurple, emoji="⭐", disabled=True, row=1)
    async def apply_rec_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._apply(interaction, recommended=True, exact=False)

    @discord.ui.button(label=_("Apply exact"), style=discord.ButtonStyle.grey, emoji="🧹", disabled=True, row=1)
    async def apply_exact_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._apply(interaction, recommended=True, exact=True)

    @discord.ui.button(label=_("Cancel"), style=discord.ButtonStyle.red, custom_id="cancel", row=1)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content=_("Setup cancelled."), view=self)


class ConfirmView(AuthorView):
    def __init__(self, author: discord.abc.User, *, confirm_label: str = "Continuar"):
        super().__init__(author, timeout=60)
        self.value: Optional[bool] = None
        self.confirm.label = confirm_label
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Los callbacks no pasan por un comando: se usa el idioma del servidor.
        await set_contextual_locales_from_guild(interaction.client, interaction.guild)
        return await super().interaction_check(interaction)

    @discord.ui.button(label=_("Continue"), style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label=_("Cancel"), style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.stop()
        await interaction.response.defer()


class ModuleToggleSelect(discord.ui.Select):
    def __init__(self, view: "ModulesView", category: str, effective: Dict[str, str]):
        options = []
        for info in MODULES.values():
            if info.category != category or info.core:
                continue
            state = effective.get(info.key, STATE_MISSING)
            active = state in (STATE_ON, STATE_MISSING_ON)
            options.append(
                discord.SelectOption(
                    label=(_("Disable {name}") if active else _("Enable {name}")).format(name=_(info.name))[:100],
                    value=info.key,
                    emoji=STATE_ICON[state],
                    description=_(info.description)[:100],
                )
            )
        super().__init__(placeholder=_("{category}: enable / disable").format(category=_(category)), options=options[:25])
        self.modules_view = view
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Los callbacks no pasan por un comando: se usa el idioma del servidor.
        await set_contextual_locales_from_guild(interaction.client, interaction.guild)
        return await super().interaction_check(interaction)

    async def callback(self, interaction: discord.Interaction) -> None:
        key = self.values[0]
        cog = self.modules_view.cog
        states = await cog.config.guild(interaction.guild).modules()
        effective = await cog.effective_states(interaction.guild, states)
        enable = effective.get(key) not in (STATE_ON, STATE_MISSING_ON)
        if enable:
            deps = [d for d in resolve_dependencies([key]) if not states.get(d, False)]
            if deps:
                names = humanize_list([MODULES[d].name for d in deps])
                confirm = ConfirmView(interaction.user)
                await interaction.response.send_message(
                    _("**{name}** requires {names}.\n{names} will be enabled automatically.").format(name=MODULES[key].name, names=names),
                    view=confirm,
                    ephemeral=True,
                )
                await confirm.wait()
                if not confirm.value:
                    return await interaction.edit_original_response(content=_("Cancelled."), view=None)
                ok, msg = await cog.set_module(interaction.guild, key, True, actor=interaction.user)
                await interaction.edit_original_response(content=msg, view=None)
            else:
                await interaction.response.defer()
                ok, msg = await cog.set_module(interaction.guild, key, True, actor=interaction.user)
                await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.defer()
            ok, msg = await cog.set_module(interaction.guild, key, False, actor=interaction.user)
            await interaction.followup.send(msg, ephemeral=True)
        await self.modules_view.refresh()


class ModulesView(AuthorView):
    def __init__(self, cog: "TriniProfiles", ctx: commands.Context):
        super().__init__(ctx.author, timeout=300)
        self.cog = cog
        self.ctx = ctx
        self.category: Optional[str] = None
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Los callbacks no pasan por un comando: se usa el idioma del servidor.
        await set_contextual_locales_from_guild(interaction.client, interaction.guild)
        return await super().interaction_check(interaction)

    async def build(self) -> discord.Embed:
        self.clear_items()
        states = await self.cog.config.guild(self.ctx.guild).modules()
        effective = await self.cog.effective_states(self.ctx.guild, states)
        categories = sorted({m.category for m in MODULES.values() if not m.core})
        if self.category is None:
            self.category = categories[0]
        cat_select = discord.ui.Select(
            placeholder=_("Category"),
            options=[
                discord.SelectOption(label=_(c), value=c, default=(c == self.category))
                for c in categories
            ],
        )

        async def cat_callback(interaction: discord.Interaction):
            self.category = cat_select.values[0]
            embed = await self.build()
            await interaction.response.edit_message(embed=embed, view=self)

        cat_select.callback = cat_callback
        self.add_item(cat_select)
        self.add_item(ModuleToggleSelect(self, self.category, effective))
        return await self.cog.build_modules_embed(self.ctx.guild, states, effective)

    async def refresh(self) -> None:
        embed = await self.build()
        if self.message is not None:
            try:
                await self.message.edit(embed=embed, view=self)
            except discord.HTTPException:
                pass


@cog_i18n(_)
class TriniProfiles(DashboardIntegration, commands.Cog):
    """La Trini profile-based setup: templates, modules, dependencies and presets."""

    __author__ = "Killerbite95"
    __version__ = "1.0.0"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0x7121AF11E5, force_registration=True)
        self.config.register_guild(
            profile=None,
            security_level="standard",
            modules={},
            sync_red=True,
            applied_at=None,
            history=[],
        )
        self.config.register_global(presets={})

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre = super().format_help_for_context(ctx)
        return _("{pre}\n\nVersion: {version}").format(pre=pre, version=self.__version__)

    async def red_delete_data_for_user(self, **kwargs) -> None:
        return

    async def cog_check(self, ctx: commands.Context) -> bool:
        # Los slash de discord.py NO heredan los checks del grupo en los
        # subcomandos (con prefijo si). Este cog_check se ejecuta en ambos casos.
        if ctx.guild is None:
            return False
        if await ctx.bot.is_owner(ctx.author) or await ctx.bot.is_admin(ctx.author):
            return True
        return ctx.author.guild_permissions.manage_guild

    # ------------------------------------------------------------------
    # API publica para otros cogs
    # ------------------------------------------------------------------

    async def get_profile(self, guild: discord.Guild) -> Dict[str, Any]:
        data = await self.config.guild(guild).all()
        return {
            "profile": data["profile"],
            "security_level": data["security_level"],
            "modules": {k: v for k, v in data["modules"].items() if v},
            "hints": list(PROFILES[data["profile"]].protected_role_hints) if data["profile"] in PROFILES else [],
        }

    async def effective_states(self, guild: discord.Guild, states: Optional[Dict[str, bool]] = None) -> Dict[str, str]:
        """Estado REAL de cada modulo en ``guild``.

        Para los cogs cargados se pregunta a Red si estan desactivados en el
        servidor (``disablecog``), que es lo que decide si sus comandos
        funcionan. El apunte de Profiles solo cuenta para los cogs que no
        estan cargados (si "quieres" tenerlos activos o no).
        """
        if states is None:
            states = await self.config.guild(guild).modules()
        out: Dict[str, str] = {}
        for info in MODULES.values():
            wanted = info.core or bool(states.get(info.key, False))
            cog = resolve_cog(self.bot, info)
            if cog is None:
                out[info.key] = STATE_MISSING_ON if wanted else STATE_MISSING
            elif info.core:
                out[info.key] = STATE_ON
            else:
                disabled = await self.bot.cog_disabled_in_guild(cog, guild)
                out[info.key] = STATE_OFF if disabled else STATE_ON
        return out

    async def is_module_enabled(self, guild: discord.Guild, key: str) -> bool:
        return bool((await self.config.guild(guild).modules()).get(key, False))

    async def trini_export(self, guild: discord.Guild) -> Dict[str, Any]:
        data = await self.config.guild(guild).all()
        return {k: data[k] for k in ("profile", "security_level", "modules", "sync_red")}

    async def trini_import(self, guild: discord.Guild, data: Dict[str, Any], *, same_guild: bool) -> List[str]:
        for key in ("profile", "security_level", "modules", "sync_red"):
            if key in data:
                await self.config.guild(guild).set_raw(key, value=data[key])
        for key, enabled in data.get("modules", {}).items():
            await self._sync_red(guild, key, bool(enabled))
        return []

    # ------------------------------------------------------------------
    # Logica
    # ------------------------------------------------------------------

    async def _log(self, guild: discord.Guild, actor: Optional[discord.abc.User], action: str, detail: str) -> None:
        async with self.config.guild(guild).history() as history:
            history.append(
                {
                    "ts": int(time.time()),
                    "actor": actor.id if actor else None,
                    "action": action,
                    "detail": detail,
                }
            )
            del history[:-MAX_HISTORY]
        self.bot.dispatch("trini_settings_change", guild, "Profiles", actor, action, detail)

    async def _sync_red(self, guild: discord.Guild, key: str, enabled: bool) -> None:
        if not await self.config.guild(guild).sync_red():
            return
        info = MODULES.get(key)
        if info is None or info.core or info.key == "profiles":
            return
        cache = getattr(self.bot, "_disabled_cog_cache", None)
        if cache is None:
            return
        name = resolve_qualified_name(self.bot, info)
        try:
            if enabled:
                await cache.enable_cog_in_guild(name, guild.id)
            else:
                await cache.disable_cog_in_guild(name, guild.id)
        except Exception:
            log.exception("No se pudo sincronizar %s con Red en %s", name, guild.id)

    async def set_module(
        self, guild: discord.Guild, key: str, enabled: bool, *, actor: Optional[discord.abc.User]
    ) -> tuple:
        info = MODULES.get(key)
        if info is None:
            return False, _("Unknown module: `{key}`.").format(key=key)
        if info.core:
            if enabled:
                return True, _("**{info_name}** is a core module: it's always enabled.").format(info_name=_(info.name))
            return False, _("**{info_name}** is a core module and can't be disabled.").format(info_name=_(info.name))
        async with self.config.guild(guild).modules() as states:
            if enabled:
                to_enable = [key] + [d for d in resolve_dependencies([key]) if not states.get(d, False)]
                for k in to_enable:
                    states[k] = True
                changed = to_enable
            else:
                active = [k for k, v in states.items() if v]
                blockers = dependents_of(key, active)
                if blockers:
                    names = "\n".join(f"• {MODULES[b].name}" for b in blockers if b in MODULES)
                    return False, _("**{info_name}** can't be disabled.\n\nActive dependents:\n{names}").format(info_name=info.name, names=names)
                states[key] = False
                changed = [key]
        for k in changed:
            await self._sync_red(guild, k, enabled)
        names = humanize_list([MODULES[k].name for k in changed])
        await self._log(guild, actor, "module_enable" if enabled else "module_disable", names)
        msg = f"{_('🟢 Enabled') if enabled else _('⚫ Disabled')}: **{names}**."
        missing = [MODULES[k] for k in changed if enabled and resolve_cog(self.bot, MODULES[k]) is None]
        if missing:
            msg += _("\n⚠️ Not loaded in the bot: ") + humanize_list(
                [f"{m.name}" + (f" (`{m.package}`)" if m.package else "") for m in missing]
            )
        if not await self.config.guild(guild).sync_red():
            msg += _("\nℹ️ Red sync is disabled (`trini syncred`): this only changes Profiles' record.")
        return True, msg

    async def apply_profile(
        self,
        guild: discord.Guild,
        profile: ProfileInfo,
        *,
        actor: Optional[discord.abc.User],
        include_recommended: bool,
        exact: bool,
        modules_override: Optional[Dict[str, bool]] = None,
        security_level: Optional[str] = None,
    ) -> discord.Embed:
        backups = self.bot.get_cog("TriniBackups")
        if exact and backups is not None and hasattr(backups, "create_snapshot"):
            try:
                await backups.create_snapshot(guild, name=f"pre-profile-{profile.key}", kind="security", author=actor)
            except Exception:
                log.exception("No se pudo crear el snapshot previo al perfil")

        if modules_override is not None:
            wanted = {k for k, v in modules_override.items() if v and k in MODULES}
        else:
            levels = (ON, RECOMMENDED) if include_recommended else (ON,)
            wanted = {k for k, lvl in profile.modules.items() if lvl in levels}
        wanted |= set(resolve_dependencies(list(wanted)))
        wanted.add("profiles")

        enabled, disabled = [], []
        async with self.config.guild(guild).modules() as states:
            for key in wanted:
                if not states.get(key, False):
                    states[key] = True
                    enabled.append(key)
            if exact:
                for key, value in list(states.items()):
                    info = MODULES.get(key)
                    if value and key not in wanted and (info is None or not info.core):
                        states[key] = False
                        disabled.append(key)
        # Se sincronizan TODOS los deseados (no solo los que cambian de apunte):
        # asi se corrige tambien un ``disablecog`` hecho a mano fuera de Profiles.
        for key in wanted:
            await self._sync_red(guild, key, True)
        for key in disabled:
            await self._sync_red(guild, key, False)

        await self.config.guild(guild).profile.set(profile.key)
        await self.config.guild(guild).security_level.set(security_level or profile.security_level)
        await self.config.guild(guild).applied_at.set(int(time.time()))
        await self._log(
            guild,
            actor,
            "profile_apply",
            f"{profile.key} (+{len(enabled)} / -{len(disabled)}{_(', exact') if exact else ''})",
        )
        self.bot.dispatch("trini_profile_applied", guild, profile.key, actor)

        embed = discord.Embed(
            title=_("{emoji} Profile applied: {profile_name}").format(emoji=profile.emoji, profile_name=_(profile.name)),
            color=discord.Color.green(),
            description=_("A profile only sets up the base. You can change any module with `trini modules`."),
        )
        if enabled:
            embed.add_field(
                name=_("Enabled"),
                value=_join_capped([f"{MODULES[k].emoji} {MODULES[k].name}" for k in sorted(enabled) if k in MODULES]),
                inline=True,
            )
        if disabled:
            embed.add_field(
                name=_("Disabled"),
                value=_join_capped([f"{MODULES[k].emoji} {MODULES[k].name}" for k in sorted(disabled) if k in MODULES]),
                inline=True,
            )
        missing = [MODULES[k] for k in wanted if k in MODULES and resolve_cog(self.bot, MODULES[k]) is None]
        if missing:
            embed.add_field(
                name=_("⚠️ Not loaded in the bot"),
                value=_join_capped([
                    f"• {m.name}" + (f" — {hint}" if (hint := m.install_hint()) else "")
                    for m in missing
                ]),
                inline=False,
            )
        embed.add_field(
            name=_("🔐 Security level"),
            value=f"`{security_level or profile.security_level}`",
            inline=False,
        )
        if self.bot.get_cog("TriniSecurity") is not None:
            embed.set_footer(text=_("Recommended next step: security audit"))
        return embed

    async def build_profile_preview(self, guild: discord.Guild, profile: ProfileInfo) -> discord.Embed:
        embed = discord.Embed(
            title=f"{profile.emoji} {_(profile.name)}",
            description=_(profile.description),
            color=COLOR,
        )
        lines = []
        for key, level in sorted(profile.modules.items(), key=lambda kv: (kv[1] != ON, kv[1] != RECOMMENDED, kv[0])):
            info = MODULES.get(key)
            if info is None:
                continue
            loaded = resolve_cog(self.bot, info) is not None
            lines.append(
                f"{info.emoji} **{_(info.name)}** — {_(LEVEL_LABELS[level])}{'' if loaded else _(' · _not loaded_')}"
            )
        embed.add_field(name=_("Modules"), value=_join_capped(lines), inline=False)
        deps = resolve_dependencies([k for k, lvl in profile.modules.items() if lvl != OPTIONAL])
        if deps:
            embed.add_field(
                name=_("Automatic dependencies"),
                value=humanize_list([MODULES[d].name for d in deps]),
                inline=False,
            )
        embed.add_field(name=_("Recommended security"), value=f"`{profile.security_level}`", inline=True)
        if profile.protected_role_hints:
            embed.add_field(
                name=_("Roles to protect"),
                value=", ".join(profile.protected_role_hints),
                inline=True,
            )
        embed.set_footer(
            text=_("Apply: enables what's selected · +recommended: includes ⭐ · exact: also disables the rest")
        )
        return embed

    async def build_modules_embed(
        self, guild: discord.Guild, states: Dict[str, bool], effective: Optional[Dict[str, str]] = None
    ) -> discord.Embed:
        data = await self.config.guild(guild).all()
        if effective is None:
            effective = await self.effective_states(guild, states)
        profile = PROFILES.get(data["profile"])
        embed = discord.Embed(
            title=_("🧩 La Trini modules"),
            color=COLOR,
            description=(
                _("Profile: **{emoji} {profile_name}**").format(emoji=profile.emoji, profile_name=_(profile.name)) if profile else _("Profile: _not set up_ (`trini setup`)")
            )
            + _("\nSync with Red (`enablecog`/`disablecog`): **{value}**").format(value='si' if data['sync_red'] else 'no'),
        )
        by_cat: Dict[str, List[str]] = {}
        counts: Dict[str, int] = {}
        for info in MODULES.values():
            state = effective.get(info.key, STATE_MISSING)
            counts[state] = counts.get(state, 0) + 1
            deps = f" ← {', '.join(info.depends)}" if info.depends else ""
            by_cat.setdefault(info.category, []).append(f"{STATE_ICON[state]} {info.emoji} {_(info.name)}{deps}")
        for cat, lines in by_cat.items():
            embed.add_field(name=_(cat), value=_join_capped(lines, 700), inline=True)
        summary = " · ".join(f"{STATE_ICON[k]} {counts[k]}" for k in (STATE_ON, STATE_OFF, STATE_MISSING_ON, STATE_MISSING) if counts.get(k))
        embed.description += f"\n{summary}"
        embed.set_footer(text=_(STATE_LEGEND))
        return embed

    # ------------------------------------------------------------------
    # Export / import
    # ------------------------------------------------------------------

    async def active_modules(self, guild: discord.Guild) -> Dict[str, bool]:
        """Modulos activos segun el estado REAL (no solo el apunte de Profiles).

        Asi un servidor que nunca paso por `trini setup` exporta/guarda igualmente
        todo lo que tiene funcionando.
        """
        effective = await self.effective_states(guild)
        return {k: st in (STATE_ON, STATE_MISSING_ON) for k, st in effective.items() if not MODULES[k].core}

    async def build_export(self, guild: discord.Guild) -> Dict[str, Any]:
        data = await self.config.guild(guild).all()
        modules = await self.active_modules(guild)
        cogs: Dict[str, Any] = {}
        raw_cogs: List[str] = []
        for key, enabled in modules.items():
            info = MODULES.get(key)
            if not enabled or info is None:
                continue
            cog = resolve_cog(self.bot, info)
            if cog is None:
                continue
            exported = await export_cog(cog, guild)
            if exported is not None:
                cogs[cog.qualified_name] = exported
                if not hasattr(cog, "trini_export"):
                    raw_cogs.append(cog.qualified_name)
        payload: Dict[str, Any] = {
            "format": "trini-profile",
            "version": EXPORT_VERSION,
            "exported_at": int(time.time()),
            "source_guild": {"id": guild.id, "name": guild.name},
            "profile": data["profile"],
            "security_level": data["security_level"],
            "modules": modules,
            "dependencies": {k: list(MODULES[k].depends) for k, v in modules.items() if v and MODULES[k].depends},
            "cogs": cogs,
            # Cogs sin soporte Trini: se copia su configuracion completa tal cual.
            "raw_cogs": raw_cogs,
        }
        payload["references"] = collect_references(cogs, guild)
        return payload

    async def run_import(
        self, guild: discord.Guild, payload: Dict[str, Any], actor: discord.abc.User
    ) -> List[str]:
        warnings: List[str] = []
        same_guild = (payload.get("source_guild") or {}).get("id") == guild.id
        profile = PROFILES.get(payload.get("profile") or "custom", PROFILES["custom"])
        await self.apply_profile(
            guild,
            profile,
            actor=actor,
            include_recommended=False,
            exact=False,
            modules_override=payload.get("modules", {}),
            security_level=payload.get("security_level"),
        )
        cogs_data, missing = remap_references(payload.get("cogs", {}), payload.get("references", {}), guild)
        if missing and not same_guild:
            warnings.append(_("References not found: ") + ", ".join(missing[:20]))
        for cog_name, data in cogs_data.items():
            cog = self.bot.get_cog(cog_name)
            if cog is None:
                warnings.append(_("{cog_name}: not loaded, skipped.").format(cog_name=cog_name))
                continue
            try:
                warnings.extend(await import_cog(cog, guild, data, same_guild=same_guild))
            except Exception as exc:
                log.exception("Error importando %s", cog_name)
                warnings.append(_("{cog_name}: import error ({exc}).").format(cog_name=cog_name, exc=exc))
        await self._log(guild, actor, "profile_import", _("from {get}").format(get=(payload.get('source_guild') or {}).get('name', '?')))
        return warnings

    # ------------------------------------------------------------------
    # Comandos: trini
    # ------------------------------------------------------------------

    @commands.hybrid_group(name="trini")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def trini(self, ctx: commands.Context):
        """General La Trini settings."""

    @trini.command(name="setup")
    async def trini_setup(self, ctx: commands.Context):
        """Setup wizard: choose how this Discord is used."""
        embed = discord.Embed(
            title=_("⚙️ La Trini setup"),
            description=_("How is this Discord used?\n\n")
            + "\n".join(f"{p.emoji} **{_(p.name)}** — {_(p.description)}" for p in PROFILES.values()),
            color=COLOR,
        )
        current = await self.config.guild(ctx.guild).profile()
        if current in PROFILES:
            embed.set_footer(text=_("Current profile: {name}").format(name=_(PROFILES[current].name)))
        view = SetupView(self, ctx)
        view.message = await ctx.send(embed=embed, view=view)

    @trini.command(name="modules")
    async def trini_modules(self, ctx: commands.Context):
        """View and enable/disable modules."""
        view = ModulesView(self, ctx)
        embed = await view.build()
        view.message = await ctx.send(embed=embed, view=view)

    @trini.command(name="enable")
    async def trini_enable(self, ctx: commands.Context, module: str):
        """Enable a module (and its dependencies)."""
        module = module.lower()
        deps = [d for d in resolve_dependencies([module]) if not (await self.config.guild(ctx.guild).modules()).get(d)]
        if module in MODULES and deps:
            view = ConfirmView(ctx.author)
            names = humanize_list([MODULES[d].name for d in deps])
            msg = await ctx.send(
                _("**{name}** requires {names}.\n\n{names} will be enabled automatically.").format(name=MODULES[module].name, names=names),
                view=view,
            )
            await view.wait()
            if not view.value:
                return await msg.edit(content=_("Cancelled."), view=None)
            await msg.delete()
        ok, text = await self.set_module(ctx.guild, module, True, actor=ctx.author)
        await ctx.send(text)

    @trini.command(name="disable")
    async def trini_disable(self, ctx: commands.Context, module: str):
        """Disable a module (if nothing depends on it)."""
        ok, text = await self.set_module(ctx.guild, module.lower(), False, actor=ctx.author)
        await ctx.send(text)

    @trini_enable.autocomplete("module")
    @trini_disable.autocomplete("module")
    async def _module_autocomplete(self, interaction: discord.Interaction, current: str):
        current = current.lower()
        return [
            discord.app_commands.Choice(name=f"{m.name} ({m.key})", value=m.key)
            for m in MODULES.values()
            if not m.core and (current in m.key or current in m.name.lower())
        ][:25]

    @trini.command(name="status")
    async def trini_status(self, ctx: commands.Context):
        """Server profile summary."""
        data = await self.config.guild(ctx.guild).all()
        embed = await self.build_modules_embed(ctx.guild, data["modules"])
        embed.title = _("📋 La Trini status in {guild}").format(guild=ctx.guild.name)[:256]
        embed.add_field(name=_("Security level"), value=f"`{data['security_level']}`", inline=False)
        if data["applied_at"]:
            embed.add_field(name=_("Profile applied"), value=f"<t:{data['applied_at']}:R>", inline=False)
        await ctx.send(embed=embed)

    @trini.command(name="securitylevel")
    async def trini_securitylevel(self, ctx: commands.Context, level: str):
        """Recommended security level: standard, high or strict."""
        level = level.lower()
        if level not in ("standard", "high", "strict"):
            return await ctx.send(_("Valid levels: `standard`, `high`, `strict`."))
        await self.config.guild(ctx.guild).security_level.set(level)
        await self._log(ctx.guild, ctx.author, "security_level", level)
        await ctx.send(_("Security level: `{level}`.").format(level=level))

    @trini.command(name="syncred")
    async def trini_syncred(self, ctx: commands.Context, enabled: bool):
        """Sync modules with Red's `enablecog`/`disablecog` in this server."""
        await self.config.guild(ctx.guild).sync_red.set(enabled)
        await self._log(ctx.guild, ctx.author, "sync_red", str(enabled))
        await ctx.send(_("Red sync: **{value}**.").format(value='activada' if enabled else 'desactivada'))

    @trini.command(name="log")
    async def trini_log(self, ctx: commands.Context):
        """Profiles settings change history."""
        history = await self.config.guild(ctx.guild).history()
        if not history:
            return await ctx.send(_("No changes recorded."))
        lines = []
        for h in reversed(history[-40:]):
            who = f"<@{h['actor']}>" if h.get("actor") else "sistema"
            lines.append(f"<t:{h['ts']}:f> · {who} · `{h['action']}` {h['detail']}")
        for page in pagify("\n".join(lines), page_length=3900):
            await ctx.send(
                embed=discord.Embed(title=_("📜 Profiles · history"), description=page, color=COLOR),
                allowed_mentions=discord.AllowedMentions.none(),
            )

    # ------------------------------------------------------------------
    # Comandos: profile
    # ------------------------------------------------------------------

    @commands.hybrid_group(name="profile")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def profile(self, ctx: commands.Context):
        """Custom presets and settings export/import."""

    @profile.command(name="save")
    async def profile_save(self, ctx: commands.Context, *, name: str):
        """Save the current setup as a reusable preset."""
        name = _clean_name(name)
        if not name:
            return await ctx.send(_("Give the preset a name."))
        data = await self.config.guild(ctx.guild).all()
        data["modules"] = await self.active_modules(ctx.guild)
        async with self.config.presets() as presets:
            existing = presets.get(name.lower())
            if existing and existing["owner_guild"] != ctx.guild.id and not await self.bot.is_owner(ctx.author):
                return await ctx.send(_("A preset with that name already exists, created in another server."))
            presets[name.lower()] = {
                "name": name,
                "profile": data["profile"],
                "security_level": data["security_level"],
                "modules": data["modules"],
                "owner_guild": ctx.guild.id,
                "author": ctx.author.id,
                "created_at": int(time.time()),
            }
        await self._log(ctx.guild, ctx.author, "preset_save", name)
        active = [MODULES[k].name for k, v in data["modules"].items() if v and k in MODULES]
        await ctx.send(_("💾 Preset **{name}** saved ({count} active modules).").format(name=name, count=len(active)))

    @profile.command(name="apply")
    async def profile_apply(self, ctx: commands.Context, *, name: str):
        """Apply a saved preset."""
        presets = await self.config.presets()
        preset = presets.get(_clean_name(name).lower())
        if preset is None:
            return await ctx.send(_("That preset doesn't exist. See `profile list`."))
        view = ConfirmView(ctx.author, confirm_label="Aplicar")
        active = [MODULES[k].name for k, v in preset["modules"].items() if v and k in MODULES]
        msg = await ctx.send(
            _("**{name}** will be applied:\n{value}").format(name=preset['name'], value=box(humanize_list(active) or '-')), view=view
        )
        await view.wait()
        if not view.value:
            return await msg.edit(content=_("Cancelled."), view=None)
        profile = PROFILES.get(preset.get("profile") or "custom", PROFILES["custom"])
        embed = await self.apply_profile(
            ctx.guild,
            profile,
            actor=ctx.author,
            include_recommended=False,
            exact=True,
            modules_override=preset["modules"],
            security_level=preset.get("security_level"),
        )
        embed.title = _("💾 Preset applied: {name}").format(name=preset['name'])
        await msg.edit(content=None, embed=embed, view=None)

    @profile.command(name="list")
    async def profile_list(self, ctx: commands.Context):
        """List presets and built-in profiles."""
        presets = await self.config.presets()
        embed = discord.Embed(title=_("💾 Profiles and presets"), color=COLOR)
        embed.add_field(
            name=_("Built-in"),
            value="\n".join(f"{p.emoji} `{p.key}` {_(p.name)}" for p in PROFILES.values()),
            inline=False,
        )
        if presets:
            embed.add_field(
                name=_("Saved presets"),
                value=_join_capped([
                    _("• **{name}** · {value} modules · <t:{created_at}:d>").format(name=p['name'], value=sum(1 for v in p['modules'].values() if v), created_at=p['created_at'])
                    for p in presets.values()
                ]),
                inline=False,
            )
        await ctx.send(embed=embed)

    @profile.command(name="delete")
    async def profile_delete(self, ctx: commands.Context, *, name: str):
        """Delete a saved preset."""
        name = _clean_name(name)
        async with self.config.presets() as presets:
            preset = presets.get(name.lower())
            if preset is None:
                return await ctx.send(_("That preset doesn't exist."))
            if preset["owner_guild"] != ctx.guild.id and not await self.bot.is_owner(ctx.author):
                return await ctx.send(_("It can only be deleted from the server that created it."))
            del presets[name.lower()]
        await self._log(ctx.guild, ctx.author, "preset_delete", name)
        await ctx.send(_("🗑 Preset **{name}** deleted.").format(name=name))

    @profile.command(name="export")
    async def profile_export(self, ctx: commands.Context):
        """Export modules and active cog settings to JSON."""
        async with ctx.typing():
            payload = await self.build_export(ctx.guild)
        fp = io.BytesIO(json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8"))
        name = f"trini-profile-{ctx.guild.id}-{time.strftime('%Y%m%d-%H%M')}.json"
        await self._log(ctx.guild, ctx.author, "profile_export", name)
        text = _("🏠 Server: **{escape_markdown}** (`{guild_id}`)\n🕒 {format_dt}\n📤 Exported **{count}** cogs and **{value}** modules.\n⚠️ The file contains server settings, share it carefully.").format(escape_markdown=discord.utils.escape_markdown(ctx.guild.name), guild_id=ctx.guild.id, format_dt=discord.utils.format_dt(discord.utils.utcnow(), 'f'), count=len(payload['cogs']), value=sum(1 for v in payload['modules'].values() if v))
        if ctx.interaction is not None:
            return await ctx.send(text, file=discord.File(fp, filename=name), ephemeral=True)
        try:
            await ctx.author.send(text, file=discord.File(fp, filename=name))
            await ctx.send(_("📬 I've sent you the export by DM."))
        except discord.HTTPException:
            await ctx.send(_("I can't DM you. Enable DMs or use the slash version of the command."))

    @profile.command(name="import")
    async def profile_import(self, ctx: commands.Context, file: Optional[discord.Attachment] = None):
        """Import a JSON generated with `profile export`."""
        if file is None and ctx.message and ctx.message.attachments:
            file = ctx.message.attachments[0]
        if file is None:
            return await ctx.send(_("Attach the exported JSON file."))
        if file.size > 2_000_000:
            return await ctx.send(_("The file is too large."))
        try:
            payload = json.loads(await file.read())
        except (ValueError, discord.HTTPException):
            return await ctx.send(_("It isn't valid JSON."))
        if not isinstance(payload, dict) or payload.get("format") != "trini-profile":
            return await ctx.send(_("The file isn't a Trini Profiles export."))
        if not isinstance(payload.get("modules", {}), dict) or not isinstance(payload.get("cogs", {}), dict):
            return await ctx.send(_("The file is corrupted (modules or cogs with an invalid format)."))
        source = payload.get("source_guild") or {}
        active = [MODULES[k].name for k, v in payload.get("modules", {}).items() if v and k in MODULES]
        view = ConfirmView(ctx.author, confirm_label="Importar")
        msg = await ctx.send(
            embed=discord.Embed(
                title=_("📥 Import settings"),
                color=discord.Color.orange(),
                description=(
                    _("Source: **{get}** (`{get2}`)\nProfile: `{get3}` · Security: `{get4}`\n\n**Modules:** {value}\n**Cog settings:** {value2}\n\nChannels and roles are re-mapped by name if the server is different.\nThe current settings of those cogs will be overwritten.").format(get=source.get('name', '?'), get2=source.get('id', '?'), get3=payload.get('profile'), get4=payload.get('security_level'), value=humanize_list(active) or '-', value2=humanize_list(list(payload.get('cogs', {}).keys())) or '-')
                    + (
                        _("\n\n⚠️ **Full copy (no Trini support):** ")
                        + humanize_list(payload.get("raw_cogs") or [])
                        + _(". It may include runtime data from the source server.")
                        if payload.get("raw_cogs") else ""
                    )
                ),
            ),
            view=view,
        )
        await view.wait()
        if not view.value:
            return await msg.edit(content=_("Cancelled."), embed=None, view=None)
        async with ctx.typing():
            warnings = await self.run_import(ctx.guild, payload, ctx.author)
        text = _("✅ Import completed.")
        if warnings:
            text += "\n" + box("\n".join(warnings)[:1800])
        await msg.edit(content=text, embed=None, view=None)
