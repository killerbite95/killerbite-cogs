import discord
from redbot.core import commands, Config, bank, checks
import random

class AdvancedBlackjackView(discord.ui.View):
    """
    Vista con los botones de Hit, Stand, Double Down, Split y Help.
    Se encarga de interactuar con la partida en curso.
    """
    __author__ = "Killerbite95"  # Aquí se declara el autor
    def __init__(self, cog, ctx, timeout=120):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.ctx = ctx

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Solo el autor del comando puede usar los botones.
        return interaction.user.id == self.ctx.author.id

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary, emoji="🃏")
    async def hit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.player_hit(interaction, self.ctx)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.success, emoji="✋")
    async def stand_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.player_stand(interaction, self.ctx)

    @discord.ui.button(label="Double Down", style=discord.ButtonStyle.danger, emoji="💰")
    async def double_down_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.player_double_down(interaction, self.ctx)

    @discord.ui.button(label="Split", style=discord.ButtonStyle.secondary, emoji="🔀")
    async def split_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.player_split(interaction, self.ctx)

    @discord.ui.button(label="Help", style=discord.ButtonStyle.gray, emoji="❓")
    async def help_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        reglas = (
            "**Reglas rápidas de Blackjack:**\n"
            "• **Hit**: Pides otra carta.\n"
            "• **Stand**: Te plantas con tu mano actual.\n"
            "• **Double Down**: Duplicas la apuesta para la mano actual, recibes solo 1 carta más y te plantas.\n"
            "• **Split**: Si tus 2 primeras cartas tienen el mismo valor, puedes dividirlas en 2 manos (apuesta adicional igual a la base).\n"
            "• El Dealer se planta en 17 o más.\n"
            "• Si superas 21, pierdes.\n"
            "• Blackjack = 21 con 2 cartas.\n"
        )
        await interaction.response.send_message(reglas, ephemeral=True)

    async def on_timeout(self):
        # Deshabilita los botones al expirar el tiempo.
        for child in self.children:
            child.disabled = True
        # Opcional: se puede editar el mensaje para notificar que la partida expiró.

