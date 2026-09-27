from __future__ import annotations

import datetime
import re
from typing import Optional

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore
    ZoneInfoNotFoundError = Exception  # type: ignore

WEEKDAYS = {
    "lunes": 0, "monday": 0, "mon": 0, "lun": 0,
    "martes": 1, "tuesday": 1, "tue": 1, "mar": 1,
    "miercoles": 2, "miércoles": 2, "wednesday": 2, "wed": 2, "mie": 2,
    "jueves": 3, "thursday": 3, "thu": 3, "jue": 3,
    "viernes": 4, "friday": 4, "fri": 4, "vie": 4,
    "sabado": 5, "sábado": 5, "saturday": 5, "sat": 5, "sab": 5,
    "domingo": 6, "sunday": 6, "sun": 6, "dom": 6,
}
WEEKDAY_NAMES = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]

TIME_RE = re.compile(r"^(\d{1,2})[:.h](\d{2})$")
REL_RE = re.compile(r"^(?:\+|en\s+|in\s+)(\d+)\s*(m|min|h|d)$", re.I)


def get_tz(name: str) -> datetime.tzinfo:
    if ZoneInfo is not None:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return datetime.timezone.utc


def valid_tz(name: str) -> bool:
    if ZoneInfo is None:
        return name.upper() == "UTC"
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


def parse_time(text: str) -> Optional[datetime.time]:
    m = TIME_RE.match(text.strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return None
    return datetime.time(h, mi)


def parse_datetime(text: str, tz_name: str, *, now: Optional[datetime.datetime] = None) -> Optional[int]:
    """Convierte texto a timestamp. Acepta:

    ``02/10/2026 22:00`` · ``02/10 22:00`` · ``2026-10-02 22:00`` · ``22:00`` ·
    ``hoy 22:00`` · ``mañana 22:00`` · ``viernes 22:00`` · ``+2h`` / ``en 30m``.
    """
    tz = get_tz(tz_name)
    now = now or datetime.datetime.now(tz)
    text = " ".join(text.strip().lower().split())
    if not text:
        return None

    m = REL_RE.match(text)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = {"m": datetime.timedelta(minutes=n), "min": datetime.timedelta(minutes=n),
                 "h": datetime.timedelta(hours=n), "d": datetime.timedelta(days=n)}[unit]
        return int((now + delta).timestamp())

    parts = text.split(" ")
    time_part = parse_time(parts[-1])
    if time_part is None:
        return None
    date_text = " ".join(parts[:-1])
    date: Optional[datetime.date] = None
    if date_text in ("", "hoy", "today"):
        date = now.date()
        if not date_text and datetime.datetime.combine(date, time_part, tz) <= now:
            date = date + datetime.timedelta(days=1)
    elif date_text in ("mañana", "manana", "tomorrow"):
        date = now.date() + datetime.timedelta(days=1)
    elif date_text in WEEKDAYS:
        target = WEEKDAYS[date_text]
        days = (target - now.weekday()) % 7
        date = now.date() + datetime.timedelta(days=days)
        if days == 0 and datetime.datetime.combine(date, time_part, tz) <= now:
            date += datetime.timedelta(days=7)
    else:
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
            try:
                date = datetime.datetime.strptime(date_text, fmt).date()
                break
            except ValueError:
                continue
        if date is None:
            for fmt in ("%d/%m", "%d-%m"):
                try:
                    d = datetime.datetime.strptime(date_text, fmt)
                    date = datetime.date(now.year, d.month, d.day)
                    if datetime.datetime.combine(date, time_part, tz) < now - datetime.timedelta(days=1):
                        date = datetime.date(now.year + 1, d.month, d.day)
                    break
                except ValueError:
                    continue
    if date is None:
        return None
    return int(datetime.datetime.combine(date, time_part, tz).timestamp())


def next_occurrence(start: int, freq: str, tz_name: str, weekday: Optional[int] = None, at: Optional[str] = None) -> int:
    """Siguiente ocurrencia de un evento recurrente, respetando la hora local."""
    tz = get_tz(tz_name)
    local = datetime.datetime.fromtimestamp(start, tz)
    t = parse_time(at) if at else None
    t = t or local.time().replace(second=0, microsecond=0)
    if freq == "daily":
        date = local.date() + datetime.timedelta(days=1)
    else:
        target = weekday if weekday is not None else local.weekday()
        days = (target - local.weekday()) % 7 or 7
        date = local.date() + datetime.timedelta(days=days)
    return int(datetime.datetime.combine(date, t, tz).timestamp())


def format_local(ts: int, tz_name: str) -> str:
    return datetime.datetime.fromtimestamp(ts, get_tz(tz_name)).strftime("%d/%m/%Y %H:%M")
