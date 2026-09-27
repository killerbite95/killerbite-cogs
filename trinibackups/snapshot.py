"""
Captura estructural, diff y plan de restauracion no destructiva.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import discord

FORMAT = "trini-backup"
VERSION = 1

CHANNEL_TYPES = {
    discord.ChannelType.text: "text",
    discord.ChannelType.news: "news",
    discord.ChannelType.voice: "voice",
    discord.ChannelType.stage_voice: "stage",
    discord.ChannelType.category: "category",
    discord.ChannelType.forum: "forum",
}
if hasattr(discord.ChannelType, "media"):
    CHANNEL_TYPES[discord.ChannelType.media] = "media"

TYPE_ICON = {"text": "#", "news": "📢", "voice": "🔊", "stage": "🎙", "category": "📁", "forum": "💬", "media": "🖼"}

STATE = {True: "✅", False: "❌", None: "➖"}


PERM_ALIASES = {"read_messages": "view_channel", "manage_emojis": "manage_expressions", "use_slash_commands": "use_application_commands"}


def _label(perm: str) -> str:
    return PERM_ALIASES.get(perm, perm).replace("_", " ").title()


# ----------------------------------------------------------------------
# Captura
# ----------------------------------------------------------------------


def capture_structure(guild: discord.Guild) -> Dict[str, Any]:
    roles = []
    for r in guild.roles:
        roles.append(
            {
                "id": r.id,
                "name": r.name,
                "color": r.color.value,
                "hoist": r.hoist,
                "mentionable": r.mentionable,
                "position": r.position,
                "permissions": r.permissions.value,
                "managed": r.managed,
                "default": r.is_default(),
                "bot_id": r.tags.bot_id if r.tags else None,
            }
        )
    channels = []
    for c in guild.channels:
        ctype = CHANNEL_TYPES.get(c.type)
        if ctype is None:
            continue
        overwrites = []
        for target, ow in c.overwrites.items():
            allow, deny = ow.pair()
            is_role = isinstance(target, discord.Role)
            overwrites.append(
                {
                    "id": target.id,
                    "type": "role" if is_role else "member",
                    "name": ("@everyone" if is_role and target.is_default() else getattr(target, "name", str(target.id))),
                    "allow": allow.value,
                    "deny": deny.value,
                }
            )
        data: Dict[str, Any] = {
            "id": c.id,
            "name": c.name,
            "type": ctype,
            "category_id": c.category_id if not isinstance(c, discord.CategoryChannel) else None,
            "position": c.position,
            "synced": getattr(c, "permissions_synced", False) if not isinstance(c, discord.CategoryChannel) else None,
            "overwrites": overwrites,
        }
        if isinstance(c, (discord.TextChannel, discord.ForumChannel)):
            data["topic"] = c.topic
            data["nsfw"] = c.nsfw
            data["slowmode"] = c.slowmode_delay
            data["default_auto_archive"] = c.default_auto_archive_duration
        if isinstance(c, discord.ForumChannel):
            data["tags"] = [{"name": t.name, "moderated": t.moderated, "emoji": str(t.emoji) if t.emoji else None} for t in c.available_tags]
        if isinstance(c, (discord.VoiceChannel, discord.StageChannel)):
            data["bitrate"] = c.bitrate
            data["user_limit"] = c.user_limit
            data["nsfw"] = getattr(c, "nsfw", False)
            data["slowmode"] = getattr(c, "slowmode_delay", 0)
        channels.append(data)
    return {
        "guild": {
            "id": guild.id,
            "name": guild.name,
            "verification_level": str(guild.verification_level),
            "explicit_content_filter": str(guild.explicit_content_filter),
            "default_notifications": str(guild.default_notifications),
            "mfa_level": int(guild.mfa_level.value if hasattr(guild.mfa_level, "value") else guild.mfa_level),
            "afk_timeout": guild.afk_timeout,
            "afk_channel": guild.afk_channel.id if guild.afk_channel else None,
            "system_channel": guild.system_channel.id if guild.system_channel else None,
            "rules_channel": guild.rules_channel.id if guild.rules_channel else None,
            "invites_disabled": "INVITES_DISABLED" in guild.features,
        },
        "roles": roles,
        "channels": channels,
        "bots": [{"id": m.id, "name": str(m)} for m in guild.members if m.bot],
    }


def counts(snapshot: Dict[str, Any]) -> Dict[str, int]:
    return {
        "roles": len(snapshot.get("roles", [])),
        "channels": len([c for c in snapshot.get("channels", []) if c["type"] != "category"]),
        "categories": len([c for c in snapshot.get("channels", []) if c["type"] == "category"]),
        "bots": len(snapshot.get("bots", [])),
        "trini": len(snapshot.get("trini", {})),
    }


# ----------------------------------------------------------------------
# Diff
# ----------------------------------------------------------------------


def _perm_names(value: int) -> set:
    return {name for name, v in discord.Permissions(value) if v}


def _ow_state(ow: Optional[Dict[str, Any]], perm: str) -> Optional[bool]:
    if ow is None:
        return None
    if perm in _perm_names(ow["allow"]):
        return True
    if perm in _perm_names(ow["deny"]):
        return False
    return None


def diff_snapshots(old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, List[str]]:
    """Devuelve {seccion: [lineas]} con las diferencias de ``old`` a ``new``."""
    out: Dict[str, List[str]] = {"SERVIDOR": [], "ROLES": [], "CANALES": [], "PERMISOS DE CANALES": [], "BOTS": [], "CONFIGURACION LA TRINI": []}

    # Servidor
    og, ng = old.get("guild", {}), new.get("guild", {})
    labels = {"name": "Nombre", "verification_level": "Verificacion", "explicit_content_filter": "Filtro de contenido",
              "mfa_level": "2FA moderacion", "default_notifications": "Notificaciones", "invites_disabled": "Invitaciones pausadas"}
    for key, label in labels.items():
        if og.get(key) != ng.get(key):
            out["SERVIDOR"].append(f"{label}: {og.get(key)} → {ng.get(key)}")

    # Roles
    old_roles = {r["id"]: r for r in old.get("roles", [])}
    new_roles = {r["id"]: r for r in new.get("roles", [])}
    role_names = {**{k: v["name"] for k, v in old_roles.items()}, **{k: v["name"] for k, v in new_roles.items()}}
    for rid, r in new_roles.items():
        if rid not in old_roles:
            out["ROLES"].append(f"+ @{r['name']}" + (" (bot)" if r.get("managed") else ""))
    for rid, r in old_roles.items():
        if rid not in new_roles:
            out["ROLES"].append(f"- @{r['name']}")
    for rid, n in new_roles.items():
        o = old_roles.get(rid)
        if o is None:
            continue
        lines = []
        if o["name"] != n["name"]:
            lines.append(f"  nombre: {o['name']} → {n['name']}")
        if o["permissions"] != n["permissions"]:
            op, np_ = _perm_names(o["permissions"]), _perm_names(n["permissions"])
            lines += [f"  + {_label(p)}" for p in sorted(np_ - op)]
            lines += [f"  - {_label(p)}" for p in sorted(op - np_)]
        for key, label in (("color", "color"), ("hoist", "separado"), ("mentionable", "mencionable")):
            if o.get(key) != n.get(key):
                ov, nv = o.get(key), n.get(key)
                if key == "color":
                    ov, nv = f"#{ov:06x}", f"#{nv:06x}"
                lines.append(f"  {label}: {ov} → {nv}")
        if lines:
            out["ROLES"].append(f"{'@everyone' if n.get('default') else n['name']}\n" + "\n".join(lines))
    common = [rid for rid in new_roles if rid in old_roles]
    old_order = sorted(common, key=lambda i: old_roles[i]["position"])
    new_order = sorted(common, key=lambda i: new_roles[i]["position"])
    moved = [rid for idx, rid in enumerate(new_order) if old_order.index(rid) != idx]
    if moved and len(moved) <= len(common):
        # Solo se informan roles que cambian de orden relativo.
        names = [role_names[r] for r in moved[:10]]
        out["ROLES"].append(f"~ Jerarquia: {len(moved)} rol(es) cambian de posicion ({', '.join(names)}{'…' if len(moved) > 10 else ''})")

    # Canales
    old_ch = {c["id"]: c for c in old.get("channels", [])}
    new_ch = {c["id"]: c for c in new.get("channels", [])}
    ch_names = {**{k: v["name"] for k, v in old_ch.items()}, **{k: v["name"] for k, v in new_ch.items()}}

    def cname(c: Dict[str, Any]) -> str:
        return f"{TYPE_ICON.get(c['type'], '#')}{c['name']}"

    for cid, c in new_ch.items():
        if cid not in old_ch:
            out["CANALES"].append(f"+ {cname(c)}")
    for cid, c in old_ch.items():
        if cid not in new_ch:
            out["CANALES"].append(f"- {cname(c)}")
    for cid, n in new_ch.items():
        o = old_ch.get(cid)
        if o is None:
            continue
        lines = []
        if o["name"] != n["name"]:
            lines.append(f"  nombre: {o['name']} → {n['name']}")
        if o.get("category_id") != n.get("category_id"):
            lines.append(f"  categoria: {ch_names.get(o.get('category_id'), '—')} → {ch_names.get(n.get('category_id'), '—')}")
        for key, label in (("topic", "topic"), ("nsfw", "NSFW"), ("slowmode", "slowmode"), ("bitrate", "bitrate"), ("user_limit", "limite")):
            if o.get(key) != n.get(key):
                ov, nv = o.get(key), n.get(key)
                if key == "topic":
                    ov, nv = (ov or "—")[:40], (nv or "—")[:40]
                lines.append(f"  {label}: {ov} → {nv}")
        if lines:
            out["CANALES"].append(f"{cname(n)}\n" + "\n".join(lines))
        # Overwrites
        o_ow = {w["id"]: w for w in o.get("overwrites", [])}
        n_ow = {w["id"]: w for w in n.get("overwrites", [])}
        ow_lines = []
        for tid in set(o_ow) | set(n_ow):
            a, b = o_ow.get(tid), n_ow.get(tid)
            if a and b and a["allow"] == b["allow"] and a["deny"] == b["deny"]:
                continue
            target = (b or a)["name"]
            perms = set()
            for w in (a, b):
                if w:
                    perms |= _perm_names(w["allow"]) | _perm_names(w["deny"])
            for p in sorted(perms):
                sa, sb = _ow_state(a, p), _ow_state(b, p)
                if sa != sb:
                    ow_lines.append(f"  {_label(p)}: {target} {STATE[sa]} → {STATE[sb]}")
        if ow_lines:
            out["PERMISOS DE CANALES"].append(f"{cname(n)}\n" + "\n".join(ow_lines[:15]) + (f"\n  … y {len(ow_lines) - 15} mas" if len(ow_lines) > 15 else ""))

    # Bots
    old_bots = {b["id"]: b for b in old.get("bots", [])}
    new_bots = {b["id"]: b for b in new.get("bots", [])}
    out["BOTS"] += [f"+ {b['name']}" for bid, b in new_bots.items() if bid not in old_bots]
    out["BOTS"] += [f"- {b['name']}" for bid, b in old_bots.items() if bid not in new_bots]

    # Configuracion Trini
    ot, nt = old.get("trini", {}), new.get("trini", {})
    for cog in sorted(set(ot) | set(nt)):
        if cog not in ot:
            out["CONFIGURACION LA TRINI"].append(f"+ {cog}")
        elif cog not in nt:
            out["CONFIGURACION LA TRINI"].append(f"- {cog}")
        elif ot[cog] != nt[cog]:
            keys = sorted(k for k in set(ot[cog]) | set(nt[cog]) if ot[cog].get(k) != nt[cog].get(k)) if isinstance(ot[cog], dict) and isinstance(nt[cog], dict) else []
            out["CONFIGURACION LA TRINI"].append(f"~ {cog}: {', '.join(keys[:8]) or 'cambios'}")

    return {k: v for k, v in out.items() if v}


def diff_to_embeds(diff: Dict[str, List[str]], title: str, subtitle: str) -> List[discord.Embed]:
    if not diff:
        return [discord.Embed(title=title, description=f"{subtitle}\n\n🟢 Sin diferencias.", color=discord.Color.green())]
    embeds: List[discord.Embed] = []
    current = discord.Embed(title=title, description=subtitle, color=discord.Color.orange())
    size = len(subtitle)
    for section, lines in diff.items():
        chunk: List[str] = []
        chunk_len = 0
        parts: List[str] = []
        for line in lines:
            if chunk_len + len(line) + 1 > 1000:
                parts.append("\n".join(chunk))
                chunk, chunk_len = [], 0
            chunk.append(line[:990])
            chunk_len += len(line) + 1
        if chunk:
            parts.append("\n".join(chunk))
        for i, part in enumerate(parts):
            name = section if i == 0 else f"{section} (cont.)"
            if len(current.fields) >= 10 or size + len(part) > 5200:
                embeds.append(current)
                current = discord.Embed(title=f"{title} (cont.)", color=discord.Color.orange())
                size = 0
            current.add_field(name=name, value=f"```diff\n{part[:1000]}\n```"[:1024], inline=False)
            size += len(part) + len(name)
    embeds.append(current)
    return embeds[:10]


# ----------------------------------------------------------------------
# Plan de restauracion segura
# ----------------------------------------------------------------------


@dataclass
class RestorePlan:
    create_roles: List[Dict[str, Any]] = field(default_factory=list)
    update_roles: List[Tuple[discord.Role, Dict[str, Any], List[str]]] = field(default_factory=list)
    reorder_roles: Dict[discord.Role, int] = field(default_factory=dict)
    create_channels: List[Dict[str, Any]] = field(default_factory=list)
    update_channels: List[Tuple[discord.abc.GuildChannel, Dict[str, Any], List[str]]] = field(default_factory=list)
    overwrites: List[Tuple[int, Dict[str, Any], str]] = field(default_factory=list)  # (snap channel id, overwrite, label)
    trini: List[str] = field(default_factory=list)
    role_map: Dict[int, int] = field(default_factory=dict)
    channel_map: Dict[int, int] = field(default_factory=dict)
    skipped: List[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not any([self.create_roles, self.update_roles, self.reorder_roles, self.create_channels, self.update_channels, self.overwrites, self.trini])


def build_plan(guild: discord.Guild, snap: Dict[str, Any], options: Dict[str, bool]) -> RestorePlan:
    plan = RestorePlan()
    me = guild.me
    top = me.top_role

    # --- Mapeo de roles ---
    live_by_name: Dict[str, List[discord.Role]] = {}
    for r in guild.roles:
        live_by_name.setdefault(r.name, []).append(r)
    for rs in snap.get("roles", []):
        live = guild.get_role(rs["id"])
        if live is None and rs.get("default"):
            live = guild.default_role
        if live is None and len(live_by_name.get(rs["name"], [])) == 1:
            live = live_by_name[rs["name"]][0]
        if live is not None:
            plan.role_map[rs["id"]] = live.id
            continue
        if rs.get("managed"):
            plan.skipped.append(f"@{rs['name']} (rol de bot/integracion)")
            continue
        if options.get("roles", True):
            plan.create_roles.append(rs)

    # --- Actualizacion de roles existentes ---
    if options.get("permissions", True):
        for rs in snap.get("roles", []):
            live = guild.get_role(plan.role_map.get(rs["id"], 0))
            if live is None or live.managed:
                continue
            if not live.is_default() and live >= top:
                if live.permissions.value != rs["permissions"]:
                    plan.skipped.append(f"@{live.name} (por encima del bot)")
                continue
            changes: Dict[str, Any] = {}
            desc: List[str] = []
            if live.permissions.value != rs["permissions"]:
                changes["permissions"] = discord.Permissions(rs["permissions"])
                added = _perm_names(rs["permissions"]) - _perm_names(live.permissions.value)
                removed = _perm_names(live.permissions.value) - _perm_names(rs["permissions"])
                desc.append(" ".join([f"+{_label(p)}" for p in sorted(added)] + [f"-{_label(p)}" for p in sorted(removed)]))
            if not live.is_default():
                if live.name != rs["name"]:
                    changes["name"] = rs["name"]
                    desc.append(f"nombre → {rs['name']}")
                if live.color.value != rs["color"]:
                    changes["colour"] = discord.Colour(rs["color"])
                if live.hoist != rs["hoist"]:
                    changes["hoist"] = rs["hoist"]
                if live.mentionable != rs["mentionable"]:
                    changes["mentionable"] = rs["mentionable"]
                    desc.append(f"mencionable → {rs['mentionable']}")
            if changes:
                plan.update_roles.append((live, changes, desc))

    # --- Reordenar ---
    if options.get("positions", False):
        pairs = []
        for rs in snap.get("roles", []):
            live = guild.get_role(plan.role_map.get(rs["id"], 0))
            if live is None or live.is_default() or live >= top:
                continue
            pairs.append((rs["position"], live))
        slots = sorted(r.position for _, r in pairs)
        desired = [r for _, r in sorted(pairs, key=lambda p: p[0])]
        for pos, role in zip(slots, desired):
            if role.position != pos:
                plan.reorder_roles[role] = pos

    # --- Mapeo de canales ---
    live_ch_by_key: Dict[Tuple[str, str], List[discord.abc.GuildChannel]] = {}
    for c in guild.channels:
        live_ch_by_key.setdefault((c.name, CHANNEL_TYPES.get(c.type, "?")), []).append(c)
    snap_channels = sorted(snap.get("channels", []), key=lambda c: (c["type"] != "category", c["position"]))
    for cs in snap_channels:
        live = guild.get_channel(cs["id"])
        if live is None and len(live_ch_by_key.get((cs["name"], cs["type"]), [])) == 1:
            live = live_ch_by_key[(cs["name"], cs["type"])][0]
        if live is not None:
            plan.channel_map[cs["id"]] = live.id
        elif options.get("channels", True):
            plan.create_channels.append(cs)

    # --- Actualizacion de canales existentes ---
    if options.get("channels", True):
        for cs in snap_channels:
            live = guild.get_channel(plan.channel_map.get(cs["id"], 0))
            if live is None:
                continue
            changes = {}
            desc = []
            if live.name != cs["name"]:
                changes["name"] = cs["name"]
                desc.append(f"nombre → {cs['name']}")
            if "topic" in cs and getattr(live, "topic", None) != cs.get("topic") and hasattr(live, "topic"):
                changes["topic"] = cs.get("topic") or ""
                desc.append("topic")
            if "nsfw" in cs and hasattr(live, "nsfw") and live.nsfw != cs.get("nsfw"):
                changes["nsfw"] = cs.get("nsfw", False)
                desc.append(f"NSFW → {cs.get('nsfw')}")
            if "slowmode" in cs and hasattr(live, "slowmode_delay") and live.slowmode_delay != (cs.get("slowmode") or 0):
                changes["slowmode_delay"] = cs.get("slowmode") or 0
                desc.append(f"slowmode → {cs.get('slowmode')}s")
            if cs.get("category_id") and not isinstance(live, discord.CategoryChannel):
                target_cat = plan.channel_map.get(cs["category_id"])
                if target_cat and live.category_id != target_cat:
                    changes["category_id"] = target_cat
                    desc.append("categoria")
            if changes:
                plan.update_channels.append((live, changes, desc))

    # --- Overwrites ---
    if options.get("permissions", True):
        for cs in snap_channels:
            live = guild.get_channel(plan.channel_map.get(cs["id"], 0))
            if live is None:
                continue  # los canales nuevos se crean ya con sus overwrites
            current = {t.id: ow.pair() for t, ow in live.overwrites.items()}
            for ow in cs.get("overwrites", []):
                tid = plan.role_map.get(ow["id"], ow["id"]) if ow["type"] == "role" else ow["id"]
                if ow["type"] == "role" and guild.get_role(tid) is None and ow["id"] not in [r["id"] for r in plan.create_roles]:
                    continue
                if ow["type"] == "member" and guild.get_member(tid) is None:
                    continue
                cur = current.get(tid)
                if cur and cur[0].value == ow["allow"] and cur[1].value == ow["deny"]:
                    continue
                plan.overwrites.append((cs["id"], ow, f"{live.name} · {ow['name']}"))

    if options.get("trini", True):
        plan.trini = sorted(snap.get("trini", {}).keys())
    return plan


def plan_summary(plan: RestorePlan) -> str:
    lines = ["Se realizaran:", ""]
    if plan.create_roles:
        lines.append(f"+ Crear {len(plan.create_roles)} roles")
    cats = [c for c in plan.create_channels if c["type"] == "category"]
    chans = [c for c in plan.create_channels if c["type"] != "category"]
    if cats:
        lines.append(f"+ Crear {len(cats)} categorias")
    if chans:
        lines.append(f"+ Crear {len(chans)} canales")
    perm_changes = len(plan.overwrites) + sum(1 for _, c, _ in plan.update_roles if "permissions" in c)
    if perm_changes:
        lines.append(f"~ Modificar {perm_changes} permisos")
    other_roles = sum(1 for _, c, _ in plan.update_roles if set(c) - {"permissions"})
    if other_roles:
        lines.append(f"~ Modificar {other_roles} roles")
    if plan.reorder_roles:
        lines.append(f"~ Reordenar {len(plan.reorder_roles)} roles")
    if plan.update_channels:
        lines.append(f"~ Modificar {len(plan.update_channels)} canales")
    if plan.trini:
        lines.append(f"~ Restaurar configuracion de {len(plan.trini)} modulos Trini")
    if plan.empty:
        lines.append("Nada que restaurar: el servidor ya coincide con el backup.")
    lines += ["", "No se eliminara ningun elemento actual."]
    return "\n".join(lines)


def plan_details(plan: RestorePlan, limit: int = 25) -> List[str]:
    out = []
    out += [f"+ @{r['name']}" for r in plan.create_roles]
    out += [f"+ {TYPE_ICON.get(c['type'], '#')}{c['name']}" for c in plan.create_channels]
    out += [f"~ @{r.name}: {'; '.join(d)}" for r, _, d in plan.update_roles if d]
    out += [f"~ {TYPE_ICON.get(CHANNEL_TYPES.get(c.type, 'text'), '#')}{c.name}: {', '.join(d)}" for c, _, d in plan.update_channels]
    out += [f"~ overwrite {label}" for _, _, label in plan.overwrites]
    if len(out) > limit:
        out = out[:limit] + [f"… y {len(out) - limit} mas"]
    return out


def now_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S", time.gmtime())
