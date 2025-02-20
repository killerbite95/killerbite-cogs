import os
import io
import random
import string
import discord
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from redbot.core import commands, Config, checks
from redbot.core.data_manager import bundled_data_path
from typing import Optional, Tuple, List

# Tipo para colores
ColorTuple = Tuple[int, int, int]

def random_color(low: int, high: int, extra: Optional[int] = None) -> ColorTuple:
    if extra is None:
        return (random.randint(low, high), random.randint(low, high), random.randint(low, high))
    else:
        return (random.randint(low, high), random.randint(low, high), extra)

class CaptchaGenerator:
    """
    Genera una imagen de captcha inspirada en el cog original.
    Se crean imágenes para cada carácter y se pegan con offsets aleatorios; además, se añade ruido.
    """
    def __init__(self, width: int, height: int, font_path: str, font_size: int):
        self._width = width
        self._height = height
        self.font = ImageFont.truetype(font_path, font_size)
        # Tabla de lookup para la máscara (se deja como identidad)
        self.lookup_table = list(range(256))

    def _draw_character(self, char: str, color: ColorTuple) -> Image.Image:
        """Dibuja un carácter en una imagen RGBA con fondo transparente."""
        # Usamos getbbox en lugar de getsize
        bbox = self.font.getbbox(char)
        size = (bbox[2] - bbox[0], bbox[3] - bbox[1])
        img = Image.new("RGBA", size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)
        # Ajustamos el offset para que se dibuje correctamente
        draw.text((-bbox[0], -bbox[1]), char, font=self.font, fill=color)
        return img

    def _create_captcha_image(self, chars: str, color: ColorTuple, background: ColorTuple) -> Image.Image:
        """Crea la imagen base pegando imágenes de cada carácter con offsets aleatorios."""
        image: Image.Image = Image.new("RGB", (self._width, self._height), background)
        draw: ImageDraw.Draw = ImageDraw.Draw(image)

        images: List[Image.Image] = []
        for char in chars:
            if random.random() > 0.5:
                images.append(self._draw_character(" ", color))
            images.append(self._draw_character(char, color))

        text_width: int = sum(im.size[0] for im in images)
        new_width: int = max(text_width, self._width)
        image = image.resize((new_width, self._height))

        average: int = int(text_width / len(chars))
        rand: int = int(0.25 * average)
        offset: int = int(average * 0.1)

        for img in images:
            w, h = img.size
            mask: Image.Image = img.convert("L").point(self.lookup_table)
            image.paste(img, (offset, int((self._height - h) / 2)), mask)
            offset = offset + w + random.randint(-rand, 0)

        if new_width > self._width:
            image = image.resize((self._width, self._height))
        return image

    def _create_noise_dots(self, image: Image.Image, color: ColorTuple) -> None:
        """Añade puntos de ruido a la imagen."""
        draw = ImageDraw.Draw(image)
        for _ in range(random.randint(100, 300)):
            x = random.randint(0, image.size[0]-1)
            y = random.randint(0, image.size[1]-1)
            draw.point((x, y), fill=color)

    def _create_noise_curve(self, image: Image.Image, color: ColorTuple) -> None:
        """Añade una curva de ruido a la imagen."""
        draw = ImageDraw.Draw(image)
        x1 = random.randint(0, image.size[0] // 2)
        y1 = random.randint(0, image.size[1])
        x2 = random.randint(image.size[0] // 2, image.size[0])
        y2 = random.randint(0, image.size[1])
        draw.line((x1, y1, x2, y2), fill=color, width=2)

    def _generate(self, chars: str) -> Image.Image:
        background: ColorTuple = random_color(238, 255)
        color: ColorTuple = random_color(10, 200, random.randint(220, 255))
        image: Image.Image = self._create_captcha_image(chars, color, background)
        self._create_noise_dots(image, color)
        self._create_noise_curve(image, color)
        image = image.filter(ImageFilter.SMOOTH)
        return image

    def generate(self, chars: str, format: str = "png") -> io.BytesIO:
        image: Image.Image = self._generate(chars)
        byte: io.BytesIO = io.BytesIO()
        image.save(byte, format=format)
        byte.seek(0)
        return byte

class AdvancedCaptcha(commands.Cog):
    """Cog avanzado de Captcha que utiliza CaptchaGenerator para generar imágenes similares al cog original.
    
    Incluye comandos de configuración, asignación de rol, habilitar/deshabilitar y reset.
    """
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0xDEADBEEF, force_registration=True)
        default_guild = {
            "captcha_enabled": True,
            "captcha_channel": None,
            "invite_link": None,
            "verification_timeout": 5,
            "max_attempts": 5,
            "bypass_list": [],
            "verified_role": None,
            "embed_title": "Verificación Captcha",
            "embed_description": "Para acceder al servidor, debes demostrar que eres humano completando el captcha.",
            "embed_color": 0x3498DB,
            "embed_image": None
        }
        self.config.register_guild(**default_guild)
        self.process_messages = {}
        self.data_path = bundled_data_path(self)
        self.font_data = os.path.join(self.data_path, "DroidSansMono.ttf")
        self._width = 600
        self._height = 200
        self._font_size = 200
        self.captcha_generator = CaptchaGenerator(self._width, self._height, self.font_data, self._font_size)

    def generate_captcha_image(self, captcha_code: str) -> discord.File:
        byte = self.captcha_generator.generate(captcha_code, format="png")
        return discord.File(fp=byte, filename="captcha.png")

    # -------------------------------------------------------------------------
    # EVENTOS
    # -------------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        guild_config = await self.config.guild(guild).all()
        if not guild_config["captcha_enabled"]:
            return
        channel_id = guild_config["captcha_channel"]
        if not channel_id:
            return
        if member.id in guild_config["bypass_list"]:
            return
        channel = guild.get_channel(channel_id)
        if not channel:
            return
        self.process_messages[member.id] = []
        self.bot.loop.create_task(self.start_captcha_process(member, channel))

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.id in self.process_messages:
            for msg in self.process_messages[member.id]:
                try:
                    await msg.delete()
                except Exception:
                    pass
            del self.process_messages[member.id]

    # -------------------------------------------------------------------------
    # PROCESO CAPTCHA
    # -------------------------------------------------------------------------
    async def start_captcha_process(self, member: discord.Member, channel: discord.TextChannel):
        guild = member.guild
        guild_config = await self.config.guild(guild).all()
        verification_timeout = guild_config["verification_timeout"]
        max_attempts = guild_config["max_attempts"]
        invite_link = guild_config["invite_link"]
        proc_msgs = self.process_messages.get(member.id, [])

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

        time_limit = verification_timeout * 60
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
                success = await channel.send(f"{member.mention}, ¡captcha verificado correctamente!")
                proc_msgs.append(success)
                await self.assign_verified_role(member, guild_config["verified_role"])
                await self.delete_process_messages(proc_msgs)
                break
            else:
                attempts_left -= 1
                feedback = await channel.send(f"{member.mention}, captcha incorrecto. Te quedan {attempts_left} intento(s).")
                proc_msgs.append(feedback)
                await self.safe_delete(msg)
                if attempts_left <= 0:
                    await self.fail_captcha(member, invite_link, channel, proc_msgs)
                    break

        self.process_messages.pop(member.id, None)

    async def assign_verified_role(self, member: discord.Member, role_id: Optional[int]):
        if role_id:
            role = member.guild.get_role(role_id)
            if role:
                try:
                    await member.add_roles(role, reason="Captcha verificado")
                except discord.Forbidden:
                    pass

    async def fail_captcha(self, member: discord.Member, invite_link: Optional[str],
                             channel: discord.TextChannel, proc_msgs: List[discord.Message]):
        if invite_link:
            try:
                await member.send(
                    f"Lo sentimos, no has completado el captcha a tiempo. Puedes volver a intentarlo usando este enlace:\n{invite_link}"
                )
            except discord.Forbidden:
                pass
        try:
            await member.kick(reason="No completó el captcha a tiempo.")
        except discord.Forbidden:
            pass
        await self.delete_process_messages(proc_msgs)

    async def delete_process_messages(self, messages: List[discord.Message]):
        for msg in messages:
            await self.safe_delete(msg)

    async def safe_delete(self, message: discord.Message):
        try:
            await message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

    # -------------------------------------------------------------------------
    # COMANDOS DE CONFIGURACIÓN
    # -------------------------------------------------------------------------
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def setcaptchachannel(self, ctx, channel: discord.TextChannel):
        await self.config.guild(ctx.guild).captcha_channel.set(channel.id)
        await ctx.send(f"Canal de captcha establecido en {channel.mention}")

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def setcaptchatime(self, ctx, minutes: int):
        if minutes < 1:
            return await ctx.send("El tiempo mínimo es de 1 minuto.")
        await self.config.guild(ctx.guild).verification_timeout.set(minutes)
        await ctx.send(f"Tiempo de verificación establecido en {minutes} minuto(s).")

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def setcaptchaattempts(self, ctx, attempts: int):
        if attempts < 1:
            return await ctx.send("Debe haber al menos 1 intento.")
        await self.config.guild(ctx.guild).max_attempts.set(attempts)
        await ctx.send(f"Número máximo de intentos establecido en {attempts}.")

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def setcaptchainvite(self, ctx, invite_link: str):
        await self.config.guild(ctx.guild).invite_link.set(invite_link)
        await ctx.send("Invitación configurada correctamente.")

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def setcaptchatitle(self, ctx, *, title: str):
        await self.config.guild(ctx.guild).embed_title.set(title)
        await ctx.send(f"Título del embed establecido a: {title}")

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def setcaptchadesc(self, ctx, *, description: str):
        await self.config.guild(ctx.guild).embed_description.set(description)
        await ctx.send("Descripción del embed actualizada.")

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def setcaptchacolor(self, ctx, color: str):
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
        await self.config.guild(ctx.guild).verified_role.set(role.id)
        await ctx.send(f"Rol de verificados establecido a: {role.mention}")

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def togglecaptcha(self, ctx, state: str):
        state = state.lower()
        if state not in ("on", "off"):
            return await ctx.send("Uso: !togglecaptcha on / off")
        enabled = state == "on"
        await self.config.guild(ctx.guild).captcha_enabled.set(enabled)
        await ctx.send(f"Captcha {'habilitado' if enabled else 'deshabilitado'}.")

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def setupcaptcha(self, ctx):
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
            "   - Título:\n"
            "      `!setcaptchatitle Verificación Captcha`\n"
            "   - Descripción:\n"
            "      `!setcaptchadesc Para acceder, demuestra que eres humano completando el captcha.`\n"
            "   - Color:\n"
            "      `!setcaptchacolor #3498DB`\n"
            "   - Thumbnail (opcional):\n"
            "      `!setcaptchaimage https://imgur.com/C2c0SpZ`\n\n"
            "**6. Establecer el rol de verificados:**\n"
            "   `!setcaptchaverifiedrole @Verificado`\n\n"
            "**7. Enviar el embed informativo:**\n"
            "   `!setcaptchaembed`\n\n"
            "**8. Ver la configuración actual:**\n"
            "   `!showcaptchasettings`\n"
        )
        await ctx.send(instructions)

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def showcaptchasettings(self, ctx):
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

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def resetcaptcha(self, ctx):
        default = {
            "captcha_enabled": True,
            "captcha_channel": None,
            "invite_link": None,
            "verification_timeout": 5,
            "max_attempts": 5,
            "bypass_list": [],
            "verified_role": None,
            "embed_title": "Verificación Captcha",
            "embed_description": "Para acceder al servidor, debes demostrar que eres humano completando el captcha.",
            "embed_color": 0x3498DB,
            "embed_image": None
        }
        await self.config.guild(ctx.guild).clear()
        await self.config.guild(ctx.guild).set(default)
        self.process_messages.clear()
        await ctx.send("¡La configuración del captcha ha sido reiniciada a los valores por defecto!")

def setup(bot):
    bot.add_cog(AdvancedCaptcha(bot))
