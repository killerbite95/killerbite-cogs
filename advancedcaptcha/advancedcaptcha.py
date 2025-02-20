import discord
import asyncio
import random
import string
import io
from redbot.core import commands, Config, checks
from typing import Optional
from PIL import Image, ImageDraw, ImageFont  # Requiere Pillow

class AdvancedCaptcha(commands.Cog):
    """Cog avanzado de Captcha con verificación automática, asignación de rol y gestión completa.

    - El embed informativo se envía mediante !setcaptchaembed y permanece fijo.
    - Al unirse, se envía un desafío (imagen con captcha) en el canal configurado, siempre que el captcha esté habilitado.
    - Al verificar, se asigna el rol configurado al usuario.
    - Se registra y, al finalizar cada proceso, se eliminan únicamente los mensajes relacionados.
    - !resetcaptcha reinicia la configuración a los valores por defecto y limpia los datos internos.
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0xDEADBEEF, force_registration=True)
        default_guild = {
            "captcha_enabled": True,         # Captcha activado por defecto
            "captcha_channel": None,         # Canal de captcha (sin configurar)
            "invite_link": None,             # Invitación para reingreso (sin configurar)
            "verification_timeout": 5,       # Tiempo límite en minutos (5 por defecto)
            "max_attempts": 5,               # Intentos máximos (5 por defecto)
            "bypass_list": [],               # Lista de bypass (vacía)
            "verified_role": None,           # Rol de verificados (sin configurar)
            # Configuración del Embed informativo
            "embed_title": "Verificación Captcha",
            "embed_description": (
                "Para acceder al servidor, debes demostrar que eres humano completando el captcha."
            ),
            "embed_color": 0x3498DB,         # Azul por defecto
            "embed_image": None              # Thumbnail (opcional)
        }
        self.config.register_guild(**default_guild)
        # Diccionario para almacenar los mensajes de cada proceso: {user_id: [message, ...]}
        self.process_messages = {}
        # Indica la ruta donde el cog busca los datos “bundled”
        self.data_path = bundled_data_path(self)
        # Construye la ruta completa al archivo de la fuente
        self.font_data = os.path.join(self.data_path, "DroidSansMono.ttf")

    # -------------------------------------------------------------------------
    # Función para generar la imagen del captcha
    # -------------------------------------------------------------------------
    def generate_captcha_image(self, captcha_code: str) -> discord.File:
        """Genera una imagen PNG con el código captcha usando la fuente ubicada en font_data."""
        width, height = 600, 200
        font_size = 380
        image = Image.new("RGB", (width, height), color=(255, 255, 255))
        draw = ImageDraw.Draw(image)

        try:
            # Cargamos la fuente desde la ruta self.font_data
            font = ImageFont.truetype(self.font_data, font_size)
        except Exception as e:
            print(f"No se pudo cargar la fuente en {self.font_data}: {e}")
            font = ImageFont.load_default()

        # Calculamos el tamaño del texto para centrarlo
        bbox = draw.textbbox((0, 0), captcha_code, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (width - text_width) / 2
        y = (height - text_height) / 2

        draw.text((x, y), captcha_code, font=font, fill=(0, 0, 0))

        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        buffer.seek(0)
        return discord.File(fp=buffer, filename="captcha.png")
    # =========================================================================
    #                             EVENTOS
    # =========================================================================
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Al unirse un miembro, inicia el proceso de captcha si está habilitado y no tiene bypass."""
        guild = member.guild
        guild_config = await self.config.guild(guild).all()
        if not guild_config["captcha_enabled"]:
            return

        channel_id = guild_config["captcha_channel"]
        bypass_list = guild_config["bypass_list"]
        if not channel_id or member.id in bypass_list:
            return

        channel = guild.get_channel(channel_id)
        if not channel:
            return

        # Inicializa la lista de mensajes para este proceso y lanza el captcha.
        self.process_messages[member.id] = []
        self.bot.loop.create_task(self.start_captcha_process(member, channel))

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Al salir un miembro, se limpia su información de proceso para evitar datos residuales."""
        if member.id in self.process_messages:
            for msg in self.process_messages[member.id]:
                try:
                    await msg.delete()
                except Exception:
                    pass
            del self.process_messages[member.id]

    # =========================================================================
    #                           PROCESO CAPTCHA
    # =========================================================================
    async def start_captcha_process(self, member: discord.Member, channel: discord.TextChannel):
        """Gestiona el proceso de captcha para un miembro, registrando y controlando sus mensajes."""
        guild = member.guild
        guild_config = await self.config.guild(guild).all()
        verification_timeout = guild_config["verification_timeout"]
        max_attempts = guild_config["max_attempts"]
        invite_link = guild_config["invite_link"]
        proc_msgs = self.process_messages.get(member.id, [])

        # Genera el captcha y crea la imagen
        captcha_code = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
        captcha_file = self.generate_captcha_image(captcha_code)
        try:
            challenge = await channel.send(
                f"{member.mention}, escribe el texto que ves en la imagen para continuar:",
                file=captcha_file
            )
            proc_msgs.append(challenge)
        except discord.Forbidden:
            return

        time_limit = verification_timeout * 60  # Convertir minutos a segundos
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
                verified_msg = await channel.send(f"{member.mention}, ¡captcha verificado correctamente!")
                proc_msgs.append(verified_msg)
                await self.assign_verified_role(member, guild_config["verified_role"])
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

    async def assign_verified_role(self, member: discord.Member, role_id: Optional[int]):
        """Asigna el rol verificado al usuario, si se configuró."""
        if role_id:
            role = member.guild.get_role(role_id)
            if role:
                try:
                    await member.add_roles(role, reason="Captcha verificado")
                except discord.Forbidden:
                    pass

    async def fail_captcha(self, member: discord.Member, invite_link: Optional[str], channel: discord.TextChannel, proc_msgs: list):
        """Envía DM con invitación (si se configuró), expulsa al miembro y borra sus mensajes del proceso."""
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
        """Elimina todos los mensajes registrados de un proceso de captcha."""
        for msg in messages:
            await self.safe_delete(msg)

    async def safe_delete(self, message: discord.Message):
        """Intenta borrar un mensaje sin lanzar errores si faltan permisos."""
        try:
            await message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

    # =========================================================================
    #                    COMANDOS DE CONFIGURACIÓN
    # =========================================================================
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def setcaptchachannel(self, ctx, channel: discord.TextChannel):
        """Establece el canal donde se enviarán los captchas."""
        await self.config.guild(ctx.guild).captcha_channel.set(channel.id)
        await ctx.send(f"Canal de captcha establecido en {channel.mention}")

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def setcaptchatime(self, ctx, minutes: int):
        """
        Establece el tiempo (en minutos) para completar el captcha.
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
        """Establece el título del embed informativo. Valor por defecto: 'Verificación Captcha'."""
        await self.config.guild(ctx.guild).embed_title.set(title)
        await ctx.send(f"Título del embed establecido a: {title}")

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def setcaptchadesc(self, ctx, *, description: str):
        """Establece la descripción del embed informativo."""
        await self.config.guild(ctx.guild).embed_description.set(description)
        await ctx.send("Descripción del embed actualizada.")

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def setcaptchacolor(self, ctx, color: str):
        """
        Establece el color del embed informativo.
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
        Establece el thumbnail del embed informativo.
        Ejemplo: !setcaptchaimage https://i.imgur.com/bBJelmT.png
        Sin argumentos, elimina el thumbnail.
        """
        if image_url and not (image_url.startswith("http://") or image_url.startswith("https://")):
            return await ctx.send("La URL de la imagen debe comenzar con http:// o https://")
        await self.config.guild(ctx.guild).embed_image.set(image_url)
        if image_url:
            await ctx.send(f"Thumbnail del embed establecido a {image_url}")
        else:
            await ctx.send("Thumbnail del embed eliminado.")

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def setcaptchaverifiedrole(self, ctx, role: discord.Role):
        """
        Establece el rol que se asignará a los usuarios que verifiquen el captcha.
        Ejemplo: !setcaptchaverifiedrole @Verificado
        """
        await self.config.guild(ctx.guild).verified_role.set(role.id)
        await ctx.send(f"Rol de verificados establecido a: {role.mention}")

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def togglecaptcha(self, ctx, state: str):
        """
        Habilita o deshabilita el sistema de captcha.
        Uso: !togglecaptcha on / off
        """
        state = state.lower()
        if state not in ("on", "off"):
            return await ctx.send("Uso: !togglecaptcha on / off")
        enabled = state == "on"
        await self.config.guild(ctx.guild).captcha_enabled.set(enabled)
        await ctx.send(f"Captcha {'habilitado' if enabled else 'deshabilitado'}.")

    # =========================================================================
    #              COMANDOS DE AYUDA Y RESET DE CONFIGURACIÓN
    # =========================================================================
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def setupcaptcha(self, ctx):
        """
        Envía las instrucciones para configurar el captcha, junto con ejemplos. Los valores por defecto son:
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
             - Thumbnail (opcional):
                `!setcaptchaimage https://i.imgur.com/bBJelmT.png`
          6. Establecer el rol de verificados:
             `!setcaptchaverifiedrole @Verificado`
          7. Enviar el embed informativo al canal de captcha:
             `!setcaptchaembed`
          8. Para ver la configuración actual:
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
            "   - Thumbnail (opcional):\n"
            "      `!setcaptchaimage https://i.imgur.com/bBJelmT.png`\n\n"
            "**6. Establecer el rol de verificados:**\n"
            "   `!setcaptchaverifiedrole @Verificado`\n\n"
            "**7. Enviar el embed informativo al canal de captcha:**\n"
            "   `!setcaptchaembed`\n\n"
            "**8. Ver la configuración actual:**\n"
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
        embed.add_field(name="Captcha habilitado", value=str(guild_config["captcha_enabled"]), inline=False)
        embed.add_field(name="Canal de captcha", value=f"<#{guild_config['captcha_channel']}>" if guild_config["captcha_channel"] else "No configurado", inline=False)
        embed.add_field(name="Tiempo de verificación", value=f"{guild_config['verification_timeout']} minuto(s)", inline=False)
        embed.add_field(name="Intentos máximos", value=str(guild_config["max_attempts"]), inline=False)
        embed.add_field(name="Invitación", value=guild_config["invite_link"] if guild_config["invite_link"] else "No configurada", inline=False)
        embed.add_field(name="Rol verificado", value=f"<@&{guild_config['verified_role']}>" if guild_config["verified_role"] else "No configurado", inline=False)
        embed.add_field(name="Título del embed", value=guild_config["embed_title"], inline=False)
        embed.add_field(name="Descripción del embed", value=guild_config["embed_description"], inline=False)
        embed.add_field(name="Color del embed", value=f"#{guild_config['embed_color']:06X}", inline=False)
        embed.add_field(name="Thumbnail del embed", value=guild_config["embed_image"] if guild_config["embed_image"] else "No configurado", inline=False)
        await ctx.send(embed=embed)

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
            embed.set_thumbnail(url=guild_config["embed_image"])
        await channel.send(embed=embed)
        await ctx.send(f"Embed de captcha enviado en {channel.mention}")

    # =========================================================================
    #                  COMANDO RESET DE CONFIGURACIÓN
    # =========================================================================
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def resetcaptcha(self, ctx):
        """
        Reinicia la configuración del captcha a sus valores por defecto y limpia todos los datos internos.
        
        ¡ATENCIÓN! Esto borrará toda la configuración actual de este cog en el servidor.
        """
        default = {
            "captcha_enabled": True,
            "captcha_channel": None,
            "invite_link": None,
            "verification_timeout": 5,
            "max_attempts": 5,
            "bypass_list": [],
            "verified_role": None,
            "embed_title": "Verificación Captcha",
            "embed_description": (
                "Para acceder al servidor, debes demostrar que eres humano completando el captcha."
            ),
            "embed_color": 0x3498DB,
            "embed_image": None
        }
        await self.config.guild(ctx.guild).clear()
        await self.config.guild(ctx.guild).set(default)
        self.process_messages.clear()
        await ctx.send("¡La configuración del captcha ha sido reiniciada a los valores por defecto!")

def setup(bot):
    bot.add_cog(AdvancedCaptcha(bot))
