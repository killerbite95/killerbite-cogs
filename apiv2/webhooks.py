"""
Outgoing webhook system for APIv2.
Dispatches Discord events to external URLs with HMAC-SHA256 signing.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Optional

import aiohttp
from redbot.core import Config

logger = logging.getLogger("red.killerbite95.apiv2.webhooks")

SUPPORTED_EVENTS = frozenset({
    "member_join",
    "member_remove",
    "member_ban",
    "member_unban",
    "message",
})


class WebhookManager:
    """Manages outgoing webhooks stored in Red's Config."""

    def __init__(self, config: Config):
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None
        self._cache: dict[str, dict] = {}

    async def initialize(self):
        """Create HTTP session and load webhook cache."""
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10)
        )
        await self._load_cache()

    async def close(self):
        """Close the HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None

    async def _load_cache(self):
        """Load webhooks from config into memory."""
        self._cache = dict(await self.config.webhooks())

    async def create(
        self,
        name: str,
        url: str,
        events: list[str],
        guild_id: int | None = None,
    ) -> Optional[str]:
        """Create a new webhook. Returns the signing secret, or None if name exists."""
        webhooks = await self.config.webhooks()
        if name in webhooks:
            return None

        secret = secrets.token_urlsafe(32)
        webhooks[name] = {
            "url": url,
            "events": events,
            "secret": secret,
            "active": True,
            "guild_id": guild_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.config.webhooks.set(webhooks)
        await self._load_cache()
        logger.info(f"Webhook created: {name} -> {url} (events: {events})")
        return secret

    async def delete(self, name: str) -> bool:
        """Delete a webhook by name."""
        webhooks = await self.config.webhooks()
        if name not in webhooks:
            return False
        del webhooks[name]
        await self.config.webhooks.set(webhooks)
        await self._load_cache()
        logger.info(f"Webhook deleted: {name}")
        return True

    async def list_webhooks(self) -> list[dict]:
        """List all webhooks (without secrets)."""
        webhooks = await self.config.webhooks()
        return [
            {
                "name": name,
                "url": data["url"],
                "events": data["events"],
                "active": data["active"],
                "guild_id": data.get("guild_id"),
                "created_at": data["created_at"],
            }
            for name, data in webhooks.items()
        ]

    def _sign_payload(self, secret: str, body: str) -> str:
        """Create HMAC-SHA256 signature for a payload."""
        return hmac.new(
            secret.encode(),
            body.encode(),
            hashlib.sha256,
        ).hexdigest()

    async def dispatch(self, event: str, payload: dict, guild_id: int | None = None):
        """Fire event to all matching webhooks (non-blocking)."""
        if not self._session:
            return

        for name, data in self._cache.items():
            if not data.get("active") or event not in data.get("events", []):
                continue
            wh_guild = data.get("guild_id")
            if wh_guild is not None and guild_id is not None and int(wh_guild) != guild_id:
                continue
            asyncio.create_task(self._deliver(name, data, event, payload))

    async def _deliver(self, name: str, data: dict, event: str, payload: dict):
        """Deliver a single webhook call."""
        body = json.dumps({
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": payload,
        })

        signature = self._sign_payload(data["secret"], body)

        headers = {
            "Content-Type": "application/json",
            "X-APIv2-Event": event,
            "X-APIv2-Signature": f"sha256={signature}",
            "User-Agent": "Red-APIv2/2.0",
        }

        try:
            async with self._session.post(data["url"], data=body, headers=headers) as resp:
                if resp.status >= 400:
                    logger.warning(f"Webhook {name} delivery failed: {resp.status} for {event}")
                else:
                    logger.debug(f"Webhook {name} delivered: {event} -> {resp.status}")
        except Exception as e:
            logger.warning(f"Webhook {name} error for {event}: {e}")

    async def test(self, name: str) -> int | str | None:
        """Send a test ping. Returns status code, error string, or None if not found."""
        webhooks = await self.config.webhooks()
        data = webhooks.get(name)
        if data is None:
            return None

        body = json.dumps({
            "event": "ping",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {"message": "Test ping from APIv2"},
        })

        signature = self._sign_payload(data["secret"], body)

        headers = {
            "Content-Type": "application/json",
            "X-APIv2-Event": "ping",
            "X-APIv2-Signature": f"sha256={signature}",
            "User-Agent": "Red-APIv2/2.0",
        }

        if not self._session:
            await self.initialize()

        try:
            async with self._session.post(data["url"], data=body, headers=headers) as resp:
                return resp.status
        except Exception as e:
            return str(e)
