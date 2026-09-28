import logging
from typing import Optional
from datetime import datetime, timezone

import discord
from redbot.core import checks, commands, Config
from redbot.core.i18n import Translator, cog_i18n, set_contextual_locales_from_guild
from .dashboard_integration import DashboardIntegration

_ = Translator("AdvCheck", __file__)

@cog_i18n(_)
class Check(DashboardIntegration, commands.Cog):
    """Advanced cog to run full checks on users with an interactive UI and Slash Command support.

    Shows basic info, roles, join date, avatar, permissions, activity
    and sanctions. The sanctions section reads the real ban data
    (from the PruneBans ban cog) and silently runs the warnings command.
    """
    __version__ = "2.3.0"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.log = logging.getLogger("red.cog.adv_check")

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre_processed = super().format_help_for_context(ctx)
        return _("{pre_processed}\n\nVersion: {version}").format(pre_processed=pre_processed, version=self.__version__)

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        # Este cog no almacena datos de usuario.
        return

    @commands.hybrid_command(name="advcheck", aliases=["check"], with_app_command=True)
    @checks.mod()
    @commands.max_concurrency(1, commands.BucketType.guild)
    async def advcheck(self, ctx: commands.Context, member: discord.Member):
        """Run a full check on the given user.

        Shows an interactive UI (ephemeral message) to browse:
          • Basic info
          • Roles
          • Join date
          • Avatar
          • Permissions
          • Activity
          • Sanctions
        """
        embeds = {
            "basic": self._build_basic_info(member),
            "roles": self._build_roles_embed(member),
            "join_date": self._build_join_date_embed(member),
            "avatar": self._build_avatar_embed(member),
            "permissions": self._build_permissions_embed(member),
            "activity": self._build_activity_embed(member)
        }
        # Se obtiene el apartado de sanciones de forma asíncrona, pasando el ctx para poder invocar el comando de warnings.
        embeds["sanctions"] = await self._build_sanctions_embed(ctx, member)

        for embed in embeds.values():
            if embed.description and len(embed.description) > 4000:
                embed.description = embed.description[:3990] + "\n…"
        view = CheckView(ctx.author.id, member, embeds)
        view.message = await ctx.send(embed=embeds["basic"], view=view, ephemeral=True)

    def _build_basic_info(self, member: discord.Member) -> discord.Embed:
        """Crea un embed con información básica del usuario (sin discriminador)."""
        embed = discord.Embed(
            title=_("Basic info of {member}").format(member=member.display_name),
            color=member.color
        )
        embed.add_field(name=_("ID"), value=str(member.id), inline=True)
        embed.add_field(name=_("Name"), value=member.name, inline=True)
        embed.add_field(name=_("Status"), value=str(member.status).title(), inline=True)
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        return embed

    def _build_roles_embed(self, member: discord.Member) -> discord.Embed:
        """Crea un embed que muestra los roles asignados (excluyendo @everyone)."""
        roles = [role.mention for role in member.roles if role.name != "@everyone"]
        description = ", ".join(roles) if roles else _("Has no roles.")
        embed = discord.Embed(
            title=_("Roles of {member}").format(member=member.display_name),
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
            description = _("Joined on {date} ({days} days ago)").format(
                date=join_date.strftime("%d/%m/%Y %H:%M:%S"),
                days=delta.days
            )
        else:
            description = _("The join date is not available.")
        embed = discord.Embed(
            title=_("Join date of {member}").format(member=member.display_name),
            description=description,
            color=member.color
        )
        return embed

    def _build_avatar_embed(self, member: discord.Member) -> discord.Embed:
        """Crea un embed que muestra el avatar actual del usuario."""
        avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
        embed = discord.Embed(
            title=_("Avatar of {member}").format(member=member.display_name),
            color=member.color
        )
        embed.set_image(url=avatar_url)
        return embed

    def _build_permissions_embed(self, member: discord.Member) -> discord.Embed:
        """Crea un embed que lista los permisos activos del usuario en el servidor."""
        perms = member.guild_permissions
        active_perms = [perm.replace("_", " ").title() for perm, value in perms if value]
        description = ", ".join(active_perms) if active_perms else _("Has no special permissions.")
        embed = discord.Embed(
            title=_("Permissions of {member}").format(member=member.display_name),
            description=description,
            color=member.color
        )
        return embed

    def _build_activity_embed(self, member: discord.Member) -> discord.Embed:
        """Crea un embed que muestra la actividad actual del usuario."""
        status = str(member.status).title()
        description = _("Status: {status}\n").format(status=status)
        if member.activity:
            activity = member.activity
            description += _("Activity: {name}").format(name=activity.name)
            if getattr(activity, "details", None):
                description += f" - {activity.details}"
        else:
            description += _("No activity recorded.")
        embed = discord.Embed(
            title=_("Activity of {member}").format(member=member.display_name),
            description=description,
            color=member.color
        )
        return embed

    async def _build_sanctions_embed(self, ctx: commands.Context, member: discord.Member) -> discord.Embed:
        """Crea un embed con las sanciones registradas del usuario.
        
        Se obtiene la información de baneos del cog PruneBans y se invoca el comando de warnings de forma invisible.
        """
        # Obtener información de baneos desde el cog PruneBans
        ban_info_str = _("No bans recorded.")
        prune_cog = self.bot.get_cog("PruneBans")
        if prune_cog is not None:
            ban_conf = Config.get_conf(prune_cog, identifier=1234567890)
            ban_track = await ban_conf.guild(member.guild).ban_track()
            if str(member.id) in ban_track:
                info = ban_track[str(member.id)]
                ban_date = info.get("ban_date", "Desconocido")
                unban_date = info.get("unban_date", "Desconocido")
                balance = info.get("balance", "Desconocido")
                ban_info_str = _("**Banned:** Yes\n**Ban date:** {ban_date}\n**Cleanup date:** {unban_date}\n**Credits:** {balance}").format(ban_date=ban_date, unban_date=unban_date, balance=balance)
        else:
            ban_info_str = _("The ban cog was not found.")
        
        # Obtener warnings ejecutando el comando "warnings" de forma invisible
        warnings_info = _("No warnings recorded.")
        warns_cmd = self.bot.get_command("warnings")
        if warns_cmd is not None:
            captured = []
            # Guardar la función original para restaurarla después
            original_send = ctx.send

            async def fake_send(content=None, **kwargs):
                if content:
                    captured.append(content)

            ctx.send = fake_send
            try:
                # Invoca el comando warnings, pasando el miembro
                await ctx.invoke(warns_cmd, member=member)
            except Exception:
                warnings_info = _("Error while getting warnings.")
            finally:
                ctx.send = original_send
            if captured:
                warnings_info = "\n".join(captured)
        else:
            warnings_info = _("The warnings command is not available.")
        
        description = _("{ban_info_str}\n\n**Warnings:** {warnings_info}").format(ban_info_str=ban_info_str, warnings_info=warnings_info)
        embed = discord.Embed(
            title=_("Sanctions of {member}").format(member=member.display_name),
            description=description,
            color=member.color
        )
        return embed

class CheckView(discord.ui.View):
    """Vista interactiva para navegar por la información del usuario."""
    def __init__(self, author_id: int, member: discord.Member, embeds: dict, timeout: float = 120.0):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.member = member
        self.embeds = embeds
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        await set_contextual_locales_from_guild(interaction.client, interaction.guild)
        # Con el prefijo el mensaje es publico: solo quien lanzo el check puede navegar.
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                _("Only whoever ran the command can use this menu."), ephemeral=True
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @discord.ui.select(
        placeholder=_("Choose a section"),
        options=[
            discord.SelectOption(label=_("ℹ️ Basic"), value="basic"),
            discord.SelectOption(label=_("👥 Roles"), value="roles"),
            discord.SelectOption(label=_("📅 Joined"), value="join_date"),
            discord.SelectOption(label=_("🖼️ Avatar"), value="avatar"),
            discord.SelectOption(label=_("🛡️ Permissions"), value="permissions"),
            discord.SelectOption(label=_("⚡ Activity"), value="activity"),
            discord.SelectOption(label=_("🚫 Sanctions"), value="sanctions")
        ]
    )
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        """Actualiza el embed mostrado según la selección."""
        value = select.values[0]
        embed = self.embeds.get(value)
        if embed:
            await interaction.response.edit_message(embed=embed)
        else:
            await interaction.response.send_message(_("The selected section was not found."), ephemeral=True)
