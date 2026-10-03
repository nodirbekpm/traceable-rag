"""Answer cache. A cache failure must never fail a question, so errors read as misses."""

import json
import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 24 * 3600


class Cache(Protocol):
    def get(self, key: str) -> list[dict[str, Any]] | None: ...

    def set(self, key: str, events: list[dict[str, Any]]) -> None: ...


class MemoryCache:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def get(self, key: str) -> list[dict[str, Any]] | None:
        raw = self._data.get(key)
        return None if raw is None else json.loads(raw)

    def set(self, key: str, events: list[dict[str, Any]]) -> None:
        self._data[key] = json.dumps(events)


class RedisCache:
    def __init__(self, url: str, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        import redis

        self._redis = redis.Redis.from_url(url, socket_timeout=0.5, socket_connect_timeout=0.5)
        self._ttl = ttl_seconds

    def get(self, key: str) -> list[dict[str, Any]] | None:
        try:
            raw = self._redis.get(f"anchor:answer:{key}")
        except Exception as exc:
            logger.warning("cache read failed: %s", exc)
            return None
        return None if raw is None else json.loads(raw)

    def set(self, key: str, events: list[dict[str, Any]]) -> None:
        try:
            self._redis.set(f"anchor:answer:{key}", json.dumps(events), ex=self._ttl)
        except Exception as exc:
            logger.warning("cache write failed: %s", exc)
