import discord
import asyncio
import random
import string
from redbot.core import commands, Config, checks
from typing import Optional

class AdvancedCaptcha(commands.Cog):
    """Cog avanzado de Captcha con verificación automática tras unirse al servidor."""

    def __init__(self, bot):
        self.bot = bot

        # Configuración persistente a nivel de guild
        self.config = Config.get_conf(self, identifier=0xDEADCAFE, force_registration=True)
        default_guild = {
            "captcha_channel": None,          # ID del canal donde se hará la verificación
            "invite_link": None,             # Invitación para reingresar al servidor
            "verification_hours": 24,        # Tiempo límite (en horas)
            "max_attempts": 3,               # Número de intentos
            "bypass_list": [],               # IDs de usuarios con bypass
            # Config Embed
            "embed_title": "Verificación captcha",
            "embed_description": (
                "Para acceder al servidor, debes demostrar que eres humano "
                "completando el captcha.\n\n"
                "Escribe la respuesta todo junto, sin espacios, y **no importa** "
                "si usas mayúsculas o minúsculas."
            ),
            "embed_color": 0x3498DB,         # Color por defecto (azul)
            "embed_image": None              # Imagen grande en el embed (no thumbnail)
        }
        self.config.register_guild(**default_guild)

        # Estructura en memoria para manejar tareas de captcha en curso
        # user_id -> asyncio.Task
        self.captcha_tasks = {}

    # =========================================================================
    #                              EVENTOS
    # =========================================================================
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """
        Evento que se dispara cuando un miembro se une al servidor.
        Si no está en la bypass_list, se inicia el proceso de captcha.
        """
        guild = member.guild
        # Obtenemos la config del servidor
        guild_config = await self.config.guild(guild).all()
        channel_id = guild_config["captcha_channel"]
        bypass_list = guild_config["bypass_list"]
        
        # Si no hay canal configurado o el usuario está en bypass, no hacemos nada.
        if not channel_id or member.id in bypass_list:
            return

        # Intentamos obtener el canal
        channel = guild.get_channel(channel_id)
        if not channel:
            return  # Canal inválido, no podemos hacer nada

        # Generamos la tarea asíncrona que gestionará el captcha de este usuario
        task = self.bot.loop.create_task(self.start_captcha_process(member, channel))
        self.captcha_tasks[member.id] = task

    # =========================================================================
    #                              PROCESO CAPTCHA
    # =========================================================================
    async def start_captcha_process(self, member: discord.Member, channel: discord.TextChannel):
        """
        Inicia la secuencia de captcha para un usuario en particular.
        - Envía embed personalizado.
        - Envía el código captcha.
        - Escucha respuestas hasta agotar intentos o tiempo.
        - Expulsa si falla o no responde a tiempo, tras enviar DM con invitación.
        """
        guild = member.guild
        guild_config = await self.config.guild(guild).all()

        verification_hours = guild_config["verification_hours"]
        max_attempts = guild_config["max_attempts"]
        invite_link = guild_config["invite_link"]

        # Embed personalizado
        embed_title = guild_config["embed_title"]
        embed_description = guild_config["embed_description"]
        embed_color = guild_config["embed_color"]
        embed_image = guild_config["embed_image"]

        embed = discord.Embed(
            title=embed_title,
            description=embed_description,
            color=embed_color
        )
        if embed_image:
            embed.set_image(url=embed_image)

        # Enviamos el embed
        try:
            await channel.send(content=f"{member.mention}", embed=embed)
        except discord.Forbidden:
            # Si no tenemos permisos para mencionar/embeds, nos detenemos
            return

        # Generamos el captcha
        captcha_code = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
        # Enviamos un mensaje con el captcha
        prompt = None
        try:
            prompt = await channel.send(
                f"{member.mention}, escribe el siguiente captcha para continuar:\n**{captcha_code}**"
            )
        except discord.Forbidden:
            pass

        # Tiempo total de verificación en segundos
        time_limit = verification_hours * 3600
        end_time = discord.utils.utcnow().timestamp() + time_limit
        attempts_left = max_attempts

        # Bucle de escucha: permitimos hasta X intentos o hasta que pase el tiempo
        while attempts_left > 0:
            # Calculamos el tiempo restante
            remaining_time = end_time - discord.utils.utcnow().timestamp()
            if remaining_time <= 0:
                # Se acabó el tiempo
                await self.fail_captcha(member, invite_link)
                break

            try:
                # Esperamos un mensaje del usuario en el canal
                msg = await self.bot.wait_for(
                    "message",
                    timeout=remaining_time,
                    check=lambda m: m.author == member and m.channel == channel
                )
            except asyncio.TimeoutError:
                # Se agotó el tiempo
                await self.fail_captcha(member, invite_link)
                break

            # Si llega un mensaje, verificamos
            if msg.content.lower() == captcha_code.lower():
                # Éxito
                await channel.send(f"{member.mention}, ¡captcha verificado correctamente!")
                # Limpiamos mensajes si tenemos permisos
                if prompt:
                    await self.safe_delete(prompt)
                await self.safe_delete(msg)
                break
            else:
                # Falla
                attempts_left -= 1
                await channel.send(
                    f"{member.mention}, captcha incorrecto. Te quedan {attempts_left} intento(s)."
                )
                await self.safe_delete(msg)

                if attempts_left <= 0:
                    # Sin intentos, expulsamos
                    await self.fail_captcha(member, invite_link)

        # Eliminamos la tarea de la tabla
        self.captcha_tasks.pop(member.id, None)

    async def fail_captcha(self, member: discord.Member, invite_link: Optional[str]):
        """
        Envía un DM al usuario con la invitación (si existe) y lo expulsa del servidor.
        """
        if invite_link:
            try:
                await member.send(
                    f"Lo sentimos, no has completado el captcha a tiempo. "
                    f"Puedes volver a intentarlo usando este enlace:\n{invite_link}"
                )
            except discord.Forbidden:
                pass
        # Expulsamos
        try:
            await member.kick(reason="No completó el captcha a tiempo.")
        except discord.Forbidden:
            pass

    async def safe_delete(self, message: discord.Message):
        """Borra un mensaje si se tienen los permisos necesarios."""
        try:
            await message.delete()
        except discord.Forbidden:
            pass
        except discord.HTTPException:
            pass

    # =========================================================================
    #                          COMANDOS DE CONFIGURACIÓN
    # =========================================================================
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def setcaptchachannel(self, ctx, channel: discord.TextChannel):
        """
        Establece el canal donde se enviarán los captchas a los nuevos usuarios.
        """
        await self.config.guild(ctx.guild).captcha_channel.set(channel.id)
        await ctx.send(f"Canal de captcha establecido en {channel.mention}")

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def setcaptchatime(self, ctx, hours: int):
        """
        Establece el tiempo (en horas) que tiene un usuario para completar el captcha.
        """
        if hours < 1:
            return await ctx.send("El tiempo mínimo es 1 hora.")
        await self.config.guild(ctx.guild).verification_hours.set(hours)
        await ctx.send(f"Tiempo de verificación establecido en {hours} horas.")

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def setcaptchaattempts(self, ctx, attempts: int):
        """
        Establece el número máximo de intentos para resolver el captcha.
        """
        if attempts < 1:
            return await ctx.send("Debe haber al menos 1 intento.")
        await self.config.guild(ctx.guild).max_attempts.set(attempts)
        await ctx.send(f"Número de intentos máximo establecido en {attempts}.")

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def setcaptchainvite(self, ctx, invite_link: str):
        """
        Establece la invitación que se enviará por DM al usuario antes de expulsarlo.
        """
        # Podríamos validar un poco el formato, pero se asume que el admin sabe lo que hace
        await self.config.guild(ctx.guild).invite_link.set(invite_link)
        await ctx.send("Invitación configurada correctamente.")

    # =========================================================================
    #                         COMANDOS DE EMBED PERSONALIZADO
    # =========================================================================
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def setcaptchatitle(self, ctx, *, title: str):
        """Establece el título del embed de captcha."""
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
        Formato recomendado: hex (p. ej. #3498DB) o nombre 'blue', 'red', etc.
        """
        # Intentamos parsear color como hex (#FFFFFF) o como nombre.
        color_value = None
        if color.startswith("#"):
            try:
                color_value = int(color.strip("#"), 16)
            except ValueError:
                pass
        else:
            # Intentamos que sea un nombre de color de la librería discord.Color
            # (solo unos pocos predefinidos). O lo parseamos como hex sin '#'
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
                # Intentamos parsear como hex sin #
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
        Envía sin argumentos para eliminar la imagen.
        """
        if image_url and not (image_url.startswith("http://") or image_url.startswith("https://")):
            return await ctx.send("La URL de la imagen debe comenzar con http:// o https://")
        await self.config.guild(ctx.guild).embed_image.set(image_url)
        if image_url:
            await ctx.send(f"Imagen del embed establecida a {image_url}")
        else:
            await ctx.send("Imagen del embed eliminada.")

    # =========================================================================
    #                            BYPASS
    # =========================================================================
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @commands.command()
    async def bypasscaptcha(self, ctx, member: discord.Member):
        """
        Otorga bypass a un usuario para que no sea expulsado por captcha.
        """
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
        """
        Elimina el bypass de un usuario para que sea obligado a pasar captcha en futuros joins.
        """
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
        """
        Muestra la lista de usuarios con bypass.
        """
        bypass_list = await self.config.guild(ctx.guild).bypass_list()
        if not bypass_list:
            return await ctx.send("No hay usuarios con bypass.")
        # Convertimos IDs a nombres legibles
        mentions = []
        for user_id in bypass_list:
            user = ctx.guild.get_member(user_id)
            if user:
                mentions.append(f"{user.mention} (ID: {user.id})")
            else:
                mentions.append(f"Usuario desconocido (ID: {user_id})")

        await ctx.send("Usuarios con bypass:\n" + "\n".join(mentions))

def setup(bot):
    bot.add_cog(AdvancedCaptcha(bot))
