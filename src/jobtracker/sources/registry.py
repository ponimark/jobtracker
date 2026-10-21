"""Load sources.yaml and instantiate the correct adapter for each entry."""
from pathlib import Path
from typing import Any

import yaml

from jobtracker.sources.ashby import AshbyAdapter
from jobtracker.sources.base import SourceAdapter
from jobtracker.sources.careers import CareersAdapter
from jobtracker.sources.github_list import GithubListAdapter
from jobtracker.sources.greenhouse import GreenhouseAdapter
from jobtracker.sources.adzuna import AdzunaAdapter
from jobtracker.sources.hnhiring import HNHiringAdapter
from jobtracker.sources.jobspy import JobSpyAdapter
from jobtracker.sources.lever import LeverAdapter
from jobtracker.sources.remoteok import RemoteOKAdapter
from jobtracker.sources.smartrecruiters import SmartRecruitersAdapter
from jobtracker.sources.workable import WorkableAdapter
from jobtracker.sources.workday import WorkdayAdapter
from jobtracker.sources.wwr import WWRAdapter
from jobtracker.sources.ycombinator import YCombinatorAdapter

_ATS_MAP: dict[str, type[SourceAdapter]] = {
    "greenhouse": GreenhouseAdapter,
    "lever": LeverAdapter,
    "ashby": AshbyAdapter,
    "smartrecruiters": SmartRecruitersAdapter,
    "workable": WorkableAdapter,
    "remoteok": RemoteOKAdapter,
    "weworkremotely": WWRAdapter,
    "ycombinator": YCombinatorAdapter,
    "workday": WorkdayAdapter,
    "hnhiring": HNHiringAdapter,
    "adzuna": AdzunaAdapter,
    "jobspy": JobSpyAdapter,
    "careers": CareersAdapter,
    "github_list": GithubListAdapter,
}

_RESERVED_KEYS = {"ats", "slug", "name", "priority", "poll_interval_s"}


def _poll_interval(entry: dict[str, Any], defaults: dict[str, Any]) -> int:
    if "poll_interval_s" in entry:
        return int(entry["poll_interval_s"])
    ats_defaults = defaults.get(entry["ats"], {})
    return int(ats_defaults.get("poll_interval_s", 60))


def _priority_to_interval(priority: str, base: int) -> int:
    mapping = {"high": max(30, base // 2), "normal": base, "low": base * 2}
    return mapping.get(priority, base)


def load_sources(config_path: Path) -> list[tuple[SourceAdapter, int]]:
    """
    Parse sources.yaml and return a list of (adapter, poll_interval_seconds) tuples.
    """
    with config_path.open() as f:
        config = yaml.safe_load(f)

    defaults: dict[str, Any] = config.get("defaults", {})
    sources: list[dict[str, Any]] = config.get("sources", [])
    result: list[tuple[SourceAdapter, int]] = []

    for entry in sources:
        ats = entry["ats"]
        adapter_cls = _ATS_MAP.get(ats)
        if adapter_cls is None:
            continue  # unknown ATS, skip

        base_interval = _poll_interval(entry, defaults)
        priority = entry.get("priority", "normal")
        interval = _priority_to_interval(priority, base_interval)

        extra = {k: v for k, v in entry.items() if k not in _RESERVED_KEYS}
        adapter = adapter_cls(
            slug=entry["slug"],
            company_name=entry.get("name"),
            **extra,
        )
        result.append((adapter, interval))

    return result
