"""
Trini Events - actividades con inscripciones, lista de espera, recordatorios,
roles y canales temporales, eventos recurrentes, integracion con ArenCup y
estadisticas de asistencia.

By Killerbite95
"""

from __future__ import annotations

import asyncio
import copy
import datetime
import logging
import time
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

import discord
from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.bot import Red

from .dashboard_integration import DashboardIntegration
from .timeparse import (
    WEEKDAY_NAMES,
    WEEKDAYS,
    format_local,
    get_tz,
    next_occurrence,
    parse_datetime,
    parse_time,
    valid_tz,
)
from .views import ArenCupModal, EventButton, EventModal, OpenModalView, event_view

log = logging.getLogger("red.killerbite95.trinievents")

STATUS_COLOR = {
    "scheduled": discord.Color.from_rgb(88, 101, 242),
    "ongoing": discord.Color.green(),
    "ended": discord.Color.dark_grey(),
    "cancelled": discord.Color.red(),
}
STATUS_LABEL = {
    "scheduled": "📅 Programado",
    "ongoing": "🟢 En curso",
    "ended": "🏁 Finalizado",
    "cancelled": "🚫 Cancelado",
}
MAX_EVENTS_KEPT = 300


def is_event_staff():
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            return False
        if await ctx.bot.is_owner(ctx.author) or await ctx.bot.is_admin(ctx.author):
            return True
        perms = ctx.author.guild_permissions
        if perms.manage_events or perms.manage_guild:
            return True
        staff = await ctx.bot.get_cog("TriniEvents").config.guild(ctx.guild).staff_role()
        return bool(staff and any(r.id == staff for r in ctx.author.roles))

    return commands.check(predicate)


