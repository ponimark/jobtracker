from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

PACIFIC_TZ = ZoneInfo("America/Los_Angeles")


def to_pacific(value: datetime) -> datetime:
    """Convert a datetime to America/Los_Angeles for display."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(PACIFIC_TZ)


def format_pacific(value: datetime, *, with_seconds: bool = False) -> str:
    """Format a datetime as Pacific time for the UI and CLI."""
    local = to_pacific(value)
    fmt = "%Y-%m-%d %H:%M:%S %Z" if with_seconds else "%Y-%m-%d %H:%M %Z"
    return local.strftime(fmt)


def sort_pacific(value: datetime) -> str:
    """Sort-friendly Pacific timestamp string."""
    return to_pacific(value).strftime("%Y-%m-%dT%H:%M:%S")
