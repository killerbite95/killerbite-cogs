import discord
from redbot.core import commands, Config, bank, checks
import random
from .dashboard_integration import DashboardIntegration
from redbot.core.i18n import Translator, cog_i18n, set_contextual_locales_from_guild

_ = Translator("Blackjack", __file__)

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
        await set_contextual_locales_from_guild(interaction.client, interaction.guild)
        # Solo el autor del comando puede usar los botones.
        return interaction.user.id == self.ctx.author.id

    @discord.ui.button(label=_("Hit"), style=discord.ButtonStyle.primary, emoji="🃏")
    async def hit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.player_hit(interaction, self.ctx)

    @discord.ui.button(label=_("Stand"), style=discord.ButtonStyle.success, emoji="✋")
    async def stand_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.player_stand(interaction, self.ctx)

    @discord.ui.button(label=_("Double Down"), style=discord.ButtonStyle.danger, emoji="💰")
    async def double_down_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.player_double_down(interaction, self.ctx)

    @discord.ui.button(label=_("Split"), style=discord.ButtonStyle.secondary, emoji="🔀")
    async def split_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.player_split(interaction, self.ctx)

    @discord.ui.button(label=_("Help"), style=discord.ButtonStyle.gray, emoji="❓")
    async def help_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        reglas = _("**Quick Blackjack rules:**\n• **Hit**: Draw another card.\n• **Stand**: Keep your current hand.\n• **Double Down**: Double the bet for this hand, take exactly 1 more card and stand.\n• **Split**: If your first 2 cards have the same value you can split them into 2 hands (extra bet equal to the base bet).\n• The dealer stands on 17 or more.\n• Going over 21 loses.\n• Blackjack = 21 with 2 cards.\n")
        await interaction.response.send_message(reglas, ephemeral=True)

    async def on_timeout(self):
        # Deshabilita los botones al expirar el tiempo.
        for child in self.children:
            child.disabled = True
        # Solo la vista vigente de la partida la resuelve (las anteriores ya
        # fueron sustituidas al pulsar un boton): se planta en lo que quede.
        game = self.cog.games.get(self.ctx.author.id)
        if not game or game.get("view") is not self:
            return
        await set_contextual_locales_from_guild(self.cog.bot, getattr(self.ctx, "guild", None))
        game["active_hand"] = len(game["player_hands"])
        message = game.get("message")
        if message is not None:
            try:
                await message.edit(view=None)
            except discord.HTTPException:
                pass
        await self.ctx.send(
            _("{author}, time is up: you stand automatically.").format(author=self.ctx.author.mention),
            allowed_mentions=discord.AllowedMentions(users=[self.ctx.author]),
        )
        await self.cog.dealer_phase(self.ctx)
        # Opcional: se puede editar el mensaje para notificar que la partida expiró.

