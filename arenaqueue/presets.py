# arenaqueue/presets.py
# coding: utf-8

import discord
from redbot.core import commands, Config
from redbot.core.utils.chat_formatting import box

# Presets de juegos soportados
game_presets = {
    "leagueoflegends": {
        "display": "League of Legends",
        "teamsize": 5,
        "roles": ["Top", "Jungle", "Mid", "ADC", "Support"],
    },
    "valorant": {
        "display": "Valorant",
        "teamsize": 5,
        "roles": ["Controller", "Initiator", "Sentinel", "Duelist", "Flex"],
    },
    "overwatch": {
        "display": "Overwatch",
        "teamsize": 5,
        "roles": ["Tank", "DPS 1", "DPS 2", "Support 1", "Support 2"],
    },
    "dota2": {
        "display": "Dota 2",
        "teamsize": 5,
        "roles": ["Hard Carry", "Midlaner", "Offlaner", "Soft Support", "Hard Support"],
    },
    "crossfire": {
        "display": "Crossfire",
        "teamsize": 5,
        "roles": ["Entry 1", "Entry 2", "Backup 1", "Backup 2", "Sniper"],
    },
    "pokemonunite": {
        "display": "Pokemon Unite",
        "teamsize": 5,
        "roles": ["Top Laner", "Attacker", "Support", "Defender", "Jungler"],
    },
}

class PresetsCog(commands.Cog):
    """🎲 Presets de juegos para arenaqueue"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=8901234567)
        default_guild = {"selected_preset": None}
        self.config.register_guild(**default_guild)

    @commands.group(name="preset", invoke_without_command=True)
    @commands.guild_only()
    async def preset(self, ctx: commands.Context):
        """Grupo de comandos para presets de juego"""
        await ctx.send_help(ctx.command)

    @preset.command(name="list")
    async def preset_list(self, ctx: commands.Context):
        """Lista todos los presets de juego disponibles"""
        lines = []
        for key, info in game_presets.items():
            lines.append(f"• **{info['display']}** (clave: `{key}`) - {info['teamsize']}v{info['teamsize']}")
        await ctx.send(box("\n".join(lines), lang="ini"))

    @preset.command(name="select")
    @commands.admin_or_permissions(manage_guild=True)
    async def preset_select(self, ctx: commands.Context, preset_key: str):
        """Selecciona un preset para la configuración de colas"""
        key = preset_key.lower()
        preset = game_presets.get(key)
        if not preset:
            await ctx.send("❌ Preset no encontrado. Usa `preset list` para ver opciones.")
            return
        await self.config.guild(ctx.guild).selected_preset.set(key)
        await ctx.send(f"✅ Preset seleccionado: **{preset['display']}**")

    @preset.command(name="current")
    async def preset_current(self, ctx: commands.Context):
        """Muestra el preset de juego actualmente seleccionado"""
        key = await self.config.guild(ctx.guild).selected_preset()
        if not key:
            await ctx.send("ℹ️ No hay un preset seleccionado.")
            return
        preset = game_presets.get(key)
        desc = (
            f"Juego: **{preset['display']}**\n"
            f"Tamaño de equipo: {preset['teamsize']}v{preset['teamsize']}\n"
            f"Roles: {', '.join(preset['roles'])}"
        )
        await ctx.send(box(desc, lang="yaml"))

    @preset.command(name="customsetup")
    @commands.admin_or_permissions(manage_guild=True)
    async def preset_customsetup(
        self,
        ctx: commands.Context,
        teamsize: int,
        *roles: str
    ):
        """Configura un preset personalizado si no está en lista"""
        if teamsize < 1 or teamsize > 8:
            await ctx.send("❌ Tamaño de equipo inválido (1-8).")
            return
        if len(roles) != teamsize:
            await ctx.send(f"❌ Debes especificar exactamente {teamsize} roles.")
            return
        custom_key = f"custom_{ctx.guild.id}"
        game_presets[custom_key] = {
            "display": f"Custom ({teamsize}v{teamsize})",
            "teamsize": teamsize,
            "roles": list(roles),
        }
        await self.config.guild(ctx.guild).selected_preset.set(custom_key)
        await ctx.send(f"✅ Preset personalizado configurado y seleccionado: {', '.join(roles)}")

    async def get_preset(self, guild: discord.Guild):
        """Ayuda para otros cogs: devuelve el preset actual (diccionario)"""
        key = await self.config.guild(guild).selected_preset()
        if not key:
            return None
        return game_presets.get(key)

# Para cargar el cog en __init__.py:
# await bot.add_cog(PresetsCog(bot))