class Blackjack(commands.Cog):
    """Cog de Blackjack avanzado con economía, botones interactivos, sistema de administración y una UI mejorada."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=5432123456, force_registration=True)
        # Registramos la configuración global para los emojis de las cartas.
        default_ranks = {"A": "A", "2": "2", "3": "3", "4": "4", "5": "5", "6": "6", "7": "7", "8": "8", "9": "9", "10": "10", "J": "J", "Q": "Q", "K": "K"}
        default_suits = {"♣": "♣", "♦": "♦", "♥": "♥", "♠": "♠"}
        self.config.register_global(ranks=default_ranks, suits=default_suits)

        # Variable caché para la configuración de las cartas.
        self.card_config = {"ranks": default_ranks.copy(), "suits": default_suits.copy()}
        # Cargamos la configuración de forma asíncrona.
        self.bot.loop.create_task(self.initialize_card_config())

        # Diccionario para partidas activas:
        # self.games[user_id] = {
        #    "deck": [...],
        #    "dealer_hand": [...],
        #    "player_hands": [[...], [...], ...],
        #    "active_hand": int,
        #    "base_bet": int,
        #    "total_bet": int,
        #    "split_used": bool,
        #    "double_down_used": [bool, ...]  # Una por cada mano
        # }
        self.games = {}

    async def initialize_card_config(self):
        self.card_config["ranks"] = await self.config.ranks()
        self.card_config["suits"] = await self.config.suits()

    # ====================
    # Comando de juego
    # ====================

    @commands.command(name="blackjack")
    @checks.mod_or_permissions(manage_guild=True)
    async def blackjack_cmd(self, ctx, bet: int):
        """
        Inicia una partida de Blackjack con la apuesta indicada.
        Ejemplo: `[p]blackjack 100`
        """
        if bet <= 0:
            return await ctx.send("La apuesta debe ser mayor que 0.")

        balance = await bank.get_balance(ctx.author)
        if balance < bet:
            return await ctx.send("No tienes suficiente saldo para esa apuesta.")

        # Retiramos la apuesta inicial.
        await bank.withdraw_credits(ctx.author, bet)

        deck = self.create_deck()
        random.shuffle(deck)

        # Repartimos cartas: 2 para el jugador, 2 para el dealer.
        player_hand = [deck.pop(), deck.pop()]
        dealer_hand = [deck.pop(), deck.pop()]

        # Guardamos la partida en memoria.
        self.games[ctx.author.id] = {
            "deck": deck,
            "dealer_hand": dealer_hand,
            "player_hands": [player_hand],
            "active_hand": 0,
            "base_bet": bet,
            "total_bet": bet,
            "split_used": False,
            "double_down_used": [False]
        }

        # Embed inicial: color neutro (azul) y footer con instrucciones.
        embed = self.build_embed(ctx)
        embed.title = "Blackjack: Mano #1"
        embed.color = discord.Color.blue()
        embed.set_footer(text=f"Apuesta base: {bet} | Saldo tras apostar: {balance - bet}\nUsa los botones para jugar.")
        view = AdvancedBlackjackView(self, ctx, timeout=120)
        await ctx.send(embed=embed, view=view)

    # ====================
    # Funciones de jugadas
    # ====================

    async def player_hit(self, interaction: discord.Interaction, ctx):
        """El jugador pide una carta (Hit)."""
        game = self.games.get(ctx.author.id)
        if not game:
            return await interaction.response.send_message("No tienes una partida activa.", ephemeral=True)

        active_idx = game["active_hand"]
        current_hand = game["player_hands"][active_idx]
        current_hand.append(game["deck"].pop())
        val = self.hand_value(current_hand)

        if val > 21:
            # El jugador se pasa (BUST).
            embed = self.build_embed(ctx, busted_hand=active_idx)
            embed.title = f"Mano #{active_idx+1} - Te pasaste con {val}."
            game["active_hand"] += 1
            if game["active_hand"] < len(game["player_hands"]):
                embed.title += f" Jugando mano #{game['active_hand']+1}..."
                await interaction.response.edit_message(embed=embed, view=self.build_view(ctx))
            else:
                await interaction.response.edit_message(embed=embed, view=None)
                await self.dealer_phase(ctx)
        else:
            embed = self.build_embed(ctx)
            embed.title = f"Blackjack: Mano #{active_idx+1}"
            await interaction.response.edit_message(embed=embed, view=self.build_view(ctx))

    async def player_stand(self, interaction: discord.Interaction, ctx):
        """El jugador se planta (Stand) en la mano actual."""
        game = self.games.get(ctx.author.id)
        if not game:
            return await interaction.response.send_message("No tienes una partida activa.", ephemeral=True)
        game["active_hand"] += 1

        embed = self.build_embed(ctx)
        embed.title = f"Te has plantado en la mano #{game['active_hand']}."
        if game["active_hand"] < len(game["player_hands"]):
            embed.title = f"Mano #{game['active_hand']+1}..."
            await interaction.response.edit_message(embed=embed, view=self.build_view(ctx))
        else:
            await interaction.response.edit_message(embed=embed, view=None)
            await self.dealer_phase(ctx)

    async def player_double_down(self, interaction: discord.Interaction, ctx):
        """El jugador dobla la apuesta (Double Down) en la mano actual."""
        game = self.games.get(ctx.author.id)
        if not game:
            return await interaction.response.send_message("No tienes una partida activa.", ephemeral=True)
        active_idx = game["active_hand"]
        current_hand = game["player_hands"][active_idx]

        if len(current_hand) != 2:
            return await interaction.response.send_message("Solo puedes doblar con 2 cartas en la mano.", ephemeral=True)
        if game["double_down_used"][active_idx]:
            return await interaction.response.send_message("Ya has doblado en esta mano.", ephemeral=True)

        bet_add = game["base_bet"]
        bal = await bank.get_balance(ctx.author)
        if bal < bet_add:
            return await interaction.response.send_message("No tienes saldo suficiente para doblar la apuesta.", ephemeral=True)

        await bank.withdraw_credits(ctx.author, bet_add)
        game["total_bet"] += bet_add
        game["double_down_used"][active_idx] = True
        current_hand.append(game["deck"].pop())
        val = self.hand_value(current_hand)

        embed = self.build_embed(ctx)
        embed.title = f"Mano #{active_idx+1} - Doblaste la apuesta."
        embed.set_footer(text=f"Apuesta total: {game['total_bet']} | Saldo actual: {bal - bet_add}")
        if val > 21:
            embed.title += f" Te pasaste con {val}."

        game["active_hand"] += 1
        if game["active_hand"] < len(game["player_hands"]):
            embed.title += f" Ahora mano #{game['active_hand']+1}..."
            await interaction.response.edit_message(embed=embed, view=self.build_view(ctx))
        else:
            await interaction.response.edit_message(embed=embed, view=None)
            await self.dealer_phase(ctx)

    async def player_split(self, interaction: discord.Interaction, ctx):
        """Divide la mano si las dos primeras cartas tienen el mismo valor (Split)."""
        game = self.games.get(ctx.author.id)
        if not game:
            return await interaction.response.send_message("No tienes una partida activa.", ephemeral=True)
        active_idx = game["active_hand"]
        current_hand = game["player_hands"][active_idx]

        if len(current_hand) != 2:
            return await interaction.response.send_message("Solo puedes dividir con exactamente 2 cartas.", ephemeral=True)
        if game["split_used"]:
            return await interaction.response.send_message("Solo se permite dividir una vez en esta versión.", ephemeral=True)
        if self.card_value_for_split(current_hand[0]) != self.card_value_for_split(current_hand[1]):
            return await interaction.response.send_message("Solo puedes dividir si ambas cartas tienen el mismo valor.", ephemeral=True)

        add_bet = game["base_bet"]
        bal = await bank.get_balance(ctx.author)
        if bal < add_bet:
            return await interaction.response.send_message("No tienes suficiente saldo para dividir (split).", ephemeral=True)

        await bank.withdraw_credits(ctx.author, add_bet)
        game["total_bet"] += add_bet

        # Realizar el split: se separan las dos cartas y se reparte una adicional a cada mano.
        card1 = current_hand[0]
        card2 = current_hand[1]
        new_hand1 = [card1, game["deck"].pop()]
        new_hand2 = [card2, game["deck"].pop()]

        game["player_hands"][active_idx] = new_hand1
        game["player_hands"].insert(active_idx+1, new_hand2)
        game["double_down_used"][active_idx] = False
        game["double_down_used"].insert(active_idx+1, False)
        game["split_used"] = True

        embed = self.build_embed(ctx)
        embed.title = f"Has dividido tu mano. Ahora tienes {len(game['player_hands'])} manos."
        embed.set_footer(text=f"Apuesta total: {game['total_bet']} | Saldo actual: {bal - add_bet}")
        await interaction.response.edit_message(embed=embed, view=self.build_view(ctx))

    # ====================================
    # Fase del Dealer y resolución final
    # ====================================

    async def dealer_phase(self, ctx):
        """Fase del Dealer tras que el jugador termine sus jugadas."""
        game = self.games.get(ctx.author.id)
        if not game:
            return

        dealer_hand = game["dealer_hand"]
        # El Dealer roba hasta tener al menos 17.
        while self.hand_value(dealer_hand) < 17:
            dealer_hand.append(game["deck"].pop())
        dealer_val = self.hand_value(dealer_hand)

        results = []
        total_win = 0
        base_bet = game["base_bet"]

        for idx, hand in enumerate(game["player_hands"]):
            val = self.hand_value(hand)
            portion_bet = base_bet
            if game["double_down_used"][idx]:
                portion_bet *= 2

            if val > 21:
                results.append(f"Mano {idx+1}: ❌ Perdiste (te pasaste).")
            else:
                if dealer_val > 21:
                    total_win += portion_bet * 2
                    results.append(f"Mano {idx+1}: ✅ Dealer se pasó, ganaste {portion_bet*2}!")
                else:
                    if val > dealer_val:
                        total_win += portion_bet * 2
                        results.append(f"Mano {idx+1}: ✅ Ganaste {portion_bet*2} (tu {val} vs dealer {dealer_val}).")
                    elif val < dealer_val:
                        results.append(f"Mano {idx+1}: ❌ Perdiste (tu {val} vs dealer {dealer_val}).")
                    else:
                        total_win += portion_bet
                        results.append(f"Mano {idx+1}: ⚠️ Empate, recuperas {portion_bet}.")
        # Depositar ganancia si corresponde.
        if total_win > 0:
            await bank.deposit_credits(ctx.author, total_win)

        # Determinar color final del embed según resultado global.
        if total_win > game["total_bet"]:
            final_color = discord.Color.green()   # Ganancia
        elif total_win == game["total_bet"]:
            final_color = discord.Color.orange()    # Empate
        else:
            final_color = discord.Color.red()       # Pérdida

        embed_final = self.build_embed(ctx, reveal_dealer=True)
        embed_final.title = "Resultado Final"
        embed_final.color = final_color
        resumen = "\n".join(results)
        embed_final.add_field(name="Dealer", value=f"Valor: **{dealer_val}**", inline=False)
        embed_final.add_field(name="Resumen", value=resumen, inline=False)
        embed_final.set_footer(text=f"Ganancia total: {total_win} créditos.")
        await ctx.send(embed=embed_final)

        # Limpiar la partida.
        self.games.pop(ctx.author.id, None)

    # ============================
    # Utilidades y funciones auxiliares
    # ============================

    def create_deck(self):
        """Crea una baraja estándar de 52 cartas."""
        palos = ["♣", "♦", "♥", "♠"]
        valores = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
        deck = [(v, p) for p in palos for v in valores]
        return deck

    def hand_value(self, hand):
        """Calcula el valor de una mano de Blackjack, tratando los ases como 11 o 1."""
        value = 0
        aces = 0
        for card in hand:
            rank = card[0]
            if rank in ["J", "Q", "K"]:
                value += 10
            elif rank == "A":
                aces += 1
                value += 11
            else:
                value += int(rank)
        while value > 21 and aces:
            value -= 10
            aces -= 1
        return value

    def card_to_str(self, card):
        """
        Convierte una carta (valor, palo) en cadena.
        Se utilizan los emojis configurados; si no hay configuración para
        un valor o palo, se usa el valor por defecto.
        """
        rank, suit = card
        emoji_rank = self.card_config.get("ranks", {}).get(rank, rank)
        emoji_suit = self.card_config.get("suits", {}).get(suit, suit)
        return f"{emoji_rank}{emoji_suit}"

    def format_hand(self, hand, reveal_all=True):
        """
        Formatea la mano en un string.
        Si reveal_all es False, muestra solo la primera carta y oculta el resto con el emoji 🂠.
        """
        if not reveal_all and len(hand) > 1:
            return f"{self.card_to_str(hand[0])} 🂠"
        return " ".join(self.card_to_str(c) for c in hand)

    def build_embed(self, ctx, reveal_dealer=False, busted_hand=None):
        """
        Construye un embed mostrando la mano del dealer y las manos del jugador.
        Se utiliza Markdown para mayor claridad.
        """
        game = self.games.get(ctx.author.id)
        if not game:
            return discord.Embed(description="Error: no se encontró la partida.", color=discord.Color.red())

        dealer_hand = game["dealer_hand"]
        embed = discord.Embed(color=discord.Color.blue())
        embed.description = f"**Dealer:** {self.format_hand(dealer_hand, reveal_dealer)}"
        if reveal_dealer:
            embed.description += f" (Valor: **{self.hand_value(dealer_hand)}**)"
        for i, hand in enumerate(game["player_hands"]):
            hand_str = self.format_hand(hand, reveal_all=True)
            val = self.hand_value(hand)
            field_name = f"**Tu mano #{i+1}**"
            if i == game["active_hand"]:
                field_name += " _(Jugando)_"
            if busted_hand is not None and busted_hand == i:
                field_name += " - **BUSTED!**"
            if len(hand) == 2 and val == 21:
                val_str = "**Blackjack!**"
            else:
                val_str = f"Valor: **{val}**"
            embed.add_field(name=field_name, value=f"{hand_str}\n{val_str}", inline=False)
        return embed

    def build_view(self, ctx):
        """Reconstruye la vista para actualizar los botones."""
        return AdvancedBlackjackView(self, ctx, timeout=120)

    def card_value_for_split(self, card):
        """
        Retorna un valor para comparar si dos cartas pueden dividirse.
        J, Q, K y 10 se agrupan como 10; A se considera 1; el resto se convierte a entero.
        """
        rank = card[0]
        if rank in ["J", "Q", "K", "10"]:
            return 10
        if rank == "A":
            return 1
        return int(rank)

    # ============================
    # Comandos de administración (Admin)
    # ============================

    @commands.group(name="bjadmin")
    @checks.admin_or_permissions(administrator=True)
    async def bjadmin(self, ctx):
        """
        Comandos de administración para Blackjack.
        Permite configurar la representación de las cartas mediante emojis.
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @bjadmin.command(name="setrank")
    async def set_rank(self, ctx, rank: str, emoji: str):
        """
        Configura el emoji para un valor (rank) específico.
        Ejemplo: `[p]bjadmin setrank A 🅰️`
        Valores permitidos: A, 2, 3, 4, 5, 6, 7, 8, 9, 10, J, Q, K.
        """
        allowed = {"A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"}
        if rank not in allowed:
            return await ctx.send("Valor (rank) inválido. Los valores permitidos son: " + ", ".join(allowed))
        self.card_config["ranks"][rank] = emoji
        await self.config.ranks.set(self.card_config["ranks"])
        await ctx.send(f"El valor **{rank}** se ha configurado a: {emoji}")

    @bjadmin.command(name="setsuit")
    async def set_suit(self, ctx, suit: str, emoji: str):
        """
        Configura el emoji para un palo (suit) específico.
        Ejemplo: `[p]bjadmin setsuit ♠️ 🃑`
        Palos permitidos: ♣, ♦, ♥, ♠.
        """
        allowed = {"♣", "♦", "♥", "♠"}
        if suit not in allowed:
            return await ctx.send("Palo (suit) inválido. Los palos permitidos son: " + ", ".join(allowed))
        self.card_config["suits"][suit] = emoji
        await self.config.suits.set(self.card_config["suits"])
        await ctx.send(f"El palo **{suit}** se ha configurado a: {emoji}")

    @bjadmin.command(name="show")
    async def show_config(self, ctx):
        """
        Muestra la configuración actual de emojis para las cartas.
        """
        msg = "**Configuración actual de cartas:**\n\n**Valores (Ranks):**\n"
        for k, v in self.card_config["ranks"].items():
            msg += f"{k}: {v}\n"
        msg += "\n**Palos (Suits):**\n"
        for k, v in self.card_config["suits"].items():
            msg += f"{k}: {v}\n"
        await ctx.send(msg)

    @bjadmin.command(name="reset")
    async def reset_config(self, ctx):
        """
        Restablece la configuración de emojis de las cartas a los valores por defecto.
        """
        default_ranks = {"A": "A", "2": "2", "3": "3", "4": "4", "5": "5", "6": "6", "7": "7", "8": "8", "9": "9", "10": "10", "J": "J", "Q": "Q", "K": "K"}
        default_suits = {"♣": "♣", "♦": "♦", "♥": "♥", "♠": "♠"}
        self.card_config["ranks"] = default_ranks
        self.card_config["suits"] = default_suits
        await self.config.ranks.set(default_ranks)
        await self.config.suits.set(default_suits)
        await ctx.send("La configuración de cartas se ha restablecido a los valores por defecto.")

    # ============================
    # Limpieza del cog
    # ============================

    def cog_unload(self):
        """Limpia las partidas activas al descargarse el cog."""
        self.games.clear()
