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

from .third_party import get_adapter
from redbot.core.i18n import Translator

_ = Translator("TriniProfiles", __file__)

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


# Claves de datos en tiempo de ejecucion (historiales, caches, contadores...)
# que no son configuracion. Se descartan cuando un cog no implementa
# ``trini_export`` y hay que volcar su Config en bruto.
_RUNTIME_KEY_EXACT = frozenset({
    "history", "cache", "cooldowns", "user_cooldowns", "stats", "statistics",
    "opened", "archived", "active", "entries", "leaderboard", "logs",
})
_RUNTIME_KEY_SUFFIXES = ("_history", "_cache", "_cooldowns", "_stats", "_log_entries")


def _is_runtime_key(key: Any) -> bool:
    name = str(key).lower()
    return name in _RUNTIME_KEY_EXACT or name.endswith(_RUNTIME_KEY_SUFFIXES)


SCOPES_KEY = "__trini_scopes__"


def find_config(cog: commands.Cog) -> Optional[Config]:
    """``Config`` del cog: normalmente ``self.config``, pero algunos cogs de
    terceros lo guardan con otro nombre (p. ej. Sticky usa ``self.conf``)."""
    config = getattr(cog, "config", None)
    if isinstance(config, Config):
        return config
    for value in vars(cog).values():
        if isinstance(value, Config):
            return value
    return None


def _drop_path(data: Dict[str, Any], path: Tuple[str, ...]) -> None:
    node: Any = data
    for key in path[:-1]:
        node = node.get(key) if isinstance(node, dict) else None
        if node is None:
            return
    if isinstance(node, dict):
        node.pop(path[-1], None)


def _deep_merge(base: Any, update: Any) -> Any:
    """``update`` sobre ``base`` conservando lo que ``update`` no trae."""
    if isinstance(base, dict) and isinstance(update, dict):
        merged = dict(base)
        for key, value in update.items():
            merged[key] = _deep_merge(base.get(key), value) if key in base else value
        return merged
    return update


async def _export_raw(cog: commands.Cog, config: Config, guild: discord.Guild) -> Dict[str, Any]:
    """Copia en bruto de un cog sin ``trini_export``, afinada con su adaptador."""
    adapter = get_adapter(cog.qualified_name)
    data = await config.guild(guild).all()
    data = {k: v for k, v in data.items() if not _is_runtime_key(k) and k not in adapter.runtime}
    for path in adapter.runtime_paths:
        _drop_path(data, path)
    scopes: Dict[str, Any] = {}
    if adapter.channel:
        channels = {
            str(cid): {k: v for k, v in values.items() if k not in adapter.channel_runtime}
            for cid, values in (await config.all_channels()).items()
            if guild.get_channel(cid) is not None
        }
        if channels:
            scopes["channel"] = channels
    if adapter.role:
        roles = {str(rid): values for rid, values in (await config.all_roles()).items() if guild.get_role(rid) is not None}
        if roles:
            scopes["role"] = roles
    for group in adapter.custom_guild_groups:
        entries = await config.custom(group, str(guild.id)).all()
        if entries:
            scopes.setdefault("custom", {})[group] = entries
    if scopes:
        data[SCOPES_KEY] = scopes
    return data


async def export_cog(cog: commands.Cog, guild: discord.Guild) -> Optional[Dict[str, Any]]:
    """Exporta la configuracion de servidor de un cog (o ``None`` si no es posible)."""
    try:
        exporter = getattr(cog, "trini_export", None)
        if exporter is not None:
            return _json_safe(await exporter(guild))
        config = find_config(cog)
        if config is not None:
            return _json_safe(await _export_raw(cog, config, guild))
    except Exception:
        log.exception("No se pudo exportar la configuracion de %s", cog.qualified_name)
    return None


async def _import_raw(
    cog: commands.Cog, config: Config, guild: discord.Guild, data: Dict[str, Any], *, same_guild: bool
) -> List[str]:
    adapter = get_adapter(cog.qualified_name)
    data = dict(data)
    scopes = data.pop(SCOPES_KEY, None) or {}
    group = config.guild(guild)
    current = await group.all()
    merge_keys = {path[0] for path in adapter.runtime_paths}
    for key, value in data.items():
        if key not in current or _is_runtime_key(key) or key in adapter.runtime:
            continue
        if key in adapter.local and not same_guild:
            continue
        if key in merge_keys:
            # Conserva los datos de funcionamiento actuales (contadores, ultimo mensaje).
            value = _deep_merge(current[key], value)
        await group.set_raw(key, value=value)
    for cid, values in (scopes.get("channel") or {}).items():
        if not str(cid).isdigit() or guild.get_channel(int(cid)) is None:
            continue
        channel_group = config.channel_from_id(int(cid))
        channel_current = await channel_group.all()
        for key, value in values.items():
            if key in channel_current and key not in adapter.channel_runtime:
                await channel_group.set_raw(key, value=value)
    for rid, values in (scopes.get("role") or {}).items():
        if not str(rid).isdigit() or guild.get_role(int(rid)) is None:
            continue
        role_group = config.role_from_id(int(rid))
        role_current = await role_group.all()
        for key, value in values.items():
            if key in role_current:
                await role_group.set_raw(key, value=value)
    for group_name, entries in (scopes.get("custom") or {}).items():
        if group_name not in adapter.custom_guild_groups:
            continue
        for sub_id, values in entries.items():
            # En los grupos soportados el segundo identificador es un canal del servidor.
            if str(sub_id).isdigit() and guild.get_channel(int(sub_id)) is None:
                continue
            await config.custom(group_name, str(guild.id), str(sub_id)).set(values)
    return [_(adapter.note)] if adapter.note and not same_guild else []


async def import_cog(
    cog: commands.Cog, guild: discord.Guild, data: Dict[str, Any], *, same_guild: bool
) -> List[str]:
    """Importa configuracion en un cog. Devuelve avisos."""
    importer = getattr(cog, "trini_import", None)
    if importer is not None:
        return list(await importer(guild, data, same_guild=same_guild) or [])
    config = find_config(cog)
    if config is not None:
        return await _import_raw(cog, config, guild, data, same_guild=same_guild)
    return [_("{qualified_name}: doesn't support import.").format(qualified_name=cog.qualified_name)]
