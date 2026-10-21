"""ETag / If-Modified-Since caching via Redis for conditional GETs."""
from dataclasses import dataclass
from typing import Any

import redis.asyncio as aioredis

from jobtracker.config import settings

_redis: aioredis.Redis | None = None  # type: ignore[type-arg]


def _get_redis() -> aioredis.Redis:  # type: ignore[type-arg]
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


@dataclass
class ConditionalHeaders:
    etag: str | None = None
    last_modified: str | None = None

    def as_request_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.etag:
            headers["If-None-Match"] = self.etag
        if self.last_modified:
            headers["If-Modified-Since"] = self.last_modified
        return headers


async def get_conditional_headers(url: str) -> ConditionalHeaders:
    """Retrieve cached ETag/Last-Modified for a URL."""
    r = _get_redis()
    key = f"etag:{url}"
    data: dict[str, Any] = await r.hgetall(key)  # type: ignore[misc]
    return ConditionalHeaders(
        etag=data.get("etag"),
        last_modified=data.get("last_modified"),
    )


async def store_conditional_headers(
    url: str,
    etag: str | None,
    last_modified: str | None,
    ttl_s: int = 86400,
) -> None:
    """Store ETag/Last-Modified after a successful response."""
    if not etag and not last_modified:
        return
    r = _get_redis()
    key = f"etag:{url}"
    mapping: dict[str, str] = {}
    if etag:
        mapping["etag"] = etag
    if last_modified:
        mapping["last_modified"] = last_modified
    await r.hset(key, mapping=mapping)  # type: ignore[misc]
    await r.expire(key, ttl_s)
