"""Redis-backed deduplication for ingested jobs."""
import redis.asyncio as aioredis

from jobtracker.config import settings

_redis: aioredis.Redis | None = None  # type: ignore[type-arg]
_SEEN_TTL = 86400 * 14  # 14 days
_GLOBAL_EXT_KEY = "seen:external_ids"


def _get_redis() -> aioredis.Redis:  # type: ignore[type-arg]
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def _seen_key(source_id: int) -> str:
    return f"seen:{source_id}"


async def filter_new_external_ids(source_id: int, external_ids: list[str]) -> list[str]:
    """Return only external_ids not yet seen for this source."""
    if not external_ids:
        return []
    r = _get_redis()
    key = _seen_key(source_id)
    # SMISMEMBER — O(N) bulk check, available since Redis 6.2
    results = await r.smismember(key, *external_ids)  # type: ignore[misc]
    return [eid for eid, seen in zip(external_ids, results) if not seen]


async def mark_seen(source_id: int, external_ids: list[str]) -> None:
    """Add external_ids to the per-source seen-set and the global cross-source set."""
    if not external_ids:
        return
    r = _get_redis()
    key = _seen_key(source_id)
    await r.sadd(key, *external_ids)  # type: ignore[misc]
    await r.expire(key, _SEEN_TTL)
    # Cross-source: same Indeed ID from two JobSpy queries must not re-insert.
    await r.sadd(_GLOBAL_EXT_KEY, *external_ids)  # type: ignore[misc]
    await r.expire(_GLOBAL_EXT_KEY, _SEEN_TTL)


async def filter_globally_new_external_ids(external_ids: list[str]) -> list[str]:
    """Return external_ids never seen by any source (JobSpy cross-query dedupe)."""
    if not external_ids:
        return []
    r = _get_redis()
    results = await r.smismember(_GLOBAL_EXT_KEY, *external_ids)  # type: ignore[misc]
    return [eid for eid, seen in zip(external_ids, results) if not seen]
