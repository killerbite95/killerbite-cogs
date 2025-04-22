# arenaqueue/challenges.py
# coding: utf-8

from redbot.core import commands, Config
from redbot.core.utils.chat_formatting import box, pagify
import discord

# Definición de retos gratuitos
FREE_CHALLENGES = {
    "Novice 🌱": {
        "desc": "Reach 15 total games played",
        "difficulty": "Easy",
        "check": lambda data: data.get("total_games", 0) >= 15,
    },
    "Adventurer 👢": {
        "desc": "Reach 30 total games played",
        "difficulty": "Easy",
        "check": lambda data: data.get("total_games", 0) >= 30,
    },
    "Rising Star ⭐": {
        "desc": "Reach 1800 MMR",
        "difficulty": "Easy",
        "check": lambda data: data.get("mmr", 0) >= 1800,
    },
    "Mighty 💪": {
        "desc": "Reach 60 total games played",
        "difficulty": "Normal",
        "check": lambda data: data.get("total_games", 0) >= 60,
    },
    "Centurion 🛡": {
        "desc": "Reach 120 total games played",
        "difficulty": "Normal",
        "check": lambda data: data.get("total_games", 0) >= 120,
    },
    "Veteran Vanguard 🛡": {
        "desc": "Reach 2500 MMR",
        "difficulty": "Normal",
        "check": lambda data: data.get("mmr", 0) >= 2500,
    },
    "Valiant 🏆": {
        "desc": "Reach 250 total games played",
        "difficulty": "Hard",
        "check": lambda data: data.get("total_games", 0) >= 250,
    },
    "Heroic 🦸‍♀️": {
        "desc": "Reach 500 total games played",
        "difficulty": "Hard",
        "check": lambda data: data.get("total_games", 0) >= 500,
    },
    "Supreme Ace 🏆": {
        "desc": "Reach 3000 MMR",
        "difficulty": "Hard",
        "check": lambda data: data.get("mmr", 0) >= 3000,
    },
    "Ultimate Flex 💪": {
        "desc": "Get a 5 game win streak",
        "difficulty": "Hard",
        "check": lambda data: data.get("win_streak", 0) >= 5,
    },
    "Ultimate Flex II 💪💪": {
        "desc": "Get a 10 game win streak",
        "difficulty": "Hardest",
        "check": lambda data: data.get("win_streak", 0) >= 10,
    },
}


class ChallengesCog(commands.Cog):
    """🎮 Sistema de retos para arenaqueue (free only)"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=2345678901)
        default_guild = {
            "enabled": False,
        }
        default_user = {
            "progress": {},  # nombre del reto -> True/False
        }
        self.config.register_guild(**default_guild)
        self.config.register_user(**default_user)

    @commands.group(name="challenges", invoke_without_command=True)
    @commands.guild_only()
    async def challenges(self, ctx: commands.Context):
        """Grupo de comandos para el sistema de retos."""
        await ctx.send_help(ctx.command)

    @challenges.command(name="start")
    @commands.admin_or_permissions(manage_guild=True)
    async def challenges_start(self, ctx: commands.Context):
        """Inicia (o reanuda) el sistema de retos."""
        await self.config.guild(ctx.guild).enabled.set(True)
        await ctx.send("🎉 El sistema de retos ha sido **iniciado**. ¡Que comience la diversión!")

    @challenges.command(name="pause")
    @commands.admin_or_permissions(manage_guild=True)
    async def challenges_pause(self, ctx: commands.Context):
        """Pausa la progresión de retos para todos."""
        await self.config.guild(ctx.guild).enabled.set(False)
        await ctx.send("⏸️ El sistema de retos ha sido **pausado**. Nadie progresará hasta volver a iniciarlo.")

    @challenges.command(name="show_all")
    @commands.guild_only()
    async def challenges_show_all(self, ctx: commands.Context):
        """Muestra todos los retos gratuitos disponibles."""
        lines = []
        for name, info in FREE_CHALLENGES.items():
            lines.append(f"**{name}** ({info['difficulty']}): {info['desc']}")
        message = "\n".join(lines)
        for page in pagify(message, delims=["\n"], prefix="", suffix=""):
            await ctx.send(box(page, lang="ini"))

    @challenges.command(name="personal")
    @commands.guild_only()
    async def challenges_personal(self, ctx: commands.Context):
        """Muestra tu progreso en los retos."""
        enabled = await self.config.guild(ctx.guild).enabled()
        if not enabled:
            await ctx.send("⚠️ El sistema de retos está pausado o no iniciado.")
            return
        data = await self.config.user(ctx.author).progress()
        lines = []
        for name in FREE_CHALLENGES:
            status = "✅" if data.get(name) else "❌"
            lines.append(f"{status} {name}")
        await ctx.send("\n".join(lines))

    @challenges.command(name="refresh")
    @commands.bot_has_permissions(send_messages=True)
    @commands.guild_only()
    async def challenges_refresh(self, ctx: commands.Context):
        """Forzar comprobación de progresión de retos (p. ej. tras una partida)."""
        enabled = await self.config.guild(ctx.guild).enabled()
        if not enabled:
            await ctx.send("⚠️ El sistema de retos está pausado o no iniciado.")
            return

        user = ctx.author
        # Simulación: extraer stats desde algún lado; aquí usamos placeholders
        # En tu implementación real, reemplaza esto con llamadas a DB de partidas, MMR, rachas, etc.
        stats = {
            "total_games": 42,
            "mmr": 1850,
            "win_streak": 3,
        }

        progress = await self.config.user(user).progress()
        unlocked = []
        for name, info in FREE_CHALLENGES.items():
            if not progress.get(name) and info["check"](stats):
                progress[name] = True
                unlocked.append(name)
        await self.config.user(user).progress.set(progress)

        if unlocked:
            for name in unlocked:
                # Asigna rol o felicita si quieres; aquí solo mensaje
                await ctx.send(f"🎉 {user.mention} ¡Has desbloqueado el reto **{name}**!")
        else:
            await ctx.send("ℹ️ No hay nuevos retos desbloqueados en esta actualización.")
