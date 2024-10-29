import json
import os
from redbot.core import commands, Config, checks
import discord
import asyncio
import logging

class ColaCoins(commands.Cog):
    """Gestiona las ColaCoins para los usuarios. By Killerbite95"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_global = {
            "colacoins": {},
            "emoji": ""  # Emoji predeterminado, inicialmente vacío
        }
        self.config.register_global(**default_global)
        self.logger = logging.getLogger("red.ColaCoins")
        self.logger.setLevel(logging.INFO)  # Cambia a DEBUG para más detalles
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
        handler.setFormatter(formatter)
        if not self.logger.handlers:
            self.logger.addHandler(handler)

    async def save_data(self):
        data = await self.config.colacoins()
        with open("colacoins_data.json", "w") as f:
            json.dump(data, f)
        self.logger.debug("Datos de ColaCoins guardados en colacoins_data.json.")

    async def load_data(self):
        if os.path.exists("colacoins_data.json"):
            with open("colacoins_data.json", "r") as f:
                data = json.load(f)
                await self.config.colacoins.set(data)
                self.logger.info("Datos de ColaCoins cargados desde colacoins_data.json.")

    @commands.Cog.listener()
    async def on_ready(self):
        await self.load_data()
        self.logger.info("ColaCoins cog cargado y datos cargados.")

    @commands.admin_or_permissions(administrator=True)
    @commands.command(name="givecolacoins", aliases=["darcolacoins"])
    async def give_colacoins(self, ctx, user: discord.Member, amount: int):
        """Da ColaCoins a un usuario. / Give ColaCoins to a user."""
        if amount <= 0:
            mensaje = (
                "El monto a dar debe ser positivo." 
                if ctx.invoked_with == 'darcolacoins' 
                else 
                "The amount to give must be positive."
            )
            await ctx.send(mensaje)
            return

        async with self.config.colacoins() as colacoins:
            if str(user.id) not in colacoins:
                colacoins[str(user.id)] = 0
            colacoins[str(user.id)] += amount
            emoji = await self.config.emoji() or ""
            mensaje = (
                f"{amount} {emoji} ColaCoins dados a {user.display_name}. Ahora tiene {colacoins[str(user.id)]} {emoji} ColaCoins."
                if ctx.invoked_with == 'darcolacoins' 
                else 
                f"{amount} {emoji} ColaCoins given to {user.display_name}. Now they have {colacoins[str(user.id)]} {emoji} ColaCoins."
            )
            await ctx.send(mensaje)
        await self.save_data()
        self.logger.info(f"{ctx.author} ha dado {amount} ColaCoins a {user}.")

    @commands.admin_or_permissions(administrator=True)
    @commands.command(name="removecolacoins", aliases=["quitarcolacoins"])
    async def remove_colacoins(self, ctx, user: discord.Member, amount: int):
        """Quita ColaCoins a un usuario. / Remove ColaCoins from a user."""
        if amount <= 0:
            mensaje = (
                "El monto a quitar debe ser positivo." 
                if ctx.invoked_with == 'quitarcolacoins' 
                else 
                "The amount to remove must be positive."
            )
            await ctx.send(mensaje)
            return

        async with self.config.colacoins() as colacoins:
            current = colacoins.get(str(user.id), 0)
            if current < amount:
                emoji = await self.config.emoji() or ""
                mensaje = (
                    f"No se puede quitar {amount} {emoji} ColaCoins. {user.display_name} no tiene suficientes ColaCoins."
                    if ctx.invoked_with == 'quitarcolacoins' 
                    else 
                    f"Cannot remove {amount} {emoji} ColaCoins. {user.display_name} does not have enough ColaCoins."
                )
                await ctx.send(mensaje)
                return
            colacoins[str(user.id)] -= amount
            emoji = await self.config.emoji() or ""
            mensaje = (
                f"{amount} {emoji} ColaCoins quitadas a {user.display_name}. Ahora tiene {colacoins[str(user.id)]} {emoji} ColaCoins."
                if ctx.invoked_with == 'quitarcolacoins' 
                else 
                f"{amount} {emoji} ColaCoins removed from {user.display_name}. Now they have {colacoins[str(user.id)]} {emoji} ColaCoins."
            )
            await ctx.send(mensaje)
        await self.save_data()
        self.logger.info(f"{ctx.author} ha quitado {amount} ColaCoins a {user}.")

    @commands.admin_or_permissions(administrator=True)
    @commands.command(name="vercolacoins", aliases=["viewcolacoins"])
    async def ver_colacoins(self, ctx, user: discord.Member):
        """Verifica la cantidad de ColaCoins de un usuario. / Check the ColaCoins amount of a user."""
        colacoins = await self.config.colacoins()
        amount = colacoins.get(str(user.id), 0)
        emoji = await self.config.emoji() or ""
        mensaje = (
            f"{user.display_name} tiene {amount} {emoji} ColaCoins."
            if ctx.invoked_with == 'vercolacoins' 
            else 
            f"{user.display_name} has {amount} {emoji} ColaCoins."
        )
        await ctx.send(mensaje)
        self.logger.info(f"{ctx.author} ha verificado las ColaCoins de {user}: {amount}.")

    @commands.command(name="colacoins", aliases=["miscolacoins"])
    async def user_colacoins(self, ctx):
        """Permite a un usuario ver cuántas ColaCoins tiene. / Allows a user to see how many ColaCoins they have."""
        colacoins = await self.config.colacoins()
        amount = colacoins.get(str(ctx.author.id), 0)
        emoji = await self.config.emoji() or ""
        mensaje = (
            f"Tienes {amount} {emoji} ColaCoins."
            if ctx.invoked_with == 'miscolacoins' 
            else 
            f"You have {amount} {emoji} ColaCoins."
        )
        await ctx.send(mensaje)
        self.logger.info(f"{ctx.author} ha consultado sus ColaCoins: {amount}.")

    @commands.admin_or_permissions(administrator=True)
    @commands.command(name="setcolacoinemoji", aliases=["establecercolacoinemoji"])
    async def set_colacoin_emoji(self, ctx, emoji: str):
        """Establece el emoji para las ColaCoins. / Set the emoji for ColaCoins."""
        await self.config.emoji.set(emoji)
        mensaje = (
            f"Emoji de ColaCoins establecido a {emoji}."
            if ctx.invoked_with == 'establecercolacoinemoji' 
            else 
            f"ColaCoins emoji set to {emoji}."
        )
        await ctx.send(mensaje)
        self.logger.info(f"{ctx.author} ha establecido el emoji de ColaCoins a {emoji}.")

    # --- Nuevos Comandos Añadidos ---

    @commands.group(name="colacoins", invoke_without_command=True)
    async def colacoins_group(self, ctx):
        """Gestiona las ColaCoins. / Manages ColaCoins."""
        # Si se invoca solo !colacoins o !miscolacoins, muestra las ColaCoins del usuario
        await self.user_colacoins(ctx)

    @colacoins_group.command(name="list", aliases=["lista"])
    @checks.admin_or_permissions(administrator=True)
    async def list_colacoins(self, ctx):
        """Muestra una leaderboard de los usuarios con más ColaCoins. / Shows a leaderboard of users with the most ColaCoins."""
        colacoins = await self.config.colacoins()
        if not colacoins:
            mensaje = (
                "No hay usuarios con ColaCoins actualmente." 
                if ctx.invoked_with == 'lista' 
                else 
                "There are no users with ColaCoins currently."
            )
            await ctx.send(mensaje)
            return

        # Crear una lista de tuplas (usuario_id, cantidad)
        sorted_colacoins = sorted(colacoins.items(), key=lambda x: x[1], reverse=True)
        
        # Preparar los datos para la leaderboard
        leaderboard = []
        for idx, (user_id, amount) in enumerate(sorted_colacoins, start=1):
            user = self.bot.get_user(int(user_id))
            if user:
                username = user.display_name
            else:
                username = f"Usuario ID {user_id}" if ctx.invoked_with == 'lista' else f"User ID {user_id}"
            emoji = await self.config.emoji() or ""
            leaderboard.append(f"**{idx}. {username}** - {amount} {emoji} ColaCoins")

        # Implementar la paginación (10 usuarios por página)
        per_page = 10
        pages = [leaderboard[i:i + per_page] for i in range(0, len(leaderboard), per_page)]
        total_pages = len(pages)
        current_page = 0

        # Crear el embed inicial
        embed = discord.Embed(
            title="🏆 Leaderboard de ColaCoins" if ctx.invoked_with == 'lista' else "🏆 ColaCoins Leaderboard",
            description="\n".join(pages[current_page]),
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"Página {current_page + 1} de {total_pages}")

        message = await ctx.send(embed=embed)

        if total_pages <= 1:
            return  # No se necesita paginación

        # Agregar reacciones de navegación
        await message.add_reaction("◀️")
        await message.add_reaction("▶️")

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["◀️", "▶️"] and reaction.message.id == message.id

        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)
            except asyncio.TimeoutError:
                # Quitar las reacciones si no hay actividad
                await message.clear_reactions()
                break
            else:
                if str(reaction.emoji) == "▶️":
                    if current_page + 1 < total_pages:
                        current_page += 1
                        embed.description = "\n".join(pages[current_page])
                        embed.set_footer(text=f"Página {current_page + 1} de {total_pages}")
                        await message.edit(embed=embed)
                elif str(reaction.emoji) == "◀️":
                    if current_page > 0:
                        current_page -= 1
                        embed.description = "\n".join(pages[current_page])
                        embed.set_footer(text=f"Página {current_page + 1} de {total_pages}")
                        await message.edit(embed=embed)
                # Remover la reacción del usuario para permitir múltiples reacciones
                await message.remove_reaction(reaction, user)
