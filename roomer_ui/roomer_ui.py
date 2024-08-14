import discord
from redbot.core import commands, Config
from discord.ui import Button, View

class RoomerUI(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_guild = {
            "temp_channels": {},
            "interface_channel_id": None,
            "required_role": None,
        }
        self.config.register_guild(**default_guild)

    @commands.command(name="setchannel")
    @commands.admin_or_permissions(administrator=True)
    async def set_interface_channel(self, ctx, channel: discord.TextChannel):
        await self.config.guild(ctx.guild).interface_channel_id.set(channel.id)
        await ctx.send(f"Canal de interfaz establecido en {channel.mention}")

    @commands.command(name="sendUI")
    @commands.admin_or_permissions(administrator=True)
    async def send_ui(self, ctx):
        interface_channel_id = await self.config.guild(ctx.guild).interface_channel_id()
        if interface_channel_id is None:
            await ctx.send("No se ha establecido un canal para la interfaz. Usa !setchannel para establecerlo.")
            return

        channel = self.bot.get_channel(interface_channel_id)
        if channel is None:
            await ctx.send("El canal configurado no es válido.")
            return

        embed = discord.Embed(
            title="TempVoice Interface",
            description="Esta interfaz se puede usar para gestionar canales de voz temporales. Más opciones están disponibles con comandos prefijados.",
            color=0x00ff00
        )

        buttons = [
            ("NAME", discord.ButtonStyle.blurple),
            ("LIMIT", discord.ButtonStyle.blurple),
            ("PRIVACY", discord.ButtonStyle.blurple),
            ("INVITE", discord.ButtonStyle.green),
            ("KICK", discord.ButtonStyle.red),
            ("REGION", discord.ButtonStyle.blurple),
            ("BLOCK", discord.ButtonStyle.red),
            ("UNBLOCK", discord.ButtonStyle.green),
            ("CLAIM", discord.ButtonStyle.green),
            ("DELETE", discord.ButtonStyle.red),
        ]

        view = View()
        for label, style in buttons:
            button = Button(label=label, style=style)

            async def button_callback(interaction):
                await interaction.response.send_message(f"Función `{interaction.component.label}` seleccionada.", ephemeral=True)

            button.callback = button_callback
            view.add_item(button)

        await channel.send(embed=embed, view=view)

    @commands.command(name="createroom")
    @commands.admin_or_permissions(administrator=True)
    async def create_temp_voice(self, ctx):
        embed = discord.Embed(
            title="Crear Canal de Voz Temporal",
            description="Haz clic en el botón para crear un canal de voz temporal.",
            color=0x00ff00
        )
        button = Button(label="Crear Canal", style=discord.ButtonStyle.green)
        view = View()
        view.add_item(button)

        async def button_callback(interaction):
            category = discord.utils.get(ctx.guild.categories, name="Temporary Channels")
            if not category:
                category = await ctx.guild.create_category("Temporary Channels")

            channel = await ctx.guild.create_voice_channel(name=f"Canal de {ctx.author.name}", category=category)
            async with self.config.guild(ctx.guild).temp_channels() as temp_channels:
                temp_channels[channel.id] = channel.id

            await interaction.response.send_message(f"Canal de voz '{channel.name}' creado con éxito.", ephemeral=True)
            await self.manage_temp_voice(ctx, channel)

        button.callback = button_callback
        await ctx.send(embed=embed, view=view)

    async def manage_temp_voice(self, ctx, channel):
        embed = discord.Embed(
            title="Gestionar Canal de Voz Temporal",
            description="Usa los botones para administrar tu canal.",
            color=0x00ff00
        )

        name_button = Button(label="Nombre", style=discord.ButtonStyle.blurple)
        limit_button = Button(label="Límite", style=discord.ButtonStyle.blurple)
        privacy_button = Button(label="Privacidad", style=discord.ButtonStyle.blurple)
        invite_button = Button(label="Invitar", style=discord.ButtonStyle.green)
        kick_button = Button(label="Expulsar", style=discord.ButtonStyle.red)
        region_button = Button(label="Región", style=discord.ButtonStyle.blurple)
        block_button = Button(label="Bloquear", style=discord.ButtonStyle.red)
        unblock_button = Button(label="Desbloquear", style=discord.ButtonStyle.green)
        claim_button = Button(label="Reclamar", style=discord.ButtonStyle.green)
        delete_button = Button(label="Eliminar", style=discord.ButtonStyle.red)

        view = View()
        buttons = [name_button, limit_button, privacy_button, invite_button, kick_button, region_button, block_button, unblock_button, claim_button, delete_button]
        for button in buttons:
            view.add_item(button)

        async def name_callback(interaction):
            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel
            await interaction.response.send_message("Escribe el nuevo nombre del canal:", ephemeral=True)
            new_name_msg = await self.bot.wait_for('message', check=check)
            new_name = new_name_msg.content
            await channel.edit(name=new_name)
            await ctx.send(f"Canal renombrado a '{new_name}'.")

        async def limit_callback(interaction):
            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel
            await interaction.response.send_message("Escribe el nuevo límite de usuarios (número):", ephemeral=True)
            limit_msg = await self.bot.wait_for('message', check=check)
            limit = int(limit_msg.content)
            await channel.edit(user_limit=limit)
            await ctx.send(f"Límite de usuarios establecido en '{limit}'.")

        async def privacy_callback(interaction):
            await interaction.response.send_message("Alternando privacidad del canal.", ephemeral=True)
            overwrite = channel.overwrites_for(ctx.guild.default_role)
            overwrite.connect = not overwrite.connect
            await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
            await ctx.send(f"Privacidad del canal {'habilitada' if overwrite.connect else 'deshabilitada'}.")

        async def invite_callback(interaction):
            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel
            await interaction.response.send_message("Menciona al usuario que deseas invitar:", ephemeral=True)
            invite_msg = await self.bot.wait_for('message', check=check)
            user = invite_msg.mentions[0]
            overwrite = channel.overwrites_for(user)
            overwrite.connect = True
            await channel.set_permissions(user, overwrite=overwrite)
            await ctx.send(f"{user.name} ha sido invitado al canal.")

        async def kick_callback(interaction):
            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel
            await interaction.response.send_message("Menciona al usuario que deseas expulsar:", ephemeral=True)
            kick_msg = await self.bot.wait_for('message', check=check)
            user = kick_msg.mentions[0]
            overwrite = channel.overwrites_for(user)
            overwrite.connect = False
            await channel.set_permissions(user, overwrite=overwrite)
            await ctx.send(f"{user.name} ha sido expulsado del canal.")

        async def region_callback(interaction):
            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel
            await interaction.response.send_message("Escribe la región del servidor (ej. us-west, eu-central):", ephemeral=True)
            region_msg = await self.bot.wait_for('message', check=check)
            region = region_msg.content
            await channel.edit(rtc_region=region)
            await ctx.send(f"Región del canal establecida en '{region}'.")

        async def block_callback(interaction):
            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel
            await interaction.response.send_message("Menciona al usuario que deseas bloquear:", ephemeral=True)
            block_msg = await self.bot.wait_for('message', check=check)
            user = block_msg.mentions[0]
            overwrite = channel.overwrites_for(user)
            overwrite.connect = False
            await channel.set_permissions(user, overwrite=overwrite)
            await interaction.followup.send(f"{user.name} ha sido bloqueado del canal.")

        async def unblock_callback(interaction):
            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel
            await interaction.response.send_message("Menciona al usuario que deseas desbloquear:", ephemeral=True)
            unblock_msg = await self.bot.wait_for('message', check=check)
            user = unblock_msg.mentions[0]
            overwrite = channel.overwrites_for(user)
            overwrite.connect = True
            await channel.set_permissions(user, overwrite=overwrite)
            await interaction.followup.send(f"{user.name} ha sido desbloqueado del canal.")

        async def claim_callback(interaction):
            await interaction.response.send_message(f"Reclamando el canal {channel.name}.", ephemeral=True)
            self.temp_channels[channel.id] = channel
            await interaction.followup.send(f"Canal '{channel.name}' ha sido reclamado.")

        async def delete_callback(interaction):
            await interaction.response.send_message(f"Eliminando el canal {channel.name}.", ephemeral=True)
            await channel.delete()
            del self.temp_channels[channel.id]
            await interaction.followup.send(f"Canal '{channel.name}' ha sido eliminado.")

        # Asignar los callbacks a los botones
        name_button.callback = name_callback
        limit_button.callback = limit_callback
        privacy_button.callback = privacy_callback
        invite_button.callback = invite_callback
        kick_button.callback = kick_callback
        region_button.callback = region_callback
        block_button.callback = block_callback
        unblock_button.callback = unblock_callback
        claim_button.callback = claim_callback
        delete_button.callback = delete_callback

        await ctx.send(embed=embed, view=view)
