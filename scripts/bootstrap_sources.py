"""
Bootstrap sources.yaml by crawling public company lists and probing ATS endpoints.

Pipeline:
  1. Gather company names from:
     - HN "Ask HN: Who is hiring?" threads (last N months via Algolia)
     - GitHub poteto/hiring-without-whiteboards README
  2. For each name, generate slug candidates (lowercase-nospace variants).
  3. Probe each candidate against the supported ATS endpoints.
  4. Write new (ats, slug) pairs to config/sources.yaml.
  5. Cache results so re-runs only probe new companies.

Run:
    python scripts/bootstrap_sources.py
    python scripts/bootstrap_sources.py --months 3 --concurrency 20 --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Iterable

import httpx

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
SOURCES_YAML = CONFIG_DIR / "sources.yaml"
CACHE_PATH = CONFIG_DIR / "bootstrap_cache.json"
UNRESOLVED_LOG = CONFIG_DIR / "unresolved_companies.txt"
DEAD_LOG = CONFIG_DIR / "dead_slugs.txt"

USER_AGENT = "personal-job-tracker/0.1"
HTTP_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

RECHECK_UNRESOLVED_DAYS = 14
RECHECK_DEAD_DAYS = 30

# ─────────────────────────────── ATS probes ────────────────────────────────

@dataclass
class ProbeResult:
    ats: str
    slug: str
    job_count: int


async def _probe_greenhouse(client: httpx.AsyncClient, slug: str) -> ProbeResult | None:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    r = await client.get(url)
    if r.status_code != 200:
        return None
    data = _safe_json(r)
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if jobs is None:
        return None
    return ProbeResult(ats="greenhouse", slug=slug, job_count=len(jobs))


async def _probe_lever(client: httpx.AsyncClient, slug: str) -> ProbeResult | None:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    r = await client.get(url)
    if r.status_code != 200:
        return None
    data = _safe_json(r)
    if not isinstance(data, list):
        return None
    return ProbeResult(ats="lever", slug=slug, job_count=len(data))


async def _probe_ashby(client: httpx.AsyncClient, slug: str) -> ProbeResult | None:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    r = await client.get(url)
    if r.status_code != 200:
        return None
    data = _safe_json(r)
    if not isinstance(data, dict) or "jobs" not in data:
        return None
    return ProbeResult(ats="ashby", slug=slug, job_count=len(data.get("jobs") or []))


async def _probe_smartrecruiters(client: httpx.AsyncClient, slug: str) -> ProbeResult | None:
    url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
    r = await client.get(url)
    if r.status_code != 200:
        return None
    data = _safe_json(r)
    if not isinstance(data, dict) or "content" not in data:
        return None
    return ProbeResult(ats="smartrecruiters", slug=slug, job_count=len(data.get("content") or []))


async def _probe_workable(client: httpx.AsyncClient, slug: str) -> ProbeResult | None:
    url = f"https://apply.workable.com/api/v1/widget/accounts/{slug}"
    r = await client.get(url)
    if r.status_code != 200:
        return None
    data = _safe_json(r)
    if not isinstance(data, dict):
        return None
    jobs = data.get("jobs") or data.get("openings") or []
    return ProbeResult(ats="workable", slug=slug, job_count=len(jobs) if isinstance(jobs, list) else 0)


async def _probe_recruitee(client: httpx.AsyncClient, slug: str) -> ProbeResult | None:
    url = f"https://{slug}.recruitee.com/api/offers/"
    try:
        r = await client.get(url)
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    data = _safe_json(r)
    if not isinstance(data, dict) or "offers" not in data:
        return None
    return ProbeResult(ats="recruitee", slug=slug, job_count=len(data.get("offers") or []))


PROBES = (
    _probe_greenhouse,
    _probe_lever,
    _probe_ashby,
    _probe_smartrecruiters,
    _probe_workable,
    _probe_recruitee,
)


def _safe_json(response: httpx.Response) -> object:
    try:
        return response.json()
    except Exception:
        return None


# ──────────────────────────── Slug generation ──────────────────────────────

_COMPANY_SUFFIX_RE = re.compile(
    r",?\s*(inc\.?|llc\.?|ltd\.?|corp\.?|co\.|gmbh|ag|plc|sa|srl|s\.a\.|limited)$",
    re.IGNORECASE,
)
_NON_WORD_RE = re.compile(r"[^a-z0-9]+")


def _name_to_candidates(name: str) -> list[str]:
    name = name.strip()
    if not name:
        return []
    base = _COMPANY_SUFFIX_RE.sub("", name).strip()
    base = base.lower()
    compact = _NON_WORD_RE.sub("", base)
    hyphen = _NON_WORD_RE.sub("-", base).strip("-")
    candidates = []
    seen: set[str] = set()
    for c in (compact, hyphen, base):
        if c and c not in seen and 2 <= len(c) <= 40:
            candidates.append(c)
            seen.add(c)
    return candidates


# ───────────────────────────── Seed sources ────────────────────────────────

_HN_ALGOLIA = "https://hn.algolia.com/api/v1"


async def seed_from_hn_hiring(client: httpx.AsyncClient, months: int) -> set[str]:
    """Pull top-level comments from the last `months` 'Ask HN: Who is hiring?' threads."""
    r = await client.get(
        f"{_HN_ALGOLIA}/search",
        params={"query": "Ask HN: Who is hiring", "tags": "story", "hitsPerPage": str(months * 2)},
    )
    r.raise_for_status()
    stories = [
        h for h in (r.json().get("hits") or [])
        if "who is hiring" in (h.get("title") or "").lower()
    ][:months]

    names: set[str] = set()
    for story in stories:
        story_id = story["objectID"]
        page = 0
        while True:
            r2 = await client.get(
                f"{_HN_ALGOLIA}/search",
                params={
                    "tags": f"comment,story_{story_id}",
                    "hitsPerPage": "1000",
                    "page": str(page),
                },
            )
            if r2.status_code != 200:
                break
            payload = r2.json()
            hits = payload.get("hits") or []
            for hit in hits:
                name = _extract_company_from_hn(hit.get("comment_text") or "")
                if name:
                    names.add(name)
            if page + 1 >= (payload.get("nbPages") or 1):
                break
            page += 1
    return names


def _extract_company_from_hn(comment_html: str) -> str | None:
    # Strip HTML tags, take first non-empty line, first pipe-separated token.
    text = re.sub(r"<[^>]+>", " ", comment_html)
    text = re.sub(r"&\w+;", " ", text)
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        first = re.split(r"\s*\|\s*", line)[0].strip()
        first = re.sub(r"\([^)]*\)", "", first).strip()  # drop "(YC W22)" etc.
        if 2 <= len(first) <= 60 and not first.lower().startswith(("http", "www")):
            return first
        return None
    return None


_POTETO_RAW = "https://raw.githubusercontent.com/poteto/hiring-without-whiteboards/master/README.md"
# Company rows look like: "- [Company Name](https://example.com) | Location | Description"
_POTETO_ROW_RE = re.compile(r"^-\s*\[([^\]]+)\]\([^)]+\)\s*\|")


async def seed_from_poteto(client: httpx.AsyncClient) -> set[str]:
    r = await client.get(_POTETO_RAW)
    r.raise_for_status()
    names: set[str] = set()
    for line in r.text.splitlines():
        m = _POTETO_ROW_RE.match(line)
        if not m:
            continue
        name = m.group(1).strip()
        if 2 <= len(name) <= 60:
            names.add(name)
    return names


# ─────────────────────────────── Cache I/O ─────────────────────────────────

@dataclass
class Cache:
    resolved: dict[str, dict] = field(default_factory=dict)
    unresolved: dict[str, dict] = field(default_factory=dict)
    dead: dict[str, dict] = field(default_factory=dict)
    last_run: str | None = None

    @classmethod
    def load(cls) -> "Cache":
        if not CACHE_PATH.exists():
            return cls()
        try:
            raw = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return cls()
        return cls(
            resolved=raw.get("resolved", {}),
            unresolved=raw.get("unresolved", {}),
            dead=raw.get("dead", {}),
            last_run=raw.get("last_run"),
        )

    def save(self) -> None:
        CACHE_PATH.write_text(
            json.dumps(
                {
                    "last_run": self.last_run,
                    "resolved": self.resolved,
                    "unresolved": self.unresolved,
                    "dead": self.dead,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )


def _is_fresh(entry: dict, max_age_days: int) -> bool:
    ts = entry.get("last_checked")
    if not ts:
        return False
    try:
        checked = datetime.fromisoformat(ts)
    except ValueError:
        return False
    return (datetime.now(UTC) - checked) < timedelta(days=max_age_days)


# ──────────────────────── sources.yaml manipulation ────────────────────────

_YAML_SOURCE_RE = re.compile(
    r"^\s*-\s*ats:\s*(\S+)\s*\n\s*slug:\s*(\S+)", re.MULTILINE
)


def load_existing_pairs() -> set[tuple[str, str]]:
    if not SOURCES_YAML.exists():
        return set()
    text = SOURCES_YAML.read_text(encoding="utf-8")
    return {(m.group(1), m.group(2)) for m in _YAML_SOURCE_RE.finditer(text)}


def append_new_sources(entries: list[ProbeResult], name_by_slug: dict[str, str]) -> None:
    if not entries:
        return
    lines = ["", "  # ── Added by bootstrap_sources.py ─────────────────────────────────────────"]
    for e in entries:
        display = name_by_slug.get(e.slug, e.slug)
        lines.append(f"  - ats: {e.ats}")
        lines.append(f"    slug: {e.slug}")
        lines.append(f"    name: {display}")
        lines.append("")
    with SOURCES_YAML.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


# ───────────────────────────── Orchestration ───────────────────────────────


async def probe_name(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    name: str,
    known: set[tuple[str, str]],
) -> tuple[str, ProbeResult | None, str]:
    """Return (name, probe_result_or_none, reason). reason in {live, empty_only, none}."""
    candidates = _name_to_candidates(name)
    best_empty: ProbeResult | None = None
    async with sem:
        for slug in candidates:
            for probe in PROBES:
                try:
                    result = await probe(client, slug)
                except httpx.HTTPError:
                    continue
                if result is None:
                    continue
                if (result.ats, result.slug) in known:
                    # Already in sources.yaml — treat as resolved, don't re-add.
                    return name, None, "already_known"
                if result.job_count > 0:
                    return name, result, "live"
                if best_empty is None:
                    best_empty = result
    if best_empty is not None:
        return name, best_empty, "empty_only"
    return name, None, "none"


async def main_async(args: argparse.Namespace) -> None:
    cache = Cache.load()
    existing = load_existing_pairs()
    print(f"Loaded {len(existing)} existing sources.yaml entries.")

    async with httpx.AsyncClient(
        timeout=HTTP_TIMEOUT,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/plain,*/*"},
        follow_redirects=True,
        http2=True,
    ) as client:
        print(f"\nGathering seeds (HN: last {args.months} months, poteto)...")
        hn_task = asyncio.create_task(seed_from_hn_hiring(client, args.months))
        pt_task = asyncio.create_task(seed_from_poteto(client))
        hn_names = await hn_task
        pt_names = await pt_task
        print(f"  HN 'Who is Hiring' : {len(hn_names):>5} names")
        print(f"  poteto/hwow        : {len(pt_names):>5} names")

        seeds = hn_names | pt_names
        print(f"  Total unique       : {len(seeds):>5}")

        # Filter via cache to avoid re-probing recent work.
        to_probe: list[str] = []
        fast_path_hits = 0
        for name in sorted(seeds):
            if name in cache.resolved:
                fast_path_hits += 1
                continue
            if name in cache.dead and _is_fresh(cache.dead[name], RECHECK_DEAD_DAYS):
                continue
            if name in cache.unresolved and _is_fresh(cache.unresolved[name], RECHECK_UNRESOLVED_DAYS):
                continue
            to_probe.append(name)
        print(f"  Fast-path (cached) : {fast_path_hits:>5}")
        print(f"  To probe           : {len(to_probe):>5}")

        if args.limit:
            to_probe = to_probe[: args.limit]
            print(f"  Limited to         : {len(to_probe):>5}")

        sem = asyncio.Semaphore(args.concurrency)
        new_live: list[ProbeResult] = []
        new_empty: list[ProbeResult] = []
        name_by_slug: dict[str, str] = {}
        unresolved_names: list[str] = []

        total = len(to_probe)
        done = 0
        tasks = [
            asyncio.create_task(probe_name(client, sem, n, existing))
            for n in to_probe
        ]
        for fut in asyncio.as_completed(tasks):
            name, result, reason = await fut
            done += 1
            now_iso = datetime.now(UTC).isoformat()
            if reason == "live" and result is not None:
                new_live.append(result)
                name_by_slug.setdefault(result.slug, name)
                cache.resolved[name] = {
                    "ats": result.ats,
                    "slug": result.slug,
                    "status": "live",
                    "job_count": result.job_count,
                    "last_checked": now_iso,
                }
                existing.add((result.ats, result.slug))
                if done % 25 == 0 or done == total:
                    print(f"  [{done}/{total}] {name[:30]:<30} → {result.ats}/{result.slug} ({result.job_count} jobs)")
            elif reason == "empty_only" and result is not None:
                new_empty.append(result)
                name_by_slug.setdefault(result.slug, name)
                cache.resolved[name] = {
                    "ats": result.ats,
                    "slug": result.slug,
                    "status": "empty",
                    "job_count": 0,
                    "last_checked": now_iso,
                }
                existing.add((result.ats, result.slug))
            elif reason == "already_known":
                # Resolved but already in yaml — record it so we skip next time.
                cache.resolved[name] = {"status": "already_in_yaml", "last_checked": now_iso}
            else:
                unresolved_names.append(name)
                cache.unresolved[name] = {"reason": "no_ats_detected", "last_checked": now_iso}

        print()
        print(f"Resolved (jobs > 0) : {len(new_live)}")
        print(f"Resolved (empty)    : {len(new_empty)}")
        print(f"Unresolved          : {len(unresolved_names)}")

    # Write outputs (unless dry run).
    cache.last_run = datetime.now(UTC).isoformat()
    if args.dry_run:
        print("\n(dry-run: nothing written)")
        return

    new_entries = new_live + (new_empty if args.include_empty else [])
    append_new_sources(new_entries, name_by_slug)
    cache.save()

    if unresolved_names:
        UNRESOLVED_LOG.write_text("\n".join(sorted(set(unresolved_names))) + "\n", encoding="utf-8")

    print(f"\nAppended {len(new_entries)} new sources to {SOURCES_YAML.name}.")
    print(f"Cache written to {CACHE_PATH.name}.")
    if unresolved_names:
        print(f"Unresolved names logged to {UNRESOLVED_LOG.name}.")


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Bootstrap sources.yaml from public company lists.")
    p.add_argument("--months", type=int, default=6, help="How many HN 'Who is hiring' threads to crawl.")
    p.add_argument("--concurrency", type=int, default=20, help="Concurrent probes.")
    p.add_argument("--limit", type=int, default=0, help="Probe at most N names (0 = no cap).")
    p.add_argument("--include-empty", action="store_true", help="Include companies with live ATS but 0 jobs today.")
    p.add_argument("--dry-run", action="store_true", help="Discover but do not write.")
    return p.parse_args(list(argv) if argv is not None else None)


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)


if __name__ == "__main__":
    main()
