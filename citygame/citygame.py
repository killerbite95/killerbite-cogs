# citygame.py

from redbot.core import commands, Config, bank, checks
from redbot.core.bot import Red
import discord
import random
import os
from discord.ext import tasks

from .utils.helpers import (
    get_translations,
    get_asset,
    update_experience,
    validate_role,
    get_language,
    send_embed_with_image,
    safe_get_translation,
    language_set_required,
    get_level_multiplier,
)
from .utils.items import ITEMS  # Importar los objetos

import logging
import asyncio
import datetime

log = logging.getLogger("red.citygame")

BaseCog = getattr(commands, "Cog", object)

class CiudadVirtual(commands.Cog):
    """Un juego de roles donde los usuarios pueden ser mafia, civil o policía."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_member = {
            "role": None,
            "achievements": [],
            "level": 1,
            "xp": 0,
            "language": None,
            "skills": {},
            "jail_time": None,  # Almacenar como timestamp
            "properties": [],
            "inventory": [],
            "daily_mission": None,
            "daily_mission_completed": False,
        }
        self.config.register_member(**default_member)
        
        # Convertir la lista de ITEMS a un diccionario para facilitar el acceso
        default_items = {item["name_key"]: {"price": item["price"], "description_key": item["description_key"], "roles": item["roles"]} for item in ITEMS}
        
        default_guild = {
            "leaderboard": {},
            "economy_multiplier": 1.0,
            "items": default_items,
        }
        self.config.register_guild(**default_guild)
        self.translations_cache = {}
        self.asset_path = os.path.join(os.path.dirname(__file__), 'assets')
        self.jail_check.start()

    def cog_unload(self):
        """Se llama cuando el cog se descarga."""
        self.jail_check.cancel()

    @tasks.loop(seconds=60)
    async def jail_check(self):
        """Verifica periódicamente si los usuarios deben ser liberados de la cárcel."""
        now = datetime.datetime.utcnow().timestamp()
        async with self.config.all_guilds() as guilds:
            for guild_id, guild_data in guilds.items():
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    continue
                members = guild.members
                for member in members:
                    jail_time = await self.config.member(member).jail_time()
                    if jail_time and jail_time <= now:
                        await self.config.member(member).jail_time.set(None)
                        # Enviar mensaje de liberación
                        try:
                            await member.send(safe_get_translation(await get_translations(self, member), "liberado_jail"))
                        except discord.Forbidden:
                            pass  # No se pudo enviar mensaje al usuario

    @juego.command(name="elegir_rol", aliases=["choose_role"])
    async def elegir_rol(self, ctx, role: str):
        """Permite al usuario elegir su rol en el juego.

        Args:
            role: El rol que desea elegir ('mafia', 'policia', 'civil').
        """
        try:
            member = ctx.author
            translations = await get_translations(self, member)
            validated_role = validate_role(role)

            if not validated_role:
                await ctx.send(safe_get_translation(translations, "role_invalid"))
                return

            await self.config.member(member).role.set(validated_role)
            await ctx.send(safe_get_translation(translations, "role_selected").format(role=validated_role.capitalize()))
        except KeyError as e:
            log.error(f"Clave de traducción faltante en 'elegir_rol': {e}")
            await ctx.send(f"Error en las traducciones: {e}")
        except Exception as e:
            log.exception(f"Error inesperado en 'elegir_rol': {e}")
            await ctx.send("Ha ocurrido un error. Inténtalo más tarde.")

    @juego.command(name="comprar", aliases=["buy"])
    @language_set_required()
    async def comprar(self, ctx, *, item_name: str):
        """Compra un objeto de la tienda.

        Args:
            item_name: El nombre del objeto que deseas comprar.
        """
        try:
            member = ctx.author
            guild = ctx.guild
            translations = await get_translations(self, member)
            guild_items = await self.config.guild(guild).items()
            item_key = item_name.lower()
            item = guild_items.get(item_key)

            if not item:
                await ctx.send(safe_get_translation(translations, "item_not_found"))
                return

            price = item.get("price", 50)
            description_key = item.get("description_key", "")
            roles_allowed = item.get("roles", [])

            # Verificar si el objeto es permitido para el rol del usuario
            user_role = await self.config.member(member).role()
            if user_role not in roles_allowed:
                await ctx.send(safe_get_translation(translations, "item_not_allowed").format(item=item_name.capitalize(), role=user_role))
                return

            # Definir ítems únicos o limitados
            unique_items = ["item_contraseña_secreta"]  # Usar name_key
            max_quantity = 1

            member_inventory = await self.config.member(member).inventory()
            if item_key in unique_items:
                if member_inventory.count(item_key) >= max_quantity:
                    await ctx.send(safe_get_translation(translations, "item_limit_reached").format(item=item_name.capitalize()))
                    return

            if not await bank.can_spend(member, price):
                await ctx.send(safe_get_translation(translations, "not_enough_money"))
                return

            await bank.withdraw_credits(member, price)
            member_inventory.append(item_key)
            await self.config.member(member).inventory.set(member_inventory)
            await ctx.send(safe_get_translation(translations, "item_purchased").format(item=item_name.capitalize()))
        except KeyError as e:
            log.error(f"Clave de traducción faltante en 'comprar': {e}")
            await ctx.send(f"Error en las traducciones: {e}")
        except Exception as e:
            log.exception(f"Error inesperado en 'comprar': {e}")
            await ctx.send("Ha ocurrido un error. Inténtalo más tarde.")

    @juego.command(name="inventario", aliases=["inventory"])
    @language_set_required()
    async def inventario(self, ctx):
        """Muestra tu inventario."""
        try:
            member = ctx.author
            guild = ctx.guild
            member_inventory = await self.config.member(member).inventory()
            translations = await get_translations(self, member)

            if not member_inventory:
                await ctx.send(safe_get_translation(translations, "inventory_empty"))
                return

            guild_items = await self.config.guild(guild).items()
            inventory_dict = {}
            for item in member_inventory:
                inventory_dict[item] = inventory_dict.get(item, 0) + 1  # Contar la cantidad de cada ítem

            inventory_text = ""
            for item, quantity in inventory_dict.items():
                item_info = guild_items.get(item, {})
                name_key = item_info.get("name_key", "item_unknown")
                description_key = item_info.get("description_key", "item_unknown_desc")
                translated_name = safe_get_translation(translations, name_key)
                translated_description = safe_get_translation(translations, description_key)
                inventory_text += f"**{translated_name}** x{quantity}: {translated_description}\n"

            embed = discord.Embed(
                title=safe_get_translation(translations, "inventory_title"),
                description=inventory_text,
                color=discord.Color.teal()
            )
            await ctx.send(embed=embed)
        except KeyError as e:
            log.error(f"Clave de traducción faltante en 'inventario': {e}")
            await ctx.send(f"Error en las traducciones: {e}")
        except Exception as e:
            log.exception(f"Error inesperado en 'inventario': {e}")
            await ctx.send("Ha ocurrido un error. Inténtalo más tarde.")

    @juego.command(name="trabajar", aliases=["work"])
    @language_set_required()
    async def trabajar(self, ctx):
        """Permite al usuario trabajar para ganar monedas."""
        try:
            member = ctx.author
            guild = ctx.guild
            translations = await get_translations(self, member)
            user_role = await self.config.member(member).role()
            member_inventory = await self.config.member(member).inventory()
            guild_items = await self.config.guild(guild).items()

            base_earnings = random.randint(100, 200)
            multiplier = 1.0

            # Aplicar efectos pasivos de los objetos
            if "item_herramientas_robo" in member_inventory and user_role == "mafia":
                multiplier += 0.5  # 50% de aumento
            if "item_kit_supervivencia" in member_inventory and user_role == "civil":
                multiplier += 0.3  # 30% de aumento

            earnings = int(base_earnings * multiplier)
            await bank.deposit_credits(member, earnings)

            await ctx.send(safe_get_translation(translations, "trabajar_realizado").format(earnings=earnings))
        except KeyError as e:
            log.error(f"Clave de traducción faltante en 'trabajar': {e}")
            await ctx.send(f"Error en las traducciones: {e}")
        except Exception as e:
            log.exception(f"Error inesperado en 'trabajar': {e}")
            await ctx.send("Ha ocurrido un error. Inténtalo más tarde.")

    @juego.command(name="accion", aliases=["action"])
    @language_set_required()
    async def accion(self, ctx):
        """Permite al usuario realizar una acción según su rol."""
        try:
            member = ctx.author
            guild = ctx.guild
            translations = await get_translations(self, member)
            user_role = await self.config.member(member).role()
            member_inventory = await self.config.member(member).inventory()
            guild_items = await self.config.guild(guild).items()

            if not user_role:
                await ctx.send(safe_get_translation(translations, "role_not_set"))
                return

            if user_role == "mafia":
                # Realizar acción de mafia
                base_earnings = random.randint(200, 400)
                multiplier = 1.0

                # Aplicar efectos pasivos de los objetos
                if "item_herramientas_robo" in member_inventory:
                    multiplier += 0.5  # 50% de aumento
                if "item_camuflaje" in member_inventory:
                    # Reducir la probabilidad de ser detectado (ejemplo)
                    pass  # Implementar lógica de camuflaje

                earnings = int(base_earnings * multiplier)
                await bank.deposit_credits(member, earnings)

                await ctx.send(safe_get_translation(translations, "accion_mafia_realizada").format(earnings=earnings))
            
            elif user_role == "policia":
                # Realizar acción de policía
                base_earnings = random.randint(150, 300)
                multiplier = 1.0

                # Aplicar efectos pasivos de los objetos
                if "item_uniform_policia" in member_inventory:
                    multiplier += 0.4  # 40% de aumento
                if "item_binoculares" in member_inventory:
                    # Implementar ventaja de binoculares (ejemplo)
                    pass  # Implementar lógica de binoculares

                earnings = int(base_earnings * multiplier)
                await bank.deposit_credits(member, earnings)

                await ctx.send(safe_get_translation(translations, "accion_policia_realizada").format(earnings=earnings))
            
            elif user_role == "civil":
                # Realizar acción de civil
                base_earnings = random.randint(80, 150)
                multiplier = 1.0

                # Aplicar efectos pasivos de los objetos
                if "item_kit_supervivencia" in member_inventory:
                    multiplier += 0.3  # 30% de aumento

                earnings = int(base_earnings * multiplier)
                await bank.deposit_credits(member, earnings)

                await ctx.send(safe_get_translation(translations, "accion_civil_realizada").format(earnings=earnings))
            
            else:
                await ctx.send(safe_get_translation(translations, "role_invalid_action"))
        except KeyError as e:
            log.error(f"Clave de traducción faltante en 'accion': {e}")
            await ctx.send(f"Error en las traducciones: {e}")
        except Exception as e:
            log.exception(f"Error inesperado en 'accion': {e}")
            await ctx.send("Ha ocurrido un error. Inténtalo más tarde.")

    @juego.group(name="admin", aliases=["administrativo"], invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def admin(self, ctx):
        """Comandos administrativos para gestionar el juego."""
        translations = await get_translations(self, ctx.author)
        await ctx.send(safe_get_translation(translations, "admin_help"))

    @admin.command(name="add_item", aliases=["añadir_objeto"])
    async def add_item(self, ctx, item_name: str, price: int, *, description: str, roles: str):
        """Añade un nuevo ítem a la tienda.

        Args:
            item_name: El nombre del ítem.
            price: El precio del ítem.
            description: La descripción del ítem.
            roles: Los roles que pueden usar el ítem, separados por comas (e.g., mafia,policia).
        """
        try:
            guild_items = await self.config.guild(ctx.guild).items()
            name_key = f"item_{item_name.lower().replace(' ', '_')}"
            description_key = f"{name_key}_desc"
            item_key = name_key

            if item_key in guild_items:
                await ctx.send(safe_get_translation(await get_translations(self, ctx.author), "item_already_exists"))
                return

            roles_list = [role.strip().lower() for role in roles.split(",")]

            guild_items[item_key] = {
                "price": price,
                "description_key": description_key,
                "roles": roles_list,
                "name_key": name_key  # Añadido para facilitar traducciones en el inventario
            }
            await self.config.guild(ctx.guild).items.set(guild_items)

            translations = await get_translations(self, ctx.author)
            await ctx.send(safe_get_translation(translations, "item_added").format(item=item_name.capitalize(), price=price))
        except KeyError as e:
            log.error(f"Clave de traducción faltante en 'add_item': {e}")
            await ctx.send(f"Error en las traducciones: {e}")
        except Exception as e:
            log.exception(f"Error inesperado en 'add_item': {e}")
            await ctx.send("Ha ocurrido un error. Inténtalo más tarde.")

    @admin.command(name="remove_item", aliases=["quitar_objeto"])
    async def remove_item(self, ctx, *, item_name: str):
        """Quita un ítem de la tienda.

        Args:
            item_name: El nombre del ítem.
        """
        try:
            guild_items = await self.config.guild(ctx.guild).items()
            name_key = f"item_{item_name.lower().replace(' ', '_')}"
            item_key = name_key

            if item_key not in guild_items:
                await ctx.send(safe_get_translation(await get_translations(self, ctx.author), "item_not_found"))
                return

            del guild_items[item_key]
            await self.config.guild(ctx.guild).items.set(guild_items)

            translations = await get_translations(self, ctx.author)
            await ctx.send(safe_get_translation(translations, "item_removed").format(item=item_name.capitalize()))
        except KeyError as e:
            log.error(f"Clave de traducción faltante en 'remove_item': {e}")
            await ctx.send(f"Error en las traducciones: {e}")
        except Exception as e:
            log.exception(f"Error inesperado en 'remove_item': {e}")
            await ctx.send("Ha ocurrido un error. Inténtalo más tarde.")

    @admin.command(name="update_item", aliases=["actualizar_objeto"])
    async def update_item(self, ctx, item_name: str, price: int = None, *, description: str = None):
        """Actualiza el precio y/o descripción de un ítem existente en la tienda.

        Args:
            item_name: El nombre del ítem.
            price: El nuevo precio del ítem (opcional).
            description: La nueva descripción del ítem (opcional).
        """
        try:
            guild_items = await self.config.guild(ctx.guild).items()
            name_key = f"item_{item_name.lower().replace(' ', '_')}"
            item_key = name_key

            if item_key not in guild_items:
                await ctx.send(safe_get_translation(await get_translations(self, ctx.author), "item_not_found"))
                return

            if price is not None:
                guild_items[item_key]["price"] = price
            if description is not None:
                guild_items[item_key]["description_key"] = f"{item_key}_desc"
                # Aquí, necesitarás añadir las traducciones correspondientes en los archivos de traducción.

            await self.config.guild(ctx.guild).items.set(guild_items)

            translations = await get_translations(self, ctx.author)
            await ctx.send(safe_get_translation(translations, "item_updated").format(item=item_name.capitalize()))
        except KeyError as e:
            log.error(f"Clave de traducción faltante en 'update_item': {e}")
            await ctx.send(f"Error en las traducciones: {e}")
        except Exception as e:
            log.exception(f"Error inesperado en 'update_item': {e}")
            await ctx.send("Ha ocurrido un error. Inténtalo más tarde.")

    @juego.command(name="set_language", aliases=["establecer_idioma"])
    async def set_language(self, ctx, language: str):
        """Establece el idioma preferido del usuario.

        Args:
            language: El idioma que deseas establecer ('en' o 'es').
        """
        try:
            member = ctx.author
            translations = await get_translations(self, member)
            if language.lower() not in ["en", "es"]:
                await ctx.send(safe_get_translation(translations, "language_invalid"))
                return

            await self.config.member(member).language.set(language.lower())
            await ctx.send(safe_get_translation(translations, "language_set").format(language=language.upper()))
        except KeyError as e:
            log.error(f"Clave de traducción faltante en 'set_language': {e}")
            await ctx.send(f"Error en las traducciones: {e}")
        except Exception as e:
            log.exception(f"Error inesperado en 'set_language': {e}")
            await ctx.send("Ha ocurrido un error. Inténtalo más tarde.")

    @juego.command(name="help", aliases=["ayuda"])
    async def help_command(self, ctx):
        """Muestra la ayuda del juego."""
        try:
            member = ctx.author
            translations = await get_translations(self, member)
            help_title = safe_get_translation(translations, "help_title")
            help_text = safe_get_translation(translations, "help_text")

            embed = discord.Embed(
                title=help_title,
                description=help_text,
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
        except KeyError as e:
            log.error(f"Clave de traducción faltante en 'help': {e}")
            await ctx.send(f"Error en las traducciones: {e}")
        except Exception as e:
            log.exception(f"Error inesperado en 'help': {e}")
            await ctx.send("Ha ocurrido un error. Inténtalo más tarde.")

    def cog_command_error(self, ctx, error):
        """Maneja los errores de los comandos del cog."""
        if isinstance(error, commands.MissingPermissions):
            return  # Puedes manejar este error si lo deseas
        log.error(f"Error en el comando {ctx.command}: {error}")
