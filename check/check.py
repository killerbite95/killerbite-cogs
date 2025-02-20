import logging
from datetime import datetime

import discord
from redbot.core import checks, commands
from redbot.core.i18n import Translator, cog_i18n

_ = Translator("Check", __file__)

@cog_i18n(_)
class Check(commands.Cog):
    """Cog para realizar verificaciones completas en usuarios con UI interactiva y soporte para Slash Commands.
    
    Este cog permite obtener información básica, roles, fecha de ingreso, avatar, permisos y actividad,
    todo integrado en una UI interactiva que utiliza componentes de Discord.
    """
    __version__ = "2.3.0"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.log = logging.getLogger("red.cog.dav-cogs.check")

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nVersion: {self.__version__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        # Este cog no almacena datos de usuario.
        return

    @commands.hybrid_command(name="check", with_app_command=True)
    @checks.mod()
    @commands.max_concurrency(1, commands.BucketType.guild)
    async def check(self, ctx: commands.Context, member: discord.Member):
        """
        Realiza una verificación completa del usuario especificado.

        Muestra una UI interactiva para navegar entre:
          • Información Básica
          • Roles
          • Fecha de Ingreso
          • Avatar
          • Permisos
          • Actividad
        """
        # Construir los embeds para cada sección
        embeds = {
            "basic": self._build_basic_info(member),
            "roles": self._build_roles_embed(member),
            "join_date": self._build_join_date_embed(member),
            "avatar": self._build_avatar_embed(member),
            "permissions": self._build_permissions_embed(member),
            "activity": self._build_activity_embed(member)
        }
        view = CheckView(member, embeds)
        # Envía el mensaje inicial con la información básica y la UI interactiva
        await ctx.send(embed=embeds["basic"], view=view)

    def _build_basic_info(self, member: discord.Member) -> discord.Embed:
        """Crea un embed con información básica del usuario."""
        embed = discord.Embed(
            title=_("Información Básica de {member}").format(member=member.display_name),
            color=member.color
        )
        embed.add_field(name=_("ID"), value=str(member.id), inline=True)
        embed.add_field(name=_("Nombre"), value=member.name, inline=True)
        embed.add_field(name=_("Discriminador"), value=member.discriminator, inline=True)
        embed.add_field(name=_("Estado"), value=str(member.status).title(), inline=True)
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        return embed

    def _build_roles_embed(self, member: discord.Member) -> discord.Embed:
        """Crea un embed que muestra los roles asignados (excluyendo @everyone)."""
        roles = [role.mention for role in member.roles if role.name != "@everyone"]
        description = ", ".join(roles) if roles else _("No tiene roles asignados.")
        embed = discord.Embed(
            title=_("Roles de {member}").format(member=member.display_name),
            description=description,
            color=member.color
        )
        return embed

    def _build_join_date_embed(self, member: discord.Member) -> discord.Embed:
        """Crea un embed con la fecha de ingreso del usuario al servidor."""
        join_date = member.joined_at
        if join_date:
            delta = datetime.utcnow() - join_date
            description = _("Se unió el {date} (hace {days} días)").format(
                date=join_date.strftime("%d/%m/%Y %H:%M:%S"),
                days=delta.days
            )
        else:
            description = _("La fecha de ingreso no está disponible.")
        embed = discord.Embed(
            title=_("Fecha de Ingreso de {member}").format(member=member.display_name),
            description=description,
            color=member.color
        )
        return embed

    def _build_avatar_embed(self, member: discord.Member) -> discord.Embed:
        """Crea un embed que muestra el avatar actual del usuario."""
        avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
        embed = discord.Embed(
            title=_("Avatar de {member}").format(member=member.display_name),
            color=member.color
        )
        embed.set_image(url=avatar_url)
        return embed

    def _build_permissions_embed(self, member: discord.Member) -> discord.Embed:
        """Crea un embed que lista los permisos activos del usuario en el servidor."""
        perms = member.guild_permissions
        active_perms = [perm.replace("_", " ").title() for perm, value in perms if value]
        description = ", ".join(active_perms) if active_perms else _("No tiene permisos especiales.")
        embed = discord.Embed(
            title=_("Permisos de {member}").format(member=member.display_name),
            description=description,
            color=member.color
        )
        return embed

    def _build_activity_embed(self, member: discord.Member) -> discord.Embed:
        """Crea un embed que muestra la actividad actual del usuario."""
        status = str(member.status).title()
        description = _("Estado: {status}\n").format(status=status)
        if member.activity:
            activity = member.activity
            description += _("Actividad: {name}").format(name=activity.name)
            if getattr(activity, "details", None):
                description += f" - {activity.details}"
        else:
            description += _("No tiene actividad registrada.")
        embed = discord.Embed(
            title=_("Actividad de {member}").format(member=member.display_name),
            description=description,
            color=member.color
        )
        return embed

class CheckView(discord.ui.View):
    """Vista interactiva para navegar por la información del usuario."""
    def __init__(self, member: discord.Member, embeds: dict, timeout: float = 120.0):
        super().__init__(timeout=timeout)
        self.member = member
        self.embeds = embeds

    @discord.ui.select(
        placeholder="Selecciona una sección",
        options=[
            discord.SelectOption(label="Información Básica", value="basic"),
            discord.SelectOption(label="Roles", value="roles"),
            discord.SelectOption(label="Fecha de Ingreso", value="join_date"),
            discord.SelectOption(label="Avatar", value="avatar"),
            discord.SelectOption(label="Permisos", value="permissions"),
            discord.SelectOption(label="Actividad", value="activity")
        ]
    )
    async def select_callback(self, select: discord.ui.Select, interaction: discord.Interaction):
        """Callback que actualiza el embed mostrado según la selección."""
        value = select.values[0]
        embed = self.embeds.get(value)
        if embed:
            await interaction.response.edit_message(embed=embed)
        else:
            await interaction.response.send_message(_("No se encontró la sección seleccionada."), ephemeral=True)

    @discord.ui.button(label="Cerrar", style=discord.ButtonStyle.red)
    async def close_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        """Botón para cerrar la interfaz interactiva."""
        await interaction.message.delete()
        self.stop()
