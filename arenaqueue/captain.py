# arenaqueue/captain.py
# coding: utf-8

import discord
from random import shuffle
from redbot.core import commands, Config
from redbot.core.utils.chat_formatting import humanize_list

class CaptainQueueCog(commands.Cog):
    """⚔️ Captain Queue para arenaqueue"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=5678901234)
        default_guild = {
            "cq_channels": {},    # channel_id -> queue data
        }
        self.config.register_guild(**default_guild)

    @commands.group(name="captain", invoke_without_command=True)
    @commands.guild_only()
    async def captain(self, ctx: commands.Context):
        """Grupo de comandos para Captain Queue."""
        await ctx.send_help(ctx.command)

    @captain.group(name="queue", invoke_without_command=True)
    @commands.guild_only()
    async def cq_queue(self, ctx: commands.Context):
        """Subgrupo de comandos para configurar Captain Queue."""
        await ctx.send_help(ctx.command)

    @cq_queue.command(name="configure")
    @commands.admin_or_permissions(manage_guild=True)
    async def cq_configure(self, ctx: commands.Context, pick_channel: discord.TextChannel = None, sel_channel: discord.TextChannel = None):
        """
        Configura los canales de Captain Queue.
        pick_channel: canal donde se unen jugadores
        sel_channel: canal donde se hacen los picks
        """
        pick = pick_channel or ctx.channel
        sel = sel_channel or pick
        data = {
            "pick_channel": pick.id,
            "selection_channel": sel.id,
            "state": None,  # se llena cuando se inicia un CQ
        }
        guild_conf = await self.config.guild(ctx.guild).cq_channels()
        guild_conf[str(pick.id)] = data
        await self.config.guild(ctx.guild).cq_channels.set(guild_conf)
        await ctx.send(f"✅ Captain Queue configurada.\n• Canal de cola: {pick.mention}\n• Canal de selección: {sel.mention}")

    @cq_queue.command(name="start")
    @commands.admin_or_permissions(manage_guild=True)
    async def cq_start(
        self,
        ctx: commands.Context,
        mode: str = commands.choice(["highest", "lowest", "random", "admin"]),
        pick_order: str = commands.choice(["alternate", "snake"]),
    ):
        """
        Inicia una Captain Queue en este canal.
        mode: highest | lowest | random | admin
        pick_order: alternate | snake
        """
        guild_conf = await self.config.guild(ctx.guild).cq_channels()
        data = guild_conf.get(str(ctx.channel.id))
        if not data:
            await ctx.send("❌ Este canal no está configurado como Captain Queue.")
            return
        # obtén la lista de jugadores en cola
        pick_chan = ctx.guild.get_channel(data["pick_channel"])
        guild_q = await self.bot.get_cog("QueueCog").config.guild(ctx.guild).queues()
        q = guild_q.get(str(pick_chan.id), {}).get("waiting", [])
        if len(q) < 2:
            await ctx.send("❌ Se necesitan al menos 2 jugadores en la cola.")
            return

        # Selección de capitanes
        players = q.copy()
        if mode == "highest":
            # requiere que tengas MMR en DB, aquí asumimos orden de la cola como proxy
            captains = [players.pop(0), players.pop(0)]
        elif mode == "lowest":
            captains = [players.pop(), players.pop()]
        elif mode == "random":
            shuffle(players)
            captains = [players.pop(0), players.pop(0)]
        else:  # admin
            await ctx.send("❓ Modo admin: menciona a los 2 capitanes con `/captain queue setcaps @A @B`")
            # guardamos selección pendiente
            data["state"] = {"mode": "admin", "pick_order": pick_order, "captains": [], "remaining": players, "teams": {}}
            guild_conf[str(ctx.channel.id)] = data
            await self.config.guild(ctx.guild).cq_channels.set(guild_conf)
            return

        # Creamos orden de picks
        order = []
        if pick_order == "alternate":
            a, b = captains
            longer = players.copy()
            for i, p in enumerate(longer):
                order.append(captains[i % 2])
        else:  # snake
            a, b = captains
            seq = [a, b]
            cnt = len(players)
            while len(order) < cnt:
                order.extend(seq if (len(order)//len(seq)) % 2 == 0 else seq[::-1])
            order = order[:cnt]

        # Guardamos estado
        data["state"] = {
            "mode": mode,
            "pick_order": pick_order,
            "captains": captains,
            "remaining": players,
            "order": order,
            "teams": {str(captains[0]): [], str(captains[1]): []},
        }
        guild_conf[str(ctx.channel.id)] = data
        await self.config.guild(ctx.guild).cq_channels.set(guild_conf)

        # Anunciamos
        mentions = [f"<@{uid}>" for uid in captains]
        sel_chan = ctx.guild.get_channel(data["selection_channel"])
        await sel_chan.send(
            f"⚔️ Captain Queue iniciada!\n"
            f"Capitanes: {mentions[0]} y {mentions[1]}\n"
            f"Orden de picks: {pick_order}\n"
            f"Comando `/captain pick @jugador` para cada turno."
        )

    @cq_queue.command(name="setcaps")
    @commands.admin_or_permissions(manage_guild=True)
    async def cq_setcaps(self, ctx: commands.Context, cap1: discord.Member, cap2: discord.Member):
        """
        (Sólo para mode=admin) Asigna manualmente los capitanes.
        """
        guild_conf = await self.config.guild(ctx.guild).cq_channels()
        data = guild_conf.get(str(ctx.channel.id))
        state = data.get("state")
        if not state or state.get("mode") != "admin":
            await ctx.send("❌ No hay selección admin en curso en este canal.")
            return
        players = state["remaining"]
        captains = [cap1.id, cap2.id]
        for c in captains:
            if c not in players:
                players.append(c)
        for c in captains:
            players.remove(c)
        state.update({
            "captains": captains,
            "remaining": players,
        })
        # Creamos orden (snake by default)
        seq = captains
        cnt = len(players)
        order = []
        while len(order) < cnt:
            order.extend(seq if (len(order)//len(seq)) % 2 == 0 else seq[::-1])
        state["order"] = order[:cnt]
        state["teams"] = {str(captains[0]): [], str(captains[1]): []}
        data["state"] = state
        guild_conf[str(ctx.channel.id)] = data
        await self.config.guild(ctx.guild).cq_channels.set(guild_conf)
        mentions = [f"<@{uid}>" for uid in captains]
        await ctx.send(f"✅ Capitanes establecidos: {mentions[0]} y {mentions[1]}. Comienza con `/captain pick @jugador`.")

    @captain.command(name="pick")
    @commands.guild_only()
    async def captain_pick(self, ctx: commands.Context, member: discord.Member):
        """
        Realiza un pick en la Captain Queue activa.
        """
        # Buscamos la CQ activa en este canal de selección
        guild_conf = await self.config.guild(ctx.guild).cq_channels()
        data = None
        for cfg in guild_conf.values():
            if cfg.get("selection_channel") == ctx.channel.id:
                data = cfg
                break
        if not data:
            await ctx.send("❌ Este canal no es un canal de selección activo.")
            return
        state = data.get("state")
        order = state.get("order", [])
        teams = state["teams"]
        captains = state["captains"]
        # ¿Es el turno correcto?
        if ctx.author.id != order[0]:
            await ctx.send("❌ No es tu turno de pick.")
            return
        # ¿jugador válido?
        if member.id not in state["remaining"]:
            await ctx.send("❌ Este jugador no está en la cola.")
            return
        # Asignar
        cap_id = ctx.author.id
        teams[str(cap_id)].append(member.id)
        state["remaining"].remove(member.id)
        # Avanzar turno
        state["order"].pop(0)
        data["state"] = state
        guild_conf[str(data["pick_channel"])] = data
        await self.config.guild(ctx.guild).cq_channels.set(guild_conf)

        # Confirmación
        team_mentions = [f"<@{uid}>" for uid in teams[str(cap_id)]]
        await ctx.send(f"✅ {ctx.author.mention} ha pickeado a {member.mention}.\nEquipo: {humanize_list(team_mentions)}")

        # Si no quedan por asignar, finalizamos
        if not state["order"]:
            sel_chan = ctx.channel
            all_teams = []
            for cap in captains:
                tm = [f"<@{uid}>" for uid in teams[str(cap)]]
                all_teams.append(f"**Capitán <@{cap}>**: {humanize_list(tm)}")
            await sel_chan.send("🏁 **Draft completado!**\n" + "\n".join(all_teams))
            # Limpiar estado
            data["state"] = None
            guild_conf[str(data["pick_channel"])] = data
            await self.config.guild(ctx.guild).cq_channels.set(guild_conf)

    @cq_queue.command(name="cancel")
    @commands.admin_or_permissions(manage_guild=True)
    async def cq_cancel(self, ctx: commands.Context):
        """Cancela la Captain Queue activa y limpia el estado."""
        guild_conf = await self.config.guild(ctx.guild).cq_channels()
        data = guild_conf.get(str(ctx.channel.id))
        if not data or not data.get("state"):
            await ctx.send("❌ No hay Captain Queue activa en este canal.")
            return
        data["state"] = None
        guild_conf[str(ctx.channel.id)] = data
        await self.config.guild(ctx.guild).cq_channels.set(guild_conf)
        await ctx.send("❌ Captain Queue cancelada y estado limpio.")
