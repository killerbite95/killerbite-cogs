"""
Exportacion / importacion portable de configuracion de cogs.

Protocolo que puede implementar cualquier cog compatible con La Trini:

    async def trini_export(self, guild: discord.Guild) -> dict
    async def trini_import(self, guild: discord.Guild, data: dict, *, same_guild: bool) -> list[str]

Si un cog no implementa el protocolo pero tiene un atributo ``config`` de Red,
se usa su configuracion de servidor tal cual (``config.guild(guild).all()``).

Los IDs de canales y roles se guardan junto a su nombre para poder
re-mapearlos al importar en otro servidor.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import discord
from redbot.core import Config, commands

log = logging.getLogger("red.killerbite95.triniprofiles.portable")

SNOWFLAKE_MIN = 10**15


def _is_snowflake(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= SNOWFLAKE_MIN:
        return value
    if isinstance(value, str) and value.isdigit() and 16 <= len(value) <= 21:
        return int(value)
    return None


def collect_references(data: Any, guild: discord.Guild) -> Dict[str, Dict[str, str]]:
    """Busca IDs de canales/roles del servidor dentro de ``data``."""
    refs: Dict[str, Dict[str, str]] = {}

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                visit(k)
                visit(v)
            return
        if isinstance(value, (list, tuple, set)):
            for v in value:
                visit(v)
            return
        sid = _is_snowflake(value)
        if sid is None:
            return
        role = guild.get_role(sid)
        if role is not None:
            refs[str(sid)] = {"kind": "role", "name": role.name}
            return
        channel = guild.get_channel(sid)
        if channel is not None:
            refs[str(sid)] = {
                "kind": "channel",
                "name": channel.name,
                "type": str(channel.type),
            }

    visit(data)
    return refs


def remap_references(
    data: Any, refs: Dict[str, Dict[str, str]], guild: discord.Guild
) -> Tuple[Any, List[str]]:
    """Sustituye IDs antiguos por los equivalentes por nombre en ``guild``."""
    mapping: Dict[int, Optional[int]] = {}
    missing: List[str] = []
    for old, ref in refs.items():
        old_id = int(old)
        target = None
        if ref.get("kind") == "role":
            target = guild.get_role(old_id) or discord.utils.get(guild.roles, name=ref.get("name"))
        elif ref.get("kind") == "channel":
            target = guild.get_channel(old_id) or discord.utils.get(
                guild.channels, name=ref.get("name")
            )
        if target is None:
            missing.append(f"{ref.get('kind')} `{ref.get('name')}`")
            mapping[old_id] = None
        else:
            mapping[old_id] = target.id

    def convert(value: Any) -> Any:
        if isinstance(value, dict):
            return {convert(k): convert(v) for k, v in value.items()}
        if isinstance(value, list):
            return [convert(v) for v in value]
        sid = _is_snowflake(value)
        if sid is not None and sid in mapping:
            new = mapping[sid]
            if isinstance(value, str):
                return str(new) if new is not None else value
            return new
        return value

    return convert(data), missing


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


async def export_cog(cog: commands.Cog, guild: discord.Guild) -> Optional[Dict[str, Any]]:
    """Exporta la configuracion de servidor de un cog (o ``None`` si no es posible)."""
    try:
        exporter = getattr(cog, "trini_export", None)
        if exporter is not None:
            return _json_safe(await exporter(guild))
        config = getattr(cog, "config", None)
        if isinstance(config, Config):
            return _json_safe(await config.guild(guild).all())
    except Exception:
        log.exception("No se pudo exportar la configuracion de %s", cog.qualified_name)
    return None


async def import_cog(
    cog: commands.Cog, guild: discord.Guild, data: Dict[str, Any], *, same_guild: bool
) -> List[str]:
    """Importa configuracion en un cog. Devuelve avisos."""
    importer = getattr(cog, "trini_import", None)
    if importer is not None:
        return list(await importer(guild, data, same_guild=same_guild) or [])
    config = getattr(cog, "config", None)
    if isinstance(config, Config):
        group = config.guild(guild)
        defaults = await group.all()
        for key, value in data.items():
            if key in defaults:
                await group.set_raw(key, value=value)
        return []
    return [f"{cog.qualified_name}: no soporta importacion."]
