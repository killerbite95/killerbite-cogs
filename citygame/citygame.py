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

import logging

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
            "jail_time": 0,
            "properties": [],
            "inventory": [],
            "daily_mission": None,
            "daily_mission_completed": False,
        }
        self.config.register_member(**default_member)
        default_guild = {
            "leaderboard": {},
            "economy_multiplier": 1.0,
            "items": {},
        }
        self.config.register_guild(**default_guild)
        self.translations_cache = {}
        self.asset_path = os.path.join(os.path.dirname(__file__), 'assets')
        self.jail_check.start()

    def cog_unload(self):
        """Se llama cuando el cog se descarga."""
        self.jail_check.cancel()

    @commands.group(name="juego", aliases=["game"], invoke_without_command=True)
    async def juego(self, ctx):
        """Comando principal para Ciudad Virtual.

        Muestra el mensaje de ayuda con todos los comandos disponibles.
        """
        try:
            translations = await get_translations(self, ctx.author)
            help_text = safe_get_translation(translations, "help_text")
            embed = discord.Embed(
                title=safe_get_translation(translations, "help_title"),
                description=help_text,
                color=discord.Color.blue()
            )
            image_filename = 'ciudad_virtual_bienvenida.png'
            await send_embed_with_image(ctx, embed, image_filename, self.asset_path)
        except KeyError as e:
            log.error(f"Clave de traducción faltante en 'juego': {e}")
            await ctx.send(f"Error en las traducciones: {e}")
        except Exception as e:
            log.exception(f"Error inesperado en 'juego': {e}")
            await ctx.send("Ha ocurrido un error. Inténtalo más tarde.")

    @juego.command(name="establecer_idioma", aliases=["set_language"])
    async def establecer_idioma(self, ctx, language: str):
        """Establece tu idioma preferido.

        Args:
            language: El código del idioma ('es' o 'en').
        """
        member = ctx.author
        supported_languages = ['es', 'en']
        language = language.lower()

        if language not in supported_languages:
            await ctx.send(
                f"El idioma '{language}' no es compatible. "
                f"Idiomas disponibles: {', '.join(supported_languages)}."
            )
            return

        await self.config.member(member).language.set(language)
        translations = await get_translations(self, member)
        await ctx.send(
            safe_get_translation(translations, "language_set").format(language=language)
        )

    @juego.command(name="elegir_rol", aliases=["choose_role"])
    @language_set_required()
    async def elegir_rol(self, ctx, rol: str):
        """Elige tu rol en el juego: mafia, civil o policía.

        Args:
            rol: El rol que el usuario desea elegir.
        """
        try:
            member = ctx.author
            translations = await get_translations(self, member)
            valid_role = validate_role(rol)
            if not valid_role:
                await ctx.send(safe_get_translation(translations, "role_invalid"))
                return
            await self.config.member(member).role.set(valid_role)
            image_filename = f'rol_{valid_role}.png'
            embed = discord.Embed(
                description=safe_get_translation(translations, "role_selected").format(role=valid_role),
                color=discord.Color.green()
            )
            await send_embed_with_image(ctx, embed, image_filename, self.asset_path)
            await ctx.message.add_reaction("✅")
        except KeyError as e:
            log.error(f"Clave de traducción faltante en 'elegir_rol': {e}")
            await ctx.send(f"Error en las traducciones: {e}")
        except Exception as e:
            log.exception(f"Error inesperado en 'elegir_rol': {e}")
            await ctx.send("Ha ocurrido un error. Inténtalo más tarde.")

    @juego.command(name="accion", aliases=["action"])
    @commands.cooldown(1, 60, commands.BucketType.user)
    @language_set_required()
    async def accion(self, ctx):
        """Realiza una acción dependiendo de tu rol, gana experiencia y monedas.

        Este comando tiene un cooldown de 60 segundos por usuario.
        """
        try:
            member = ctx.author
            member_config = self.config.member(member)
            translations = await get_translations(self, member)
            role = await member_config.role()
            jail_time = await member_config.jail_time()
            if jail_time > 0:
                embed = discord.Embed(
                    title=safe_get_translation(translations, "in_jail_title"),
                    description=safe_get_translation(translations, "in_jail").format(time=jail_time),
                    color=discord.Color.dark_gray()
                )
                image_filename = 'en_carcel.png'
                await send_embed_with_image(ctx, embed, image_filename, self.asset_path)
                return
            if not role:
                await ctx.send(safe_get_translation(translations, "no_role"))
                return

            multiplier = await self.config.guild(ctx.guild).economy_multiplier()
            level_multiplier = await get_level_multiplier(self, member)
            earnings, xp_gain = 0, 0

            if role == 'mafia':
                earnings = random.randint(100, 200) * multiplier * level_multiplier
                xp_gain = random.randint(10, 20)
                event_chance = random.randint(1, 100)
                if event_chance <= 20:
                    await member_config.jail_time.set(3)
                    embed = discord.Embed(
                        title=safe_get_translation(translations, "caught_title"),
                        description=safe_get_translation(translations, "caught_by_police"),
                        color=discord.Color.red()
                    )
                    image_filename = 'en_carcel.png'
                    await send_embed_with_image(ctx, embed, image_filename, self.asset_path)
                    return
                await bank.deposit_credits(member, int(earnings))
                embed_color = discord.Color.red()
                action_desc = safe_get_translation(translations, "action_mafia").format(
                    earnings=int(earnings),
                    xp_gain=xp_gain
                )
                image_filename = 'accion_mafia.png'

            elif role == 'civil':
                earnings = random.randint(50, 150) * multiplier * level_multiplier
                xp_gain = random.randint(5, 15)
                await bank.deposit_credits(member, int(earnings))
                embed_color = discord.Color.green()
                action_desc = safe_get_translation(translations, "action_civilian").format(
                    earnings=int(earnings),
                    xp_gain=xp_gain
                )
                image_filename = 'accion_civil.png'

            elif role == 'policia':
                earnings = random.randint(80, 180) * multiplier * level_multiplier
                xp_gain = random.randint(8, 18)
                await bank.deposit_credits(member, int(earnings))
                embed_color = discord.Color.blue()
                action_desc = safe_get_translation(translations, "action_police").format(
                    earnings=int(earnings),
                    xp_gain=xp_gain
                )
                image_filename = 'accion_policia.png'

            else:
                await ctx.send(safe_get_translation(translations, "role_invalid"))
                return

            embed = discord.Embed(
                title=safe_get_translation(translations, "action_title"),
                description=action_desc,
                color=embed_color
            )
            await update_experience(self, member, xp_gain, translations)
            await send_embed_with_image(ctx, embed, image_filename, self.asset_path)
        except KeyError as e:
            log.error(f"Clave de traducción faltante en 'accion': {e}")
            await ctx.send(f"Error en las traducciones: {e}")
        except Exception as e:
            log.exception(f"Error inesperado en 'accion': {e}")
            await ctx.send("Ha ocurrido un error. Inténtalo más tarde.")

    @accion.error
    async def accion_error(self, ctx, error):
        """Maneja errores del comando accion, como el cooldown.

        Args:
            ctx: Contexto del comando.
            error: El error que ocurrió.
        """
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(
                f"Por favor, espera {int(error.retry_after)} "
                f"segundos antes de usar este comando nuevamente."
            )

    @juego.command(name="trabajar", aliases=["work"])
    @commands.cooldown(1, 3600, commands.BucketType.user)
    @language_set_required()
    async def trabajar(self, ctx):
        """Trabaja en tu profesión y gana dinero."""
        try:
            member = ctx.author
            member_config = self.config.member(member)
            translations = await get_translations(self, member)
            role = await member_config.role()
            if not role:
                await ctx.send(safe_get_translation(translations, "no_role"))
                return

            multiplier = await self.config.guild(ctx.guild).economy_multiplier()
            level_multiplier = await get_level_multiplier(self, member)
            earnings = random.randint(200, 400) * multiplier * level_multiplier
            xp_gain = random.randint(20, 40)
            await bank.deposit_credits(member, int(earnings))
            await update_experience(self, member, xp_gain, translations)

            embed = discord.Embed(
                title=safe_get_translation(translations, "work_title"),
                description=safe_get_translation(translations, "work_success").format(
                    earnings=int(earnings),
                    xp_gain=xp_gain
                ),
                color=discord.Color.gold()
            )
            image_filename = 'trabajar.png'
            await send_embed_with_image(ctx, embed, image_filename, self.asset_path)
        except KeyError as e:
            log.error(f"Clave de traducción faltante en 'trabajar': {e}")
            await ctx.send(f"Error en las traducciones: {e}")
        except Exception as e:
            log.exception(f"Error inesperado en 'trabajar': {e}")
            await ctx.send("Ha ocurrido un error. Inténtalo más tarde.")

    @trabajar.error
    async def trabajar_error(self, ctx, error):
        """Maneja errores del comando trabajar, como el cooldown."""
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(
                f"Por favor, espera {int(error.retry_after // 60)} "
                f"minutos antes de volver a trabajar."
            )

    @juego.command(name="mision_diaria", aliases=["daily_mission"])
    @language_set_required()
    async def mision_diaria(self, ctx):
        """Obtiene tu misión diaria."""
        try:
            member = ctx.author
            member_config = self.config.member(member)
            translations = await get_translations(self, member)
            daily_mission = await member_config.daily_mission()
            daily_completed = await member_config.daily_mission_completed()

            if daily_completed:
                await ctx.send(safe_get_translation(translations, "daily_mission_completed"))
                return

            if daily_mission:
                await ctx.send(safe_get_translation(translations, "daily_mission_in_progress").format(
                    mission=daily_mission))
                return

            # Generar una nueva misión diaria
            missions = safe_get_translation(translations, "daily_missions")
            mission = random.choice(missions)
            await member_config.daily_mission.set(mission)
            await ctx.send(safe_get_translation(translations, "daily_mission_assigned").format(
                mission=mission))
        except KeyError as e:
            log.error(f"Clave de traducción faltante en 'mision_diaria': {e}")
            await ctx.send(f"Error en las traducciones: {e}")
        except Exception as e:
            log.exception(f"Error inesperado en 'mision_diaria': {e}")
            await ctx.send("Ha ocurrido un error. Inténtalo más tarde.")

    @juego.command(name="logros", aliases=["achievements"])
    @language_set_required()
    async def logros(self, ctx):
        """Muestra tus logros obtenidos."""
        try:
            member = ctx.author
            member_config = self.config.member(member)
            achievements = await member_config.achievements()
            translations = await get_translations(self, member)

            if not achievements:
                await ctx.send(safe_get_translation(translations, "no_achievements"))
                return

            achievements_text = "\n".join(achievements)
            embed = discord.Embed(
                title=safe_get_translation(translations, "achievements_title"),
                description=achievements_text,
                color=discord.Color.purple()
            )
            await ctx.send(embed=embed)
        except KeyError as e:
            log.error(f"Clave de traducción faltante en 'logros': {e}")
            await ctx.send(f"Error en las traducciones: {e}")
        except Exception as e:
            log.exception(f"Error inesperado en 'logros': {e}")
            await ctx.send("Ha ocurrido un error. Inténtalo más tarde.")

    @juego.command(name="clasificacion", aliases=["leaderboard"])
    @language_set_required()
    async def clasificacion(self, ctx):
        """Muestra la clasificación de jugadores."""
        try:
            guild_members = await self.config.all_members(ctx.guild)
            translations = await get_translations(self, ctx.author)

            leaderboard = []
            for member_id, data in guild_members.items():
                member = ctx.guild.get_member(member_id)
                if member:
                    level = data.get("level", 1)
                    xp = data.get("xp", 0)
                    leaderboard.append((member.name, level, xp))

            if not leaderboard:
                await ctx.send(safe_get_translation(translations, "no_leaderboard_data"))
                return

            # Ordenar por nivel y experiencia
            leaderboard.sort(key=lambda x: (x[1], x[2]), reverse=True)
            leaderboard_text = ""
            for idx, (name, level, xp) in enumerate(leaderboard[:10], start=1):
                leaderboard_text += f"{idx}. {name} - Nivel {level}, XP {xp}\n"

            embed = discord.Embed(
                title=safe_get_translation(translations, "leaderboard_title"),
                description=leaderboard_text,
                color=discord.Color.dark_gold()
            )
            await ctx.send(embed=embed)
        except KeyError as e:
            log.error(f"Clave de traducción faltante en 'clasificacion': {e}")
            await ctx.send(f"Error en las traducciones: {e}")
        except Exception as e:
            log.exception(f"Error inesperado en 'clasificacion': {e}")
            await ctx.send("Ha ocurrido un error. Inténtalo más tarde.")

    @juego.command(name="desafiar", aliases=["challenge"])
    @language_set_required()
    async def desafiar(self, ctx, opponent: discord.Member):
        """Desafía a otro jugador.

        Args:
            opponent: El miembro al que deseas desafiar.
        """
        try:
            member = ctx.author
            if opponent.bot or opponent == member:
                await ctx.send("No puedes desafiar a este usuario.")
                return

            member_level = await self.config.member(member).level()
            opponent_level = await self.config.member(opponent).level()

            if member_level < opponent_level:
                winner = opponent
            else:
                winner = member

            translations = await get_translations(self, member)
            await ctx.send(safe_get_translation(translations, "challenge_result").format(
                winner=winner.display_name
            ))

            # Otorgar recompensa al ganador
            reward = 100 * await get_level_multiplier(self, winner)
            await bank.deposit_credits(winner, int(reward))
        except KeyError as e:
            log.error(f"Clave de traducción faltante en 'desafiar': {e}")
            await ctx.send(f"Error en las traducciones: {e}")
        except Exception as e:
            log.exception(f"Error inesperado en 'desafiar': {e}")
            await ctx.send("Ha ocurrido un error. Inténtalo más tarde.")

    @juego.command(name="comprar", aliases=["buy"])
    @language_set_required()
    async def comprar(self, ctx, item_name: str):
        """Compra un objeto de la tienda.

        Args:
            item_name: El nombre del objeto que deseas comprar.
        """
        try:
            member = ctx.author
            translations = await get_translations(self, member)
            guild_items = await self.config.guild(ctx.guild).items()
            item = guild_items.get(item_name.lower())

            if not item:
                await ctx.send(safe_get_translation(translations, "item_not_found"))
                return

            price = item.get("price")
            if not await bank.can_spend(member, price):
                await ctx.send(safe_get_translation(translations, "not_enough_money"))
                return

            await bank.withdraw_credits(member, price)
            member_inventory = await self.config.member(member).inventory()
            member_inventory.append(item_name)
            await self.config.member(member).inventory.set(member_inventory)
            await ctx.send(safe_get_translation(translations, "item_purchased").format(item=item_name))
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
            member_inventory = await self.config.member(member).inventory()
            translations = await get_translations(self, member)

            if not member_inventory:
                await ctx.send(safe_get_translation(translations, "inventory_empty"))
                return

            inventory_text = "\n".join(member_inventory)
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

    @tasks.loop(minutes=1)
    async def jail_check(self):
        """Tarea en segundo plano que reduce el tiempo en la cárcel de los usuarios.

        Se ejecuta cada minuto.
        """
        all_members = await self.config.all_members()
        for guild_id, members in all_members.items():
            for member_id, data in members.items():
                jail_time = data.get("jail_time", 0)
                if jail_time > 0:
                    jail_time -= 1
                    user = self.bot.get_user(member_id)
                    if jail_time == 0 and user:
                        translations = await get_translations(self, user)
                        embed = discord.Embed(
                            title=safe_get_translation(translations, "released_title"),
                            description=safe_get_translation(translations, "released_from_jail"),
                            color=discord.Color.green()
                        )
                        image_filename = 'liberado.png'
                        try:
                            await user.send(
                                embed=embed,
                                file=discord.File(
                                    os.path.join(self.asset_path, image_filename),
                                    filename=image_filename
                                )
                            )
                        except FileNotFoundError:
                            await user.send(embed=embed)
                    await self.config.member_from_ids(guild_id, member_id).jail_time.set(jail_time)

    @jail_check.before_loop
    async def before_jail_check(self):
        """Espera a que el bot esté listo antes de iniciar la tarea."""
        await self.bot.wait_until_ready()
