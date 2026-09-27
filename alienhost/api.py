"""
Cliente minimo de la API de Pelican (compatible con la de Pterodactyl).

- Client API (``/api/client``): claves ``pacc_`` que cada usuario crea en
  su area cliente (Perfil → Claves API).
- Application API (``/api/application``): clave ``papp_`` opcional del
  owner del bot para los comandos de administracion.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlparse

import aiohttp

log = logging.getLogger("red.killerbite95.alienhost.api")

USER_AGENT = "LaTrini-AlienHost/1.0 (+https://github.com/killerbite95/killerbite-cogs)"


class PelicanError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message

    @property
    def friendly(self) -> str:
        return {
            401: "La clave API no es valida o ha sido revocada. Vuelve a vincular con `alienhost link`.",
            403: "Tu clave API no tiene permiso para esto (o la IP del bot no esta permitida en la clave).",
            404: "No encontrado en el panel.",
            409: "El servidor esta ocupado o en un estado que no permite la accion.",
            429: "Demasiadas peticiones al panel. Espera un momento.",
        }.get(self.status, self.message or "Error del panel.")


def normalize_panel(url: str) -> Optional[str]:
    """Devuelve ``https://host[:port]`` o ``None`` si la URL no es valida."""
    url = (url or "").strip()
    if not url:
        return None
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http") or not parsed.hostname:
        return None
    return f"{parsed.scheme}://{parsed.netloc}".lower()


def q(value: Any) -> str:
    return quote(str(value), safe="")


class PelicanClient:
    def __init__(self, session: aiohttp.ClientSession, panel: str, key: str):
        self.session = session
        self.panel = panel.rstrip("/")
        self.key = key

    async def request(self, method: str, path: str, *, json: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        }
        try:
            async with self.session.request(method, f"{self.panel}{path}", headers=headers, json=json, params=params, allow_redirects=False) as resp:
                if resp.status == 204:
                    return {}
                try:
                    data = await resp.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError):
                    data = None
                if resp.status >= 400 or (300 <= resp.status < 400):
                    detail = ""
                    if isinstance(data, dict) and data.get("errors"):
                        detail = data["errors"][0].get("detail", "")
                    raise PelicanError(resp.status, detail or f"HTTP {resp.status}")
                return data if isinstance(data, dict) else {}
        except aiohttp.ClientError as exc:
            log.debug("Error de red con %s: %s", self.panel, exc)
            raise PelicanError(503, "No se pudo contactar con el panel.") from exc
        except asyncio.TimeoutError as exc:
            raise PelicanError(504, "El panel no respondio a tiempo.") from exc

    # ---- Client API ----

    async def account(self) -> Dict[str, Any]:
        return (await self.request("GET", "/api/client/account")).get("attributes", {})

    async def servers(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        page = 1
        while page <= 10:
            data = await self.request("GET", "/api/client", params={"page": page, "per_page": 50})
            out += [s.get("attributes", {}) for s in data.get("data", [])]
            pag = data.get("meta", {}).get("pagination", {})
            if pag.get("current_page", 1) >= pag.get("total_pages", 1):
                break
            page += 1
        return out

    async def server(self, identifier: str) -> Dict[str, Any]:
        """``identifier`` debe ser el UUID del servidor (segun el spec de la Client API)."""
        data = await self.request("GET", f"/api/client/servers/{q(identifier)}")
        attrs = data.get("attributes", {})
        attrs["_meta"] = data.get("meta", {})
        return attrs

    async def resources(self, identifier: str) -> Dict[str, Any]:
        return (await self.request("GET", f"/api/client/servers/{q(identifier)}/resources")).get("attributes", {})

    async def power(self, identifier: str, signal: str) -> None:
        await self.request("POST", f"/api/client/servers/{q(identifier)}/power", json={"signal": signal})

    async def backups(self, identifier: str) -> Dict[str, Any]:
        data = await self.request("GET", f"/api/client/servers/{q(identifier)}/backups")
        return {
            "backups": [b.get("attributes", {}) for b in data.get("data", [])],
            "meta": data.get("meta", {}),
        }

    async def create_backup(self, identifier: str) -> Dict[str, Any]:
        return (await self.request("POST", f"/api/client/servers/{q(identifier)}/backups", json={})).get("attributes", {})

    # ---- Application API (admin) ----

    async def app_list(self, resource: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        data = await self.request("GET", f"/api/application/{resource}", params={"per_page": 100, **(params or {})})
        return [d.get("attributes", {}) for d in data.get("data", [])]

    async def app_get(self, resource: str, ident: Any, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return (await self.request("GET", f"/api/application/{resource}/{q(ident)}", params=params)).get("attributes", {})
