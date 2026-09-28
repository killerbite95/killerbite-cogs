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
STATE_LEGEND = "🟢 funcionando · 🔴 desactivado en este servidor · 🟠 activado pero no cargado · ⚫ no cargado"


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
        marker = f"… y {remaining} mas" if remaining else ""
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
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "Solo quien ejecuto el comando puede usar estos controles.", ephemeral=True
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
                label=p.name, value=p.key, emoji=p.emoji, description=p.description[:100]
            )
            for p in PROFILES.values()
        ]
        super().__init__(placeholder="¿Como se utiliza este Discord?", options=options)
        self.setup_view = view

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

    async def _apply(self, interaction: discord.Interaction, *, recommended: bool, exact: bool):
        if self.selected is None:
            return await interaction.response.send_message("Elige un perfil primero.", ephemeral=True)
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

    @discord.ui.button(label="Aplicar", style=discord.ButtonStyle.green, emoji="✅", disabled=True, row=1)
    async def apply_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._apply(interaction, recommended=False, exact=False)

    @discord.ui.button(label="Aplicar + recomendados", style=discord.ButtonStyle.blurple, emoji="⭐", disabled=True, row=1)
    async def apply_rec_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._apply(interaction, recommended=True, exact=False)

    @discord.ui.button(label="Aplicar exacto", style=discord.ButtonStyle.grey, emoji="🧹", disabled=True, row=1)
    async def apply_exact_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._apply(interaction, recommended=True, exact=True)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.red, custom_id="cancel", row=1)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="Setup cancelado.", view=self)


