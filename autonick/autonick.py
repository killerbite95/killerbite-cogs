import discord
import time
import re
from typing import List, Optional
from redbot.core import commands, Config, checks
from .dashboard_integration import DashboardIntegration

DEFAULT_FORBIDDEN_NAMES = [
    # Palabrotas y ofensas
    "mierda", "puta", "puto", "joder", "coño", "culo", "idiota", "imbecil", "estúpido",
    # Figuras controvertidas, dictadores y famosos
    "hitler", "adolf hitler", "stalin", "mussolini", "lenin", "pol pot", "kim jong-un",
    "mao zedong", "gaddafi", "muammar gaddafi", "saddam hussein", "fidel castro", "che guevara",
    "trump", "putin", "obama", "biden", "macron", "merkel", "de gaulle", "nixon", "franco",
    "xi jinping"
]

class AutoNick(DashboardIntegration, commands.Cog):
    """
    Cog que permite a los usuarios establecer su apodo mediante el envío de un mensaje en un canal configurado.
    Se valida el contenido del nombre para evitar palabrotas y nombres prohibidos (incluyendo dictadores y famosos).

    Comandos disponibles (como slash o prefijo):
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
                    f"{message.author.mention}, debes esperar {remaining} segundos antes de cambiar tu apodo nuevamente."
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
                f"{message.author.mention}, el apodo no puede tener mas de 32 caracteres.",
                allowed_mentions=mention_only,
            )
            return

        if not await self.is_valid_name(new_nick, message.guild):
            await message.channel.send(
                f"{message.author.mention}, el nombre contiene palabras o nombres no permitidos. Por favor, elige otro."
            )
            return

        self.cooldowns[message.author.id] = now

        try:
            await message.author.edit(nick=new_nick)
            await message.channel.send(
                f"{message.author.mention}, tu apodo ha sido cambiado a: **{discord.utils.escape_markdown(new_nick)}**",
                allowed_mentions=mention_only,
            )
        except discord.Forbidden:
            await message.channel.send(
                f"{message.author.mention}, no tengo permisos para cambiar tu apodo."
            )
        except Exception as e:
            await message.channel.send(f"Error al cambiar el apodo: {str(e)}")

    @commands.hybrid_group(name="autonick", with_app_command=True)
    async def autonick(self, ctx: commands.Context):
        """
        Grupo principal de comandos de AutoNick.
        Usa `/autonick help` para ver todos los subcomandos.
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help("autonick")

    @autonick.command(name="setchannel")
    @checks.admin_or_permissions(manage_guild=True)
    async def set_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """
        Establece el canal donde se escucharán los mensajes para cambiar el apodo.
        Ejemplo: `/autonick setchannel #nombre-del-canal`
        """
        await self.config.guild(ctx.guild).channel.set(channel.id)
        await ctx.send(f"El canal para AutoNick ha sido establecido a {channel.mention}.")

    @autonick.command(name="setcooldown")
    @checks.admin_or_permissions(manage_guild=True)
    async def set_cooldown(self, ctx: commands.Context, seconds: int):
        """
        Establece el cooldown (en segundos) entre cambios de apodo.
        Ejemplo: `/autonick setcooldown 30`
        """
        if seconds < 0:
            return await ctx.send("El cooldown debe ser un número positivo.")
        await self.config.guild(ctx.guild).cooldown.set(seconds)
        await ctx.send(f"El cooldown ha sido establecido a {seconds} segundos.")

    @autonick.command(name="info")
    async def info(self, ctx: commands.Context):
        """
        Muestra la configuración actual del cog AutoNick.
        Ejemplo: `/autonick info`
        """
        channel_id = await self.config.guild(ctx.guild).channel()
        cooldown = await self.config.guild(ctx.guild).cooldown()
        channel = ctx.guild.get_channel(channel_id) if channel_id else None
        embed = discord.Embed(title="Configuración de AutoNick", color=discord.Color.blue())
        embed.add_field(name="Canal", value=channel.mention if channel else "No configurado", inline=False)
        embed.add_field(name="Cooldown", value=f"{cooldown} segundos", inline=False)
        await ctx.send(embed=embed)

    @autonick.group(name="admin", invoke_without_command=True, with_app_command=True)
    @checks.admin_or_permissions(manage_guild=True)
    async def admin(self, ctx: commands.Context):
        """
        Comandos administrativos para AutoNick.
        Uso: `/autonick admin <subcomando>`
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help("autonick admin")

    @admin.command(name="addforbidden")
    @checks.admin_or_permissions(manage_guild=True)
    async def add_forbidden(self, ctx: commands.Context, *, word: str):
        """
        Añade una palabra o frase a la lista de nombres prohibidos.
        Ejemplo: `/autonick admin addforbidden [palabra o frase]`
        """
        word = word.lower().strip()
        forbidden = await self.get_forbidden_names(ctx.guild)
        if word in forbidden:
            return await ctx.send("Esa palabra ya se encuentra en la lista de prohibidos.")
        forbidden.append(word)
        await self.set_forbidden_names(ctx.guild, forbidden)
        await ctx.send(f"La palabra '{word}' ha sido añadida a la lista de prohibidos.")

    @admin.command(name="removeforbidden")
    @checks.admin_or_permissions(manage_guild=True)
    async def remove_forbidden(self, ctx: commands.Context, *, word: str):
        """
        Elimina una palabra o frase de la lista de nombres prohibidos.
        Ejemplo: `/autonick admin removeforbidden [palabra o frase]`
        """
        word = word.lower().strip()
        forbidden = await self.get_forbidden_names(ctx.guild)
        if word not in forbidden:
            return await ctx.send("Esa palabra no se encuentra en la lista de prohibidos.")
        forbidden.remove(word)
        await self.set_forbidden_names(ctx.guild, forbidden)
        await ctx.send(f"La palabra '{word}' ha sido eliminada de la lista de prohibidos.")

    @admin.command(name="listforbidden")
    async def list_forbidden(self, ctx: commands.Context):
        """
        Muestra la lista de todas las palabras o frases prohibidas.
        Ejemplo: `/autonick admin listforbidden`
        """
        forbidden = await self.get_forbidden_names(ctx.guild)
        if not forbidden:
            return await ctx.send("La lista de palabras prohibidas está vacía.")
        formatted = "\n".join(f"- {word}" for word in forbidden)
        if len(formatted) > 4000:
            formatted = formatted[:3990] + "\n…"
        embed = discord.Embed(title="Palabras prohibidas", description=formatted, color=discord.Color.red())
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(AutoNick(bot))
