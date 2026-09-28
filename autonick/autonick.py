import discord
import time
import re
from typing import List, Optional
from redbot.core import commands, Config, checks
from .dashboard_integration import DashboardIntegration
from redbot.core.i18n import Translator, cog_i18n, set_contextual_locales_from_guild

_ = Translator("AutoNick", __file__)

DEFAULT_FORBIDDEN_NAMES = [
    # Palabrotas y ofensas
    "mierda", "puta", "puto", "joder", "coño", "culo", "idiota", "imbecil", "estúpido",
    # Figuras controvertidas, dictadores y famosos
    "hitler", "adolf hitler", "stalin", "mussolini", "lenin", "pol pot", "kim jong-un",
    "mao zedong", "gaddafi", "muammar gaddafi", "saddam hussein", "fidel castro", "che guevara",
    "trump", "putin", "obama", "biden", "macron", "merkel", "de gaulle", "nixon", "franco",
    "xi jinping"
]

@cog_i18n(_)
class AutoNick(DashboardIntegration, commands.Cog):
    """Lets users set their nickname by sending a message in a configured channel.
    The name is checked to block swear words and forbidden names (including dictators and celebrities).

    Available commands (slash or prefix):
      • /autonick setchannel
      • /autonick setcooldown
      • /autonick info
      • /autonick admin addforbidden
      • /autonick admin removeforbidden
      • /autonick admin listforbidden
    """
    __author__ = "Killerbite95"  # Aquí se declara el autor

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=123456789012345678, force_registration=True)
        default_guild = {
            "channel": None,    # Canal configurado para escuchar mensajes
            "cooldown": 60,     # Cooldown en segundos entre cambios de apodo
            # Lista propia del servidor; None = usar la lista global por defecto.
            "forbidden_names": None,
        }
        self.config.register_guild(**default_guild)
        self.config.register_global(forbidden_names=DEFAULT_FORBIDDEN_NAMES)
        # Diccionario para rastrear el cooldown por usuario: {user_id: timestamp}
        self.cooldowns = {}


    # ------------------------------------------------------------------
    # Protocolo de La Trini: TriniProfiles (export/import) y TriniBackups
    # ------------------------------------------------------------------

    # Datos de funcionamiento (no son configuracion): ni se exportan ni se pisan.
    _TRINI_RUNTIME_KEYS = ()
    # Configuracion que solo tiene sentido en el mismo servidor.
    _TRINI_LOCAL_KEYS = ()

    async def trini_export(self, guild):
        conf = await self.config.guild(guild).all()
        return {k: v for k, v in conf.items() if k not in self._TRINI_RUNTIME_KEYS}

    async def trini_import(self, guild, data, *, same_guild):
        skip = set(self._TRINI_RUNTIME_KEYS)
        if not same_guild:
            skip |= set(self._TRINI_LOCAL_KEYS)
        data = {k: v for k, v in data.items() if k not in skip}
        group = self.config.guild(guild)
        current = await group.all()
        for key, value in data.items():
            if key in current:
                await group.set_raw(key, value=value)
        return []

    async def get_forbidden_names(self, guild: Optional[discord.Guild] = None) -> List[str]:
        """Lista de palabras prohibidas del servidor (o la global si no tiene propia)."""
        if guild is not None:
            names = await self.config.guild(guild).forbidden_names()
            if names is not None:
                return list(names)
        return list(await self.config.forbidden_names())

    async def set_forbidden_names(self, guild: discord.Guild, names: List[str]) -> None:
        """Guarda la lista del servidor (la global no se toca desde un servidor)."""
        await self.config.guild(guild).forbidden_names.set(list(names))

    async def is_valid_name(self, name: str, guild: Optional[discord.Guild] = None) -> bool:
        """
        Valida que el nombre no contenga ninguna de las palabras o frases prohibidas.
        Se utiliza una búsqueda con límites de palabra para evitar falsos positivos.
        """
        lower_name = name.lower()
        forbidden_list = await self.get_forbidden_names(guild)
        for banned in forbidden_list:
            if re.search(r'\b' + re.escape(banned) + r'\b', lower_name):
                return False
        return True

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignorar mensajes de bots o fuera de servidores
        if message.author.bot or not message.guild:
            return
        if await self.bot.cog_disabled_in_guild(self, message.guild):
            return
        await set_contextual_locales_from_guild(self.bot, message.guild)

        channel_id = await self.config.guild(message.guild).channel()
        if channel_id is None or message.channel.id != channel_id:
            return

        cooldown = await self.config.guild(message.guild).cooldown()
        now = time.time()
        last_used = self.cooldowns.get(message.author.id, 0)
        if now - last_used < cooldown:
            try:
                remaining = int(cooldown - (now - last_used))
                await message.channel.send(
                    _("{author}, you must wait {remaining} seconds before changing your nickname again.").format(author=message.author.mention, remaining=remaining)
                )
            except Exception:
                pass
            return

        new_nick = message.content.strip()
        if not new_nick:
            return
        mention_only = discord.AllowedMentions(users=[message.author], everyone=False, roles=False)
        if len(new_nick) > 32:
            await message.channel.send(
                _("{author}, the nickname can't be longer than 32 characters.").format(author=message.author.mention),
                allowed_mentions=mention_only,
            )
            return

        if not await self.is_valid_name(new_nick, message.guild):
            await message.channel.send(
                _("{author}, that name contains forbidden words or names. Please choose another one.").format(author=message.author.mention)
            )
            return

        self.cooldowns[message.author.id] = now

        try:
            await message.author.edit(nick=new_nick)
            await message.channel.send(
                _("{author}, your nickname has been changed to: **{escape_markdown}**").format(author=message.author.mention, escape_markdown=discord.utils.escape_markdown(new_nick)),
                allowed_mentions=mention_only,
            )
        except discord.Forbidden:
            await message.channel.send(
                _("{author}, I don't have permission to change your nickname.").format(author=message.author.mention)
            )
        except Exception as e:
            await message.channel.send(_("Error while changing the nickname: {e}").format(e=str(e)))

    @commands.hybrid_group(name="autonick", with_app_command=True)
    async def autonick(self, ctx: commands.Context):
        """Main AutoNick command group.
        Use `/autonick help` to see every subcommand.
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help("autonick")

    @autonick.command(name="setchannel")
    @checks.admin_or_permissions(manage_guild=True)
    async def set_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set the channel where nickname messages are read.
        Example: `/autonick setchannel #channel-name`
        """
        await self.config.guild(ctx.guild).channel.set(channel.id)
        await ctx.send(_("The AutoNick channel has been set to {channel}.").format(channel=channel.mention))

    @autonick.command(name="setcooldown")
    @checks.admin_or_permissions(manage_guild=True)
    async def set_cooldown(self, ctx: commands.Context, seconds: int):
        """Set the cooldown (in seconds) between nickname changes.
        Example: `/autonick setcooldown 30`
        """
        if seconds < 0:
            return await ctx.send(_("The cooldown must be a positive number."))
        await self.config.guild(ctx.guild).cooldown.set(seconds)
        await ctx.send(_("The cooldown has been set to {seconds} seconds.").format(seconds=seconds))

    @autonick.command(name="info")
    async def info(self, ctx: commands.Context):
        """Show the current AutoNick settings.
        Example: `/autonick info`
        """
        channel_id = await self.config.guild(ctx.guild).channel()
        cooldown = await self.config.guild(ctx.guild).cooldown()
        channel = ctx.guild.get_channel(channel_id) if channel_id else None
        embed = discord.Embed(title=_("AutoNick settings"), color=discord.Color.blue())
        embed.add_field(name=_("Channel"), value=channel.mention if channel else _("Not set"), inline=False)
        embed.add_field(name=_("Cooldown"), value=_("{cooldown} seconds").format(cooldown=cooldown), inline=False)
        await ctx.send(embed=embed)

    @autonick.group(name="admin", invoke_without_command=True, with_app_command=True)
    @checks.admin_or_permissions(manage_guild=True)
    async def admin(self, ctx: commands.Context):
        """AutoNick admin commands.
        Usage: `/autonick admin <subcommand>`
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help("autonick admin")

    @admin.command(name="addforbidden")
    @checks.admin_or_permissions(manage_guild=True)
    async def add_forbidden(self, ctx: commands.Context, *, word: str):
        """Add a word or phrase to the forbidden names list.
        Example: `/autonick admin addforbidden [word or phrase]`
        """
        word = word.lower().strip()
        forbidden = await self.get_forbidden_names(ctx.guild)
        if word in forbidden:
            return await ctx.send(_("That word is already in the forbidden list."))
        forbidden.append(word)
        await self.set_forbidden_names(ctx.guild, forbidden)
        await ctx.send(_("The word '{word}' has been added to the forbidden list.").format(word=word))

    @admin.command(name="removeforbidden")
    @checks.admin_or_permissions(manage_guild=True)
    async def remove_forbidden(self, ctx: commands.Context, *, word: str):
        """Remove a word or phrase from the forbidden names list.
        Example: `/autonick admin removeforbidden [word or phrase]`
        """
        word = word.lower().strip()
        forbidden = await self.get_forbidden_names(ctx.guild)
        if word not in forbidden:
            return await ctx.send(_("That word is not in the forbidden list."))
        forbidden.remove(word)
        await self.set_forbidden_names(ctx.guild, forbidden)
        await ctx.send(_("The word '{word}' has been removed from the forbidden list.").format(word=word))

    @admin.command(name="listforbidden")
    async def list_forbidden(self, ctx: commands.Context):
        """Show every forbidden word or phrase.
        Example: `/autonick admin listforbidden`
        """
        forbidden = await self.get_forbidden_names(ctx.guild)
        if not forbidden:
            return await ctx.send(_("The forbidden words list is empty."))
        formatted = "\n".join(f"- {word}" for word in forbidden)
        if len(formatted) > 4000:
            formatted = formatted[:3990] + "\n…"
        embed = discord.Embed(title=_("Forbidden words"), description=formatted, color=discord.Color.red())
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(AutoNick(bot))
