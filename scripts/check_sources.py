"""
Check all sources in sources.yaml and report which are healthy, broken, or empty.
Run from the project root:
    python scripts/check_sources.py
"""
import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import urlencode

import httpx
import yaml

# Make jobtracker importable so we can reuse settings for Adzuna creds.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
try:
    from jobtracker.config import settings  # type: ignore
except Exception:
    settings = None  # type: ignore

CONFIG_PATH = Path(__file__).parent.parent / "config" / "sources.yaml"


# ANSI colors
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

ATS_URLS = {
    "greenhouse":     lambda slug, _: ("GET", f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", None),
    "lever":          lambda slug, _: ("GET", f"https://api.lever.co/v0/postings/{slug}?mode=json", None),
    "smartrecruiters":lambda slug, _: ("GET", f"https://api.smartrecruiters.com/v1/companies/{slug}/postings", None),
    "workable":       lambda slug, _: ("GET", f"https://apply.workable.com/api/v3/accounts/{slug}/jobs", None),
    "remoteok":       lambda slug, _: ("GET", "https://remoteok.com/api", None),
    "weworkremotely": lambda slug, _: ("GET", "https://weworkremotely.com/remote-jobs.rss", None),
    "ycombinator":    lambda slug, _: ("GET", "https://www.workatastartup.com/jobs.json", None),
}


def count_jobs(ats: str, slug: str, data) -> int:
    if ats == "greenhouse":
        return len(data.get("jobs", []))
    if ats == "lever":
        return len(data) if isinstance(data, list) else 0
    if ats == "ashby":
        return len(data.get("jobs", []))
    if ats == "smartrecruiters":
        return data.get("totalFound", 0)
    if ats == "workable":
        return len(data.get("results", []))
    if ats == "workday":
        return data.get("total", 0)
    if ats in ("remoteok", "weworkremotely", "ycombinator", "hnhiring"):
        return -1  # feed-based, skip count
    return 0


async def check_source(client: httpx.AsyncClient, ats: str, slug: str, name: str, entry: dict) -> dict:
    try:
        # ── Ashby (GraphQL POST) ──────────────────────────────────────────────
        if ats == "ashby":
            resp = await client.post(
                "https://jobs.ashbyhq.com/api/non-user-graphql",
                json={
                    "operationName": "ApiJobBoardWithTeams",
                    "variables": {"organizationHostedJobsPageName": slug},
                    "query": "query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) { jobBoard: jobBoardWithTeams(organizationHostedJobsPageName: $organizationHostedJobsPageName) { jobs { id title } } }",
                },
                timeout=30,
            )
            if resp.status_code != 200:
                return {"name": name, "ats": ats, "slug": slug, "status": "ERROR", "jobs": 0, "error": f"HTTP {resp.status_code}"}
            jobs = resp.json().get("data", {}).get("jobBoard", {}).get("jobs", [])
            count = len(jobs)

        # ── Workday (POST search) ─────────────────────────────────────────────
        elif ats == "workday":
            host = entry.get("workday_host", "")
            path = entry.get("workday_path", "")
            if not host or not path:
                return {"name": name, "ats": ats, "slug": slug, "status": "SKIP", "jobs": 0, "error": "missing workday_host/workday_path"}
            url = f"https://{host}/wday/cxs/{slug}/{path}/jobs"
            resp = await client.post(
                url,
                json={"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""},
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            if resp.status_code != 200:
                return {"name": name, "ats": ats, "slug": slug, "status": "ERROR", "jobs": 0, "error": f"HTTP {resp.status_code} — wrong host/path?"}
            try:
                data = resp.json()
            except Exception:
                return {"name": name, "ats": ats, "slug": slug, "status": "ERROR", "jobs": 0, "error": "non-JSON response — wrong URL?"}
            if "jobPostings" not in data and "total" not in data:
                return {"name": name, "ats": ats, "slug": slug, "status": "ERROR", "jobs": 0, "error": "unexpected response shape — wrong path?"}
            count = data.get("total", 0)

        # ── HN Hiring (Algolia — just check reachability) ─────────────────────
        elif ats == "hnhiring":
            resp = await client.get(
                "https://hn.algolia.com/api/v1/search",
                params={"query": "Ask HN: Who is hiring", "tags": "story", "hitsPerPage": "1"},
                timeout=30,
            )
            if resp.status_code != 200:
                return {"name": name, "ats": ats, "slug": slug, "status": "ERROR", "jobs": 0, "error": f"HTTP {resp.status_code}"}
            hits = resp.json().get("hits", [])
            count = -1 if hits else 0  # -1 = feed OK, 0 = no thread found

        # ── Adzuna (API with app_id/app_key) ──────────────────────────────────
        elif ats == "adzuna":
            app_id = getattr(settings, "adzuna_app_id", "") or os.environ.get("ADZUNA_APP_ID", "")
            app_key = getattr(settings, "adzuna_app_key", "") or os.environ.get("ADZUNA_APP_KEY", "")
            if not app_id or not app_key:
                return {"name": name, "ats": ats, "slug": slug, "status": "ERROR", "jobs": 0, "error": "missing ADZUNA_APP_ID/APP_KEY"}
            country = (entry.get("country") or "us").strip().lower()
            query = (entry.get("query") or slug.replace("-", " ")).strip()
            params = {
                "app_id": app_id,
                "app_key": app_key,
                "what": query,
                "results_per_page": "1",
                "sort_by": "date",
            }
            if entry.get("location"):
                params["where"] = str(entry["location"]).strip()
            if entry.get("max_days_old") is not None:
                params["max_days_old"] = str(entry["max_days_old"])
            url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
            resp = await client.get(url, params=params, timeout=20)
            if resp.status_code != 200:
                return {"name": name, "ats": ats, "slug": slug, "status": "ERROR", "jobs": 0, "error": f"HTTP {resp.status_code}"}
            data = resp.json()
            count = int(data.get("count", 0))

        # ── All other GET-based ATS ───────────────────────────────────────────
        else:
            if ats not in ATS_URLS:
                return {"name": name, "ats": ats, "slug": slug, "status": "SKIP", "jobs": 0, "error": "unknown ATS"}
            _, url, _ = ATS_URLS[ats](slug, entry)
            resp = await client.get(url, timeout=15)
            if resp.status_code == 404:
                return {"name": name, "ats": ats, "slug": slug, "status": "ERROR", "jobs": 0, "error": "404 — wrong slug?"}
            if resp.status_code != 200:
                return {"name": name, "ats": ats, "slug": slug, "status": "ERROR", "jobs": 0, "error": f"HTTP {resp.status_code}"}
            body = resp.text.strip()
            if not body:
                return {"name": name, "ats": ats, "slug": slug, "status": "EMPTY", "jobs": 0, "error": "empty response"}
            try:
                data = resp.json()
            except Exception:
                # RSS feeds (WWR, RemoteOK) return non-JSON — that's fine
                return {"name": name, "ats": ats, "slug": slug, "status": "OK", "jobs": -1, "error": None}
            count = count_jobs(ats, slug, data)

        if count == -1:
            return {"name": name, "ats": ats, "slug": slug, "status": "OK", "jobs": -1, "error": None}
        if count == 0:
            return {"name": name, "ats": ats, "slug": slug, "status": "EMPTY", "jobs": 0, "error": "0 jobs returned"}
        return {"name": name, "ats": ats, "slug": slug, "status": "OK", "jobs": count, "error": None}

    except httpx.TimeoutException:
        return {"name": name, "ats": ats, "slug": slug, "status": "ERROR", "jobs": 0, "error": "timeout"}
    except Exception as e:
        return {"name": name, "ats": ats, "slug": slug, "status": "ERROR", "jobs": 0, "error": str(e)[:80]}


async def main():
    config = yaml.safe_load(CONFIG_PATH.read_text())
    sources = config.get("sources", [])

    print(f"\n{BOLD}Checking {len(sources)} sources...{RESET}\n")

    async with httpx.AsyncClient(follow_redirects=True) as client:
        tasks = [
            check_source(client, s["ats"], s["slug"], s.get("name", s["slug"]), s)
            for s in sources
        ]
        results = await asyncio.gather(*tasks)

    ok     = [r for r in results if r["status"] == "OK"]
    empty  = [r for r in results if r["status"] == "EMPTY"]
    errors = [r for r in results if r["status"] == "ERROR"]
    skips  = [r for r in results if r["status"] == "SKIP"]

    # Print errors first — most important
    if errors:
        print(f"{RED}{BOLD}BROKEN ({len(errors)}){RESET}")
        for r in errors:
            print(f"  {RED}✗{RESET}  {r['name']:<22} [{r['ats']}/{r['slug']}]  →  {r['error']}")
        print()

    if empty:
        print(f"{YELLOW}{BOLD}EMPTY — 0 jobs ({len(empty)}){RESET}")
        for r in empty:
            print(f"  {YELLOW}?{RESET}  {r['name']:<22} [{r['ats']}/{r['slug']}]")
        print()

    if skips:
        print(f"{YELLOW}{BOLD}SKIPPED ({len(skips)}){RESET}")
        for r in skips:
            print(f"  {YELLOW}-{RESET}  {r['name']:<22} [{r['ats']}/{r['slug']}]  →  {r['error']}")
        print()

    if ok:
        print(f"{GREEN}{BOLD}OK ({len(ok)}){RESET}")
        for r in ok:
            jobs_label = f"{r['jobs']} jobs" if r["jobs"] != -1 else "feed"
            print(f"  {GREEN}✓{RESET}  {r['name']:<22} [{r['ats']}/{r['slug']}]  →  {jobs_label}")
        print()

    print(f"{BOLD}Summary:{RESET} {GREEN}{len(ok)} ok{RESET}  {YELLOW}{len(empty)} empty{RESET}  {RED}{len(errors)} broken{RESET}  {len(skips)} skipped\n")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
