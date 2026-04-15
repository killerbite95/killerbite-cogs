"""
API Key authentication and rate limiting for APIv2.
"""

import secrets
import time
import logging
from datetime import datetime, timezone
from typing import Optional

from redbot.core import Config

logger = logging.getLogger("red.killerbite95.apiv2.auth")


class RateLimiter:
    """In-memory sliding window rate limiter with per-key limits."""

    def __init__(self, default_max: int = 200, window_seconds: int = 60):
        self.default_max = default_max
        self.window = window_seconds
        # key_name -> list of timestamps
        self._hits: dict[str, list[float]] = {}
        # key_name -> custom max requests (None = use default)
        self._limits: dict[str, int] = {}

    def set_key_limit(self, key_name: str, max_requests: int | None):
        """Set a custom rate limit for a key. None resets to default."""
        if max_requests is None:
            self._limits.pop(key_name, None)
        else:
            self._limits[key_name] = max_requests

    def get_key_limit(self, key_name: str) -> int:
        """Get the effective rate limit for a key."""
        return self._limits.get(key_name, self.default_max)

    def is_allowed(self, key_name: str) -> tuple[bool, int]:
        """Check if a request is allowed. Returns (allowed, remaining)."""
        now = time.monotonic()
        cutoff = now - self.window
        max_req = self.get_key_limit(key_name)

        hits = self._hits.get(key_name, [])
        # Prune old entries
        hits = [t for t in hits if t > cutoff]
        hits.append(now)
        self._hits[key_name] = hits

        remaining = max(0, max_req - len(hits))
        return len(hits) <= max_req, remaining

    def get_retry_after(self, key_name: str) -> float:
        """Seconds until the oldest request in the window expires."""
        hits = self._hits.get(key_name, [])
        if not hits:
            return 0.0
        return max(0.0, hits[0] + self.window - time.monotonic())


class KeyManager:
    """Manages API keys stored in Red's Config."""

    def __init__(self, config: Config):
        self.config = config
        # Cache: token_value -> key_data dict
        self._cache: dict[str, dict] = {}

    async def load_cache(self):
        """Load all keys into memory for fast lookup."""
        keys = await self.config.api_keys()
        self._cache.clear()
        for name, data in keys.items():
            if data.get("active", False):
                self._cache[data["token"]] = {**data, "name": name}

    async def create_key(self, name: str) -> Optional[str]:
        """Create a new API key. Returns the token or None if name exists."""
        keys = await self.config.api_keys()
        if name in keys:
            return None

        token = secrets.token_urlsafe(32)
        keys[name] = {
            "token": token,
            "active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_used": None,
            "rate_limit": None,  # None = use global default
        }
        await self.config.api_keys.set(keys)
        await self.load_cache()
        logger.info(f"API key created: {name}")
        return token

    async def revoke_key(self, name: str) -> bool:
        """Revoke an API key by name. Returns True if found."""
        keys = await self.config.api_keys()
        if name not in keys:
            return False

        keys[name]["active"] = False
        await self.config.api_keys.set(keys)
        await self.load_cache()
        logger.info(f"API key revoked: {name}")
        return True

    async def get_key_info(self, name: str) -> Optional[dict]:
        """Get key metadata (without token) by name."""
        keys = await self.config.api_keys()
        data = keys.get(name)
        if data is None:
            return None
        return {
            "name": name,
            "active": data["active"],
            "created_at": data["created_at"],
            "last_used": data.get("last_used"),
        }

    async def get_key_token(self, name: str) -> Optional[str]:
        """Get the raw token value for a key (for [p]apiv2 key show)."""
        keys = await self.config.api_keys()
        data = keys.get(name)
        if data is None:
            return None
        return data["token"]

    async def set_rate_limit(self, name: str, limit: int | None) -> bool:
        """Set a custom rate limit for a key. None resets to default."""
        keys = await self.config.api_keys()
        if name not in keys:
            return False
        keys[name]["rate_limit"] = limit
        await self.config.api_keys.set(keys)
        return True

    async def list_keys(self) -> list[dict]:
        """List all keys with metadata (no tokens)."""
        keys = await self.config.api_keys()
        result = []
        for name, data in keys.items():
            result.append({
                "name": name,
                "active": data["active"],
                "created_at": data["created_at"],
                "last_used": data.get("last_used"),
                "rate_limit": data.get("rate_limit"),
            })
        return result

    def validate_token(self, token: str) -> Optional[dict]:
        """Validate a token from the cache. Returns key data or None."""
        return self._cache.get(token)

    async def record_usage(self, token: str):
        """Update last_used timestamp for a key."""
        data = self._cache.get(token)
        if not data:
            return
        name = data["name"]
        now = datetime.now(timezone.utc).isoformat()
        keys = await self.config.api_keys()
        if name in keys:
            keys[name]["last_used"] = now
            await self.config.api_keys.set(keys)
            data["last_used"] = now
