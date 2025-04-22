# arenaqueue/queue.py
# coding: utf-8

from redbot.core import commands, Config
from redbot.core.utils.chat_formatting import pagify
import discord

QueueData = {
    "waiting": [],  # lista de user IDs en cola
    "channel_id": None,  # canal asociado
    "role_settings": None,  # futuros presets de roles
}

class QueueCog(commands.Cog):
    """👥 Gestión básica de colas in-house"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        # Configuración por servidor
        default_guild = {"queues": {}}  # maps channel_id -> QueueData
        self.config.register_guild(**default_guild)

    @commands.group(name="queue", invoke_without_command=True)
    @commands.guild_only()
    async def queue(self, ctx: commands.Context):
        """Grupo de comandos para colas."""
        await ctx.send_help(ctx.command)

    @queue.command(name="join")
    @commands.guild_only()
    async def queue_join(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Únete a una cola. Sino indicas canal, usa el canal actual."""
        channel = channel or ctx.channel
        guild_conf = await self.config.guild(ctx.guild).queues()
        q = guild_conf.get(str(channel.id), None)
        if q is None:
            await ctx.send(f"❌ Este canal ({channel.mention}) no está configurado como cola.")
            return
        if ctx.author.id in q["waiting"]:
            await ctx.send("⚠️ Ya estás en la cola.")
            return
        q["waiting"].append(ctx.author.id)
        await self.config.guild(ctx.guild).queues.set(guild_conf)
        await ctx.send(f"✅ {ctx.author.mention} se ha unido a la cola en {channel.mention} (posición {len(q['waiting'])}).")

    @queue.command(name="leave")
    @commands.guild_only()
    async def queue_leave(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Salir de una cola."""
        channel = channel or ctx.channel
        guild_conf = await self.config.guild(ctx.guild).queues()
        q = guild_conf.get(str(channel.id), None)
        if q is None or ctx.author.id not in q["waiting"]:
            await ctx.send("❌ No estás en la cola de este canal.")
            return
        q["waiting"].remove(ctx.author.id)
        await self.config.guild(ctx.guild).queues.set(guild_conf)
        await ctx.send(f"✅ {ctx.author.mention} ha salido de la cola en {channel.mention}.")

    @queue.command(name="status")
    @commands.guild_only()
    async def queue_status(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Muestra el estado de la cola."""
        channel = channel or ctx.channel
        guild_conf = await self.config.guild(ctx.guild).queues()
        q = guild_conf.get(str(channel.id), None)
        if q is None:
            await ctx.send("❌ Este canal no es una cola.")
            return
        if not q["waiting"]:
            await ctx.send("La cola está vacía.")
            return
        # Paginamos si hay mucha gente
        lines = []
        for pos, uid in enumerate(q["waiting"], 1):
            member = ctx.guild.get_member(uid)
            name = member.display_name if member else f"<Desconocido {uid}>"
            lines.append(f"**{pos}.** {name}")
        for page in pagify("\n".join(lines), delims=["\n"]):
            await ctx.send(page)

    @queue.command(name="start")
    @commands.mod_only()  # requiere permisos de mod/admin
    @commands.guild_only()
    async def queue_start(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Forzar inicio de juego con los que estén en cola."""
        channel = channel or ctx.channel
        guild_conf = await self.config.guild(ctx.guild).queues()
        q = guild_conf.get(str(channel.id), None)
        if q is None or not q["waiting"]:
            await ctx.send("❌ No hay una cola activa o está vacía.")
            return
        mentions = [f"<@{uid}>" for uid in q["waiting"]]
        await ctx.send("🏁 ¡Partida iniciada con:\n" + " ".join(mentions))
        # Reseteamos
        guild_conf[str(channel.id)]["waiting"] = []
        await self.config.guild(ctx.guild).queues.set(guild_conf)

    @queue.command(name="configure")
    @commands.admin_or_permissions(manage_guild=True)
    async def queue_configure(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Configura el canal actual (o indicado) como cola."""
        channel = channel or ctx.channel
        guild_conf = await self.config.guild(ctx.guild).queues()
        guild_conf[str(channel.id)] = {
            "waiting": [],
            "channel_id": channel.id,
            "role_settings": {},
        }
        await self.config.guild(ctx.guild).queues.set(guild_conf)
        await ctx.send(f"✅ {channel.mention} ha sido configurado como cola arenaqueue.")

    @queue.command(name="unconfigure")
    @commands.admin_or_permissions(manage_guild=True)
    async def queue_unconfigure(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Elimina la configuración de canal como cola."""
        channel = channel or ctx.channel
        guild_conf = await self.config.guild(ctx.guild).queues()
        if str(channel.id) in guild_conf:
            guild_conf.pop(str(channel.id))
            await self.config.guild(ctx.guild).queues.set(guild_conf)
            await ctx.send(f"✅ {channel.mention} ya no es una cola.")
        else:
            await ctx.send("❌ Este canal no estaba configurado como cola.")
