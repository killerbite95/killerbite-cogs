import discord
import asyncio
import random
import string
from redbot.core import commands, Config, checks
from typing import Optional

class AdvancedCaptcha(commands.Cog):
    """Cog avanzado de Captcha con verificación automática al unirse y borrado controlado de mensajes.

    - El embed informativo se envía mediante el comando !setcaptchaembed y permanece fijo.
    - Al unirse, se envía un mensaje individual de desafío en el canal configurado.
    - Se registran los mensajes relacionados a cada proceso de captcha para poder borrarlos
      sin afectar otros procesos o el embed informativo.
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0xDEADBEEF, force_registration=True)
        default_guild = {
            "captcha_channel": None,          # ID del canal donde se enviarán los captchas
            "invite_link": None,              # Invitación para reingresar al servidor
            "verification_timeout": 5,        # Tiempo límite en minutos para completar el captcha (por defecto 5)
            "max_attempts": 5,                # Número máximo de intentos (por defecto 5)
            "bypass_list": [],                # Lista de usuarios exentos de captcha
            # Configuración del Embed informativo (no se borra)
            "embed_title": "Verificación Captcha",
            "embed_description": (
                "Para acceder al servidor, debes demostrar que eres humano completando el captcha."
            ),
            "embed_color": 0x3498DB,          # Color por defecto (azul)
            "embed_image": None               # Imagen grande en el embed (opcional)
        }
        self.config.register_guild(**default_guild)
        # Almacena las listas de mensajes de cada proceso: {user_id: [message, ...]}
        self.process_messages = {}

    # =========================================================================
    #                              EVENTOS
    # =========================================================================
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Al unirse un miembro, inicia su proceso de captcha (si hay canal configurado y no tiene bypass)."""
        guild = member.guild
        guild_config = await self.config.guild(guild).all()
        channel_id = guild_config["captcha_channel"]
        bypass_list = guild_config["bypass_list"]

        if not channel_id or member.id in bypass_list:
            return

        channel = guild.get_channel(channel_id)
        if not channel:
            return

        # Inicia el proceso de captcha para el miembro y crea su lista de mensajes
        self.process_messages[member.id] = []
        self.bot.loop.create_task(self.start_captcha_process(member, channel))

    # =========================================================================
    #                              PROCESO CAPTCHA
    # =========================================================================
    async def start_captcha_process(self, member: discord.Member, channel: discord.TextChannel):
        """Gestiona el proceso de captcha para un miembro, registrando sus mensajes."""
        guild = member.guild
        guild_config = await self.config.guild(guild).all()
        verification_timeout = guild_config["verification_timeout"]
        max_attempts = guild_config["max_attempts"]
        invite_link = guild_config["invite_link"]

        proc_msgs = self.process_messages.get(member.id, [])

        # Envía mensaje individual de captcha (sin el embed informativo)
        captcha_code = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
        try:
            challenge = await channel.send(
                f"{member.mention}, escribe el siguiente captcha para continuar:\n**{captcha_code}**"
            )
            proc_msgs.append(challenge)
        except discord.Forbidden:
            return

        time_limit = verification_timeout * 60  # convertir a segundos
        end_time = discord.utils.utcnow().timestamp() + time_limit
        attempts_left = max_attempts

        while attempts_left > 0:
            remaining_time = end_time - discord.utils.utcnow().timestamp()
            if remaining_time <= 0:
                await self.fail_captcha(member, invite_link, channel, proc_msgs)
                break

            try:
                msg = await self.bot.wait_for(
                    "message",
                    timeout=remaining_time,
                    check=lambda m: m.author == member and m.channel == channel
                )
            except asyncio.TimeoutError:
                await self.fail_captcha(member, invite_link, channel, proc_msgs)
                break

            proc_msgs.append(msg)
            if msg.content.lower() == captcha_code.lower():
                verified = await channel.send(f"{member.mention}, ¡captcha verificado correctamente!")
                proc_msgs.append(verified)
                await self.delete_process_messages(proc_msgs)
                break
            else:
                attempts_left -= 1
                feedback = await channel.send(
                    f"{member.mention}, captcha incorrecto. Te quedan {attempts_left} intento(s)."
                )
                proc_msgs.append(feedback)
                await self.safe_delete(msg)
                if attempts_left <= 0:
                    await self.fail_captcha(member, invite_link, channel, proc_msgs)
                    break

        self.process_messages.pop(member.id, None)

    async def fail_captcha(self, member: discord.Member, invite_link: Optional[str], channel: discord.TextChannel, proc_msgs: list):
        """Envía DM con invitación (si se configuró), expulsa al miembro y borra sus mensajes de proceso."""
        if invite_link:
            try:
                await member.send(
                    f"Lo sentimos, no has completado el captcha a tiempo. "
                    f"Puedes volver a intentarlo usando este enlace:\n{invite_link}"
                )
            except discord.Forbidden:
                pass
        try:
            await member.kick(reason="No completó el captcha a tiempo.")
        except discord.Forbidden:
            pass
        await self.delete_process_messages(proc_msgs)

    async def delete_process_messages(self, messages: list):
        """Elimina todos los mensajes registrados en un proceso."""
        for msg in messages:
            await self.safe_delete(msg)

    async def safe_delete(self, message: discord.Message):
        """Intenta borrar un mensaje sin errores si faltan permisos."""
        try:
            await message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

    # =========================================================================
    #                       COMANDOS DE CONFIGURACIÓN
    # =========================================================================
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def setcaptchachannel(self, ctx, channel: discord.TextChannel):
        """Establece el canal donde se enviarán los captchas a los nuevos usuarios."""
        await self.config.guild(ctx.guild).captcha_channel.set(channel.id)
        await ctx.send(f"Canal de captcha establecido en {channel.mention}")

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def setcaptchatime(self, ctx, minutes: int):
        """
        Establece el tiempo (en minutos) que tiene un usuario para completar el captcha.
        Valor por defecto: 5 minutos.
        """
        if minutes < 1:
            return await ctx.send("El tiempo mínimo es de 1 minuto.")
        await self.config.guild(ctx.guild).verification_timeout.set(minutes)
        await ctx.send(f"Tiempo de verificación establecido en {minutes} minuto(s).")

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def setcaptchaattempts(self, ctx, attempts: int):
        """
        Establece el número máximo de intentos para resolver el captcha.
        Valor por defecto: 5 intentos.
        """
        if attempts < 1:
            return await ctx.send("Debe haber al menos 1 intento.")
        await self.config.guild(ctx.guild).max_attempts.set(attempts)
        await ctx.send(f"Número máximo de intentos establecido en {attempts}.")

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def setcaptchainvite(self, ctx, invite_link: str):
        """
        Establece la invitación que se enviará por DM al usuario antes de expulsarlo.
        Ejemplo: !setcaptchainvite https://discord.gg/ejemplo
        """
        await self.config.guild(ctx.guild).invite_link.set(invite_link)
        await ctx.send("Invitación configurada correctamente.")

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def setcaptchatitle(self, ctx, *, title: str):
        """Establece el título del embed de captcha. Valor por defecto: 'Verificación Captcha'."""
        await self.config.guild(ctx.guild).embed_title.set(title)
        await ctx.send(f"Título del embed establecido a: {title}")

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def setcaptchadesc(self, ctx, *, description: str):
        """Establece la descripción del embed de captcha."""
        await self.config.guild(ctx.guild).embed_description.set(description)
        await ctx.send("Descripción del embed actualizada.")

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def setcaptchacolor(self, ctx, color: str):
        """
        Establece el color del embed de captcha.
        Formatos válidos: #RRGGBB o nombres (ej. 'blue', 'red').
        Ejemplo: !setcaptchacolor #3498DB
        """
        color_value = None
        if color.startswith("#"):
            try:
                color_value = int(color.strip("#"), 16)
            except ValueError:
                pass
        else:
            named_colors = {
                "red": 0xFF0000,
                "blue": 0x0000FF,
                "green": 0x00FF00,
                "yellow": 0xFFFF00,
                "purple": 0x800080,
                "gold": 0xFFD700
            }
            if color.lower() in named_colors:
                color_value = named_colors[color.lower()]
            else:
                try:
                    color_value = int(color, 16)
                except ValueError:
                    pass

        if color_value is None:
            return await ctx.send("No se pudo interpretar el color. Usa formato #RRGGBB o un nombre válido.")
        await self.config.guild(ctx.guild).embed_color.set(color_value)
        await ctx.send(f"Color del embed establecido a {color}.")

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def setcaptchaimage(self, ctx, *, image_url: str = None):
        """
        Establece la imagen (grande) del embed de captcha.
        Ejemplo: !setcaptchaimage https://imgur.com/C2c0SpZ
        Sin argumentos, elimina la imagen.
        """
        if image_url and not (image_url.startswith("http://") or image_url.startswith("https://")):
            return await ctx.send("La URL de la imagen debe comenzar con http:// o https://")
        await self.config.guild(ctx.guild).embed_image.set(image_url)
        if image_url:
            await ctx.send(f"Imagen del embed establecida a {image_url}")
        else:
            await ctx.send("Imagen del embed eliminada.")

    # =========================================================================
    #                              BYPASS
    # =========================================================================
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def bypasscaptcha(self, ctx, member: discord.Member):
        """Otorga bypass para que el usuario no deba pasar el captcha al unirse."""
        bypass_list = await self.config.guild(ctx.guild).bypass_list()
        if member.id not in bypass_list:
            bypass_list.append(member.id)
            await self.config.guild(ctx.guild).bypass_list.set(bypass_list)
            await ctx.send(f"{member.mention} ha sido añadido a la lista de bypass.")
        else:
            await ctx.send("Ese usuario ya tiene bypass.")

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def unbypasscaptcha(self, ctx, member: discord.Member):
        """Elimina el bypass de un usuario."""
        bypass_list = await self.config.guild(ctx.guild).bypass_list()
        if member.id in bypass_list:
            bypass_list.remove(member.id)
            await self.config.guild(ctx.guild).bypass_list.set(bypass_list)
            await ctx.send(f"{member.mention} ya no tiene bypass.")
        else:
            await ctx.send("Ese usuario no está en la lista de bypass.")

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def showbypass(self, ctx):
        """Muestra la lista de usuarios con bypass."""
        bypass_list = await self.config.guild(ctx.guild).bypass_list()
        if not bypass_list:
            return await ctx.send("No hay usuarios con bypass.")
        mentions = []
        for user_id in bypass_list:
            user = ctx.guild.get_member(user_id)
            if user:
                mentions.append(f"{user.mention} (ID: {user.id})")
            else:
                mentions.append(f"Usuario desconocido (ID: {user_id})")
        await ctx.send("Usuarios con bypass:\n" + "\n".join(mentions))

    # =========================================================================
    #                   COMANDOS DE AYUDA Y CONFIGURACIÓN
    # =========================================================================
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def setupcaptcha(self, ctx):
        """
        Envía un mensaje con la secuencia de comandos para configurar el captcha,
        junto con ejemplos. Los valores por defecto son:
          • Tiempo de verificación: 5 minutos.
          • Intentos máximos: 5.
          • Título del embed: 'Verificación Captcha'.
          • Descripción del embed: 'Para acceder al servidor, debes demostrar que eres humano completando el captcha.'
        
        Ejemplo de configuración:
          1. Establecer el canal de captcha:
             `!setcaptchachannel #canal-de-captcha`
          2. Establecer el tiempo de verificación:
             `!setcaptchatime 5`
          3. Establecer los intentos máximos:
             `!setcaptchaattempts 5`
          4. Establecer la invitación para reingreso:
             `!setcaptchainvite https://discord.gg/ejemplo`
          5. Configurar el Embed de captcha:
             - Título (por defecto 'Verificación Captcha'):
                `!setcaptchatitle Verificación Captcha`
             - Descripción (por defecto 'Para acceder al servidor, debes demostrar que eres humano completando el captcha.'):
                `!setcaptchadesc Para acceder al servidor, debes demostrar que eres humano completando el captcha.`
             - Color (por defecto `#3498DB`):
                `!setcaptchacolor #3498DB`
             - Imagen (opcional):
                `!setcaptchaimage https://imgur.com/C2c0SpZ`
          6. Enviar el embed informativo al canal de captcha:
             `!setcaptchaembed`
          7. Para ver la configuración actual:
             `!showcaptchasettings`
        """
        instructions = (
            "**Pasos para configurar el Captcha**\n\n"
            "**1. Establecer canal de captcha:**\n"
            "   `!setcaptchachannel #canal-de-captcha`\n\n"
            "**2. Establecer tiempo de verificación (en minutos):**\n"
            "   `!setcaptchatime 5`\n\n"
            "**3. Establecer intentos máximos:**\n"
            "   `!setcaptchaattempts 5`\n\n"
            "**4. Establecer invitación para reingreso:**\n"
            "   `!setcaptchainvite https://discord.gg/ejemplo`\n\n"
            "**5. Configurar el Embed de captcha:**\n"
            "   - Título (por defecto 'Verificación Captcha'):\n"
            "      `!setcaptchatitle Verificación Captcha`\n"
            "   - Descripción (por defecto 'Para acceder al servidor, debes demostrar que eres humano completando el captcha.'):\n"
            "      `!setcaptchadesc Para acceder al servidor, debes demostrar que eres humano completando el captcha.`\n"
            "   - Color (por defecto `#3498DB`):\n"
            "      `!setcaptchacolor #3498DB`\n"
            "   - Imagen (opcional):\n"
            "      `!setcaptchaimage https://imgur.com/C2c0SpZ`\n\n"
            "**6. Enviar el embed informativo al canal de captcha:**\n"
            "   `!setcaptchaembed`\n\n"
            "**7. Ver la configuración actual:**\n"
            "   `!showcaptchasettings`\n"
        )
        await ctx.send(instructions)

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def showcaptchasettings(self, ctx):
        """
        Muestra la configuración actual del captcha.
        """
        guild_config = await self.config.guild(ctx.guild).all()
        embed = discord.Embed(title="Configuración Actual de Captcha", color=guild_config["embed_color"])
        embed.add_field(name="Canal de captcha", value=f"<#{guild_config['captcha_channel']}>" if guild_config["captcha_channel"] else "No configurado", inline=False)
        embed.add_field(name="Tiempo de verificación", value=f"{guild_config['verification_timeout']} minuto(s)", inline=False)
        embed.add_field(name="Intentos máximos", value=str(guild_config["max_attempts"]), inline=False)
        embed.add_field(name="Invitación", value=guild_config["invite_link"] if guild_config["invite_link"] else "No configurada", inline=False)
        embed.add_field(name="Título del embed", value=guild_config["embed_title"], inline=False)
        embed.add_field(name="Descripción del embed", value=guild_config["embed_description"], inline=False)
        embed.add_field(name="Color del embed", value=f"#{guild_config['embed_color']:06X}", inline=False)
        embed.add_field(name="Imagen del embed", value=guild_config["embed_image"] if guild_config["embed_image"] else "No configurada", inline=False)
        await ctx.send(embed=embed)

    # =========================================================================
    #                     COMANDO PARA ENVIAR EL EMBED INFORMATIVO
    # =========================================================================
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def setcaptchaembed(self, ctx):
        """
        Envía el embed informativo de captcha al canal configurado.
        Este embed permanece fijo y no se borra.
        """
        guild_config = await self.config.guild(ctx.guild).all()
        channel_id = guild_config["captcha_channel"]
        if not channel_id:
            return await ctx.send("No hay canal de captcha configurado. Usa !setcaptchachannel para configurarlo.")
        channel = ctx.guild.get_channel(channel_id)
        if not channel:
            return await ctx.send("El canal configurado no es válido.")
        embed = discord.Embed(
            title=guild_config["embed_title"],
            description=guild_config["embed_description"],
            color=guild_config["embed_color"]
        )
        if guild_config["embed_image"]:
            embed.set_image(url=guild_config["embed_image"])
        await channel.send(embed=embed)
        await ctx.send(f"Embed de captcha enviado en {channel.mention}")

def setup(bot):
    bot.add_cog(AdvancedCaptcha(bot))
