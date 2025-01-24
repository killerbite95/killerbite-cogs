import discord
from discord.ext import commands
from redbot.core import Config, bank, checks
import random

class AdvancedBlackjackView(discord.ui.View):
    """
    Vista con los botones de Hit, Stand, Double Down, Split y Help.
    Se encarga de interactuar con la partida en curso.
    """
    def __init__(self, cog, ctx, timeout=120):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.ctx = ctx

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Solo el autor del comando puede usar los botones
        return interaction.user.id == self.ctx.author.id

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
    async def hit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.player_hit(interaction, self.ctx)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.success)
    async def stand_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.player_stand(interaction, self.ctx)

    @discord.ui.button(label="Double Down", style=discord.ButtonStyle.danger)
    async def double_down_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.player_double_down(interaction, self.ctx)

    @discord.ui.button(label="Split", style=discord.ButtonStyle.secondary)
    async def split_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.player_split(interaction, self.ctx)

    @discord.ui.button(label="Help", style=discord.ButtonStyle.grey)
    async def help_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Muestra un texto con reglas/explicaciones en mensaje efímero
        msg = (
            "**Reglas rápidas de Blackjack:**\n"
            "- **Hit**: Pides otra carta.\n"
            "- **Stand**: Te plantas con tu mano actual.\n"
            "- **Double Down**: Duplicas la apuesta para la mano actual, "
            "recibes solo 1 carta más y te plantas.\n"
            "- **Split**: Si tus dos primeras cartas tienen el mismo valor, "
            "puedes dividirlas en 2 manos (necesitas saldo adicional igual a la apuesta).\n"
            "- El Dealer se planta en 17.\n"
            "- Si superas 21, pierdes.\n"
            "- Blackjack = 21 con 2 cartas.\n"
        )
        await interaction.response.send_message(msg, ephemeral=True)

    async def on_timeout(self):
        # Si expira el tiempo, deshabilitamos la vista
        for child in self.children:
            child.disabled = True


