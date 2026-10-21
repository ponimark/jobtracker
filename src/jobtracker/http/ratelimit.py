"""Per-host async rate limiters using aiolimiter."""
import asyncio
from aiolimiter import AsyncLimiter

# Default: 5 requests per second per host
_DEFAULT_RATE = 5.0
_DEFAULT_PERIOD = 1.0

# (loop_id, host) → limiter, so each event loop gets its own instance
_limiters: dict[tuple[int, str], AsyncLimiter] = {}

# Override rates per ATS/host
_RATE_OVERRIDES: dict[str, tuple[float, float]] = {
    "boards-api.greenhouse.io": (10.0, 1.0),
    "api.lever.co": (10.0, 1.0),
    "api.ashbyhq.com": (10.0, 1.0),
    "api.smartrecruiters.com": (5.0, 1.0),
    "apply.workable.com": (5.0, 1.0),
    "remoteok.com": (1.0, 2.0),
    "hn.algolia.com": (5.0, 1.0),
    # Workday hosts are per-company (e.g. netflix.wd1.myworkdayjobs.com)
    # They get the default 5 req/s which is conservative enough
}


def get_limiter(host: str) -> AsyncLimiter:
    loop = asyncio.get_event_loop()
    key = (id(loop), host)
    if key not in _limiters:
        rate, period = _RATE_OVERRIDES.get(host, (_DEFAULT_RATE, _DEFAULT_PERIOD))
        _limiters[key] = AsyncLimiter(rate, period)
    return _limiters[key]