class TriniEvents(DashboardIntegration, commands.Cog):
    """Eventos de comunidad: inscripciones, reservas, recordatorios, roles/canales temporales y estadisticas."""

    __author__ = "Killerbite95"
    __version__ = "1.0.0"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0x7121E7E5, force_registration=True)
        self.config.register_guild(
            events={},
            next_id=1,
            channel=None,
            timezone="Europe/Madrid",
            reminders=[1440, 60, 15],
            staff_role=None,
            staff_ping=False,
            participant_role=None,
            auto_role=False,
            role_lead=60,
            temp_channels=False,
            archive_mode="delete",
            default_duration=120,
            checkin_open=15,
        )
        self._locks: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre = super().format_help_for_context(ctx)
        return f"{pre}\n\nVersion: {self.__version__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int) -> None:
        for guild_id in (await self.config.all_guilds()):
            async with self.config.guild_from_id(guild_id).events() as events:
                for ev in events.values():
                    for key in ("participants", "waitlist", "remind", "cancelled_by", "attended"):
                        if user_id in ev.get(key, []):
                            ev[key] = [u for u in ev[key] if u != user_id]

    async def cog_check(self, ctx: commands.Context) -> bool:
        # Los slash de discord.py NO heredan los checks del grupo en los
        # subcomandos: sin esto, cualquiera podria usar `/event settings ...`.
        if ctx.guild is None:
            return False
        if ctx.command is not None and ctx.command.qualified_name.startswith("event settings"):
            if await ctx.bot.is_owner(ctx.author) or await ctx.bot.is_admin(ctx.author):
                return True
            return ctx.author.guild_permissions.manage_guild
        return True

    async def cog_load(self) -> None:
        self.bot.add_dynamic_items(EventButton)
        self.event_loop.start()
        self._dashboard_register()

    async def cog_unload(self) -> None:
        self.event_loop.cancel()
        try:
            self.bot.remove_dynamic_items(EventButton)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Export / import (protocolo Trini)
    # ------------------------------------------------------------------

    async def trini_export(self, guild: discord.Guild) -> Dict[str, Any]:
        data = await self.config.guild(guild).all()
        data.pop("events", None)
        data.pop("next_id", None)
        return data

    async def trini_import(self, guild: discord.Guild, data: Dict[str, Any], *, same_guild: bool) -> List[str]:
        current = await self.config.guild(guild).all()
        for key, value in data.items():
            if key in current and key not in ("events", "next_id"):
                await self.config.guild(guild).set_raw(key, value=value)
        return []

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def _checkin_open(self, event: Dict[str, Any], settings: Dict[str, Any], now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        end = event["start"] + event["duration"] * 60
        return event["status"] in ("scheduled", "ongoing") and event["start"] - settings["checkin_open"] * 60 <= now <= end

    def build_embed(self, guild: discord.Guild, event: Dict[str, Any], settings: Dict[str, Any]) -> discord.Embed:
        is_arencup = event["kind"] == "arencup"
        emoji = "🏆" if is_arencup else event.get("emoji") or "🎮"
        embed = discord.Embed(
            title=f"{emoji} {event['title']}",
            description=event.get("description") or None,
            color=STATUS_COLOR[event["status"]],
        )
        start = event["start"]
        arencup = event.get("arencup") or {}
        if is_arencup:
            if arencup.get("checkin"):
                embed.add_field(name="Check-in", value=f"<t:{arencup['checkin']}:t>", inline=True)
            embed.add_field(name="Inicio", value=f"<t:{start}:t>", inline=True)
            embed.add_field(name="📅", value=f"<t:{start}:D> · <t:{start}:R>", inline=False)
            if arencup.get("teams"):
                embed.add_field(name="Equipos", value=f"{arencup['teams']} equipos", inline=True)
            if event.get("remind"):
                embed.add_field(name="🔔 Recordatorios", value=str(len(event["remind"])), inline=True)
        else:
            embed.add_field(name="📅 Fecha", value=f"<t:{start}:D>", inline=True)
            embed.add_field(name="🕙 Hora", value=f"<t:{start}:t> · <t:{start}:R>", inline=True)
            slots = event["slots"]
            count = len(event["participants"])
            embed.add_field(
                name="👥 Participantes",
                value=f"{count} / {slots}" if slots else f"{count}",
                inline=True,
            )
            if event["waitlist"]:
                embed.add_field(name="Lista de espera", value=str(len(event["waitlist"])), inline=True)
            embed.add_field(name="⏱ Duracion", value=f"{event['duration']} min", inline=True)
            if event.get("required_role"):
                embed.add_field(name="Rol requerido", value=f"<@&{event['required_role']}>", inline=True)
            if event["participants"]:
                names = " ".join(f"<@{u}>" for u in event["participants"][:40])
                if count > 40:
                    names += f" y {count - 40} mas"
                embed.add_field(name="Inscritos", value=names[:1024], inline=False)
            if event["status"] in ("ongoing", "ended") and event.get("attended"):
                embed.add_field(name="✋ Check-in", value=f"{len(event['attended'])} / {count}", inline=True)
        embed.add_field(name="Estado", value=STATUS_LABEL[event["status"]], inline=True)
        footer = f"Evento #{event['id']}"
        rec = event.get("recurrence")
        if rec:
            footer += f" · se repite {'cada dia' if rec['freq'] == 'daily' else 'cada ' + WEEKDAY_NAMES[rec.get('weekday', 0)]}"
        if event.get("tag"):
            footer += f" · {event['tag']}"
        embed.set_footer(text=footer)
        return embed

    async def refresh_message(self, guild: discord.Guild, event: Dict[str, Any], settings: Optional[Dict[str, Any]] = None) -> None:
        settings = settings or await self.config.guild(guild).all()
        channel = guild.get_channel_or_thread(event.get("channel_id") or 0)
        if channel is None or not event.get("message_id"):
            return
        embed = self.build_embed(guild, event, settings)
        view = event_view(event, checkin_open=self._checkin_open(event, settings))
        try:
            msg = channel.get_partial_message(event["message_id"])
            await msg.edit(embed=embed, view=view)
        except discord.NotFound:
            event["message_id"] = None
        except discord.HTTPException:
            log.warning("No se pudo actualizar el mensaje del evento %s", event["id"])

    async def publish(self, guild: discord.Guild, event: Dict[str, Any], settings: Dict[str, Any]) -> Optional[discord.Message]:
        channel = guild.get_channel_or_thread(event.get("channel_id") or 0)
        if channel is None:
            return None
        embed = self.build_embed(guild, event, settings)
        view = event_view(event, checkin_open=self._checkin_open(event, settings))
        kwargs: Dict[str, Any] = {"embed": embed}
        if view is not None:
            kwargs["view"] = view
        msg = await channel.send(**kwargs)
        event["message_id"] = msg.id
        return msg

    # ------------------------------------------------------------------
    # Creacion
    # ------------------------------------------------------------------

    def _new_event(self, eid: int, **kw) -> Dict[str, Any]:
        base = {
            "id": eid,
            "title": "Evento",
            "description": "",
            "kind": "normal",
            "tag": None,
            "emoji": None,
            "start": 0,
            "duration": 120,
            "slots": 0,
            "required_role": None,
            "channel_id": None,
            "message_id": None,
            "creator": None,
            "participants": [],
            "waitlist": [],
            "remind": [],
            "cancelled_by": [],
            "attended": [],
            "reminders_sent": [],
            "status": "scheduled",
            "role": {"id": None, "auto": False, "assigned": False},
            "channels": {"enabled": False, "category_id": None, "ids": []},
            "recurrence": None,
            "arencup": None,
            "checkin_shown": False,
            "created_at": int(time.time()),
        }
        base.update(kw)
        return base

    async def create_event(self, guild: discord.Guild, **kw) -> Tuple[Dict[str, Any], Optional[discord.Message]]:
        settings = await self.config.guild(guild).all()
        async with self._locks[guild.id]:
            eid = await self.config.guild(guild).next_id()
            await self.config.guild(guild).next_id.set(eid + 1)
            kw.setdefault("duration", settings["default_duration"])
            kw.setdefault("channels", {"enabled": settings["temp_channels"], "category_id": None, "ids": []})
            event = self._new_event(eid, **kw)
            msg = await self.publish(guild, event, settings)
            async with self.config.guild(guild).events() as events:
                events[str(eid)] = event
                self._trim(events)
        self.bot.dispatch("trini_event_created", guild, event)
        return event, msg

    @staticmethod
    def _trim(events: Dict[str, Any]) -> None:
        finished = sorted(
            (e for e in events.values() if e["status"] in ("ended", "cancelled")),
            key=lambda e: e["start"],
        )
        while len(events) > MAX_EVENTS_KEPT and finished:
            events.pop(str(finished.pop(0)["id"]), None)

    async def _modal_create(self, interaction: discord.Interaction, values: Dict[str, str], *, channel_id: int, required_role: Optional[int], tag: Optional[str]) -> None:
        guild = interaction.guild
        tz = await self.config.guild(guild).timezone()
        start = parse_datetime(values["date"], tz)
        if start is None:
            return await interaction.response.send_message(
                "❌ Fecha no valida. Usa `02/10/2026 22:00`, `viernes 22:00`, `mañana 21:30` o `+2h`.", ephemeral=True
            )
        if start < time.time() - 60:
            return await interaction.response.send_message("❌ La fecha ya ha pasado.", ephemeral=True)
        try:
            slots = max(0, int(values["slots"] or 0))
            duration = int(values["duration"]) if values["duration"] else None
        except ValueError:
            return await interaction.response.send_message("❌ Plazas y duracion deben ser numeros.", ephemeral=True)
        kw: Dict[str, Any] = dict(
            title=values["name"], description=values["description"], start=start, slots=slots,
            required_role=required_role, channel_id=channel_id, creator=interaction.user.id, tag=tag,
        )
        if duration:
            kw["duration"] = max(5, min(duration, 7 * 1440))
        await interaction.response.defer(ephemeral=True, thinking=True)
        event, msg = await self.create_event(guild, **kw)
        await interaction.followup.send(
            f"✅ Evento **#{event['id']}** creado para {format_local(start, tz)} ({tz})." + (f" {msg.jump_url}" if msg else " ⚠️ No pude publicarlo en el canal."),
            ephemeral=True,
        )

    async def _modal_arencup(self, interaction: discord.Interaction, values: Dict[str, str], *, channel_id: int) -> None:
        guild = interaction.guild
        tz = await self.config.guild(guild).timezone()
        start = parse_datetime(values["start"], tz)
        checkin = parse_datetime(values["checkin"], tz) if values["checkin"] else None
        if start is None or (values["checkin"] and checkin is None):
            return await interaction.response.send_message("❌ Fecha no valida. Ej: `02/10/2026 19:00`.", ephemeral=True)
        url = values["url"]
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        await interaction.response.defer(ephemeral=True, thinking=True)
        event, msg = await self.create_event(
            guild,
            title=values["name"], kind="arencup", tag="ArenCup", start=start, duration=240,
            channel_id=channel_id, creator=interaction.user.id,
            arencup={"url": url or None, "checkin": checkin, "teams": values["teams"] or None},
            channels={"enabled": False, "category_id": None, "ids": []},
        )
        await interaction.followup.send(f"🏆 Evento ArenCup **#{event['id']}** publicado." + (f" {msg.jump_url}" if msg else ""), ephemeral=True)

    # ------------------------------------------------------------------
    # Botones
    # ------------------------------------------------------------------

    async def handle_button(self, interaction: discord.Interaction, action: str, event_id: int) -> str:
        guild = interaction.guild
        member = interaction.user
        settings = await self.config.guild(guild).all()
        promoted: Optional[int] = None
        async with self._locks[guild.id]:
            async with self.config.guild(guild).events() as events:
                event = events.get(str(event_id))
                if event is None:
                    return "Este evento ya no existe."
                if event["status"] in ("ended", "cancelled"):
                    return "Este evento ya ha finalizado."
                uid = member.id
                if action == "join":
                    if event.get("required_role") and not any(r.id == event["required_role"] for r in member.roles):
                        return f"Necesitas el rol <@&{event['required_role']}> para participar."
                    if uid in event["participants"]:
                        return "Ya estas inscrito. ✅"
                    if uid in event["waitlist"]:
                        return f"Ya estas en la lista de espera (posicion {event['waitlist'].index(uid) + 1})."
                    if event["slots"] and len(event["participants"]) >= event["slots"]:
                        event["waitlist"].append(uid)
                        reply = f"Plazas completas. Estas en la **lista de espera** (posicion {len(event['waitlist'])}). Te avisare si queda una plaza libre."
                    else:
                        event["participants"].append(uid)
                        reply = f"✅ Inscrito en **{event['title']}** (<t:{event['start']}:F>)."
                        if event["role"]["assigned"]:
                            await self._give_role(guild, event, [uid])
                elif action == "leave":
                    if uid in event["participants"]:
                        event["participants"].remove(uid)
                        event["cancelled_by"].append(uid)
                        if uid in event["attended"]:
                            event["attended"].remove(uid)
                        reply = "Has cancelado tu plaza."
                        if event["role"]["assigned"]:
                            await self._take_role(guild, event, [uid])
                        if event["waitlist"]:
                            promoted = event["waitlist"].pop(0)
                            event["participants"].append(promoted)
                            if event["role"]["assigned"]:
                                await self._give_role(guild, event, [promoted])
                    elif uid in event["waitlist"]:
                        event["waitlist"].remove(uid)
                        reply = "Has salido de la lista de espera."
                    else:
                        return "No estas inscrito en este evento."
                elif action == "remind":
                    if uid in event["remind"]:
                        event["remind"].remove(uid)
                        return "🔕 Ya no recibiras recordatorios de este evento."
                    event["remind"].append(uid)
                    reply = "🔔 Te avisare antes del evento por mensaje privado."
                    if event["kind"] != "arencup":
                        return reply
                elif action == "checkin":
                    if not self._checkin_open(event, settings):
                        return "El check-in no esta abierto."
                    if uid not in event["participants"]:
                        return "Solo los participantes inscritos pueden hacer check-in."
                    if uid in event["attended"]:
                        return "Ya habias hecho check-in. ✋"
                    event["attended"].append(uid)
                    reply = "✋ Check-in registrado. ¡A jugar!"
                else:
                    return "Accion desconocida."
                snapshot = copy.deepcopy(event)
        await self.refresh_message(guild, snapshot, settings)
        if promoted:
            await self._announce_promotion(guild, snapshot, promoted)
        return reply

    async def _announce_promotion(self, guild: discord.Guild, event: Dict[str, Any], user_id: int) -> None:
        member = guild.get_member(user_id)
        channel = guild.get_channel_or_thread(event.get("channel_id") or 0)
        text = f"<@{user_id}> ha pasado automaticamente de reserva a participante en **{event['title']}**."
        if channel is not None:
            try:
                ref = channel.get_partial_message(event["message_id"]) if event.get("message_id") else None
                await channel.send(text, reference=ref, mention_author=False, allowed_mentions=discord.AllowedMentions(users=True))
            except discord.HTTPException:
                pass
        if member is not None:
            try:
                await member.send(f"🎉 Se ha liberado una plaza: ya eres participante de **{event['title']}** (<t:{event['start']}:F>) en {guild.name}.")
            except discord.HTTPException:
                pass

    # ------------------------------------------------------------------
    # Roles y canales temporales
    # ------------------------------------------------------------------

    def _event_role(self, guild: discord.Guild, event: Dict[str, Any]) -> Optional[discord.Role]:
        rid = event["role"].get("id")
        return guild.get_role(rid) if rid else None

    async def _give_role(self, guild: discord.Guild, event: Dict[str, Any], user_ids: List[int]) -> None:
        role = self._event_role(guild, event)
        if role is None:
            return
        for uid in user_ids:
            member = guild.get_member(uid)
            if member is not None and role not in member.roles:
                try:
                    await member.add_roles(role, reason=f"Trini Events: evento #{event['id']}")
                except discord.HTTPException:
                    pass

    async def _take_role(self, guild: discord.Guild, event: Dict[str, Any], user_ids: List[int]) -> None:
        role = self._event_role(guild, event)
        if role is None:
            return
        for uid in user_ids:
            member = guild.get_member(uid)
            if member is not None and role in member.roles:
                try:
                    await member.remove_roles(role, reason=f"Trini Events: fin del evento #{event['id']}")
                except discord.HTTPException:
                    pass

    async def _prepare_event(self, guild: discord.Guild, event: Dict[str, Any], settings: Dict[str, Any]) -> None:
        """Una hora antes (configurable): roles y canales temporales."""
        role = None
        if settings["participant_role"]:
            role = guild.get_role(settings["participant_role"])
            event["role"].update({"id": role.id if role else None, "auto": False})
        elif settings["auto_role"] and guild.me.guild_permissions.manage_roles:
            try:
                role = await guild.create_role(name=f"🎟 {event['title']}"[:100], mentionable=False, reason=f"Trini Events: evento #{event['id']}")
                event["role"].update({"id": role.id, "auto": True})
            except discord.HTTPException:
                role = None
        event["role"]["assigned"] = True
        if role is not None:
            await self._give_role(guild, event, event["participants"])

        if event["channels"].get("enabled") and not event["channels"].get("ids") and guild.me.guild_permissions.manage_channels:
            staff = guild.get_role(settings["staff_role"]) if settings["staff_role"] else None
            overwrites: Dict[Any, discord.PermissionOverwrite] = {
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, connect=True),
            }
            if role is not None:
                overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, connect=True)
            if staff is not None:
                overwrites[staff] = discord.PermissionOverwrite(view_channel=True, send_messages=True, connect=True, manage_messages=True)
            try:
                cat = await guild.create_category(f"📁 Evento - {event['title']}"[:100], overwrites=overwrites, reason="Trini Events")
                info_ow = dict(overwrites)
                if role is not None:
                    info_ow[role] = discord.PermissionOverwrite(view_channel=True, send_messages=False)
                else:
                    info_ow[guild.default_role] = discord.PermissionOverwrite(send_messages=False)
                info = await guild.create_text_channel("informacion", category=cat, overwrites=info_ow)
                chat = await guild.create_text_channel("chat", category=cat)
                voice = await guild.create_voice_channel("Evento", category=cat)
                event["channels"].update({"category_id": cat.id, "ids": [info.id, chat.id, voice.id]})
                await info.send(embed=self.build_embed(guild, event, settings))
            except discord.HTTPException:
                log.exception("No se pudieron crear los canales del evento %s", event["id"])

    async def _cleanup_event(self, guild: discord.Guild, event: Dict[str, Any], settings: Dict[str, Any]) -> None:
        role = self._event_role(guild, event)
        if role is not None:
            if event["role"].get("auto"):
                try:
                    await role.delete(reason=f"Trini Events: fin del evento #{event['id']}")
                except discord.HTTPException:
                    pass
            else:
                await self._take_role(guild, event, list(set(event["participants"]) | set(event["cancelled_by"])))
        ids = event["channels"].get("ids") or []
        cat = guild.get_channel(event["channels"].get("category_id") or 0)
        if not ids and cat is None:
            return
        if settings["archive_mode"] == "delete":
            for cid in ids:
                ch = guild.get_channel(cid)
                if ch is not None:
                    try:
                        await ch.delete(reason="Trini Events: fin del evento")
                    except discord.HTTPException:
                        pass
            if cat is not None:
                try:
                    await cat.delete(reason="Trini Events: fin del evento")
                except discord.HTTPException:
                    pass
        elif cat is not None:
            try:
                await cat.edit(name=f"📦 {event['title']}"[:100])
                for ch in cat.channels:
                    await ch.set_permissions(guild.default_role, send_messages=False, connect=False, reason="Trini Events: archivado")
                    if role is not None and not event["role"].get("auto"):
                        await ch.set_permissions(role, send_messages=False, connect=False)
            except discord.HTTPException:
                pass

    # ------------------------------------------------------------------
    # Recordatorios y ciclo de vida
    # ------------------------------------------------------------------

    async def _send_reminder(self, guild: discord.Guild, event: Dict[str, Any], minutes: int, settings: Dict[str, Any]) -> None:
        anchor = (event.get("arencup") or {}).get("checkin") or event["start"]
        what = "el check-in" if anchor != event["start"] else "el evento"
        when = "24 horas" if minutes == 1440 else (f"{minutes // 60} hora(s)" if minutes % 60 == 0 else f"{minutes} minutos")
        embed = discord.Embed(
            title=f"🔔 {event['title']}",
            description=f"Empieza {what} en **{when}** (<t:{anchor}:t>, <t:{anchor}:R>).\nServidor: **{guild.name}**",
            color=STATUS_COLOR["scheduled"],
        )
        channel = guild.get_channel_or_thread(event.get("channel_id") or 0)
        if channel is not None and event.get("message_id"):
            embed.add_field(name="Evento", value=f"[Ver mensaje](https://discord.com/channels/{guild.id}/{channel.id}/{event['message_id']})")
        url = (event.get("arencup") or {}).get("url")
        if url:
            embed.add_field(name="Torneo", value=url)
        recipients = list(dict.fromkeys(event["participants"] + event["remind"]))
        for uid in recipients:
            member = guild.get_member(uid)
            if member is None:
                continue
            try:
                await member.send(embed=embed)
            except discord.HTTPException:
                pass
            await asyncio.sleep(0.2)
        if settings["staff_ping"] and settings["staff_role"] and channel is not None:
            try:
                await channel.send(
                    f"<@&{settings['staff_role']}> recordatorio: **{event['title']}** empieza <t:{anchor}:R>.",
                    allowed_mentions=discord.AllowedMentions(roles=True),
                )
            except discord.HTTPException:
                pass

    @tasks.loop(seconds=30)
    async def event_loop(self) -> None:
        now = time.time()
        for guild in list(self.bot.guilds):
            try:
                await self._tick_guild(guild, now)
            except Exception:
                log.exception("Error en el ciclo de eventos de %s", guild.id)

    @event_loop.before_loop
    async def _before_loop(self) -> None:
        await self.bot.wait_until_red_ready()

    async def _tick_guild(self, guild: discord.Guild, now: float) -> None:
        events = await self.config.guild(guild).events()
        active = [e for e in events.values() if e["status"] in ("scheduled", "ongoing")]
        if not active:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        settings = await self.config.guild(guild).all()
        for snapshot in active:
            eid = str(snapshot["id"])
            actions: List[str] = []
            end = snapshot["start"] + snapshot["duration"] * 60
            anchor = (snapshot.get("arencup") or {}).get("checkin") or snapshot["start"]
            due = [m for m in sorted(settings["reminders"]) if now >= anchor - m * 60 and m not in snapshot["reminders_sent"] and now < anchor]
            if due:
                actions.append("remind")
            if snapshot["kind"] != "arencup" and not snapshot["role"]["assigned"] and now >= snapshot["start"] - settings["role_lead"] * 60 and now < end:
                actions.append("prepare")
            if not snapshot.get("checkin_shown") and self._checkin_open(snapshot, settings, now):
                actions.append("checkin")
            if snapshot["status"] == "scheduled" and now >= snapshot["start"]:
                actions.append("start")
            if now >= end:
                actions.append("end")
            if not actions:
                continue

            async with self._locks[guild.id]:
                async with self.config.guild(guild).events() as evs:
                    event = evs.get(eid)
                    if event is None or event["status"] not in ("scheduled", "ongoing"):
                        continue
                    if "remind" in actions:
                        # Solo el recordatorio mas cercano; los anteriores se marcan como enviados.
                        smallest = min(due)
                        event["reminders_sent"] = sorted(set(event["reminders_sent"]) | set(m for m in settings["reminders"] if m >= smallest))
                    if "prepare" in actions:
                        await self._prepare_event(guild, event, settings)
                    if "checkin" in actions:
                        event["checkin_shown"] = True
                    if "start" in actions:
                        event["status"] = "ongoing"
                    if "end" in actions:
                        event["status"] = "ended"
                        event["ended_at"] = int(now)
                    current = copy.deepcopy(event)

            if "remind" in actions:
                await self._send_reminder(guild, current, min(due), settings)
            if "end" in actions:
                await self._cleanup_event(guild, current, settings)
                self.bot.dispatch("trini_event_ended", guild, current)
                if current.get("recurrence"):
                    await self._spawn_next(guild, current, settings)
            if any(a in actions for a in ("start", "end", "checkin")):
                await self.refresh_message(guild, current, settings)

    async def _spawn_next(self, guild: discord.Guild, event: Dict[str, Any], settings: Dict[str, Any]) -> None:
        rec = event["recurrence"]
        start = next_occurrence(event["start"], rec["freq"], settings["timezone"], rec.get("weekday"), rec.get("time"))
        while start < time.time():
            start = next_occurrence(start, rec["freq"], settings["timezone"], rec.get("weekday"), rec.get("time"))
        await self.create_event(guild, **self._clone_fields(event, start))

    @staticmethod
    def _clone_fields(event: Dict[str, Any], start: int) -> Dict[str, Any]:
        arencup = copy.deepcopy(event.get("arencup"))
        if arencup and arencup.get("checkin"):
            arencup["checkin"] = start - (event["start"] - arencup["checkin"])
        return dict(
            title=event["title"], description=event["description"], kind=event["kind"], tag=event.get("tag"),
            emoji=event.get("emoji"), start=start, duration=event["duration"], slots=event["slots"],
            required_role=event.get("required_role"), channel_id=event["channel_id"], creator=event["creator"],
            recurrence=copy.deepcopy(event.get("recurrence")), arencup=arencup,
            channels={"enabled": event["channels"].get("enabled", False), "category_id": None, "ids": []},
        )

    # ------------------------------------------------------------------
    # Estadisticas
    # ------------------------------------------------------------------

    async def compute_stats(self, guild: discord.Guild) -> Dict[str, Any]:
        events = [e for e in (await self.config.guild(guild).events()).values() if e["status"] == "ended" and e["kind"] != "arencup"]
        tracked = [e for e in events if e.get("attended")]
        participations: Counter = Counter()
        attendances: Counter = Counter()
        noshows: Counter = Counter()
        cancels: Counter = Counter()
        by_tag: Dict[str, List[int]] = defaultdict(lambda: [0, 0])
        for e in events:
            participations.update(e["participants"])
            cancels.update(e["cancelled_by"])
        for e in tracked:
            attended = set(e["attended"])
            attendances.update(attended)
            noshows.update(u for u in e["participants"] if u not in attended)
            tag = e.get("tag") or e["title"]
            by_tag[tag][0] += len(attended)
            by_tag[tag][1] += len(e["participants"])
        total_part = sum(len(e["participants"]) for e in tracked)
        total_att = sum(len(set(e["attended"])) for e in tracked)
        return {
            "events": events,
            "tracked": tracked,
            "participations": participations,
            "attendances": attendances,
            "noshows": noshows,
            "cancels": cancels,
            "by_tag": by_tag,
            "attendance_rate": (total_att / total_part * 100) if total_part else None,
        }

    # ------------------------------------------------------------------
    # Comandos
    # ------------------------------------------------------------------

    async def _get_event(self, ctx: commands.Context, event_id: int) -> Optional[Dict[str, Any]]:
        event = (await self.config.guild(ctx.guild).events()).get(str(event_id))
        if event is None:
            await ctx.send("No existe ese evento. Mira `event list`.")
        return event

    async def _event_autocomplete(self, interaction: discord.Interaction, current: str):
        if interaction.guild is None:
            return []
        events = sorted((await self.config.guild(interaction.guild).events()).values(), key=lambda e: -e["start"])
        out = []
        for e in events:
            label = f"#{e['id']} {e['title']} · {STATUS_LABEL[e['status']]}"
            if current.lower() in label.lower():
                out.append(discord.app_commands.Choice(name=label[:100], value=e["id"]))
        return out[:25]

    @commands.hybrid_group(name="event")
    @commands.guild_only()
    async def event(self, ctx: commands.Context):
        """Trini Events: actividades de comunidad."""

    @event.command(name="create")
    @is_event_staff()
    async def event_create(
        self,
        ctx: commands.Context,
        channel: Optional[discord.TextChannel] = None,
        required_role: Optional[discord.Role] = None,
        tag: Optional[str] = None,
    ):
        """Crear un evento con formulario (nombre, fecha, plazas, duracion, descripcion)."""
        target = channel or ctx.guild.get_channel(await self.config.guild(ctx.guild).channel() or 0) or ctx.channel
        if not target.permissions_for(ctx.guild.me).send_messages:
            return await ctx.send(f"No puedo publicar en {target.mention}.")

        async def submit(interaction: discord.Interaction, values: Dict[str, str]):
            await self._modal_create(interaction, values, channel_id=target.id, required_role=required_role.id if required_role else None, tag=tag)

        factory = lambda: EventModal(submit)  # noqa: E731
        if ctx.interaction is not None:
            await ctx.interaction.response.send_modal(factory())
        else:
            await ctx.send("📝 Pulsa para rellenar el evento:", view=OpenModalView(ctx.author, factory))

    @event.command(name="arencup")
    @is_event_staff()
    async def event_arencup(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Publicar un torneo de ArenCup (check-in, inicio, enlace y recordatorios)."""
        target = channel or ctx.guild.get_channel(await self.config.guild(ctx.guild).channel() or 0) or ctx.channel

        async def submit(interaction: discord.Interaction, values: Dict[str, str]):
            await self._modal_arencup(interaction, values, channel_id=target.id)

        factory = lambda: ArenCupModal(submit)  # noqa: E731
        if ctx.interaction is not None:
            await ctx.interaction.response.send_modal(factory())
        else:
            await ctx.send("🏆 Pulsa para rellenar el torneo:", view=OpenModalView(ctx.author, factory))

    @event.command(name="edit")
    @is_event_staff()
    async def event_edit(self, ctx: commands.Context, event_id: int):
        """Editar nombre, fecha, plazas, duracion y descripcion de un evento."""
        event = await self._get_event(ctx, event_id)
        if event is None:
            return
        if event["kind"] == "arencup":
            return await ctx.send("Para eventos ArenCup, cancelalo y vuelve a publicarlo.")
        tz = await self.config.guild(ctx.guild).timezone()

        async def submit(interaction: discord.Interaction, values: Dict[str, str]):
            start = parse_datetime(values["date"], tz)
            if start is None:
                return await interaction.response.send_message("❌ Fecha no valida.", ephemeral=True)
            try:
                slots = max(0, int(values["slots"] or 0))
                duration = int(values["duration"] or event["duration"])
            except ValueError:
                return await interaction.response.send_message("❌ Plazas y duracion deben ser numeros.", ephemeral=True)
            await interaction.response.defer(ephemeral=True)
            promoted: List[int] = []
            async with self._locks[ctx.guild.id]:
                async with self.config.guild(ctx.guild).events() as evs:
                    ev = evs.get(str(event_id))
                    if ev is None:
                        return
                    if ev["start"] != start:
                        ev["reminders_sent"] = []
                        ev["checkin_shown"] = False
                    ev.update(title=values["name"], description=values["description"], start=start, slots=slots, duration=max(5, duration))
                    while ev["waitlist"] and (not slots or len(ev["participants"]) < slots):
                        uid = ev["waitlist"].pop(0)
                        ev["participants"].append(uid)
                        promoted.append(uid)
                    current = copy.deepcopy(ev)
            await self.refresh_message(ctx.guild, current)
            for uid in promoted:
                await self._announce_promotion(ctx.guild, current, uid)
            await interaction.followup.send(f"✅ Evento #{event_id} actualizado.", ephemeral=True)

        defaults = {
            "name": event["title"], "date": format_local(event["start"], tz), "slots": str(event["slots"]),
            "duration": str(event["duration"]), "description": event.get("description") or "",
        }
        factory = lambda: EventModal(submit, title=f"Editar evento #{event_id}", defaults=defaults)  # noqa: E731
        if ctx.interaction is not None:
            await ctx.interaction.response.send_modal(factory())
        else:
            await ctx.send("📝 Pulsa para editar el evento:", view=OpenModalView(ctx.author, factory))

    @event.command(name="list")
    async def event_list(self, ctx: commands.Context):
        """Proximos eventos."""
        events = sorted(
            (e for e in (await self.config.guild(ctx.guild).events()).values() if e["status"] in ("scheduled", "ongoing")),
            key=lambda e: e["start"],
        )
        if not events:
            return await ctx.send("No hay eventos programados.")
        lines = []
        for e in events[:25]:
            count = f"{len(e['participants'])}/{e['slots']}" if e["slots"] else str(len(e["participants"]))
            link = f" · [ver](https://discord.com/channels/{ctx.guild.id}/{e['channel_id']}/{e['message_id']})" if e.get("message_id") else ""
            icon = "🏆" if e["kind"] == "arencup" else ("🟢" if e["status"] == "ongoing" else "📅")
            lines.append(f"{icon} `#{e['id']}` **{e['title']}** · <t:{e['start']}:f> · 👥 {count}{link}")
        await ctx.send(embed=discord.Embed(title="📅 Proximos eventos", description="\n".join(lines), color=STATUS_COLOR["scheduled"]))

    @event.command(name="info")
    async def event_info(self, ctx: commands.Context, event_id: int):
        """Ver un evento."""
        event = await self._get_event(ctx, event_id)
        if event is None:
            return
        settings = await self.config.guild(ctx.guild).all()
        embed = self.build_embed(ctx.guild, event, settings)
        if event.get("message_id"):
            embed.url = f"https://discord.com/channels/{ctx.guild.id}/{event['channel_id']}/{event['message_id']}"
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @event.command(name="participants")
    async def event_participants(self, ctx: commands.Context, event_id: int):
        """Participantes, reservas y check-in de un evento."""
        event = await self._get_event(ctx, event_id)
        if event is None:
            return
        attended = set(event["attended"])
        parts = [f"{'✋' if u in attended else '•'} <@{u}>" for u in event["participants"]]
        embed = discord.Embed(title=f"👥 {event['title']}", color=STATUS_COLOR[event["status"]])
        embed.add_field(name=f"Participantes ({len(parts)})", value="\n".join(parts)[:1024] or "—", inline=False)
        if event["waitlist"]:
            embed.add_field(name=f"Lista de espera ({len(event['waitlist'])})", value="\n".join(f"{i}. <@{u}>" for i, u in enumerate(event["waitlist"], 1))[:1024], inline=False)
        if event["remind"]:
            embed.add_field(name="🔔 Recordarme", value=str(len(event["remind"])), inline=True)
        if event["cancelled_by"]:
            embed.add_field(name="Cancelaciones", value=str(len(event["cancelled_by"])), inline=True)
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @event.command(name="cancel")
    @is_event_staff()
    async def event_cancel(self, ctx: commands.Context, event_id: int, *, reason: Optional[str] = None):
        """Cancelar un evento y avisar a los inscritos."""
        settings = await self.config.guild(ctx.guild).all()
        async with self._locks[ctx.guild.id]:
            async with self.config.guild(ctx.guild).events() as evs:
                ev = evs.get(str(event_id))
                if ev is None or ev["status"] in ("ended", "cancelled"):
                    return await ctx.send("Ese evento no existe o ya ha terminado.")
                ev["status"] = "cancelled"
                ev["recurrence"] = None
                current = copy.deepcopy(ev)
        await self.refresh_message(ctx.guild, current, settings)
        await self._cleanup_event(ctx.guild, current, settings)
        notified = 0
        for uid in dict.fromkeys(current["participants"] + current["waitlist"] + current["remind"]):
            member = ctx.guild.get_member(uid)
            if member is None:
                continue
            try:
                await member.send(f"🚫 El evento **{current['title']}** (<t:{current['start']}:F>) en {ctx.guild.name} ha sido cancelado." + (f"\nMotivo: {reason}" if reason else ""))
                notified += 1
            except discord.HTTPException:
                pass
        await ctx.send(f"🚫 Evento #{event_id} cancelado. Avisados: {notified}.")

    @event.command(name="clone")
    @is_event_staff()
    async def event_clone(self, ctx: commands.Context, event_id: int, *, when: str):
        """Repetir un evento anterior en otra fecha. Ej: `event clone 12 viernes 22:00`."""
        event = await self._get_event(ctx, event_id)
        if event is None:
            return
        tz = await self.config.guild(ctx.guild).timezone()
        start = parse_datetime(when, tz)
        if start is None or start < time.time():
            return await ctx.send("Fecha no valida o pasada. Ej: `02/10/2026 22:00`, `viernes 22:00`.")
        fields = self._clone_fields(event, start)
        fields["recurrence"] = None
        fields["creator"] = ctx.author.id
        new, msg = await self.create_event(ctx.guild, **fields)
        await ctx.send(f"✅ Evento clonado como **#{new['id']}** ({format_local(start, tz)})." + (f" {msg.jump_url}" if msg else ""))

    @event.command(name="repeat")
    @is_event_staff()
    async def event_repeat(self, ctx: commands.Context, event_id: int, frequency: str, weekday: Optional[str] = None, at: Optional[str] = None):
        """Hacer recurrente un evento: `event repeat 12 weekly friday 22:00`, `daily` o `off`."""
        frequency = frequency.lower()
        if frequency not in ("weekly", "daily", "off", "semanal", "diario"):
            return await ctx.send("Frecuencias: `weekly`, `daily`, `off`.")
        frequency = {"semanal": "weekly", "diario": "daily"}.get(frequency, frequency)
        wd = None
        if weekday:
            wd = WEEKDAYS.get(weekday.lower())
            if wd is None:
                return await ctx.send("Dia no valido (ej: `viernes`, `friday`).")
        if at and parse_time(at) is None:
            return await ctx.send("Hora no valida (ej: `22:00`).")
        async with self.config.guild(ctx.guild).events() as evs:
            ev = evs.get(str(event_id))
            if ev is None:
                return await ctx.send("No existe ese evento.")
            if frequency == "off":
                ev["recurrence"] = None
            else:
                tz = await self.config.guild(ctx.guild).timezone()
                local = datetime.datetime.fromtimestamp(ev["start"], get_tz(tz))
                ev["recurrence"] = {
                    "freq": frequency,
                    "weekday": wd if wd is not None else local.weekday(),
                    "time": at or local.strftime("%H:%M"),
                }
            current = copy.deepcopy(ev)
        await self.refresh_message(ctx.guild, current)
        if frequency == "off":
            return await ctx.send(f"El evento #{event_id} ya no se repite.")
        rec = current["recurrence"]
        when = "cada dia" if rec["freq"] == "daily" else f"cada {WEEKDAY_NAMES[rec['weekday']]}"
        await ctx.send(f"🔁 El evento #{event_id} se repetira {when} a las {rec['time']}. La siguiente edicion se publica al terminar esta.")

    @event.command(name="attend")
    @is_event_staff()
    async def event_attend(self, ctx: commands.Context, event_id: int, member: discord.Member):
        """Marcar/desmarcar manualmente la asistencia de un participante."""
        async with self.config.guild(ctx.guild).events() as evs:
            ev = evs.get(str(event_id))
            if ev is None:
                return await ctx.send("No existe ese evento.")
            if member.id not in ev["participants"]:
                return await ctx.send("Ese usuario no esta inscrito.")
            if member.id in ev["attended"]:
                ev["attended"].remove(member.id)
                text = f"Asistencia de {member.mention} desmarcada."
            else:
                ev["attended"].append(member.id)
                text = f"✋ Asistencia de {member.mention} registrada."
            current = copy.deepcopy(ev)
        await self.refresh_message(ctx.guild, current)
        await ctx.send(text, allowed_mentions=discord.AllowedMentions.none())

    @event.command(name="remove")
    @is_event_staff()
    async def event_remove(self, ctx: commands.Context, event_id: int, member: discord.Member):
        """Quitar a un participante (entra el primero de la lista de espera)."""
        promoted = None
        async with self._locks[ctx.guild.id]:
            async with self.config.guild(ctx.guild).events() as evs:
                ev = evs.get(str(event_id))
                if ev is None:
                    return await ctx.send("No existe ese evento.")
                if member.id in ev["waitlist"]:
                    ev["waitlist"].remove(member.id)
                elif member.id in ev["participants"]:
                    ev["participants"].remove(member.id)
                    if ev["role"]["assigned"]:
                        await self._take_role(ctx.guild, ev, [member.id])
                    if ev["waitlist"] and ev["status"] in ("scheduled", "ongoing"):
                        promoted = ev["waitlist"].pop(0)
                        ev["participants"].append(promoted)
                        if ev["role"]["assigned"]:
                            await self._give_role(ctx.guild, ev, [promoted])
                else:
                    return await ctx.send("Ese usuario no esta inscrito.")
                current = copy.deepcopy(ev)
        await self.refresh_message(ctx.guild, current)
        if promoted:
            await self._announce_promotion(ctx.guild, current, promoted)
        await ctx.send(f"{member.mention} eliminado del evento #{event_id}.", allowed_mentions=discord.AllowedMentions.none())

    @event_edit.autocomplete("event_id")
    @event_info.autocomplete("event_id")
    @event_participants.autocomplete("event_id")
    @event_cancel.autocomplete("event_id")
    @event_clone.autocomplete("event_id")
    @event_repeat.autocomplete("event_id")
    @event_attend.autocomplete("event_id")
    @event_remove.autocomplete("event_id")
    async def _ac_event(self, interaction: discord.Interaction, current: str):
        return await self._event_autocomplete(interaction, current)

    @event.command(name="stats")
    async def event_stats(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """Estadisticas de asistencia (del servidor o de un usuario)."""
        stats = await self.compute_stats(ctx.guild)
        events = stats["events"]
        if not events:
            return await ctx.send("Todavia no hay eventos finalizados.")
        if member is not None:
            uid = member.id
            joined = stats["participations"][uid]
            att = stats["attendances"][uid]
            embed = discord.Embed(title=f"📊 {member.display_name} en eventos", color=STATUS_COLOR["scheduled"])
            embed.add_field(name="Inscripciones", value=str(joined), inline=True)
            embed.add_field(name="Asistencias", value=str(att), inline=True)
            embed.add_field(name="No-shows", value=str(stats["noshows"][uid]), inline=True)
            embed.add_field(name="Cancelaciones", value=str(stats["cancels"][uid]), inline=True)
            tracked = sum(1 for e in stats["tracked"] if uid in e["participants"])
            if tracked:
                embed.add_field(name="Tasa de asistencia", value=f"{att / tracked * 100:.0f}%", inline=True)
            return await ctx.send(embed=embed)
        total_part = sum(len(e["participants"]) for e in events)
        with_slots = [e for e in events if e["slots"]]
        fill = (sum(len(e["participants"]) / e["slots"] for e in with_slots) / len(with_slots) * 100) if with_slots else None
        embed = discord.Embed(title="📊 Estadisticas de eventos", color=STATUS_COLOR["scheduled"])
        embed.add_field(name="Eventos finalizados", value=str(len(events)), inline=True)
        embed.add_field(name="Inscripciones", value=f"{total_part} (media {total_part / len(events):.1f})", inline=True)
        if fill is not None:
            embed.add_field(name="Ocupacion media", value=f"{fill:.0f}%", inline=True)
        embed.add_field(
            name="Asistencia historica",
            value=f"{stats['attendance_rate']:.0f}% ({len(stats['tracked'])} eventos con check-in)" if stats["attendance_rate"] is not None else "sin datos de check-in",
            inline=True,
        )
        embed.add_field(name="Cancelaciones", value=str(sum(stats["cancels"].values())), inline=True)
        embed.add_field(name="No-shows", value=str(sum(stats["noshows"].values())), inline=True)
        top_events = sorted(events, key=lambda e: -len(e["participants"]))[:5]
        embed.add_field(
            name="Eventos con mayor participacion",
            value="\n".join(f"`#{e['id']}` {e['title']} · {len(e['participants'])} · <t:{e['start']}:d>" for e in top_events),
            inline=False,
        )
        top_users = stats["participations"].most_common(5)
        if top_users:
            embed.add_field(
                name="Usuarios mas activos",
                value="\n".join(f"<@{u}> · {n} eventos · {stats['attendances'][u]} asistencias" for u, n in top_users),
                inline=False,
            )
        if stats["by_tag"]:
            rows = sorted(stats["by_tag"].items(), key=lambda kv: -kv[1][1])[:8]
            embed.add_field(
                name="Asistencia por tipo",
                value="\n".join(f"{tag}: {a / p * 100:.0f}% ({a}/{p})" for tag, (a, p) in rows if p),
                inline=False,
            )
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    # ------------------------------------------------------------------
    # Ajustes
    # ------------------------------------------------------------------

    @event.group(name="settings")
    @commands.admin_or_permissions(manage_guild=True)
    async def event_settings(self, ctx: commands.Context):
        """Configuracion de Trini Events."""

    async def _changed(self, ctx: commands.Context, key: str, value: Any) -> None:
        self.bot.dispatch("trini_settings_change", ctx.guild, "Events", ctx.author, key, str(value))

    @event_settings.command(name="show")
    async def settings_show(self, ctx: commands.Context):
        """Ver la configuracion actual."""
        s = await self.config.guild(ctx.guild).all()
        embed = discord.Embed(title="⚙️ Trini Events", color=STATUS_COLOR["scheduled"])
        embed.add_field(name="Canal por defecto", value=f"<#{s['channel']}>" if s["channel"] else "canal del comando", inline=True)
        embed.add_field(name="Zona horaria", value=s["timezone"], inline=True)
        embed.add_field(name="Recordatorios", value=", ".join(f"{m} min" for m in sorted(s["reminders"], reverse=True)) or "ninguno", inline=True)
        embed.add_field(name="Staff", value=(f"<@&{s['staff_role']}>" if s["staff_role"] else "—") + (" (ping)" if s["staff_ping"] else ""), inline=True)
        role = f"<@&{s['participant_role']}>" if s["participant_role"] else ("auto por evento" if s["auto_role"] else "no")
        embed.add_field(name="Rol de participante", value=f"{role} · {s['role_lead']} min antes", inline=True)
        embed.add_field(name="Canales temporales", value=f"{'si' if s['temp_channels'] else 'no'} · al acabar: {s['archive_mode']}", inline=True)
        embed.add_field(name="Duracion por defecto", value=f"{s['default_duration']} min", inline=True)
        embed.add_field(name="Check-in", value=f"{s['checkin_open']} min antes", inline=True)
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @event_settings.command(name="channel")
    async def settings_channel(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Canal donde se publican los eventos por defecto."""
        await self.config.guild(ctx.guild).channel.set(channel.id if channel else None)
        await self._changed(ctx, "channel", channel)
        await ctx.send(f"Canal de eventos: {channel.mention if channel else 'el del comando'}.")

    @event_settings.command(name="timezone")
    async def settings_timezone(self, ctx: commands.Context, timezone: str):
        """Zona horaria IANA para interpretar fechas (ej. `Europe/Madrid`)."""
        if not valid_tz(timezone):
            return await ctx.send("Zona horaria no valida. Ej: `Europe/Madrid`, `America/Mexico_City`, `UTC`.")
        await self.config.guild(ctx.guild).timezone.set(timezone)
        await self._changed(ctx, "timezone", timezone)
        await ctx.send(f"Zona horaria: `{timezone}`.")

    @event_settings.command(name="reminders")
    async def settings_reminders(self, ctx: commands.Context, *, minutes: str):
        """Recordatorios en minutos antes, separados por comas. Ej: `1440,60,15` o `none`."""
        if minutes.strip().lower() in ("none", "ninguno", "off"):
            values: List[int] = []
        else:
            try:
                values = sorted({int(m) for m in minutes.replace(" ", ",").split(",") if m}, reverse=True)
            except ValueError:
                return await ctx.send("Formato: `1440,60,15`.")
            if any(v <= 0 or v > 10080 for v in values) or len(values) > 5:
                return await ctx.send("Entre 1 y 10080 minutos, maximo 5 recordatorios.")
        await self.config.guild(ctx.guild).reminders.set(values)
        await self._changed(ctx, "reminders", values)
        await ctx.send(f"Recordatorios: {', '.join(f'{v} min' for v in values) or 'ninguno'}.")

    @event_settings.command(name="staffrole")
    async def settings_staffrole(self, ctx: commands.Context, role: Optional[discord.Role] = None, ping: bool = False):
        """Rol de staff de eventos (puede gestionarlos) y si se le avisa en los recordatorios."""
        await self.config.guild(ctx.guild).staff_role.set(role.id if role else None)
        await self.config.guild(ctx.guild).staff_ping.set(bool(role) and ping)
        await self._changed(ctx, "staff_role", role)
        await ctx.send(f"Staff de eventos: {role.mention if role else 'ninguno'}{' (con aviso)' if role and ping else ''}.", allowed_mentions=discord.AllowedMentions.none())

    @event_settings.command(name="participantrole")
    async def settings_participantrole(self, ctx: commands.Context, role: Optional[discord.Role] = None):
        """Rol fijo que se da a los inscritos antes del evento y se retira al acabar."""
        if role is not None and role >= ctx.guild.me.top_role:
            return await ctx.send("Ese rol esta por encima del mio.")
        await self.config.guild(ctx.guild).participant_role.set(role.id if role else None)
        await self._changed(ctx, "participant_role", role)
        await ctx.send(f"Rol de participante: {role.mention if role else 'ninguno'}.", allowed_mentions=discord.AllowedMentions.none())

    @event_settings.command(name="autorole")
    async def settings_autorole(self, ctx: commands.Context, enabled: bool):
        """Crear un rol temporal por evento (si no hay rol de participante fijo)."""
        await self.config.guild(ctx.guild).auto_role.set(enabled)
        await self._changed(ctx, "auto_role", enabled)
        await ctx.send(f"Rol automatico por evento: {'si' if enabled else 'no'}.")

    @event_settings.command(name="rolelead")
    async def settings_rolelead(self, ctx: commands.Context, minutes: int):
        """Minutos antes del evento para asignar el rol y crear canales."""
        await self.config.guild(ctx.guild).role_lead.set(max(0, min(minutes, 1440)))
        await self._changed(ctx, "role_lead", minutes)
        await ctx.send(f"Preparacion del evento: {max(0, min(minutes, 1440))} minutos antes.")

    @event_settings.command(name="tempchannels")
    async def settings_tempchannels(self, ctx: commands.Context, enabled: bool, archive_mode: Optional[str] = None):
        """Crear categoria y canales temporales por evento. Al acabar: `delete` o `archive`."""
        await self.config.guild(ctx.guild).temp_channels.set(enabled)
        if archive_mode:
            if archive_mode not in ("delete", "archive"):
                return await ctx.send("Modos: `delete`, `archive`.")
            await self.config.guild(ctx.guild).archive_mode.set(archive_mode)
        await self._changed(ctx, "temp_channels", f"{enabled} {archive_mode or ''}")
        await ctx.send(f"Canales temporales: {'si' if enabled else 'no'}" + (f" · al acabar: {archive_mode}" if archive_mode else "") + ". (Aplica a eventos nuevos)")

    @event_settings.command(name="duration")
    async def settings_duration(self, ctx: commands.Context, minutes: int):
        """Duracion por defecto de los eventos."""
        await self.config.guild(ctx.guild).default_duration.set(max(5, min(minutes, 10080)))
        await self._changed(ctx, "default_duration", minutes)
        await ctx.send(f"Duracion por defecto: {max(5, min(minutes, 10080))} min.")

    @event_settings.command(name="checkin")
    async def settings_checkin(self, ctx: commands.Context, minutes: int):
        """Minutos antes del inicio en los que se abre el check-in."""
        await self.config.guild(ctx.guild).checkin_open.set(max(0, min(minutes, 240)))
        await self._changed(ctx, "checkin_open", minutes)
        await ctx.send(f"El check-in se abre {max(0, min(minutes, 240))} min antes.")
