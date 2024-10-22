import discord
from discord.ext import commands, tasks
from redbot.core import commands, Config, checks, bank
from redbot.core.bot import Red
import asyncio
import datetime

class PruneBans(commands.Cog):
    """Cog para manejar la eliminación de créditos de usuarios baneados y hacer seguimiento de los baneos."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        self.config.register_guild(
            log_channel=None,           # Canal para logs de prune
            ban_log_channel=None,       # Canal para logs de baneos
            ban_track={}                # Seguimiento de baneos
        )
        self.update_ban_countdown.start()

    def cog_unload(self):
        self.update_ban_countdown.cancel()

    @commands.command(name="setlogprune")
    @checks.admin_or_permissions(administrator=True)
    async def set_log_prune(self, ctx, channel: discord.TextChannel):
        """Establece el canal donde se enviarán los logs de prune."""
        await self.config.guild(ctx.guild).log_channel.set(channel.id)
        await ctx.send(f"Canal de logs de prune establecido en: {channel.mention}")

    @commands.command(name="setbanlog")
    @checks.admin_or_permissions(administrator=True)
    async def set_ban_log(self, ctx, channel: discord.TextChannel):
        """Establece el canal donde se enviarán los logs de baneos."""
        await self.config.guild(ctx.guild).ban_log_channel.set(channel.id)
        await ctx.send(f"Canal de logs de baneos establecido en: {channel.mention}")

    @commands.command(name="prune")
    @checks.admin_or_permissions(administrator=True)
    async def manual_prune(self, ctx):
        """Ejecuta prune manualmente después de una confirmación."""
        guild = ctx.guild
        banned_users = [ban async for ban in guild.bans()]
        banned_user_ids = [ban_entry.user.id for ban_entry in banned_users]

        if not banned_user_ids:
            await ctx.send("No hay usuarios baneados en este servidor.")
            return

        affected_accounts = []
        for user_id in banned_user_ids:
            try:
                balance = await bank.get_balance(discord.Object(id=user_id))
                if balance > 0:
                    affected_accounts.append((user_id, balance))
            except Exception:
                continue  # Si el usuario no tiene cuenta en el banco, lo ignoramos

        if not affected_accounts:
            await ctx.send("No hay cuentas bancarias de usuarios baneados para eliminar.")
            return

        # Mostrar la lista de usuarios afectados
        description = "**Usuarios que serán afectados por el prune:**\n"
        for user_id, balance in affected_accounts:
            description += f"- ID: `{user_id}`, Créditos: `{balance}`\n"

        description += "\n**¿Deseas continuar?** Reacciona con ✅ para confirmar o ❌ para cancelar. *Esta acción es irreversible.*"

        message = await ctx.send(description)

        # Añadir reacciones de confirmación
        await message.add_reaction("✅")
        await message.add_reaction("❌")

        def check(reaction, user):
            return (
                user == ctx.author
                and str(reaction.emoji) in ["✅", "❌"]
                and reaction.message.id == message.id
            )

        try:
            reaction, user = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)
            if str(reaction.emoji) == "✅":
                # Ejecutar prune
                prune_result = await bank.prune_accounts(guild)
                if prune_result:
                    await ctx.send("Función prune ejecutada correctamente.")
                    # Enviar log al canal configurado
                    log_channel_id = await self.config.guild(guild).log_channel()
                    if log_channel_id:
                        log_channel = guild.get_channel(log_channel_id)
                        if log_channel:
                            await log_channel.send(f"Prune ejecutado por {ctx.author.mention}.")
                else:
                    await ctx.send("No se encontraron cuentas para prune.")
            else:
                await ctx.send("Operación cancelada.")
        except asyncio.TimeoutError:
            await ctx.send("No se recibió confirmación a tiempo. Operación cancelada.")

    @commands.command(name="prunetest")
    @checks.admin_or_permissions(administrator=True)
    async def prune_test(self, ctx):
        """Comando de prueba para mostrar los usuarios que serían afectados por prune."""
        guild = ctx.guild
        banned_users = [ban async for ban in guild.bans()]
        banned_user_ids = [ban_entry.user.id for ban_entry in banned_users]

        if not banned_user_ids:
            await ctx.send("No hay usuarios baneados en este servidor.")
            return

        affected_accounts = []
        for user_id in banned_user_ids:
            try:
                balance = await bank.get_balance(discord.Object(id=user_id))
                if balance > 0:
                    affected_accounts.append((user_id, balance))
            except Exception:
                continue  # Si el usuario no tiene cuenta en el banco, lo ignoramos

        if not affected_accounts:
            await ctx.send("No hay cuentas bancarias de usuarios baneados para eliminar.")
            return

        # Mostrar la lista de usuarios afectados
        description = "**Usuarios que serían afectados por el prune:**\n"
        for user_id, balance in affected_accounts:
            description += f"- ID: `{user_id}`, Créditos: `{balance}`\n"

        await ctx.send(description)

    @commands.command(name="listbans")
    @checks.admin_or_permissions(administrator=True)
    async def list_bans(self, ctx):
        """Lista los usuarios baneados con su cuenta atrás de 7 días."""
        guild = ctx.guild
        async with self.config.guild(guild).ban_track() as ban_track:
            if not ban_track:
                await ctx.send("No hay baneos en seguimiento.")
                return
            description = "**Baneos Actuales:**\n"
            now = datetime.datetime.utcnow()
            for user_id_str, ban_info in ban_track.items():
                user_id = int(user_id_str)
                unban_date = datetime.datetime.fromisoformat(ban_info["unban_date"])
                remaining_time = unban_date - now
                remaining_days = remaining_time.days
                remaining_seconds = remaining_time.seconds
                remaining_hours, remaining_minutes = divmod(remaining_seconds, 3600)
                remaining_minutes, _ = divmod(remaining_minutes, 60)
                remaining_days = max(0, remaining_days)
                remaining_hours = max(0, remaining_hours)
                remaining_minutes = max(0, remaining_minutes)
                description += (
                    f"- Usuario ID: `{user_id}`, "
                    f"Días restantes: `{remaining_days}` días, "
                    f"`{remaining_hours}` horas, `{remaining_minutes}` minutos\n"
                )
            await ctx.send(description)

    @commands.command(name="countdown")
    @checks.admin_or_permissions(administrator=True)
    async def countdown_bans(self, ctx):
        """Muestra una cuenta atrás personalizada de 7 días para cada baneo."""
        guild = ctx.guild
        async with self.config.guild(guild).ban_track() as ban_track:
            if not ban_track:
                await ctx.send("No hay baneos en seguimiento.")
                return
            description = "**Cuenta Atrás de Baneos:**\n"
            now = datetime.datetime.utcnow()
            for user_id_str, ban_info in ban_track.items():
                user_id = int(user_id_str)
                unban_date = datetime.datetime.fromisoformat(ban_info["unban_date"])
                remaining_time = unban_date - now
                remaining_days = remaining_time.days
                remaining_seconds = remaining_time.seconds
                remaining_hours, remaining_minutes = divmod(remaining_seconds, 3600)
                remaining_minutes, _ = divmod(remaining_minutes, 60)
                remaining_days = max(0, remaining_days)
                remaining_hours = max(0, remaining_hours)
                remaining_minutes = max(0, remaining_minutes)
                user = guild.get_member(user_id)
                if user:
                    user_display = f"{user} (ID: {user_id})"
                else:
                    user_display = f"ID: {user_id}"
                description += (
                    f"- {user_display}: `{remaining_days}` días, "
                    f"`{remaining_hours}` horas, `{remaining_minutes}` minutos restantes\n"
                )
            await ctx.send(description)

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        """Evento que se dispara cuando un usuario es baneado."""
        ban_log_channel_id = await self.config.guild(guild).ban_log_channel()
        if ban_log_channel_id:
            ban_log_channel = guild.get_channel(ban_log_channel_id)
            if ban_log_channel:
                ban_date = datetime.datetime.utcnow()
                unban_date = ban_date + datetime.timedelta(days=7)

                # Calcular tiempo restante en formato "in X días, Y horas y Z minutos"
                remaining_time = unban_date - ban_date  # Será siempre 7 días en este punto
                remaining_days = remaining_time.days
                remaining_seconds = remaining_time.seconds
                remaining_hours, remaining_minutes = divmod(remaining_seconds, 3600)
                remaining_minutes, _ = divmod(remaining_minutes, 60)

                countdown = f"in {remaining_days} días, {remaining_hours} horas y {remaining_minutes} minutos"

                embed = discord.Embed(
                    title="🔨 Usuario Baneado",
                    color=discord.Color.red(),
                    timestamp=ban_date
                )
                embed.add_field(name="Usuario", value=f"{user.mention} (ID: {user.id})", inline=False)
                embed.add_field(name="Fecha de Baneo", value=ban_date.strftime('%Y-%m-%d %H:%M:%S UTC'), inline=False)
                embed.add_field(name="Cuenta Atrás", value=countdown, inline=False)
                await ban_log_channel.send(embed=embed)
                
                # Guardar información del baneo
                async with self.config.guild(guild).ban_track() as ban_track:
                    ban_track[str(user.id)] = {
                        "ban_date": ban_date.isoformat(),
                        "unban_date": unban_date.isoformat(),
                        "message_id": None  # Podemos guardar el ID del mensaje si lo necesitamos en el futuro
                    }

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        """Evento que se dispara cuando un usuario es desbaneado manualmente."""
        async with self.config.guild(guild).ban_track() as ban_track:
            if str(user.id) in ban_track:
                del ban_track[str(user.id)]
                # Opcional: Notificar que el usuario ha sido desbaneado antes de completar el seguimiento
                ban_log_channel_id = await self.config.guild(guild).ban_log_channel()
                if ban_log_channel_id:
                    ban_log_channel = guild.get_channel(ban_log_channel_id)
                    if ban_log_channel:
                        await ban_log_channel.send(f"🔓 **Usuario Desbaneado Manualmente:** {user.mention} (ID: {user.id})")

    @tasks.loop(hours=24)
    async def update_ban_countdown(self):
        """Actualiza la cuenta atrás de los baneos cada 24 horas."""
        for guild in self.bot.guilds:
            ban_log_channel_id = await self.config.guild(guild).ban_log_channel()
            if not ban_log_channel_id:
                continue
            ban_log_channel = guild.get_channel(ban_log_channel_id)
            if not ban_log_channel:
                continue
            async with self.config.guild(guild).ban_track() as ban_track:
                for user_id_str, ban_info in list(ban_track.items()):
                    unban_date = datetime.datetime.fromisoformat(ban_info["unban_date"])
                    now = datetime.datetime.utcnow()
                    remaining_time = unban_date - now
                    remaining_days = remaining_time.days
                    remaining_seconds = remaining_time.seconds
                    remaining_hours, remaining_minutes = divmod(remaining_seconds, 3600)
                    remaining_minutes, _ = divmod(remaining_minutes, 60)
                    remaining_days = max(0, remaining_days)
                    remaining_hours = max(0, remaining_hours)
                    remaining_minutes = max(0, remaining_minutes)

                    # Si ya pasaron los 7 días, simplemente dejamos de hacer seguimiento
                    if remaining_time.total_seconds() <= 0:
                        del ban_track[user_id_str]
                        await ban_log_channel.send(f"⏰ **El tiempo de seguimiento ha expirado para el usuario ID {user_id_str}.**")
                    else:
                        # Opcional: Podrías actualizar los mensajes de log si guardas los message_id
                        pass  # Actualmente no se actualizan los mensajes existentes

    @update_ban_countdown.before_loop
    async def before_update_ban_countdown(self):
        await self.bot.wait_until_ready()
