"""Adapter for community-maintained GitHub new-grad job lists (SimplifyJobs etc).

Reads a repo README and parses its job tables (HTML <tr> tables or markdown pipe
tables). One yaml entry per repo. Required yaml fields:
  repo: SimplifyJobs/New-Grad-Positions
  branch: dev            (optional, default main)
  path: README.md        (optional)
Company is taken per row, so the yaml `name` is only a label.
"""
import hashlib
import html as htmllib
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from jobtracker.http.client import get_client
from jobtracker.http.ratelimit import get_limiter
from jobtracker.normalize.location import is_remote, normalise_location
from jobtracker.normalize.seniority import infer_seniority
from jobtracker.sources.base import FetchResult, NormalizedJob, SourceAdapter

_TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
_HREF = re.compile(r'href="([^"]+)"', re.I)
_MD_URL = re.compile(r"\]\((https?://[^)\s]+)\)")
_TAGS = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    text = re.sub(r"<br\s*/?>|</br>", "; ", text, flags=re.I)
    text = _TAGS.sub("", text)
    text = htmllib.unescape(text)
    text = text.replace("**", "").replace("↳", "").replace("🔥", "").replace("🛂", "")
    text = text.replace("🇺🇸", "").replace("🔒", "").replace("🎓", "")
    return re.sub(r"\s+", " ", text).strip(" ;|")


def _split_md_row(line: str) -> list[str]:
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return cells


def _norm_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


class GithubListAdapter(SourceAdapter):
    ats = "github_list"

    def __init__(self, slug: str, company_name: str | None = None, **kwargs: Any) -> None:
        super().__init__(slug, company_name, **kwargs)
        self._repo: str = kwargs.get("repo", "")
        self._branch: str = kwargs.get("branch", "main")
        self._path: str = kwargs.get("path", "README.md")

    @property
    def source_url(self) -> str:
        return f"https://raw.githubusercontent.com/{self._repo}/{self._branch}/{self._path}"

    async def fetch(self, last_etag=None, last_modified=None) -> FetchResult:
        if not self._repo:
            return FetchResult(jobs=[], status_code=0)
        host = "raw.githubusercontent.com"
        client = get_client(host)
        limiter = get_limiter(host)
        headers = {"If-None-Match": last_etag} if last_etag else {}
        async with limiter:
            r = await client.get(self.source_url, headers=headers)
        if r.status_code == 304:
            return FetchResult(jobs=[], status_code=304, not_modified=True, etag=last_etag)
        if r.status_code >= 400:
            r.raise_for_status()
        jobs = self._parse(r.text)
        return FetchResult(jobs=jobs, status_code=r.status_code, etag=r.headers.get("etag"))

    def _rows(self, text: str):
        """Yield (cells_text, apply_url) for every table row."""
        for m in _TR.finditer(text):
            tds = _TD.findall(m.group(1))
            if len(tds) < 3:
                continue
            url = None
            for td in tds[2:]:
                for href in _HREF.findall(td):
                    if "simplify.jobs/c/" in href or href.startswith("#"):
                        continue
                    url = href
                    break
                if url:
                    break
            yield [_clean(td) for td in tds], url
        for line in text.splitlines():
            if not line.startswith("|") or "---" in line or line.count("|") < 4:
                continue
            cells = _split_md_row(line)
            if len(cells) < 4:
                continue
            url = None
            for c in cells[2:]:
                mu = _MD_URL.search(c) or _HREF.search(c)
                if mu:
                    url = mu.group(1)
                    break
            yield [_clean(c) for c in cells], url

    def _parse(self, text: str) -> list[NormalizedJob]:
        jobs: dict[str, NormalizedJob] = {}
        last_company = ""
        for cells, url in self._rows(text):
            company, role = cells[0], cells[1]
            if company.lower() in ("company", "name", ""):
                company = last_company if cells[0] == "" else company
            if company.lower() == "company" or role.lower() == "role":
                continue
            if not company:
                company = last_company
            if not company or not role or not url:
                continue
            last_company = company
            location = cells[2] if len(cells) > 2 else None
            ext = hashlib.sha1(_norm_url(url).encode()).hexdigest()[:20]
            if ext in jobs:
                continue
            jobs[ext] = NormalizedJob(
                external_id=ext,
                title=role,
                company=company,
                apply_url=url,
                location=normalise_location(location) if location else None,
                remote=is_remote(location or "", ""),
                seniority=infer_seniority(role),
                raw_payload={"repo": self._repo},
            )
        return list(jobs.values())