@cog_i18n(_)
class Blackjack(DashboardIntegration, commands.Cog):
    """Advanced Blackjack cog with economy, interactive buttons, admin tools and an improved UI."""

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
        # (se carga en cog_load)

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

    async def cog_load(self):
        self._dashboard_register()
        await self.initialize_card_config()

    async def initialize_card_config(self):
        self.card_config["ranks"] = await self.config.ranks()
        self.card_config["suits"] = await self.config.suits()

    # ====================
    # Comando de juego
    # ====================

    @commands.command(name="blackjack")
    @checks.mod_or_permissions(manage_guild=True)
    async def blackjack_cmd(self, ctx, bet: int):
        """Start a Blackjack game with the given bet.
        Example: `[p]blackjack 100`
        """
        if bet <= 0:
            return await ctx.send(_("The bet must be greater than 0."))
        if ctx.author.id in self.games:
            return await ctx.send(_("You already have a game in progress. Finish it before starting another one."))

        balance = await bank.get_balance(ctx.author)
        if balance < bet:
            return await ctx.send(_("You don't have enough balance for that bet."))

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
        embed.title = _("Blackjack: Hand #1")
        embed.color = discord.Color.blue()
        embed.set_footer(text=_("Base bet: {bet} | Balance after betting: {value}\nUse the buttons to play.").format(bet=bet, value=balance - bet))
        view = self.build_view(ctx)
        self.games[ctx.author.id]["message"] = await ctx.send(embed=embed, view=view)

    # ====================
    # Funciones de jugadas
    # ====================

    async def player_hit(self, interaction: discord.Interaction, ctx):
        """El jugador pide una carta (Hit)."""
        game = self.games.get(ctx.author.id)
        if not game:
            return await interaction.response.send_message(_("You don't have an active game."), ephemeral=True)
        if game["active_hand"] >= len(game["player_hands"]):
            return await interaction.response.send_message(_("That hand is already finished."), ephemeral=True)

        active_idx = game["active_hand"]
        current_hand = game["player_hands"][active_idx]
        current_hand.append(game["deck"].pop())
        val = self.hand_value(current_hand)

        if val > 21:
            # El jugador se pasa (BUST).
            embed = self.build_embed(ctx, busted_hand=active_idx)
            embed.title = _("Hand #{value} - You busted with {val}.").format(value=active_idx+1, val=val)
            game["active_hand"] += 1
            if game["active_hand"] < len(game["player_hands"]):
                embed.title += _(" Playing hand #{value}...").format(value=game['active_hand']+1)
                await interaction.response.edit_message(embed=embed, view=self.build_view(ctx))
            else:
                await interaction.response.edit_message(embed=embed, view=None)
                await self.dealer_phase(ctx)
        else:
            embed = self.build_embed(ctx)
            embed.title = _("Blackjack: Hand #{value}").format(value=active_idx+1)
            await interaction.response.edit_message(embed=embed, view=self.build_view(ctx))

    async def player_stand(self, interaction: discord.Interaction, ctx):
        """El jugador se planta (Stand) en la mano actual."""
        game = self.games.get(ctx.author.id)
        if not game:
            return await interaction.response.send_message(_("You don't have an active game."), ephemeral=True)
        if game["active_hand"] >= len(game["player_hands"]):
            return await interaction.response.send_message(_("That hand is already finished."), ephemeral=True)
        game["active_hand"] += 1

        embed = self.build_embed(ctx)
        embed.title = _("You stood on hand #{active_hand}.").format(active_hand=game['active_hand'])
        if game["active_hand"] < len(game["player_hands"]):
            embed.title = _("Hand #{value}...").format(value=game['active_hand']+1)
            await interaction.response.edit_message(embed=embed, view=self.build_view(ctx))
        else:
            await interaction.response.edit_message(embed=embed, view=None)
            await self.dealer_phase(ctx)

    async def player_double_down(self, interaction: discord.Interaction, ctx):
        """El jugador dobla la apuesta (Double Down) en la mano actual."""
        game = self.games.get(ctx.author.id)
        if not game:
            return await interaction.response.send_message(_("You don't have an active game."), ephemeral=True)
        if game["active_hand"] >= len(game["player_hands"]):
            return await interaction.response.send_message(_("That hand is already finished."), ephemeral=True)
        active_idx = game["active_hand"]
        current_hand = game["player_hands"][active_idx]

        if len(current_hand) != 2:
            return await interaction.response.send_message(_("You can only double down with 2 cards in hand."), ephemeral=True)
        if game["double_down_used"][active_idx]:
            return await interaction.response.send_message(_("You already doubled down on this hand."), ephemeral=True)

        bet_add = game["base_bet"]
        bal = await bank.get_balance(ctx.author)
        if bal < bet_add:
            return await interaction.response.send_message(_("You don't have enough balance to double the bet."), ephemeral=True)

        await bank.withdraw_credits(ctx.author, bet_add)
        game["total_bet"] += bet_add
        game["double_down_used"][active_idx] = True
        current_hand.append(game["deck"].pop())
        val = self.hand_value(current_hand)

        embed = self.build_embed(ctx)
        embed.title = _("Hand #{value} - You doubled the bet.").format(value=active_idx+1)
        embed.set_footer(text=_("Total bet: {total_bet} | Current balance: {value}").format(total_bet=game['total_bet'], value=bal - bet_add))
        if val > 21:
            embed.title += _(" You busted with {val}.").format(val=val)

        game["active_hand"] += 1
        if game["active_hand"] < len(game["player_hands"]):
            embed.title += _(" Now hand #{value}...").format(value=game['active_hand']+1)
            await interaction.response.edit_message(embed=embed, view=self.build_view(ctx))
        else:
            await interaction.response.edit_message(embed=embed, view=None)
            await self.dealer_phase(ctx)

    async def player_split(self, interaction: discord.Interaction, ctx):
        """Divide la mano si las dos primeras cartas tienen el mismo valor (Split)."""
        game = self.games.get(ctx.author.id)
        if not game:
            return await interaction.response.send_message(_("You don't have an active game."), ephemeral=True)
        if game["active_hand"] >= len(game["player_hands"]):
            return await interaction.response.send_message(_("That hand is already finished."), ephemeral=True)
        active_idx = game["active_hand"]
        current_hand = game["player_hands"][active_idx]

        if len(current_hand) != 2:
            return await interaction.response.send_message(_("You can only split with exactly 2 cards."), ephemeral=True)
        if game["split_used"]:
            return await interaction.response.send_message(_("You can only split once in this version."), ephemeral=True)
        if self.card_value_for_split(current_hand[0]) != self.card_value_for_split(current_hand[1]):
            return await interaction.response.send_message(_("You can only split if both cards have the same value."), ephemeral=True)

        add_bet = game["base_bet"]
        bal = await bank.get_balance(ctx.author)
        if bal < add_bet:
            return await interaction.response.send_message(_("You don't have enough balance to split."), ephemeral=True)

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
        embed.title = _("You split your hand. You now have {count} hands.").format(count=len(game['player_hands']))
        embed.set_footer(text=_("Total bet: {total_bet} | Current balance: {value}").format(total_bet=game['total_bet'], value=bal - add_bet))
        await interaction.response.edit_message(embed=embed, view=self.build_view(ctx))

    # ====================================
    # Fase del Dealer y resolución final
    # ====================================

    async def dealer_phase(self, ctx):
        """Fase del Dealer tras que el jugador termine sus jugadas."""
        # Se saca la partida antes de pagar: un doble clic no puede resolverla dos veces.
        game = self.games.pop(ctx.author.id, None)
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
                results.append(_("Hand {value}: ❌ You lost (busted).").format(value=idx+1))
            else:
                if dealer_val > 21:
                    total_win += portion_bet * 2
                    results.append(_("Hand {value}: ✅ Dealer busted, you won {value2}!").format(value=idx+1, value2=portion_bet*2))
                else:
                    if val > dealer_val:
                        total_win += portion_bet * 2
                        results.append(_("Hand {value}: ✅ You won {value2} (your {val} vs dealer {dealer_val}).").format(value=idx+1, value2=portion_bet*2, val=val, dealer_val=dealer_val))
                    elif val < dealer_val:
                        results.append(_("Hand {value}: ❌ You lost (your {val} vs dealer {dealer_val}).").format(value=idx+1, val=val, dealer_val=dealer_val))
                    else:
                        total_win += portion_bet
                        results.append(_("Hand {value}: ⚠️ Push, you get {portion_bet} back.").format(value=idx+1, portion_bet=portion_bet))
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

        embed_final = self.build_embed(ctx, reveal_dealer=True, game=game)
        embed_final.title = _("Final result")
        embed_final.color = final_color
        resumen = "\n".join(results)
        embed_final.add_field(name=_("Dealer"), value=_("Value: **{dealer_val}**").format(dealer_val=dealer_val), inline=False)
        embed_final.add_field(name=_("Summary"), value=resumen, inline=False)
        embed_final.set_footer(text=_("Total winnings: {total_win} credits.").format(total_win=total_win))
        await ctx.send(embed=embed_final)

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

    def build_embed(self, ctx, reveal_dealer=False, busted_hand=None, game=None):
        """
        Construye un embed mostrando la mano del dealer y las manos del jugador.
        Se utiliza Markdown para mayor claridad.
        """
        game = game or self.games.get(ctx.author.id)
        if not game:
            return discord.Embed(description=_("Error: game not found."), color=discord.Color.red())

        dealer_hand = game["dealer_hand"]
        embed = discord.Embed(color=discord.Color.blue())
        embed.description = _("**Dealer:** {format_hand}").format(format_hand=self.format_hand(dealer_hand, reveal_dealer))
        if reveal_dealer:
            embed.description += _(" (Value: **{hand_value}**)").format(hand_value=self.hand_value(dealer_hand))
        for i, hand in enumerate(game["player_hands"]):
            hand_str = self.format_hand(hand, reveal_all=True)
            val = self.hand_value(hand)
            field_name = _("**Your hand #{value}**").format(value=i+1)
            if i == game["active_hand"]:
                field_name += " _(Jugando)_"
            if busted_hand is not None and busted_hand == i:
                field_name += _(" - **BUSTED!**")
            if len(hand) == 2 and val == 21:
                val_str = "**Blackjack!**"
            else:
                val_str = _("Value: **{val}**").format(val=val)
            embed.add_field(name=field_name, value=f"{hand_str}\n{val_str}", inline=False)
        return embed

    def build_view(self, ctx):
        """Reconstruye la vista para actualizar los botones."""
        view = AdvancedBlackjackView(self, ctx, timeout=120)
        game = self.games.get(ctx.author.id)
        if game is not None:
            game["view"] = view
        return view

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
        """Blackjack admin commands.
        Configure how cards are shown using emojis.
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @bjadmin.command(name="setrank")
    async def set_rank(self, ctx, rank: str, emoji: str):
        """Set the emoji for a specific rank.
        Example: `[p]bjadmin setrank A 🅰️`
        Allowed ranks: A, 2, 3, 4, 5, 6, 7, 8, 9, 10, J, Q, K.
        """
        allowed = {"A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"}
        if rank not in allowed:
            return await ctx.send(_("Invalid rank. Allowed ranks: ") + ", ".join(allowed))
        self.card_config["ranks"][rank] = emoji
        await self.config.ranks.set(self.card_config["ranks"])
        await ctx.send(_("Rank **{rank}** set to: {emoji}").format(rank=rank, emoji=emoji))

    @bjadmin.command(name="setsuit")
    async def set_suit(self, ctx, suit: str, emoji: str):
        """Set the emoji for a specific suit.
        Example: `[p]bjadmin setsuit ♠️ 🃑`
        Allowed suits: ♣, ♦, ♥, ♠.
        """
        allowed = {"♣", "♦", "♥", "♠"}
        if suit not in allowed:
            return await ctx.send(_("Invalid suit. Allowed suits: ") + ", ".join(allowed))
        self.card_config["suits"][suit] = emoji
        await self.config.suits.set(self.card_config["suits"])
        await ctx.send(_("Suit **{suit}** set to: {emoji}").format(suit=suit, emoji=emoji))

    @bjadmin.command(name="show")
    async def show_config(self, ctx):
        """Show the current card emoji settings."""
        msg = _("**Current card settings:**\n\n**Ranks:**\n")
        for k, v in self.card_config["ranks"].items():
            msg += f"{k}: {v}\n"
        msg += _("\n**Suits:**\n")
        for k, v in self.card_config["suits"].items():
            msg += f"{k}: {v}\n"
        await ctx.send(msg)

    @bjadmin.command(name="reset")
    async def reset_config(self, ctx):
        """Reset the card emoji settings to the defaults."""
        default_ranks = {"A": "A", "2": "2", "3": "3", "4": "4", "5": "5", "6": "6", "7": "7", "8": "8", "9": "9", "10": "10", "J": "J", "Q": "Q", "K": "K"}
        default_suits = {"♣": "♣", "♦": "♦", "♥": "♥", "♠": "♠"}
        self.card_config["ranks"] = default_ranks
        self.card_config["suits"] = default_suits
        await self.config.ranks.set(default_ranks)
        await self.config.suits.set(default_suits)
        await ctx.send(_("The card settings have been reset to the defaults."))

    # ============================
    # Limpieza del cog
    # ============================

    def cog_unload(self):
        """Limpia las partidas activas al descargarse el cog."""
        self.games.clear()
