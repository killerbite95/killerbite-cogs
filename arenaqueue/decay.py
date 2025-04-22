import discord
from discord import Embed
from datetime import datetime, timedelta
from redbot.core import commands, Config
from redbot.core.utils.chat_formatting import pagify
from redbot.core.utils import schedules
from redbot.core.utils.schedules import crontab

class DecayCog(commands.Cog):
    """📉 Sistema de MMR Decay para arenaqueue"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=6789012345)
        default_guild = {
            "brackets": [],  # lista de dicts: {"min_mmr": int, "days": int}
            "decay_type": "flat",  # "flat" o "percent"
            "decay_value": 50,      # valor o porcentaje
            "notify_days_before": 1,
            "exempt_users": []      # lista de IDs
        }
        self.config.register_guild(**default_guild)
        self.config.register_user(last_decay=0)
        self.decay_loop.start()

    def cog_unload(self):
        self.decay_loop.cancel()

    @commands.group(name="decay", invoke_without_command=True)
    @commands.admin_or_permissions(manage_guild=True)
    async def decay(self, ctx: commands.Context):
        """Grupo de comandos para configurar el MMR Decay"""
        await ctx.send_help(ctx.command)

    @decay.command(name="set_bracket")
    async def set_bracket(self, ctx: commands.Context, min_mmr: int, days: int):
        """Configura un bracket: jugadores >= min_mmr decaen tras days días inactivos"""
        guild = ctx.guild
        brackets = await self.config.guild(guild).brackets()
        brackets = [b for b in brackets if b["min_mmr"] != min_mmr]
        brackets.append({"min_mmr": min_mmr, "days": days})
        await self.config.guild(guild).brackets.set(brackets)
        embed = Embed(
            title="🔧 Bracket actualizado",
            description=f"MMR ≥ **{min_mmr}** → inactividad **{days}** días",
            colour=discord.Colour.blue()
        )
        await ctx.send(embed=embed)

    @decay.command(name="remove_bracket")
    async def remove_bracket(self, ctx: commands.Context, min_mmr: int):
        """Elimina el bracket para jugadores >= min_mmr"""
        guild = ctx.guild
        brackets = await self.config.guild(guild).brackets()
        new = [b for b in brackets if b["min_mmr"] != min_mmr]
        if len(new) == len(brackets):
            return await ctx.send("❌ No existe ningún bracket con ese MMR mínimo.")
        await self.config.guild(guild).brackets.set(new)
        embed = Embed(
            title="🗑️ Bracket eliminado",
            description=f"Bracket de MMR ≥ **{min_mmr}** ha sido eliminado.",
            colour=discord.Colour.red()
        )
        await ctx.send(embed=embed)

    @decay.command(name="list_brackets")
    async def list_brackets(self, ctx: commands.Context):
        """Lista todos los brackets configurados"""
        brackets = await self.config.guild(ctx.guild).brackets()
        if not brackets:
            return await ctx.send("⚠️ No hay brackets configurados.")
        lines = [f"• MMR ≥ **{b['min_mmr']}**: {b['days']} días" for b in sorted(brackets, key=lambda x: x['min_mmr'])]
        embed = Embed(
            title="📋 Brackets de Decay",
            description="\n".join(lines),
            colour=discord.Colour.gold()
        )
        await ctx.send(embed=embed)

    @decay.command(name="set_amount")
    async def set_amount(self, ctx: commands.Context, decay_type: str, value: float):
        """Define tipo de decay (flat/percent) y valor"""
        if decay_type not in ("flat", "percent"):
            return await ctx.send("❌ Tipo inválido. Usa `flat` o `percent`.")
        await self.config.guild(ctx.guild).decay_type.set(decay_type)
        await self.config.guild(ctx.guild).decay_value.set(value)
        embed = Embed(
            title="⚙️ Decay configurado",
            description=f"Tipo: **{decay_type}**, Valor: **{value}{'%' if decay_type=='percent' else ''}**",
            colour=discord.Colour.blurple()
        )
        await ctx.send(embed=embed)

    @decay.command(name="ignore")
    async def ignore(self, ctx: commands.Context, action: str, user: discord.Member):
        """Ignora o remueve a un usuario de Decay: `add`/`remove`"""
        guild = ctx.guild
        exempt = await self.config.guild(guild).exempt_users()
        if action == "add":
            if user.id in exempt:
                return await ctx.send("⚠️ Usuario ya está exento.")
            exempt.append(user.id)
            await self.config.guild(guild).exempt_users.set(exempt)
            await ctx.send(f"✅ {user.mention} ha sido exento de MMR decay.")
        elif action == "remove":
            if user.id not in exempt:
                return await ctx.send("❌ Usuario no estaba exento.")
            exempt.remove(user.id)
            await self.config.guild(guild).exempt_users.set(exempt)
            await ctx.send(f"✅ {user.mention} ya no está exento.")
        else:
            await ctx.send("❌ Usa `add` o `remove`.")

    @decay.command(name="status")
    async def status(self, ctx: commands.Context):
        """Muestra la configuración actual de Decay"""
        guild = ctx.guild
        brackets = await self.config.guild(guild).brackets()
        decay_type = await self.config.guild(guild).decay_type()
        decay_value = await self.config.guild(guild).decay_value()
        notify = await self.config.guild(guild).notify_days_before()
        exempt = await self.config.guild(guild).exempt_users()
        embed = Embed(title="🔍 Estado MMR Decay", colour=discord.Colour.green())
        if brackets:
            for b in sorted(brackets, key=lambda x: x['min_mmr']):
                embed.add_field(name=f"MMR ≥ {b['min_mmr']}", value=f"Decay tras {b['days']} días", inline=False)
        embed.add_field(name="Tipo / Valor", value=f"{decay_type} / {decay_value}{'%' if decay_type=='percent' else ''}", inline=False)
        embed.add_field(name="Exentos", value=("Ninguno" if not exempt else "\n".join(f"<@{uid}>" for uid in exempt)))
        embed.set_footer(text=f"Notificar {notify} día(s) antes")
        await ctx.send(embed=embed)

    @schedules.loop(schedule=crontab(hour=0, minute=0))
    async def decay_loop(self):
        """Task: revisa diariamente y aplica MMR decay / envía avisos"""
        now = datetime.utcnow()
        for guild in self.bot.guilds:
            guild_cfg = await self.config.guild(guild).all()
            brackets = guild_cfg['brackets']
            decay_type = guild_cfg['decay_type']
            decay_value = guild_cfg['decay_value']
            notify_days = guild_cfg['notify_days_before']
            exempt = guild_cfg['exempt_users']
            # Placeholder: obtener lista de usuarios con mmr y last_active
            # Se asume método get_all_player_data() -> [{"user_id":id, "mmr":val, "last_active":datetime}, ...]
            if not brackets:
                continue
            players = await self.get_all_player_data(guild)
            for p in players:
                uid = p['user_id']
                if uid in exempt:
                    continue
                mmr = p['mmr']
                last = p['last_active']
                diff = now - last
                # buscar bracket para este mmr (mayor min_mmr)
                applicable = max((b for b in brackets if mmr >= b['min_mmr']), key=lambda x: x['min_mmr'], default=None)
                if not applicable:
                    continue
                days_thresh = applicable['days']
                # aviso previo
                if days_thresh - diff.days == notify_days:
                    user = guild.get_member(uid)
                    if user:
                        try:
                            await user.send(embed=self._build_warning_embed(days_thresh, applicable, mmr))
                        except discord.Forbidden:
                            pass
                # aplicar decay si pasa threshold
                if diff.days > days_thresh:
                    # aplicar solo una vez por día; chequear last_decay en config.user
                    last_decay = await self.config.user(user).last_decay()
                    if (now - datetime.utcfromtimestamp(last_decay)).days < 1:
                        continue
                    new_mmr = self._apply_decay(mmr, decay_type, decay_value)
                    # TODO: actualizar MMR en DB
                    # registrar timestamp
                    await self.config.user(user).last_decay.set(now.timestamp())
                    # notificar en Admin Log o DM
                    try:
                        await user.send(embed=self._build_decay_embed(mmr, new_mmr))
                    except discord.Forbidden:
                        pass

    async def get_all_player_data(self, guild):
        """Placeholder: extraer datos de jugadores del sistema principal"""
        return []

    def _apply_decay(self, mmr, dtype, val):
        if dtype == 'percent':
            return int(mmr * (1 - val / 100))
        return mmr - val

    def _build_warning_embed(self, days_thresh, bracket, mmr):
        return Embed(
            title="⚠️ Aviso de MMR Decay",
            description=(
                f"Tu MMR actual es **{mmr}**.\n"
                f"Si permaneces inactivo {bracket['days']} días, perderás **{self.config.guild.decay_type}@**"
            ),
            colour=discord.Colour.orange()
        )

    def _build_decay_embed(self, old, new):
        return Embed(
            title="📉 MMR Decay aplicado",
            fields=[
                {"name": "Antes", "value": str(old), "inline": True},
                {"name": "Ahora", "value": str(new), "inline": True}
            ],
            colour=discord.Colour.red()
        )

    @decay_loop.before_loop
    async def before_decay(self):
        await self.bot.wait_until_ready()
