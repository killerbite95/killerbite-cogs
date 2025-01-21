# trinifrases.py
# Cog para Red Discord Bot que gestiona frases personalizadas y un comando principal para enviar frases aleatorias.
# Incluye persistencia de datos utilizando la configuración integrada de Red y validaciones para evitar duplicados
# y IDs inexistentes. Todos los comandos son accesibles solo para usuarios con permisos de administrador.

import discord
from redbot.core import commands, Config, checks
import random

class TriniFrases(commands.Cog):
    """
    Este cog permite administrar y mostrar frases personalizadas de "Trini".
    """

    # Estructura de config por defecto.
    default_global = {
        "phrases_data": {
            "next_id": 1,
            "phrases": {}
        }
    }

    def __init__(self, bot):
        """
        Inicializa la configuración y el bot.
        """
        self.bot = bot
        # Usa un identifier único para tu config (un número grande para evitar colisiones con otros cogs).
        self.config = Config.get_conf(self, identifier=987654321, force_registration=True)
        # Registramos la configuración por defecto en global.
        self.config.register_global(**self.default_global)

    @commands.command()
    async def trini(self, ctx):
        """
        Envía una frase aleatoria de "Trini". 
        Si no hay frases disponibles, muestra un mensaje de aviso.
        """
        data = await self.config.phrases_data()
        phrases_dict = data["phrases"]

        # Si no hay frases, mostrar mensaje de aviso
        if not phrases_dict:
            return await ctx.send(
                "¡Ay, cariño, parece que no tengo nada que decir! "
                "Añade frases con !settrini add."
            )

        # Selecciona una frase aleatoria
        random_id = random.choice(list(phrases_dict.keys()))
        random_frase = phrases_dict[random_id]
        await ctx.send(random_frase)

    @commands.group()
    @checks.admin_or_permissions(administrator=True)
    async def settrini(self, ctx):
        """
        Grupo de comandos para administrar las frases de Trini.
        Solo administradores o usuarios con permiso de administrador.
        """
        if ctx.invoked_subcommand is None:
            await ctx.send("Comandos disponibles: add, list, remove. Uso: !settrini <subcomando>")

    @settrini.command(name="add")
    async def add_frase(self, ctx, *, frase: str):
        """
        Añade una frase nueva a la lista.
        Ejemplo: !settrini add Esta es una nueva frase.
        """
        data = await self.config.phrases_data()
        phrases_dict = data["phrases"]
        next_id = data["next_id"]

        # Verificamos si la frase ya existe (ignorando mayúsculas/minúsculas)
        for existing_frase in phrases_dict.values():
            if existing_frase.lower() == frase.lower():
                return await ctx.send("Esa frase ya está guardada, cariño. Intenta con otra.")

        # Asignamos la nueva frase a un ID único y actualizamos next_id
        phrases_dict[str(next_id)] = frase
        data["next_id"] += 1

        # Guardamos los cambios en la configuración
        await self.config.phrases_data.set(data)

        await ctx.send(f"Frase añadida con ID {next_id}: {frase}")

    @settrini.command(name="list")
    async def list_frases(self, ctx):
        """
        Muestra todas las frases guardadas junto con sus IDs.
        Ejemplo: !settrini list
        """
        data = await self.config.phrases_data()
        phrases_dict = data["phrases"]

        if not phrases_dict:
            return await ctx.send("No hay frases guardadas todavía.")

        # Construimos un mensaje con ID y frase en cada línea
        mensaje = "**Lista de frases guardadas:**\n"
        for frase_id, frase_texto in phrases_dict.items():
            mensaje += f"- **ID {frase_id}:** {frase_texto}\n"

        await ctx.send(mensaje)

    @settrini.command(name="remove")
    async def remove_frase(self, ctx, frase_id: str):
        """
        Elimina una frase específica usando su ID.
        Ejemplo: !settrini remove 1
        """
        data = await self.config.phrases_data()
        phrases_dict = data["phrases"]

        # Comprobamos si existe el ID
        if frase_id not in phrases_dict:
            return await ctx.send(
                "No encuentro ese ID, cariño. Verifica la lista con !settrini list."
            )

        # Eliminamos la frase
        frase_eliminada = phrases_dict.pop(frase_id)
        await self.config.phrases_data.set(data)

        await ctx.send(f"Frase con ID {frase_id} eliminada: {frase_eliminada}")


# Función esencial para que Red sepa cómo cargar este cog.
async def setup(bot):
    await bot.add_cog(TriniFrases(bot))
