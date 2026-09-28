"""DayCounter: contadores de dias (desde una fecha) y cuentas atras (hasta una fecha).

Cada servidor puede tener varios contadores con nombre. Opcionalmente:
- avisa en un canal al llegar a un hito (100, 365, 1000 dias, aniversarios...);
- renombra un canal (de voz o texto) con el numero de dias, una vez al dia.
"""
import datetime
import logging
import re
from typing import Any, Dict, Optional, Tuple

import discord
from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.utils.chat_formatting import humanize_number

from .dashboard_integration import DashboardIntegration

log = logging.getLogger("red.killerbite.daycounter")

DEFAULT_NAME = "principal"
MAX_COUNTERS = 25
DEFAULT_COLOR = 0x3498DB
# Hitos fijos; ademas cada aniversario (365 * n) cuenta como hito.
MILESTONES = (7, 30, 50, 100, 200, 250, 300, 500, 750, 1000, 1500, 2000, 2500, 3000, 4000, 5000, 7500, 10000)
NAME_RE = re.compile(r"^[\w\-áéíóúñü]{1,32}$", re.IGNORECASE)
DEFAULT_CHANNEL_FORMAT = "📅 Día {days}"


def _today() -> datetime.date:
    return datetime.datetime.now(datetime.timezone.utc).date()