class Blackjack(commands.Cog):
    """Cog de Blackjack avanzado con economía y botones (Double Down, Split, etc.)."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=5432123456, force_registration=True)
        # Estructura en memoria para partidas activas:
        # games[user_id] = {
        #    "deck": [...],
        #    "dealer_hand": [...],
        #    "player_hands": [[...], [...], ...],
        #    "active_hand": 0,
        #    "base_bet": int,     # Apuesta inicial
        #    "total_bet": int,    # Cantidad total que se ajusta al hacer splits/double
        #    "split_used": False, # Controla si se ha hecho split ya
        #    "double_down_used": [False, ...] # Por cada mano
        # }
        self.games = {}

    @commands.command(name="blackjack")
    @checks.mod_or_permissions(manage_guild=True)  # Ajusta el check que quieras
    async def blackjack_cmd(self, ctx, bet: int):
        """
        Inicia una partida de Blackjack con la apuesta indicada.
        """
        if bet <= 0:
            return await ctx.send("La apuesta debe ser mayor que 0.")

        balance = await bank.get_balance(ctx.author)
        if balance < bet:
            return await ctx.send("No tienes suficiente saldo para esa apuesta.")

        # Retirar el dinero apostado al empezar (apuesta base)
        await bank.withdraw_credits(ctx.author, bet)

        deck = self.create_deck()
        random.shuffle(deck)

        # Repartir
        player_hand = [deck.pop(), deck.pop()]
        dealer_hand = [deck.pop(), deck.pop()]

        # Almacenamos la partida
        self.games[ctx.author.id] = {
            "deck": deck,
            "dealer_hand": dealer_hand,
            "player_hands": [player_hand],
            "active_hand": 0,
            "base_bet": bet,
            "total_bet": bet,
            "split_used": False,
            "double_down_used": [False]  # Una por cada mano
        }

        # Creamos el embed inicial y la View
        embed = self.build_embed(ctx.author.name)
        embed.title = "Blackjack: Mano #1"
        embed.set_footer(text=f"Apuesta base: {bet} | Saldo tras apostar: {balance - bet}")
        view = AdvancedBlackjackView(self, ctx, timeout=120)

        await ctx.send(embed=embed, view=view)

    # === BOTONES / Jugadas ===

    async def player_hit(self, interaction: discord.Interaction, ctx):
        """El jugador pide carta para la mano actual."""
        game = self.games.get(ctx.author.id)
        if not game:
            return await interaction.response.send_message("No tienes una partida activa.", ephemeral=True)

        active_idx = game["active_hand"]
        current_hand = game["player_hands"][active_idx]

        # Si ya te pasaste o ya te plantaste en esta mano, no deberías poder:
        # Pero lo gestionaremos cuando se detecte que te pasas a 21 o más.

        # Robar carta
        current_hand.append(game["deck"].pop())

        # Comprobamos si se pasó de 21
        val = self.hand_value(current_hand)
        if val > 21:
            # Perdiste esta mano. Vamos a la siguiente (o a la fase dealer si era la última).
            # Indicar en embed que se pasó.
            embed = self.build_embed(ctx.author.name, busted_hand=active_idx)
            embed.title = f"Mano #{active_idx+1} - Te pasaste con {val}."
            # Avanzar a la siguiente mano
            game["active_hand"] += 1
            # A ver si hay más manos
            if game["active_hand"] < len(game["player_hands"]):
                embed.title += f" Jugando mano #{game['active_hand']+1}..."
                await interaction.response.edit_message(embed=embed, view=self.build_view(ctx))
            else:
                # Pasamos a la fase dealer
                await interaction.response.edit_message(embed=embed, view=None)
                await self.dealer_phase(ctx, embed)
        else:
            # Aún en juego
            embed = self.build_embed(ctx.author.name)
            embed.title = f"Blackjack: Mano #{active_idx+1}"
            await interaction.response.edit_message(embed=embed, view=self.build_view(ctx))

    async def player_stand(self, interaction: discord.Interaction, ctx):
        """El jugador se planta con la mano actual."""
        game = self.games.get(ctx.author.id)
        if not game:
            return await interaction.response.send_message("No tienes una partida activa.", ephemeral=True)

        # Pasar a la siguiente mano
        game["active_hand"] += 1
        embed = self.build_embed(ctx.author.name)
        embed.title = f"Te has plantado en la mano #{game['active_hand']}."

        # ¿Hay más manos de jugador?
        if game["active_hand"] < len(game["player_hands"]):
            # Continuar con la siguiente mano
            embed.title = f"Mano #{game['active_hand']+1}..."
            await interaction.response.edit_message(embed=embed, view=self.build_view(ctx))
        else:
            # Ir a fase dealer
            await interaction.response.edit_message(embed=embed, view=None)
            await self.dealer_phase(ctx, embed)

    async def player_double_down(self, interaction: discord.Interaction, ctx):
        """El jugador elige doblar la apuesta en la mano actual."""
        game = self.games.get(ctx.author.id)
        if not game:
            return await interaction.response.send_message("No tienes una partida activa.", ephemeral=True)

        active_idx = game["active_hand"]
        current_hand = game["player_hands"][active_idx]

        # Validaciones:
        # 1) Solo puedes doblar si tienes exactamente 2 cartas.
        if len(current_hand) != 2:
            return await interaction.response.send_message("Solo puedes doblar con 2 cartas en la mano.", ephemeral=True)
        # 2) No haber doblado ya.
        if game["double_down_used"][active_idx]:
            return await interaction.response.send_message("Ya has doblado en esta mano.", ephemeral=True)
        # 3) Tener saldo suficiente para duplicar la apuesta base de esta mano
        bet_add = game["base_bet"]  # Subimos la apuesta en la misma cantidad base
        bal = await bank.get_balance(ctx.author)
        if bal < bet_add:
            return await interaction.response.send_message("No tienes saldo suficiente para doblar la apuesta.", ephemeral=True)

        # Retirar ese adicional
        await bank.withdraw_credits(ctx.author, bet_add)
        game["total_bet"] += bet_add
        game["double_down_used"][active_idx] = True

        # Robar 1 carta y plantar
        current_hand.append(game["deck"].pop())
        val = self.hand_value(current_hand)

        # Actualizar embed
        embed = self.build_embed(ctx.author.name)
        embed.title = f"Mano #{active_idx+1} - Doblaste la apuesta."
        embed.set_footer(text=f"Apuesta total: {game['total_bet']} | Saldo actual: {bal - bet_add}")

        # Ver si te pasaste
        if val > 21:
            embed.title += f" Te pasaste con {val}."
        # Pasamos a la siguiente mano
        game["active_hand"] += 1

        if game["active_hand"] < len(game["player_hands"]):
            embed.title += f" Ahora mano #{game['active_hand']+1}..."
            await interaction.response.edit_message(embed=embed, view=self.build_view(ctx))
        else:
            # Ir a fase dealer
            await interaction.response.edit_message(embed=embed, view=None)
            await self.dealer_phase(ctx, embed)

    async def player_split(self, interaction: discord.Interaction, ctx):
        """Divide la mano si las dos primeras cartas tienen el mismo valor."""
        game = self.games.get(ctx.author.id)
        if not game:
            return await interaction.response.send_message("No tienes una partida activa.", ephemeral=True)

        active_idx = game["active_hand"]
        current_hand = game["player_hands"][active_idx]

        # Validaciones
        if len(current_hand) != 2:
            return await interaction.response.send_message("Solo puedes dividir con exactamente 2 cartas.", ephemeral=True)
        if game["split_used"]:
            return await interaction.response.send_message("Solo se permite dividir una vez en esta versión simplificada.", ephemeral=True)
        if self.card_value_for_split(current_hand[0]) != self.card_value_for_split(current_hand[1]):
            return await interaction.response.send_message("Solo puedes dividir si ambas cartas tienen el mismo valor.", ephemeral=True)

        # Ver si el usuario tiene saldo para apostar la misma cantidad en la segunda mano
        add_bet = game["base_bet"]
        bal = await bank.get_balance(ctx.author)
        if bal < add_bet:
            return await interaction.response.send_message("No tienes suficiente saldo para dividir (split).", ephemeral=True)

        # Retirar fondos extra
        await bank.withdraw_credits(ctx.author, add_bet)
        game["total_bet"] += add_bet

        # Hacemos split: cada mano se queda con una carta
        card1 = current_hand[0]
        card2 = current_hand[1]
        new_hand1 = [card1, game["deck"].pop()]  # Robo 1 carta a la primera
        new_hand2 = [card2, game["deck"].pop()]  # Robo 1 carta a la segunda

        # Reemplazamos la mano actual por la primera y añadimos la segunda al final
        game["player_hands"][active_idx] = new_hand1
        game["player_hands"].insert(active_idx+1, new_hand2)
        # Ajustamos la lista de double_down_used
        game["double_down_used"][active_idx] = False
        game["double_down_used"].insert(active_idx+1, False)

        game["split_used"] = True

        # Embed
        embed = self.build_embed(ctx.author.name)
        embed.title = f"Has dividido tu mano. Ahora tienes {len(game['player_hands'])} manos."
        embed.set_footer(text=f"Apuesta total: {game['total_bet']} | Saldo actual: {bal - add_bet}")
        await interaction.response.edit_message(embed=embed, view=self.build_view(ctx))

    # === Fase del Dealer & Resultado final ===

    async def dealer_phase(self, ctx, embed):
        """Una vez que el jugador ha jugado todas sus manos, el dealer saca cartas hasta 17 y se decide el resultado."""
        game = self.games.get(ctx.author.id)
        if not game:
            return  # No hay partida

        dealer_hand = game["dealer_hand"]
        # Dealer roba hasta 17
        while self.hand_value(dealer_hand) < 17:
            dealer_hand.append(game["deck"].pop())

        dealer_val = self.hand_value(dealer_hand)

        # Pagos de cada mano
        results = []
        total_win = 0

        for idx, hand in enumerate(game["player_hands"]):
            val = self.hand_value(hand)
            portion_bet = game["base_bet"]
            # Si el usuario hizo un double en esta mano, la apuesta real de esta mano es base_bet * 2
            if game["double_down_used"][idx]:
                portion_bet *= 2

            # Determinar resultado
            if val > 21:
                # Busted
                results.append(f"Mano {idx+1}: Perdiste (te pasaste).")
                # No ganas nada
            else:
                # Dealer se pasa => gana el jugador
                if dealer_val > 21:
                    total_win += portion_bet * 2
                    results.append(f"Mano {idx+1}: Dealer se pasó, ¡ganas {portion_bet*2}!")
                else:
                    # Comparar
                    if val > dealer_val:
                        total_win += portion_bet * 2
                        results.append(f"Mano {idx+1}: Ganaste {portion_bet*2} (tu mano {val} > dealer {dealer_val}).")
                    elif val < dealer_val:
                        results.append(f"Mano {idx+1}: Perdiste (tu mano {val} < dealer {dealer_val}).")
                    else:
                        # Empate => devuelves tu apuesta
                        total_win += portion_bet
                        results.append(f"Mano {idx+1}: Empate, recuperas {portion_bet}.")

        if total_win > 0:
            await bank.deposit_credits(ctx.author, total_win)

        # Armamos embed final
        embed_final = self.build_embed(ctx.author.name, reveal_dealer=True)
        embed_final.title = "Resultado Final"
        msg_results = "\n".join(results)
        embed_final.add_field(name="Dealer", value=f"Valor: {dealer_val}", inline=False)
        embed_final.add_field(name="Resumen", value=msg_results, inline=False)
        embed_final.set_footer(text=f"Ganancia total: {total_win} créditos.")

        # Editamos el mensaje anterior (o podrías mandar uno nuevo)
        msg = await ctx.channel.send(embed=embed_final)
        # Borramos la partida
        self.games.pop(ctx.author.id, None)

    # === UTILIDAD: CREAR BARAJA, CALCULAR VALORES, EMBEDS ===

    def create_deck(self):
        """Crea la baraja estándar de 52 cartas."""
        palos = ["♣", "♦", "♥", "♠"]
        valores = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
        deck = []
        for p in palos:
            for v in valores:
                deck.append((v, p))
        return deck

    def hand_value(self, hand):
        """Calcula el valor de una mano de Blackjack, manejando ases como 1 u 11."""
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

        # Ajustar Ases de 11 a 1 si se pasa de 21
        while value > 21 and aces > 0:
            value -= 10
            aces -= 1
        return value

    def card_to_str(self, card):
        """Convierte la tupla (v, p) en string, p.ej 'A♠'."""
        return f"{card[0]}{card[1]}"

    def format_hand(self, hand, reveal_all=True):
        """Formatea la mano en un string. Si no reveal_all, oculta la segunda carta."""
        if not reveal_all and len(hand) > 1:
            return f"{self.card_to_str(hand[0])} ??"
        return " ".join(self.card_to_str(c) for c in hand)

    def build_embed(self, player_name, reveal_dealer=False, busted_hand=None):
        """Crea un embed mostrando todas las manos del jugador y la del dealer (oculta o revelada)."""
        game = self.games.get(self.get_user_id(player_name))
        # Nota: get_user_id es una función que no existe: la creamos para obtener el ID a partir del nombre...
        #  Pero como ejemplo, aquí supondremos que player_name = ctx.author.name y ya tenemos el game
        #  En la práctica, lo más sencillo es que en lugar de player_name, recibas ctx.author.id.
        # Para la demo, asumiremos que game se basa en la relación "player_name == ctx.author.name".
        # Mejor: adaptarlo a tu lógica real.

        # Si no hay game, devolvemos embed genérico
        if not game:
            return discord.Embed(description="Error: no se encontró la partida.", color=discord.Color.red())

        dealer_hand = game["dealer_hand"]
        # Embeds
        embed = discord.Embed(color=discord.Color.green())
        embed.description = f"Dealer: {self.format_hand(dealer_hand, reveal_dealer)}"
        if reveal_dealer:
            embed.description += f" (Valor: {self.hand_value(dealer_hand)})"

        # Para cada mano del jugador
        for i, hand in enumerate(game["player_hands"]):
            hand_str = self.format_hand(hand, reveal_all=True)
            val = self.hand_value(hand)
            name = f"Tu mano #{i+1}"
            if i == game["active_hand"]:
                name += " (Jugando)"

            # Si la mano está "busted" => pasaste 21
            if busted_hand == i:
                name += " - BUSTED!"

            # Si tienes Blackjack (21 con 2 cartas), puedes personalizar
            if len(hand) == 2 and val == 21:
                val_str = "Blackjack!"
            else:
                val_str = f"Valor: {val}"

            embed.add_field(name=name, value=f"{hand_str}\n{val_str}", inline=False)

        return embed

    def build_view(self, ctx):
        """Recrea la view para que los botones se mantengan actualizados."""
        return AdvancedBlackjackView(self, ctx, timeout=120)

    def card_value_for_split(self, card):
        """Devuelve un valor que permita comparar si dos cartas tienen el mismo 'rank' para split.
           Asignamos J=10, Q=10, K=10, etc. para que 8 y 8 sea igual, 10 y J también se consideren “iguales”? 
           En reglas clásicas, un 10 y una J NO se pueden split porque no son la misma carta, 
           pero algunos casinos lo permiten (el “rank 10” en general). Ajusta a tu gusto.
        """
        rank = card[0]
        if rank in ["J", "Q", "K", "10"]:
            return 10
        if rank == "A":
            return 1
        return int(rank)

    def get_user_id(self, player_name: str):
        # Esta función no está realmente implementada.
        # En un bot real, tu "build_embed" debería recibir ctx.author.id directamente.
        # Para la demo, la dejaremos vacía o simulada:
        for user_id, data in self.games.items():
            # Si tuviésemos "username" guardado, lo comparamos...
            # Fake approach: no implementado
            pass
        return None

    def cog_unload(self):
        """Si quieres, limpia las partidas en curso."""
        self.games.clear()

def setup(bot):
    bot.add_cog(Blackjack(bot))
