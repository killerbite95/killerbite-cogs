import discord
from discord.ext import commands, tasks
from redbot.core import Config, checks
import requests

# Mapeo de colores de Trello a valores hex
COLOR_MAP = {
    "green": 0x2ECC71,
    "yellow": 0xF1C40F,
    "orange": 0xE67E22,
    "red": 0xE74C3C,
    "purple": 0x9B59B6,
    "blue": 0x3498DB,
    "sky": 0x87CEEB,
    "pink": 0xFFC0CB,
    "lime": 0x00FF00,
    None: 0x95A5A6,
    "null": 0x95A5A6
}


class TrelloCog(commands.Cog):
    """
    Cog avanzado para Trello, enfocado en un único tablero.
    Trackea las tareas por etiquetas y publica el estado en los canales correspondientes.
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1357924680, force_registration=True)
        default_global = {
            "api_key": None,
            "api_token": None,
            "board_id": None,
            "channels": {},  # Asociar canal por etiqueta, ej: "en progreso" -> canal_id
        }
        self.config.register_global(**default_global)
        self.track_trello_changes.start()

    # ========= Comandos de configuración =========

    @commands.command(name="settrello")
    @checks.admin()
    async def set_trello_creds(self, ctx, api_key: str, api_token: str):
        """
        Guarda las credenciales de Trello (API key y token).

        Ejemplo: !settrello MI_API_KEY MI_API_TOKEN
        """
        await self.config.api_key.set(api_key)
        await self.config.api_token.set(api_token)
        await ctx.send("Credenciales de Trello guardadas correctamente.")

    @commands.command(name="settrelloboard")
    @checks.admin()
    async def set_trello_board(self, ctx, board_id: str):
        """
        Establece el tablero (board_id) con el que quieres trabajar.
        Todos los comandos usarán este único tablero.

        Ejemplo: !settrelloboard 123abcXYZ
        """
        await self.config.board_id.set(board_id)
        await ctx.send(f"Board ID configurado a {board_id}.")

    @commands.command(name="setchannel")
    @checks.admin()
    async def set_channel(self, ctx, label: str, channel: discord.TextChannel):
        """
        Asocia un canal de Discord a una etiqueta de Trello.
        El canal se utilizará para publicar el estado de las tarjetas con esa etiqueta.

        Ejemplo: !setchannel "En Progreso" #progreso
        """
        async with self.config.channels() as channels:
            # Se guarda la etiqueta en minúsculas para evitar problemas de mayúsculas/minúsculas
            channels[label.lower()] = channel.id
        await ctx.send(f"Canal {channel.mention} configurado para la etiqueta '{label}'.")

    # ========= Comandos informativos =========

    @commands.command(name="trellolists")
    async def trello_lists(self, ctx):
        """
        Muestra las listas del tablero configurado (board_id).
        
        Uso: !trellolists
        """
        api_key = await self.config.api_key()
        api_token = await self.config.api_token()
        board_id = await self.config.board_id()

        if not api_key or not api_token:
            return await ctx.send("No hay credenciales de Trello configuradas. Usa !settrello.")
        if not board_id:
            return await ctx.send("No se ha configurado el board_id. Usa !settrelloboard.")

        # Llamada a la API de Trello para obtener las listas del tablero
        url = f"https://api.trello.com/1/boards/{board_id}/lists"
        params = {
            "key": api_key,
            "token": api_token,
            "fields": "id,name"
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
        except requests.RequestException as e:
            return await ctx.send(f"Error consultando Trello: {e}")

        lists_data = resp.json()
        if not isinstance(lists_data, list):
            return await ctx.send("No se encontraron listas o el board_id es inválido.")

        embed = discord.Embed(
            title="Listas del tablero",
            description="Listado de listas disponibles en el tablero",
            color=discord.Color.gold()
        )
        for lst in lists_data:
            embed.add_field(name=lst.get("name", "Sin nombre"), value=f"ID: {lst.get('id')}", inline=False)

        await ctx.send(embed=embed)

    @commands.command(name="trellocards")
    async def trello_cards(self, ctx, list_id: str = None):
        """
        Muestra las tarjetas del tablero, con filtrado por listas.
        
        Uso: !trellocards <list_id>
        Si no se pasa list_id, muestra todas las tarjetas de todas las listas.
        """
        api_key = await self.config.api_key()
        api_token = await self.config.api_token()
        board_id = await self.config.board_id()

        if not api_key or not api_token:
            return await ctx.send("No hay credenciales de Trello configuradas. Usa !settrello.")
        if not board_id:
            return await ctx.send("No se ha configurado el board_id. Usa !settrelloboard.")
        
        cards_data = []

        if list_id:
            # Obtener las tarjetas de la lista especificada
            url = f"https://api.trello.com/1/lists/{list_id}/cards"
            params = {
                "key": api_key,
                "token": api_token,
                "fields": "id,name,labels"
            }
            try:
                resp = requests.get(url, params=params, timeout=10)
                resp.raise_for_status()
                cards_data = resp.json()
            except requests.RequestException as e:
                return await ctx.send(f"Error consultando Trello: {e}")
        else:
            # Obtener todas las listas y luego todas sus tarjetas
            url = f"https://api.trello.com/1/boards/{board_id}/lists"
            params = {
                "key": api_key,
                "token": api_token,
                "fields": "id,name"
            }
            try:
                resp = requests.get(url, params=params, timeout=10)
                resp.raise_for_status()
            except requests.RequestException as e:
                return await ctx.send(f"Error consultando Trello: {e}")

            lists_data = resp.json()
            for lst in lists_data:
                lst_id = lst.get("id")
                if not lst_id:
                    continue
                url_cards = f"https://api.trello.com/1/lists/{lst_id}/cards"
                params_cards = {
                    "key": api_key,
                    "token": api_token,
                    "fields": "id,name,labels"
                }
                try:
                    resp_cards = requests.get(url_cards, params=params_cards, timeout=10)
                    resp_cards.raise_for_status()
                    cards_data += resp_cards.json()
                except requests.RequestException:
                    continue

        if not cards_data:
            return await ctx.send("No se encontraron tarjetas.")

        embed = discord.Embed(
            title="Tarjetas del tablero",
            description="Mostrando tarjetas" if list_id else "Mostrando todas las tarjetas",
            color=discord.Color.green()
        )
        for card in cards_data:
            # Extraemos los nombres de las etiquetas (si existen)
            etiquetas = card.get("labels", [])
            labels_text = ", ".join([lbl.get("name", "Sin nombre") for lbl in etiquetas]) if etiquetas else "Sin etiquetas"
            embed.add_field(name=card.get("name", "Sin nombre"), value=f"Etiquetas: {labels_text}", inline=False)

        await ctx.send(embed=embed)

    # ========= Trackeo de cambios de Trello =========

    @tasks.loop(minutes=10)
    async def track_trello_changes(self):
        """Verifica cambios en las tarjetas del tablero y publica en el canal correspondiente."""
        api_key = await self.config.api_key()
        api_token = await self.config.api_token()
        board_id = await self.config.board_id()

        if not api_key or not api_token or not board_id:
            return

        url = f"https://api.trello.com/1/boards/{board_id}/lists"
        params = {
            "key": api_key,
            "token": api_token,
            "fields": "id,name"
        }

        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
        except requests.RequestException:
            return

        lists_data = resp.json()
        for lst in lists_data:
            list_id = lst.get("id")
            if not list_id:
                continue

            # Obtenemos las tarjetas de la lista
            url_cards = f"https://api.trello.com/1/lists/{list_id}/cards"
            params_cards = {
                "key": api_key,
                "token": api_token,
                "fields": "id,name,labels"
            }
            try:
                resp_cards = requests.get(url_cards, params=params_cards, timeout=10)
                resp_cards.raise_for_status()
            except requests.RequestException:
                continue

            cards_data = resp_cards.json()

            # Recorremos las tarjetas y sus etiquetas para notificar cambios
            for card in cards_data:
                etiquetas = card.get("labels", [])
                for label in etiquetas:
                    label_name = label.get("name")
                    if not label_name:
                        continue

                    # Se busca el canal configurado para la etiqueta (usamos lower-case)
                    async with self.config.channels() as channels:
                        channel_id = channels.get(label_name.lower())
                    if not channel_id:
                        continue

                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        embed = discord.Embed(
                            title=f"Tarea actualizada: {card.get('name', 'Sin nombre')}",
                            description=f"Etiquetas: {', '.join([lbl.get('name', 'Sin nombre') for lbl in etiquetas])}",
                            color=COLOR_MAP.get(label.get("color"), 0x95A5A6)
                        )
                        embed.add_field(name="Estado", value=f"**{label_name}**", inline=True)
                        try:
                            await channel.send(embed=embed)
                        except Exception:
                            continue

    @track_trello_changes.before_loop
    async def before_track_trello_changes(self):
        """Espera a que el bot esté listo antes de iniciar el loop."""
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(TrelloCog(bot))
