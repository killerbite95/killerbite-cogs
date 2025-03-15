import discord
from redbot.core import commands, Config, checks
import typing
import logging

# Importamos la integración del dashboard
from .dashboard_integration import DashboardIntegration, dashboard_page

logger = logging.getLogger("red.trini.simplesuggestions")

class SimpleSuggestions(DashboardIntegration, commands.Cog):
    """Cog para gestionar sugerencias en un canal de Discord. By Killerbite95"""
    __author__ = "Killerbite95"  # Aquí se declara el autor
    
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_guild = {
            "suggestion_channel": None,
            "log_channel": None,
            "suggestion_threads": False,
            "thread_auto_archive": False,
            "suggestion_id": 1,
            "suggestions": {}  # Diccionario para almacenar sugerencias por message ID
        }
        self.config.register_guild(**default_guild)

    @commands.command(name="setsuggestionchannel")
    @checks.admin_or_permissions(administrator=True)
    async def set_suggestion_channel(self, ctx, channel: discord.TextChannel):
        """Establece el canal de sugerencias."""
        await self.config.guild(ctx.guild).suggestion_channel.set(channel.id)
        await ctx.send(f"Canal de sugerencias establecido en {channel.mention}.")

    @commands.command(name="setlogchannel")
    @checks.admin_or_permissions(administrator=True)
    async def set_log_channel(self, ctx, channel: discord.TextChannel):
        """Establece el canal de logs de sugerencias."""
        await self.config.guild(ctx.guild).log_channel.set(channel.id)
        await ctx.send(f"Canal de logs de sugerencias establecido en {channel.mention}.")

    @commands.command(name="suggest")
    async def suggest(self, ctx, *, suggestion: str):
        """Envía una sugerencia al canal designado."""
        suggestion_channel_id = await self.config.guild(ctx.guild).suggestion_channel()
        if suggestion_channel_id is None:
            await ctx.send("El canal de sugerencias no ha sido configurado.")
            return

        suggestion_channel = self.bot.get_channel(suggestion_channel_id)
        if suggestion_channel is None:
            await ctx.send("El canal de sugerencias configurado no es válido.")
            return

        suggestion_id = await self.config.guild(ctx.guild).suggestion_id()
        embed = discord.Embed(
            title=f"Sugerencia #{suggestion_id}",
            description=suggestion,
            color=discord.Color.blue()
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        message = await suggestion_channel.send(embed=embed)
        
        # Añadir reacciones 👍 y 👎
        await message.add_reaction("👍")
        await message.add_reaction("👎")
        
        await self.config.guild(ctx.guild).suggestion_id.set(suggestion_id + 1)
        
        # Almacenar la sugerencia en config (usando el ID del mensaje)
        suggestions = await self.config.guild(ctx.guild).suggestions()
        suggestions[str(message.id)] = {
            "suggestion_id": suggestion_id,
            "content": suggestion,
            "author": ctx.author.id,
            "status": "Pendiente"
        }
        await self.config.guild(ctx.guild).suggestions.set(suggestions)

        if await self.config.guild(ctx.guild).suggestion_threads():
            await message.create_thread(name=f"Sugerencia #{suggestion_id}", auto_archive_duration=1440)

        await ctx.send("Tu sugerencia ha sido enviada.")

    @commands.command(name="approve")
    @checks.admin_or_permissions(administrator=True)
    async def approve_suggestion(self, ctx, message_id: int):
        """Aprueba una sugerencia."""
        suggestion_channel_id = await self.config.guild(ctx.guild).suggestion_channel()
        suggestion_channel = self.bot.get_channel(suggestion_channel_id)
        if suggestion_channel is None:
            await ctx.send("El canal de sugerencias configurado no es válido.")
            return

        try:
            message = await suggestion_channel.fetch_message(message_id)
            embed = message.embeds[0]
            embed.color = discord.Color.green()
            embed.set_footer(text="Aprobado")
            await message.edit(embed=embed)

            # Archivar el hilo si existe
            if message.thread and await self.config.guild(ctx.guild).thread_auto_archive():
                await message.thread.edit(archived=True, locked=True)

            # Actualizar en config
            suggestions = await self.config.guild(ctx.guild).suggestions()
            if str(message_id) in suggestions:
                suggestions[str(message_id)]["status"] = "Aprobado"
                await self.config.guild(ctx.guild).suggestions.set(suggestions)
            
            await ctx.send("Sugerencia aprobada.")
        except discord.NotFound:
            await ctx.send("No se encontró un mensaje con ese ID en el canal de sugerencias.")

    @commands.command(name="deny")
    @checks.admin_or_permissions(administrator=True)
    async def deny_suggestion(self, ctx, message_id: int):
        """Rechaza una sugerencia."""
        suggestion_channel_id = await self.config.guild(ctx.guild).suggestion_channel()
        suggestion_channel = self.bot.get_channel(suggestion_channel_id)
        if suggestion_channel is None:
            await ctx.send("El canal de sugerencias configurado no es válido.")
            return

        try:
            message = await suggestion_channel.fetch_message(message_id)
            embed = message.embeds[0]
            embed.color = discord.Color.red()
            embed.set_footer(text="Rechazado")
            await message.edit(embed=embed)

            # Archivar el hilo si existe
            if message.thread and await self.config.guild(ctx.guild).thread_auto_archive():
                await message.thread.edit(archived=True, locked=True)

            # Actualizar en config
            suggestions = await self.config.guild(ctx.guild).suggestions()
            if str(message_id) in suggestions:
                suggestions[str(message_id)]["status"] = "Rechazado"
                await self.config.guild(ctx.guild).suggestions.set(suggestions)
            
            await ctx.send("Sugerencia rechazada.")
        except discord.NotFound:
            await ctx.send("No se encontró un mensaje con ese ID en el canal de sugerencias.")

    @commands.command(name="togglesuggestionthreads")
    @checks.admin_or_permissions(administrator=True)
    async def toggle_suggestion_threads(self, ctx):
        """Activa o desactiva la creación de hilos para nuevas sugerencias."""
        current = await self.config.guild(ctx.guild).suggestion_threads()
        await self.config.guild(ctx.guild).suggestion_threads.set(not current)
        state = "activado" if not current else "desactivado"
        await ctx.send(f"La creación de hilos para nuevas sugerencias ha sido {state}.")

    @commands.command(name="togglethreadarchive")
    @checks.admin_or_permissions(administrator=True)
    async def toggle_thread_archive(self, ctx):
        """Activa o desactiva el archivado automático de hilos creados para sugerencias."""
        current = await self.config.guild(ctx.guild).thread_auto_archive()
        await self.config.guild(ctx.guild).thread_auto_archive.set(not current)
        state = "activado" if not current else "desactivado"
        await ctx.send(f"El archivado automático de hilos ha sido {state}.")

    @commands.command(name="editsuggest")
    async def edit_suggestion(self, ctx, message_id: int, *, new_suggestion: str):
        """Permite a un usuario editar su sugerencia."""
        suggestion_channel_id = await self.config.guild(ctx.guild).suggestion_channel()
        suggestion_channel = self.bot.get_channel(suggestion_channel_id)
        if suggestion_channel is None:
            await ctx.send("El canal de sugerencias configurado no es válido.")
            return

        try:
            message = await suggestion_channel.fetch_message(message_id)
            embed = message.embeds[0]

            if message.author != self.bot.user or embed.author.name != ctx.author.display_name:
                await ctx.send("No puedes editar esta sugerencia porque no eres el autor.")
                return

            # Verificar si la sugerencia ya ha sido aprobada o rechazada
            if embed.footer and (embed.footer.text == "Aprobado" or embed.footer.text == "Rechazado"):
                await ctx.send("No puedes editar una sugerencia que ya ha sido aprobada o rechazada.")
                return

            embed.description = new_suggestion
            await message.edit(embed=embed)
            # Actualizar en config
            suggestions = await self.config.guild(ctx.guild).suggestions()
            if str(message_id) in suggestions:
                suggestions[str(message_id)]["content"] = new_suggestion
                await self.config.guild(ctx.guild).suggestions.set(suggestions)
            await ctx.send("Tu sugerencia ha sido editada.")
        except discord.NotFound:
            await ctx.send("No se encontró un mensaje con ese ID en el canal de sugerencias.")

    # -------------------- Dashboard Integration --------------------
    @dashboard_page(name="view_suggestions", description="Ver sugerencias actuales")
    async def rpc_view_suggestions(self, guild_id: int, **kwargs) -> typing.Dict[str, typing.Any]:
        """
        Página del dashboard para ver las sugerencias actuales.
        Se espera que se pase 'guild_id' (int) en los kwargs.
        """
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return {"status": 1, "error": "Guild no encontrada."}
        suggestions = await self.config.guild(guild).suggestions()
        html_content = """
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css"
              integrity="sha384-ENjdO4Dr2bkBIFxQG+8exIg2knQW4PuAtf3y5PxC5bl80k4CL8nAeZp3rNZZ8VC3"
              crossorigin="anonymous">
        <div class="container mt-4">
          <h1 class="mb-4">Sugerencias actuales</h1>
          <table class="table table-bordered table-striped">
            <thead class="table-dark">
              <tr>
                <th scope="col">ID Mensaje</th>
                <th scope="col">ID Sugerencia</th>
                <th scope="col">Contenido</th>
                <th scope="col">Autor</th>
                <th scope="col">Estado</th>
              </tr>
            </thead>
            <tbody>
        """
        for msg_id, data in suggestions.items():
            author = self.bot.get_user(data.get("author"))
            author_name = author.display_name if author else "Desconocido"
            html_content += f"""
              <tr>
                <td>{msg_id}</td>
                <td>{data.get("suggestion_id")}</td>
                <td>{data.get("content")}</td>
                <td>{author_name}</td>
                <td>{data.get("status")}</td>
              </tr>
            """
        html_content += """
            </tbody>
          </table>
        </div>
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"
                integrity="sha384-pp6GQyJP0XKHTS0rphZo5hBjbgJf9HrYi7wkN8k82RBnANn7LkZ6A9E8M8AP52Ze"
                crossorigin="anonymous"></script>
        """
        return {"status": 0, "web_content": {"source": html_content}}

    @dashboard_page(name="approve_suggestion", description="Aprueba una sugerencia", methods=("GET", "POST"))
    async def rpc_approve_suggestion(self, guild_id: int, **kwargs) -> typing.Dict[str, typing.Any]:
        """
        Página del dashboard para aprobar una sugerencia.
        Se espera que se pase 'guild_id' (int) en los kwargs.
        """
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return {"status": 1, "error": "Guild no encontrada."}
        import wtforms
        class ApproveForm(kwargs["Form"]):
            message_id = wtforms.IntegerField("ID del mensaje", validators=[wtforms.validators.InputRequired()])
            submit = wtforms.SubmitField("Aprobar Sugerencia")
        form = ApproveForm()
        if form.validate_on_submit():
            msg_id = form.message_id.data
            suggestion_channel_id = await self.config.guild(guild).suggestion_channel()
            suggestion_channel = self.bot.get_channel(suggestion_channel_id)
            if suggestion_channel is None:
                return {"status": 1, "error": "El canal de sugerencias configurado no es válido."}
            try:
                message = await suggestion_channel.fetch_message(msg_id)
                embed = message.embeds[0]
                embed.color = discord.Color.green()
                embed.set_footer(text="Aprobado")
                await message.edit(embed=embed)
                if message.thread and await self.config.guild(guild).thread_auto_archive():
                    await message.thread.edit(archived=True, locked=True)
                suggestions = await self.config.guild(guild).suggestions()
                if str(msg_id) in suggestions:
                    suggestions[str(msg_id)]["status"] = "Aprobado"
                    await self.config.guild(guild).suggestions.set(suggestions)
                return {"status": 0, "notifications": [{"message": "Sugerencia aprobada.", "category": "success"}], "redirect_url": kwargs["request_url"]}
            except discord.NotFound:
                return {"status": 1, "error": "No se encontró el mensaje con ese ID."}
        source = "{{ form|safe }}"
        return {"status": 0, "web_content": {"source": source, "form": form}}

    @dashboard_page(name="deny_suggestion", description="Rechaza una sugerencia", methods=("GET", "POST"))
    async def rpc_deny_suggestion(self, guild_id: int, **kwargs) -> typing.Dict[str, typing.Any]:
        """
        Página del dashboard para rechazar una sugerencia.
        Se espera que se pase 'guild_id' (int) en los kwargs.
        """
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return {"status": 1, "error": "Guild no encontrada."}
        import wtforms
        class DenyForm(kwargs["Form"]):
            message_id = wtforms.IntegerField("ID del mensaje", validators=[wtforms.validators.InputRequired()])
            submit = wtforms.SubmitField("Rechazar Sugerencia")
        form = DenyForm()
        if form.validate_on_submit():
            msg_id = form.message_id.data
            suggestion_channel_id = await self.config.guild(guild).suggestion_channel()
            suggestion_channel = self.bot.get_channel(suggestion_channel_id)
            if suggestion_channel is None:
                return {"status": 1, "error": "El canal de sugerencias configurado no es válido."}
            try:
                message = await suggestion_channel.fetch_message(msg_id)
                embed = message.embeds[0]
                embed.color = discord.Color.red()
                embed.set_footer(text="Rechazado")
                await message.edit(embed=embed)
                if message.thread and await self.config.guild(guild).thread_auto_archive():
                    await message.thread.edit(archived=True, locked=True)
                suggestions = await self.config.guild(guild).suggestions()
                if str(msg_id) in suggestions:
                    suggestions[str(msg_id)]["status"] = "Rechazado"
                    await self.config.guild(guild).suggestions.set(suggestions)
                return {"status": 0, "notifications": [{"message": "Sugerencia rechazada.", "category": "success"}], "redirect_url": kwargs["request_url"]}
            except discord.NotFound:
                return {"status": 1, "error": "No se encontró el mensaje con ese ID."}
        source = "{{ form|safe }}"
        return {"status": 0, "web_content": {"source": source, "form": form}}

def setup(bot):
    bot.add_cog(SimpleSuggestions(bot))
