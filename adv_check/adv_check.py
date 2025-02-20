import logging
from datetime import datetime, timezone

import discord
from redbot.core import checks, commands, Config
from redbot.core.i18n import Translator, cog_i18n

_ = Translator("AdvCheck", __file__)

@cog_i18n(_)
class Check(commands.Cog):
    """Cog avanzado para realizar verificaciones completas en usuarios con UI interactiva y soporte para Slash Commands.
    
    Este cog muestra información básica, roles, fecha de ingreso, avatar, permisos, actividad
    y sanciones. En el apartado de sanciones se obtiene la información de baneos del cog de baneos
    (PruneBans) y los warnings del propio Red (si el cog de moderación está cargado).
    """
    __version__ = "2.3.0"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.log = logging.getLogger("red.cog.adv_check")

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nVersion: {self.__version__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        # Este cog no almacena datos de usuario.
        return

    @commands.hybrid_command(name="advcheck", aliases=["check"], with_app_command=True)
    @checks.mod()
    @commands.max_concurrency(1, commands.BucketType.guild)
    async def advcheck(self, ctx: commands.Context, member: discord.Member):
        """
        Realiza una verificación completa del usuario especificado.

        Muestra una UI interactiva (mensaje ephemeral) para navegar entre:
          • Información Básica
          • Roles
          • Fecha de Ingreso
          • Avatar
          • Permisos
          • Actividad
          • Sanciones
        """
        # Construir los embeds para cada sección (todos menos "sanciones" son síncronos)
        embeds = {
            "basic": self._build_basic_info(member),
            "roles": self._build_roles_embed(member),
            "join_date": self._build_join_date_embed(member),
            "avatar": self._build_avatar_embed(member),
            "permissions": self._build_permissions_embed(member),
            "activity": self._build_activity_embed(member)
        }
        # El apartado de sanciones requiere consultas asíncronas:
        embeds["sanctions"] = await self._build_sanctions_embed(member)

        view = CheckView(member, embeds)
        await ctx.send(embed=embeds["basic"], view=view, ephemeral=True)

    def _build_basic_info(self, member: discord.Member) -> discord.Embed:
        """Crea un embed con información básica del usuario (sin discriminador)."""
        embed = discord.Embed(
            title=_("Información Básica de {member}").format(member=member.display_name),
            color=member.color
        )
        embed.add_field(name=_("ID"), value=str(member.id), inline=True)
        embed.add_field(name=_("Nombre"), value=member.name, inline=True)
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
            now = datetime.now(tz=timezone.utc)
            delta = now - join_date
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

    async def _build_sanctions_embed(self, member: discord.Member) -> discord.Embed:
        """Crea un embed con las sanciones registradas del usuario.

        Se obtiene la información de baneos del cog PruneBans y los warnings del cog de moderación (Mod).
        """
        # Obtener información de baneos desde el cog PruneBans
        ban_info_str = "No hay baneos registrados."
        prune_cog = self.bot.get_cog("PruneBans")
        if prune_cog is not None:
            ban_conf = Config.get_conf(prune_cog, identifier=1234567890)
            ban_track = await ban_conf.guild(member.guild).ban_track()
            if str(member.id) in ban_track:
                info = ban_track[str(member.id)]
                ban_date = info.get("ban_date", "Desconocido")
                unban_date = info.get("unban_date", "Desconocido")
                balance = info.get("balance", "Desconocido")
                ban_info_str = (
                    f"**Baneado:** Sí\n"
                    f"**Fecha de baneo:** {ban_date}\n"
                    f"**Fecha de finalización:** {unban_date}\n"
                    f"**Créditos:** {balance}"
                )
        else:
            ban_info_str = "No se encontró el cog de baneos."
        
        # Obtener warnings del cog de moderación (Mod)
        warnings_info = "No hay warnings registrados."
        mod_cog = self.bot.get_cog("Mod")
        if mod_cog is not None:
            try:
                # Se asume que la configuración del Mod cog guarda los warns en 'warns'
                warns = await mod_cog.config.member(member).warns()
                if warns:
                    warnings_info = f"{len(warns)} warning(s) registrado(s)."
                else:
                    warnings_info = "No hay warnings registrados."
            except Exception:
                warnings_info = "No se pudo obtener la información de warnings."
        else:
            warnings_info = "El cog de moderación (Mod) no está cargado."
        
        description = f"{ban_info_str}\n\n**Warnings:** {warnings_info}"
        embed = discord.Embed(
            title=_("Sanciones de {member}").format(member=member.display_name),
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
            discord.SelectOption(label="ℹ️ Básica", value="basic"),
            discord.SelectOption(label="👥 Roles", value="roles"),
            discord.SelectOption(label="📅 Ingreso", value="join_date"),
            discord.SelectOption(label="🖼️ Avatar", value="avatar"),
            discord.SelectOption(label="🛡️ Permisos", value="permissions"),
            discord.SelectOption(label="⚡ Actividad", value="activity"),
            discord.SelectOption(label="🚫 Sanciones", value="sanctions")
        ]
    )
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        """Actualiza el embed mostrado según la selección."""
        value = select.values[0]
        embed = self.embeds.get(value)
        if embed:
            await interaction.response.edit_message(embed=embed)
        else:
            await interaction.response.send_message(_("No se encontró la sección seleccionada."), ephemeral=True)
