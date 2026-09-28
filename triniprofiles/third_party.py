"""Adaptadores de exportacion para cogs de terceros.

Los cogs de terceros no implementan ``trini_export``/``trini_import``, asi que
Profiles copia su ``Config`` en bruto. Estos adaptadores (sacados de la
configuracion real de cada cog) afinan esa copia:

- ``runtime`` / ``runtime_paths``: datos de funcionamiento (ultimo mensaje
  enviado, contadores...) que no son configuracion y no se copian.
- ``local``: configuracion ligada a mensajes concretos de ESTE servidor (botones
  de roles, formularios...); solo se importa en el mismo servidor.
- ``channel`` / ``role``: el cog guarda configuracion por canal o por rol (no
  solo por servidor) y tambien se exporta.
- ``custom_guild_groups``: grupos ``Config.custom`` cuyo primer identificador es
  el servidor (p. ej. las salas origen de AutoRoom).
- ``note``: aviso al importar en otro servidor.

La clave del diccionario es el ``qualified_name`` del cog cargado.
"""
from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class Adapter:
    runtime: Tuple[str, ...] = ()
    runtime_paths: Tuple[Tuple[str, str], ...] = ()
    local: Tuple[str, ...] = ()
    channel: bool = False
    channel_runtime: Tuple[str, ...] = ()
    role: bool = False
    custom_guild_groups: Tuple[str, ...] = ()
    note: str = ""


ADAPTERS: Dict[str, Adapter] = {
    # Welcome (join/leave/ban/unban): "last" es el ultimo mensaje enviado y
    # "counter" el numero de entradas; "date" es el dia del contador.
    "Welcome": Adapter(
        runtime=("date",),
        runtime_paths=tuple((event, key) for event in ("join", "leave", "ban", "unban") for key in ("last", "counter")),
    ),
    # Disboard: "nextBump" es la hora del proximo bump de ESTE servidor.
    "DisboardReminder": Adapter(runtime=("nextBump",)),
    # Sticky: todo se guarda por canal; "last" es el ultimo mensaje fijado.
    "Sticky": Adapter(channel=True, channel_runtime=("last",)),
    # LinkWarner: ajustes del servidor + excepciones por canal.
    "LinkWarner": Adapter(channel=True),
    # AutoRoom: las salas origen van en el grupo (servidor, canal origen); los
    # datos por canal son las salas creadas en ese momento (no se copian).
    "AutoRoom": Adapter(custom_guild_groups=("AUTOROOM_SOURCE",)),
    # RoleUtils: roles "sticky" por rol; los reaction roles dependen de mensajes.
    "RoleUtils": Adapter(
        role=True,
        note="RoleUtils: los reaction roles van ligados a mensajes y no se copian; vuelve a crearlos.",
    ),
    "RolesButtons": Adapter(
        local=("roles_buttons", "modes"),
        note="RolesButtons: los botones van ligados a mensajes; vuelve a crearlos en este servidor.",
    ),
    "UrlButtons": Adapter(
        local=("url_buttons",),
        note="UrlButtons: los botones van ligados a mensajes; vuelve a crearlos en este servidor.",
    ),
    "DiscordModals": Adapter(
        local=("modals",),
        note="DiscordModals: los formularios van ligados a mensajes; vuelve a crearlos en este servidor.",
    ),
    "YouTube": Adapter(
        note="YouTube: las suscripciones son globales del bot y no se copian; vuelve a suscribir los canales.",
    ),
}


def get_adapter(qualified_name: str) -> Adapter:
    return ADAPTERS.get(qualified_name, Adapter())
