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
    send_embed_with_image,  # Importamos la nueva función auxiliar
)

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
            "language": None,  # Ahora puede ser None para detectar idioma automáticamente
            "skills": {},
            "jail_time": 0,
            "properties": [],
        }
        self.config.register_member(**default_member)
        default_guild = {
            "leaderboard": {},
            "economy_multiplier": 1.0,
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
        translations = await get_translations(self, ctx.author)
        help_text = translations["help_text"]
        embed = discord.Embed(
            title=translations["help_title"],
            description=help_text,
            color=discord.Color.blue()
        )
        image_filename = 'ciudad_virtual_bienvenida.png'
        # Usamos la función auxiliar para enviar el embed
        await send_embed_with_image(ctx, embed, image_filename, self.asset_path)

    @juego.command(name="elegir_rol", aliases=["choose_role"])
    async def elegir_rol(self, ctx, rol: str):
        """Elige tu rol en el juego: mafia, civil o policía.

        Args:
            rol: El rol que el usuario desea elegir.
        """
        member = ctx.author
        translations = await get_translations(self, member)
        valid_role = validate_role(rol)
        if not valid_role:
            await ctx.send(translations["role_invalid"])
            return
        await self.config.member(member).role.set(valid_role)
        # Seleccionar imagen según el rol
        image_filename = f'rol_{valid_role}.png'
        embed = discord.Embed(
            description=translations["role_selected"].format(role=valid_role),
            color=discord.Color.green()
        )
        # Usamos la función auxiliar para enviar el embed
        await send_embed_with_image(ctx, embed, image_filename, self.asset_path)
        await ctx.message.add_reaction("✅")  # Añadir reacción de confirmación

    @juego.command(name="accion", aliases=["action"])
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def accion(self, ctx):
        """Realiza una acción dependiendo de tu rol, gana experiencia y monedas.

        Este comando tiene un cooldown de 60 segundos por usuario.
        """
        member = ctx.author
        member_config = self.config.member(member)
        translations = await get_translations(self, member)
        role = await member_config.role()
        jail_time = await member_config.jail_time()
        if jail_time > 0:
            embed = discord.Embed(
                title=translations["in_jail_title"],
                description=translations["in_jail"].format(time=jail_time),
                color=discord.Color.dark_gray()
            )
            image_filename = 'en_carcel.png'
            await send_embed_with_image(ctx, embed, image_filename, self.asset_path)
            return
        if not role:
            await ctx.send(translations["no_role"])
            return

        multiplier = await self.config.guild(ctx.guild).economy_multiplier()
        earnings, xp_gain = 0, 0

        # Determinar ganancias y experiencia según el rol
        if role == 'mafia':
            earnings = random.randint(100, 200) * multiplier
            xp_gain = random.randint(10, 20)
            event_chance = random.randint(1, 100)
            if event_chance <= 20:
                await member_config.jail_time.set(3)
                embed = discord.Embed(
                    title=translations["caught_title"],
                    description=translations["caught_by_police"],
                    color=discord.Color.red()
                )
                image_filename = 'en_carcel.png'
                await send_embed_with_image(ctx, embed, image_filename, self.asset_path)
                return
            await bank.deposit_credits(member, earnings)
            embed_color = discord.Color.red()
            action_desc = translations["action_mafia"].format(
                earnings=int(earnings),
                xp_gain=xp_gain
            )
            image_filename = 'accion_mafia.png'

        elif role == 'civil':
            earnings = random.randint(50, 150) * multiplier
            xp_gain = random.randint(5, 15)
            await bank.deposit_credits(member, earnings)
            embed_color = discord.Color.green()
            action_desc = translations["action_civilian"].format(
                earnings=int(earnings),
                xp_gain=xp_gain
            )
            image_filename = 'accion_civil.png'

        elif role == 'policia':
            earnings = random.randint(80, 180) * multiplier
            xp_gain = random.randint(8, 18)
            await bank.deposit_credits(member, earnings)
            embed_color = discord.Color.blue()
            action_desc = translations["action_police"].format(
                earnings=int(earnings),
                xp_gain=xp_gain
            )
            image_filename = 'accion_policia.png'

        else:
            await ctx.send(translations["role_invalid"])
            return

        # Crear y enviar el embed
        embed = discord.Embed(
            title=translations["action_title"],
            description=action_desc,
            color=embed_color
        )
        await update_experience(self, member, xp_gain, translations)
        # Usamos la función auxiliar para enviar el embed
        await send_embed_with_image(ctx, embed, image_filename, self.asset_path)

    @accion.error
    async def accion_error(self, ctx, error):
        """Maneja errores del comando accion, como el cooldown.

        Args:
            ctx: Contexto del comando.
            error: El error que ocurrió.
        """
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"Por favor, espera {int(error.retry_after)} segundos antes de usar este comando nuevamente.")

    # Implementación de otros comandos con modificaciones similares
    # Por ejemplo, el comando 'trabajar':

    @juego.command(name="trabajar", aliases=["work"])
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def trabajar(self, ctx):
        """Trabaja en tu profesión y gana dinero."""
        member = ctx.author
        member_config = self.config.member(member)
        translations = await get_translations(self, member)
        role = await member_config.role()
        if not role:
            await ctx.send(translations["no_role"])
            return

        multiplier = await self.config.guild(ctx.guild).economy_multiplier()
        earnings = random.randint(200, 400) * multiplier
        xp_gain = random.randint(20, 40)
        await bank.deposit_credits(member, earnings)
        await update_experience(self, member, xp_gain, translations)

        embed = discord.Embed(
            title=translations["work_title"],
            description=translations["work_success"].format(
                earnings=int(earnings),
                xp_gain=xp_gain
            ),
            color=discord.Color.gold()
        )
        image_filename = 'trabajar.png'
        await send_embed_with_image(ctx, embed, image_filename, self.asset_path)

    @trabajar.error
    async def trabajar_error(self, ctx, error):
        """Maneja errores del comando trabajar, como el cooldown."""
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"Por favor, espera {int(error.retry_after // 60)} minutos antes de volver a trabajar.")

    # Continua implementando los demás comandos siguiendo el mismo patrón...

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
                            title=translations["released_title"],
                            description=translations["released_from_jail"],
                            color=discord.Color.green()
                        )
                        image_filename = 'liberado.png'
                        try:
                            await user.send(embed=embed, file=discord.File(
                                os.path.join(self.asset_path, image_filename),
                                filename=image_filename
                            ))
                        except FileNotFoundError:
                            await user.send(embed=embed)
                    await self.config.member_from_ids(guild_id, member_id).jail_time.set(jail_time)

    @jail_check.before_loop
    async def before_jail_check(self):
        """Espera a que el bot esté listo antes de iniciar la tarea."""
        await self.bot.wait_until_ready()

    # Continúa con el resto del código...

def setup(bot: Red):
    bot.add_cog(CiudadVirtual(bot))