class ConfirmView(AuthorView):
    def __init__(self, author: discord.abc.User, *, confirm_label: str = "Continuar"):
        super().__init__(author, timeout=60)
        self.value: Optional[bool] = None
        self.confirm.label = confirm_label

    @discord.ui.button(label="Continuar", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.red)
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
                    label=f"{'Desactivar' if active else 'Activar'} {info.name}"[:100],
                    value=info.key,
                    emoji=STATE_ICON[state],
                    description=info.description[:100],
                )
            )
        super().__init__(placeholder=f"{category}: activar / desactivar", options=options[:25])
        self.modules_view = view

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
                    f"**{MODULES[key].name}** requiere {names}.\n{names} se activara automaticamente.",
                    view=confirm,
                    ephemeral=True,
                )
                await confirm.wait()
                if not confirm.value:
                    return await interaction.edit_original_response(content="Cancelado.", view=None)
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

    async def build(self) -> discord.Embed:
        self.clear_items()
        states = await self.cog.config.guild(self.ctx.guild).modules()
        effective = await self.cog.effective_states(self.ctx.guild, states)
        categories = sorted({m.category for m in MODULES.values() if not m.core})
        if self.category is None:
            self.category = categories[0]
        cat_select = discord.ui.Select(
            placeholder="Categoria",
            options=[
                discord.SelectOption(label=c, value=c, default=(c == self.category))
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


class TriniProfiles(commands.Cog):
    """Configuracion por perfiles de La Trini: plantillas, modulos, dependencias y presets."""

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
        return f"{pre}\n\nVersion: {self.__version__}"

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
            return False, f"Modulo desconocido: `{key}`."
        if info.core:
            if enabled:
                return True, f"**{info.name}** es un modulo base: siempre esta activo."
            return False, f"**{info.name}** es un modulo base y no se puede desactivar."
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
                    return False, f"No se puede desactivar **{info.name}**.\n\nDependencias activas:\n{names}"
                states[key] = False
                changed = [key]
        for k in changed:
            await self._sync_red(guild, k, enabled)
        names = humanize_list([MODULES[k].name for k in changed])
        await self._log(guild, actor, "module_enable" if enabled else "module_disable", names)
        msg = f"{'🟢 Activado' if enabled else '⚫ Desactivado'}: **{names}**."
        missing = [MODULES[k] for k in changed if enabled and resolve_cog(self.bot, MODULES[k]) is None]
        if missing:
            msg += "\n⚠️ No cargado en el bot: " + humanize_list(
                [f"{m.name}" + (f" (`{m.package}`)" if m.package else "") for m in missing]
            )
        if not await self.config.guild(guild).sync_red():
            msg += "\nℹ️ La sincronizacion con Red esta desactivada (`trini syncred`): esto solo cambia el apunte de Profiles."
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
            f"{profile.key} (+{len(enabled)} / -{len(disabled)}{', exacto' if exact else ''})",
        )
        self.bot.dispatch("trini_profile_applied", guild, profile.key, actor)

        embed = discord.Embed(
            title=f"{profile.emoji} Perfil aplicado: {profile.name}",
            color=discord.Color.green(),
            description="Un perfil solo prepara la base. Puedes cambiar cualquier modulo con `trini modules`.",
        )
        if enabled:
            embed.add_field(
                name="Activados",
                value=_join_capped([f"{MODULES[k].emoji} {MODULES[k].name}" for k in sorted(enabled) if k in MODULES]),
                inline=True,
            )
        if disabled:
            embed.add_field(
                name="Desactivados",
                value=_join_capped([f"{MODULES[k].emoji} {MODULES[k].name}" for k in sorted(disabled) if k in MODULES]),
                inline=True,
            )
        missing = [MODULES[k] for k in wanted if k in MODULES and resolve_cog(self.bot, MODULES[k]) is None]
        if missing:
            embed.add_field(
                name="⚠️ No cargados en el bot",
                value=_join_capped([
                    f"• {m.name}" + (f" — {hint}" if (hint := m.install_hint()) else "")
                    for m in missing
                ]),
                inline=False,
            )
        embed.add_field(
            name="🔐 Nivel de seguridad",
            value=f"`{security_level or profile.security_level}`",
            inline=False,
        )
        if self.bot.get_cog("TriniSecurity") is not None:
            embed.set_footer(text="Siguiente paso recomendado: security audit")
        return embed

    async def build_profile_preview(self, guild: discord.Guild, profile: ProfileInfo) -> discord.Embed:
        embed = discord.Embed(
            title=f"{profile.emoji} {profile.name}",
            description=profile.description,
            color=COLOR,
        )
        lines = []
        for key, level in sorted(profile.modules.items(), key=lambda kv: (kv[1] != ON, kv[1] != RECOMMENDED, kv[0])):
            info = MODULES.get(key)
            if info is None:
                continue
            loaded = resolve_cog(self.bot, info) is not None
            lines.append(
                f"{info.emoji} **{info.name}** — {LEVEL_LABELS[level]}{'' if loaded else ' · _no cargado_'}"
            )
        embed.add_field(name="Modulos", value=_join_capped(lines), inline=False)
        deps = resolve_dependencies([k for k, lvl in profile.modules.items() if lvl != OPTIONAL])
        if deps:
            embed.add_field(
                name="Dependencias automaticas",
                value=humanize_list([MODULES[d].name for d in deps]),
                inline=False,
            )
        embed.add_field(name="Seguridad recomendada", value=f"`{profile.security_level}`", inline=True)
        if profile.protected_role_hints:
            embed.add_field(
                name="Roles a proteger",
                value=", ".join(profile.protected_role_hints),
                inline=True,
            )
        embed.set_footer(
            text="Aplicar: activa lo marcado · +recomendados: incluye ⭐ · exacto: ademas desactiva el resto"
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
            title="🧩 Modulos de La Trini",
            color=COLOR,
            description=(
                f"Perfil: **{profile.emoji} {profile.name}**" if profile else "Perfil: _sin configurar_ (`trini setup`)"
            )
            + f"\nSincronizar con Red (`enablecog`/`disablecog`): **{'si' if data['sync_red'] else 'no'}**",
        )
        by_cat: Dict[str, List[str]] = {}
        counts: Dict[str, int] = {}
        for info in MODULES.values():
            state = effective.get(info.key, STATE_MISSING)
            counts[state] = counts.get(state, 0) + 1
            deps = f" ← {', '.join(info.depends)}" if info.depends else ""
            by_cat.setdefault(info.category, []).append(f"{STATE_ICON[state]} {info.emoji} {info.name}{deps}")
        for cat, lines in by_cat.items():
            embed.add_field(name=cat, value=_join_capped(lines, 700), inline=True)
        summary = " · ".join(f"{STATE_ICON[k]} {counts[k]}" for k in (STATE_ON, STATE_OFF, STATE_MISSING_ON, STATE_MISSING) if counts.get(k))
        embed.description += f"\n{summary}"
        embed.set_footer(text=STATE_LEGEND)
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
            warnings.append("Referencias no encontradas: " + ", ".join(missing[:20]))
        for cog_name, data in cogs_data.items():
            cog = self.bot.get_cog(cog_name)
            if cog is None:
                warnings.append(f"{cog_name}: no esta cargado, se omite.")
                continue
            try:
                warnings.extend(await import_cog(cog, guild, data, same_guild=same_guild))
            except Exception as exc:
                log.exception("Error importando %s", cog_name)
                warnings.append(f"{cog_name}: error al importar ({exc}).")
        await self._log(guild, actor, "profile_import", f"desde {(payload.get('source_guild') or {}).get('name', '?')}")
        return warnings

    # ------------------------------------------------------------------
    # Comandos: trini
    # ------------------------------------------------------------------

    @commands.hybrid_group(name="trini")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def trini(self, ctx: commands.Context):
        """Configuracion general de La Trini."""

    @trini.command(name="setup")
    async def trini_setup(self, ctx: commands.Context):
        """Asistente inicial: elige como se utiliza este Discord."""
        embed = discord.Embed(
            title="⚙️ Setup de La Trini",
            description="¿Como se utiliza este Discord?\n\n"
            + "\n".join(f"{p.emoji} **{p.name}** — {p.description}" for p in PROFILES.values()),
            color=COLOR,
        )
        current = await self.config.guild(ctx.guild).profile()
        if current in PROFILES:
            embed.set_footer(text=f"Perfil actual: {PROFILES[current].name}")
        view = SetupView(self, ctx)
        view.message = await ctx.send(embed=embed, view=view)

    @trini.command(name="modules")
    async def trini_modules(self, ctx: commands.Context):
        """Ver y activar/desactivar modulos."""
        view = ModulesView(self, ctx)
        embed = await view.build()
        view.message = await ctx.send(embed=embed, view=view)

    @trini.command(name="enable")
    async def trini_enable(self, ctx: commands.Context, module: str):
        """Activar un modulo (y sus dependencias)."""
        module = module.lower()
        deps = [d for d in resolve_dependencies([module]) if not (await self.config.guild(ctx.guild).modules()).get(d)]
        if module in MODULES and deps:
            view = ConfirmView(ctx.author)
            names = humanize_list([MODULES[d].name for d in deps])
            msg = await ctx.send(
                f"**{MODULES[module].name}** requiere {names}.\n\n{names} se activara automaticamente.",
                view=view,
            )
            await view.wait()
            if not view.value:
                return await msg.edit(content="Cancelado.", view=None)
            await msg.delete()
        ok, text = await self.set_module(ctx.guild, module, True, actor=ctx.author)
        await ctx.send(text)

    @trini.command(name="disable")
    async def trini_disable(self, ctx: commands.Context, module: str):
        """Desactivar un modulo (si nada depende de el)."""
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
        """Resumen del perfil del servidor."""
        data = await self.config.guild(ctx.guild).all()
        embed = await self.build_modules_embed(ctx.guild, data["modules"])
        embed.title = f"📋 Estado de La Trini en {ctx.guild.name}"[:256]
        embed.add_field(name="Nivel de seguridad", value=f"`{data['security_level']}`", inline=False)
        if data["applied_at"]:
            embed.add_field(name="Perfil aplicado", value=f"<t:{data['applied_at']}:R>", inline=False)
        await ctx.send(embed=embed)

    @trini.command(name="securitylevel")
    async def trini_securitylevel(self, ctx: commands.Context, level: str):
        """Nivel de seguridad recomendado: standard, high o strict."""
        level = level.lower()
        if level not in ("standard", "high", "strict"):
            return await ctx.send("Niveles validos: `standard`, `high`, `strict`.")
        await self.config.guild(ctx.guild).security_level.set(level)
        await self._log(ctx.guild, ctx.author, "security_level", level)
        await ctx.send(f"Nivel de seguridad: `{level}`.")

    @trini.command(name="syncred")
    async def trini_syncred(self, ctx: commands.Context, enabled: bool):
        """Sincronizar modulos con `enablecog`/`disablecog` de Red en este servidor."""
        await self.config.guild(ctx.guild).sync_red.set(enabled)
        await self._log(ctx.guild, ctx.author, "sync_red", str(enabled))
        await ctx.send(f"Sincronizacion con Red: **{'activada' if enabled else 'desactivada'}**.")

    @trini.command(name="log")
    async def trini_log(self, ctx: commands.Context):
        """Historial de cambios de configuracion de Profiles."""
        history = await self.config.guild(ctx.guild).history()
        if not history:
            return await ctx.send("Sin cambios registrados.")
        lines = []
        for h in reversed(history[-40:]):
            who = f"<@{h['actor']}>" if h.get("actor") else "sistema"
            lines.append(f"<t:{h['ts']}:f> · {who} · `{h['action']}` {h['detail']}")
        for page in pagify("\n".join(lines), page_length=3900):
            await ctx.send(
                embed=discord.Embed(title="📜 Profiles · historial", description=page, color=COLOR),
                allowed_mentions=discord.AllowedMentions.none(),
            )

    # ------------------------------------------------------------------
    # Comandos: profile
    # ------------------------------------------------------------------

    @commands.hybrid_group(name="profile")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def profile(self, ctx: commands.Context):
        """Presets personalizados y export/import de configuracion."""

    @profile.command(name="save")
    async def profile_save(self, ctx: commands.Context, *, name: str):
        """Guardar la configuracion actual como preset reutilizable."""
        name = _clean_name(name)
        if not name:
            return await ctx.send("Indica un nombre para el preset.")
        data = await self.config.guild(ctx.guild).all()
        data["modules"] = await self.active_modules(ctx.guild)
        async with self.config.presets() as presets:
            existing = presets.get(name.lower())
            if existing and existing["owner_guild"] != ctx.guild.id and not await self.bot.is_owner(ctx.author):
                return await ctx.send("Ya existe un preset con ese nombre creado en otro servidor.")
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
        await ctx.send(f"💾 Preset **{name}** guardado ({len(active)} modulos activos).")

    @profile.command(name="apply")
    async def profile_apply(self, ctx: commands.Context, *, name: str):
        """Aplicar un preset guardado."""
        presets = await self.config.presets()
        preset = presets.get(_clean_name(name).lower())
        if preset is None:
            return await ctx.send("No existe ese preset. Mira `profile list`.")
        view = ConfirmView(ctx.author, confirm_label="Aplicar")
        active = [MODULES[k].name for k, v in preset["modules"].items() if v and k in MODULES]
        msg = await ctx.send(
            f"Se aplicara **{preset['name']}**:\n{box(humanize_list(active) or '-')}", view=view
        )
        await view.wait()
        if not view.value:
            return await msg.edit(content="Cancelado.", view=None)
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
        embed.title = f"💾 Preset aplicado: {preset['name']}"
        await msg.edit(content=None, embed=embed, view=None)

    @profile.command(name="list")
    async def profile_list(self, ctx: commands.Context):
        """Listar presets y perfiles predefinidos."""
        presets = await self.config.presets()
        embed = discord.Embed(title="💾 Perfiles y presets", color=COLOR)
        embed.add_field(
            name="Predefinidos",
            value="\n".join(f"{p.emoji} `{p.key}` {p.name}" for p in PROFILES.values()),
            inline=False,
        )
        if presets:
            embed.add_field(
                name="Presets guardados",
                value=_join_capped([
                    f"• **{p['name']}** · {sum(1 for v in p['modules'].values() if v)} modulos · <t:{p['created_at']}:d>"
                    for p in presets.values()
                ]),
                inline=False,
            )
        await ctx.send(embed=embed)

    @profile.command(name="delete")
    async def profile_delete(self, ctx: commands.Context, *, name: str):
        """Eliminar un preset guardado."""
        name = _clean_name(name)
        async with self.config.presets() as presets:
            preset = presets.get(name.lower())
            if preset is None:
                return await ctx.send("No existe ese preset.")
            if preset["owner_guild"] != ctx.guild.id and not await self.bot.is_owner(ctx.author):
                return await ctx.send("Solo se puede borrar desde el servidor que lo creo.")
            del presets[name.lower()]
        await self._log(ctx.guild, ctx.author, "preset_delete", name)
        await ctx.send(f"🗑 Preset **{name}** eliminado.")

    @profile.command(name="export")
    async def profile_export(self, ctx: commands.Context):
        """Exportar modulos y configuracion de los cogs activos a JSON."""
        async with ctx.typing():
            payload = await self.build_export(ctx.guild)
        fp = io.BytesIO(json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8"))
        name = f"trini-profile-{ctx.guild.id}-{time.strftime('%Y%m%d-%H%M')}.json"
        await self._log(ctx.guild, ctx.author, "profile_export", name)
        text = (
            f"🏠 Servidor: **{discord.utils.escape_markdown(ctx.guild.name)}** (`{ctx.guild.id}`)\n"
            f"🕒 {discord.utils.format_dt(discord.utils.utcnow(), 'f')}\n"
            f"📤 Exportados **{len(payload['cogs'])}** cogs y **{sum(1 for v in payload['modules'].values() if v)}** modulos.\n"
            "⚠️ El archivo contiene configuracion del servidor, compartelo con cuidado."
        )
        if ctx.interaction is not None:
            return await ctx.send(text, file=discord.File(fp, filename=name), ephemeral=True)
        try:
            await ctx.author.send(text, file=discord.File(fp, filename=name))
            await ctx.send("📬 Te he enviado el export por mensaje privado.")
        except discord.HTTPException:
            await ctx.send("No puedo enviarte mensajes privados. Activalos o usa la version slash del comando.")

    @profile.command(name="import")
    async def profile_import(self, ctx: commands.Context, file: Optional[discord.Attachment] = None):
        """Importar un JSON generado con `profile export`."""
        if file is None and ctx.message and ctx.message.attachments:
            file = ctx.message.attachments[0]
        if file is None:
            return await ctx.send("Adjunta el archivo JSON exportado.")
        if file.size > 2_000_000:
            return await ctx.send("El archivo es demasiado grande.")
        try:
            payload = json.loads(await file.read())
        except (ValueError, discord.HTTPException):
            return await ctx.send("No es un JSON valido.")
        if not isinstance(payload, dict) or payload.get("format") != "trini-profile":
            return await ctx.send("El archivo no es un export de Trini Profiles.")
        if not isinstance(payload.get("modules", {}), dict) or not isinstance(payload.get("cogs", {}), dict):
            return await ctx.send("El archivo esta dañado (modulos o cogs con formato incorrecto).")
        source = payload.get("source_guild") or {}
        active = [MODULES[k].name for k, v in payload.get("modules", {}).items() if v and k in MODULES]
        view = ConfirmView(ctx.author, confirm_label="Importar")
        msg = await ctx.send(
            embed=discord.Embed(
                title="📥 Importar configuracion",
                color=discord.Color.orange(),
                description=(
                    f"Origen: **{source.get('name', '?')}** (`{source.get('id', '?')}`)\n"
                    f"Perfil: `{payload.get('profile')}` · Seguridad: `{payload.get('security_level')}`\n\n"
                    f"**Modulos:** {humanize_list(active) or '-'}\n"
                    f"**Configuracion de cogs:** {humanize_list(list(payload.get('cogs', {}).keys())) or '-'}\n\n"
                    "Los canales y roles se re-mapean por nombre si el servidor es distinto.\n"
                    "La configuracion actual de esos cogs se sobrescribira."
                    + (
                        "\n\n⚠️ **Copia completa (sin soporte Trini):** "
                        + humanize_list(payload.get("raw_cogs") or [])
                        + ". Puede incluir datos de funcionamiento del servidor de origen."
                        if payload.get("raw_cogs") else ""
                    )
                ),
            ),
            view=view,
        )
        await view.wait()
        if not view.value:
            return await msg.edit(content="Cancelado.", embed=None, view=None)
        async with ctx.typing():
            warnings = await self.run_import(ctx.guild, payload, ctx.author)
        text = "✅ Importacion completada."
        if warnings:
            text += "\n" + box("\n".join(warnings)[:1800])
        await msg.edit(content=text, embed=None, view=None)