def _parse_date(text: str) -> Optional[datetime.date]:
    """Acepta AAAA-MM-DD, DD/MM/AAAA o DD-MM-AAAA."""
    text = text.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _add_months(date: datetime.date, months: int) -> datetime.date:
    """Suma meses ajustando el dia al ultimo del mes si no existe (31 ene + 1 mes = 28/29 feb)."""
    total = date.month - 1 + months
    year, month = date.year + total // 12, total % 12 + 1
    next_month = datetime.date(year + month // 12, month % 12 + 1, 1)
    last_day = (next_month - datetime.timedelta(days=1)).day
    return datetime.date(year, month, min(date.day, last_day))


def _breakdown(start: datetime.date, end: datetime.date) -> Tuple[int, int, int]:
    """Años, meses y dias entre dos fechas (start <= end)."""
    total_months = (end.year - start.year) * 12 + (end.month - start.month)
    if _add_months(start, total_months) > end:
        total_months -= 1
    days = (end - _add_months(start, total_months)).days
    return total_months // 12, total_months % 12, days


def _plural(n: int, one: str, many: str) -> str:
    return f"{humanize_number(n)} {one if n == 1 else many}"


def _human_breakdown(years: int, months: int, days: int) -> str:
    parts = []
    if years:
        parts.append(_plural(years, "año", "años"))
    if months:
        parts.append(_plural(months, "mes", "meses"))
    if days or not parts:
        parts.append(_plural(days, "día", "días"))
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " y " + parts[-1]


def milestone_for(days: int) -> Optional[str]:
    """Texto del hito si ``days`` es un hito, si no ``None``."""
    if days > 0 and days % 365 == 0:
        years = days // 365
        return f"🎂 ¡{_plural(years, 'año', 'años')}!"
    if days in MILESTONES:
        return f"🎉 ¡{humanize_number(days)} días!"
    return None


def next_milestone(days: int) -> int:
    candidates = [m for m in MILESTONES if m > days]
    next_year = (days // 365 + 1) * 365
    return min(candidates + [next_year])


def _progress_bar(value: int, total: int, width: int = 12) -> str:
    total = max(total, 1)
    filled = max(0, min(width, round(width * value / total)))
    return "▰" * filled + "▱" * (width - filled)


class DayCounter(DashboardIntegration, commands.Cog):
    """Contadores de dias y cuentas atras con embeds, hitos y canal contador."""

    __author__ = "Killerbite95"
    __version__ = "2.0.0"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        self.config.register_guild(
            start_date=None,  # v1: se migra al contador "principal"
            counters={},  # {nombre: {"date", "title", "description", "color", "emoji", "created_by"}}
            milestone_channel=None,
            last_milestones={},  # {nombre: dias del ultimo hito anunciado}
            channel_counter={"channel_id": None, "counter": None, "format": DEFAULT_CHANNEL_FORMAT, "last_value": None},
        )
        self.daily_task.start()

    def format_help_for_context(self, ctx: commands.Context) -> str:
        return f"{super().format_help_for_context(ctx)}\n\nVersion: {self.__version__}"

    def cog_unload(self):
        self.daily_task.cancel()

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        # Solo se guarda quien creo cada contador (para mostrarlo): se anonimiza.
        for guild_id, data in (await self.config.all_guilds()).items():
            if any(c.get("created_by") == user_id for c in data.get("counters", {}).values()):
                async with self.config.guild_from_id(guild_id).counters() as counters:
                    for counter in counters.values():
                        if counter.get("created_by") == user_id:
                            counter["created_by"] = None

    # ------------------------------------------------------------------
    # Protocolo de La Trini: TriniProfiles (export/import) y TriniBackups
    # ------------------------------------------------------------------

    # Datos de funcionamiento (no son configuracion): ni se exportan ni se pisan.
    _TRINI_RUNTIME_KEYS = ("last_milestones", "start_date")
    # Configuracion que solo tiene sentido en el mismo servidor.
    _TRINI_LOCAL_KEYS = ()

    async def trini_export(self, guild):
        await self.get_counters(guild)  # migra la fecha de la v1 antes de exportar
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

    # ------------------------------------------------------------------
    # Datos
    # ------------------------------------------------------------------

    async def get_counters(self, guild: discord.Guild) -> Dict[str, Dict[str, Any]]:
        """Contadores del servidor, migrando la fecha unica de la version 1."""
        group = self.config.guild(guild)
        legacy = await group.start_date()
        if legacy:
            async with group.counters() as counters:
                counters.setdefault(DEFAULT_NAME, {"date": legacy, "title": "Contador de días"})
            await group.start_date.clear()
        return await group.counters()

    @staticmethod
    def counter_state(data: Dict[str, Any], today: Optional[datetime.date] = None) -> Dict[str, Any]:
        """Calcula dias transcurridos o restantes de un contador."""
        today = today or _today()
        date = _parse_date(str(data.get("date", ""))) or today
        delta = (today - date).days
        future = delta < 0
        start, end = (today, date) if future else (date, today)
        return {
            "date": date,
            "days": abs(delta),
            "future": future,
            "breakdown": _breakdown(start, end),
        }

    def build_embed(self, name: str, data: Dict[str, Any], guild: Optional[discord.Guild] = None) -> discord.Embed:
        state = self.counter_state(data)
        days, future = state["days"], state["future"]
        emoji = data.get("emoji") or ("⏳" if future else "📅")
        title = data.get("title") or name.capitalize()
        embed = discord.Embed(
            title=f"{emoji} {title}",
            description=data.get("description") or None,
            color=data.get("color") or DEFAULT_COLOR,
        )
        date_dt = datetime.datetime.combine(state["date"], datetime.time(), tzinfo=datetime.timezone.utc)
        if future:
            if days == 0:
                embed.add_field(name="¡Es hoy!", value="🎉", inline=False)
            else:
                embed.add_field(name="Faltan", value=f"**{_plural(days, 'día', 'días')}**", inline=True)
                embed.add_field(name="Fecha", value=discord.utils.format_dt(date_dt, "D"), inline=True)
                embed.add_field(name="Desglose", value=_human_breakdown(*state["breakdown"]), inline=False)
        else:
            embed.add_field(name="Días", value=f"**{humanize_number(days)}**", inline=True)
            embed.add_field(name="Desde", value=discord.utils.format_dt(date_dt, "D"), inline=True)
            embed.add_field(name="Semanas", value=humanize_number(days // 7), inline=True)
            embed.add_field(name="Desglose", value=_human_breakdown(*state["breakdown"]), inline=False)
            target = next_milestone(days)
            previous = max([m for m in MILESTONES if m <= days] + [(days // 365) * 365, 0])
            embed.add_field(
                name="Próximo hito",
                value=f"{_progress_bar(days - previous, target - previous)} **{humanize_number(target)}** días "
                f"(faltan {_plural(target - days, 'día', 'días')})",
                inline=False,
            )
            reached = milestone_for(days)
            if reached:
                embed.add_field(name="Hoy", value=reached, inline=False)
        footer = f"Contador: {name}"
        if guild is not None and guild.icon:
            embed.set_footer(text=footer, icon_url=guild.icon.url)
        else:
            embed.set_footer(text=footer)
        return embed

    # ------------------------------------------------------------------
    # Tarea diaria: hitos y canal contador
    # ------------------------------------------------------------------

    @tasks.loop(minutes=30)
    async def daily_task(self):
        for guild_id, data in (await self.config.all_guilds()).items():
            guild = self.bot.get_guild(guild_id)
            if guild is None or guild.unavailable:
                continue
            try:
                if await self.bot.cog_disabled_in_guild(self, guild):
                    continue
                await self._check_milestones(guild)
                await self._update_channel_counter(guild)
            except Exception:
                log.exception("Error en DayCounter para %s", guild_id)

    @daily_task.before_loop
    async def before_daily_task(self):
        await self.bot.wait_until_red_ready()

    async def _check_milestones(self, guild: discord.Guild) -> None:
        channel_id = await self.config.guild(guild).milestone_channel()
        channel = guild.get_channel_or_thread(channel_id) if channel_id else None
        if channel is None:
            return
        counters = await self.get_counters(guild)
        announced = await self.config.guild(guild).last_milestones()
        changed = False
        for name, data in counters.items():
            state = self.counter_state(data)
            if state["future"]:
                label = "🎉 ¡Hoy es el día!" if state["days"] == 0 else None
            else:
                label = milestone_for(state["days"])
            if not label or announced.get(name) == [state["days"], state["future"]]:
                continue
            announced[name] = [state["days"], state["future"]]
            changed = True
            embed = self.build_embed(name, data, guild)
            embed.title = f"{label} · {embed.title}"
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                log.warning("No se pudo anunciar el hito en %s", channel_id)
        if changed:
            await self.config.guild(guild).last_milestones.set(announced)

    async def _update_channel_counter(self, guild: discord.Guild) -> None:
        conf = await self.config.guild(guild).channel_counter()
        channel = guild.get_channel(conf.get("channel_id")) if conf.get("channel_id") else None
        if channel is None:
            return
        counters = await self.get_counters(guild)
        data = counters.get(conf.get("counter") or DEFAULT_NAME)
        if not data:
            return
        state = self.counter_state(data)
        new_name = self._format_channel_name(conf.get("format") or DEFAULT_CHANNEL_FORMAT, state)
        if channel.name == new_name or conf.get("last_value") == new_name:
            return
        if not channel.permissions_for(guild.me).manage_channels:
            return
        try:
            await channel.edit(name=new_name, reason="DayCounter: contador diario")
        except discord.HTTPException:
            log.warning("No se pudo renombrar el canal contador %s", channel.id)
            return
        async with self.config.guild(guild).channel_counter() as current:
            current["last_value"] = new_name

    @staticmethod
    def _format_channel_name(fmt: str, state: Dict[str, Any]) -> str:
        years, months, days = state["breakdown"]
        text = fmt.replace("{days}", humanize_number(state["days"])).replace("{weeks}", str(state["days"] // 7))
        text = text.replace("{years}", str(years)).replace("{months}", str(months))
        return text[:100]

    # ------------------------------------------------------------------
    # Comandos
    # ------------------------------------------------------------------

    async def _resolve(self, ctx: commands.Context, name: Optional[str]) -> Optional[Tuple[str, Dict[str, Any]]]:
        counters = await self.get_counters(ctx.guild)
        if not counters:
            await ctx.send(
                f"No hay contadores. Crea uno con `{ctx.clean_prefix}dias crear <nombre> <fecha>` "
                f"(por ejemplo `{ctx.clean_prefix}dias crear aniversario 2024-06-15`)."
            )
            return None
        if name is None:
            name = DEFAULT_NAME if DEFAULT_NAME in counters else next(iter(counters))
        name = name.lower()
        if name not in counters:
            await ctx.send(f"No existe el contador `{name}`. Mira la lista con `{ctx.clean_prefix}dias lista`.")
            return None
        return name, counters[name]

    @commands.guild_only()
    @commands.hybrid_group(name="dias", aliases=["days", "daycounter"], invoke_without_command=True, fallback="ver")
    async def dias(self, ctx: commands.Context, nombre: Optional[str] = None):
        """Muestra un contador de días (el principal si no indicas nombre)."""
        resolved = await self._resolve(ctx, nombre)
        if resolved:
            await ctx.send(embed=self.build_embed(*resolved, ctx.guild))

    @dias.command(name="lista", aliases=["list"])
    async def dias_lista(self, ctx: commands.Context):
        """Todos los contadores del servidor."""
        counters = await self.get_counters(ctx.guild)
        if not counters:
            return await ctx.send(f"No hay contadores. Crea uno con `{ctx.clean_prefix}dias crear <nombre> <fecha>`.")
        embed = discord.Embed(title=f"📅 Contadores de {ctx.guild.name}", color=DEFAULT_COLOR)
        for name, data in sorted(counters.items()):
            state = self.counter_state(data)
            emoji = data.get("emoji") or ("⏳" if state["future"] else "📅")
            if state["future"]:
                value = f"Faltan **{_plural(state['days'], 'día', 'días')}** · {state['date'].isoformat()}"
            else:
                value = f"**{_plural(state['days'], 'día', 'días')}** desde {state['date'].isoformat()}"
            embed.add_field(name=f"{emoji} {data.get('title') or name} (`{name}`)", value=value, inline=False)
        await ctx.send(embed=embed)

    @commands.admin_or_permissions(manage_guild=True)
    @dias.command(name="crear", aliases=["create", "set"])
    async def dias_crear(self, ctx: commands.Context, nombre: str, fecha: str, *, titulo: Optional[str] = None):
        """Crea o cambia un contador. Fecha AAAA-MM-DD o DD/MM/AAAA; si es futura es una cuenta atrás."""
        nombre = nombre.lower()
        if not NAME_RE.match(nombre):
            return await ctx.send("El nombre debe ser una sola palabra de hasta 32 caracteres (letras, números, `-` o `_`).")
        date = _parse_date(fecha)
        if date is None:
            return await ctx.send("Fecha no válida. Usa `AAAA-MM-DD` o `DD/MM/AAAA`, por ejemplo `2024-06-15`.")
        async with self.config.guild(ctx.guild).counters() as counters:
            if nombre not in counters and len(counters) >= MAX_COUNTERS:
                return await ctx.send(f"Máximo {MAX_COUNTERS} contadores por servidor.")
            counter = counters.setdefault(nombre, {"created_by": ctx.author.id})
            counter["date"] = date.isoformat()
            if titulo:
                counter["title"] = titulo[:100]
            data = dict(counter)
        async with self.config.guild(ctx.guild).last_milestones() as announced:
            announced.pop(nombre, None)
        await ctx.send(content=f"✅ Contador `{nombre}` guardado.", embed=self.build_embed(nombre, data, ctx.guild))

    @commands.admin_or_permissions(manage_guild=True)
    @dias.command(name="editar", aliases=["edit"])
    async def dias_editar(self, ctx: commands.Context, nombre: str, campo: str, *, valor: Optional[str] = None):
        """Edita un contador: `titulo`, `descripcion`, `color` (#hex), `emoji` o `fecha`. Sin valor lo borra."""
        nombre, campo = nombre.lower(), campo.lower()
        fields = {"titulo": "title", "title": "title", "descripcion": "description", "description": "description",
                  "color": "color", "emoji": "emoji", "fecha": "date", "date": "date"}
        if campo not in fields:
            return await ctx.send("Campo no válido. Usa `titulo`, `descripcion`, `color`, `emoji` o `fecha`.")
        key = fields[campo]
        value: Any = valor
        if valor is not None:
            if key == "color":
                try:
                    value = int(valor.strip().lstrip("#"), 16)
                except ValueError:
                    return await ctx.send("Color no válido. Usa hexadecimal, por ejemplo `#3498db`.")
            elif key == "date":
                parsed = _parse_date(valor)
                if parsed is None:
                    return await ctx.send("Fecha no válida. Usa `AAAA-MM-DD` o `DD/MM/AAAA`.")
                value = parsed.isoformat()
            elif key == "title":
                value = valor[:100]
            elif key == "description":
                value = valor[:1000]
            elif key == "emoji":
                value = valor.strip()[:64]
        elif key == "date":
            return await ctx.send("La fecha es obligatoria.")
        async with self.config.guild(ctx.guild).counters() as counters:
            if nombre not in counters:
                return await ctx.send(f"No existe el contador `{nombre}`.")
            if value is None:
                counters[nombre].pop(key, None)
            else:
                counters[nombre][key] = value
            data = dict(counters[nombre])
        await ctx.send(content="✅ Contador actualizado.", embed=self.build_embed(nombre, data, ctx.guild))

    @commands.admin_or_permissions(manage_guild=True)
    @dias.command(name="borrar", aliases=["delete", "remove"])
    async def dias_borrar(self, ctx: commands.Context, nombre: str):
        """Borra un contador."""
        nombre = nombre.lower()
        async with self.config.guild(ctx.guild).counters() as counters:
            removed = counters.pop(nombre, None)
        await ctx.send(f"🗑️ Contador `{nombre}` borrado." if removed else f"No existe el contador `{nombre}`.")

    @commands.admin_or_permissions(manage_guild=True)
    @dias.command(name="hitos", aliases=["milestones"])
    async def dias_hitos(self, ctx: commands.Context, canal: Optional[discord.TextChannel] = None):
        """Canal donde anunciar los hitos (100, 365, 1000 días, aniversarios...). Sin canal lo desactiva."""
        await self.config.guild(ctx.guild).milestone_channel.set(canal.id if canal else None)
        await ctx.send(f"✅ Los hitos se anunciarán en {canal.mention}." if canal else "✅ Anuncios de hitos desactivados.")

    @commands.admin_or_permissions(manage_guild=True)
    @dias.command(name="canal", aliases=["channel"])
    async def dias_canal(
        self,
        ctx: commands.Context,
        canal: Optional[discord.abc.GuildChannel] = None,
        nombre: Optional[str] = None,
        *,
        formato: Optional[str] = None,
    ):
        """Renombra un canal cada día con el contador. Formato: `{days}`, `{weeks}`, `{months}`, `{years}`.

        Ejemplo: `[p]dias canal #dias-online principal 📅 Día {days}`. Sin canal lo desactiva.
        """
        if canal is None:
            async with self.config.guild(ctx.guild).channel_counter() as conf:
                conf["channel_id"] = None
            return await ctx.send("✅ Canal contador desactivado.")
        if not canal.permissions_for(ctx.guild.me).manage_channels:
            return await ctx.send(f"Necesito *Gestionar canales* en {canal.mention}.")
        counters = await self.get_counters(ctx.guild)
        nombre = (nombre or DEFAULT_NAME).lower()
        if nombre not in counters:
            return await ctx.send(f"No existe el contador `{nombre}`.")
        async with self.config.guild(ctx.guild).channel_counter() as conf:
            conf.update({"channel_id": canal.id, "counter": nombre, "format": formato or DEFAULT_CHANNEL_FORMAT, "last_value": None})
        await self._update_channel_counter(ctx.guild)
        await ctx.send(
            f"✅ {canal.mention} mostrará el contador `{nombre}` y se actualizará una vez al día "
            "(Discord limita los cambios de nombre de canal)."
        )

    # Compatibilidad con la version 1 -----------------------------------

    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    @commands.command(hidden=True)
    async def establecer_fecha(self, ctx: commands.Context, year: int, month: int, day: int):
        """(v1) Fija la fecha del contador principal. Usa `dias crear`."""
        try:
            date = datetime.date(year, month, day)
        except ValueError:
            return await ctx.send("❌ Fecha inválida. Verificá que el día y mes sean correctos.")
        await self.dias_crear(ctx, DEFAULT_NAME, date.isoformat())

    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    @commands.command(hidden=True)
    async def resetear_dias(self, ctx: commands.Context):
        """(v1) Borra el contador principal. Usa `dias borrar`."""
        await self.dias_borrar(ctx, DEFAULT_NAME)
