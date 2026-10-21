"""jobtracker CLI — main entry point."""
import asyncio
from pathlib import Path
from typing import Optional

import typer
import yaml

from jobtracker.logging import configure_logging
from jobtracker.normalize.experience import resolve_experience
from jobtracker.normalize.experience import parse_experience
from jobtracker.normalize.location import is_us_location
from jobtracker.time import format_pacific

app = typer.Typer(help="Personal job scraper with semantic matching")
run_app = typer.Typer(help="Run ingestor or enricher processes")
app.add_typer(run_app, name="run")
profile_app = typer.Typer(help="Manage user profile")
app.add_typer(profile_app, name="profile")
sources_app = typer.Typer(help="Manage sources")
app.add_typer(sources_app, name="sources")
aliases_app = typer.Typer(help="Manage cross-source job aliases")
app.add_typer(aliases_app, name="aliases")


@run_app.command("ingestor")
def cmd_run_ingestor() -> None:
    """Start the job ingestion process (fetch → normalize → dedup → store)."""
    configure_logging()
    from jobtracker.config import settings
    from jobtracker.metrics.prometheus import start_metrics_server

    start_metrics_server(settings.metrics_port)
    asyncio.run(_run_ingestor())


async def _run_ingestor() -> None:
    from jobtracker.ingest.scheduler import run_ingestor
    await run_ingestor()


@run_app.command("enricher")
def cmd_run_enricher() -> None:
    """Start the enricher process (embed → match → notify)."""
    configure_logging()
    from jobtracker.config import settings
    from jobtracker.metrics.prometheus import start_metrics_server

    start_metrics_server(settings.enricher_metrics_port)
    asyncio.run(_run_enricher())


async def _run_enricher() -> None:
    from jobtracker.enrich.runner import run_enricher
    await run_enricher()


@profile_app.command("set")
def cmd_profile_set(file: Path = typer.Option(Path("config/profile.yaml"), "--file", "-f")) -> None:
    """Load profile from YAML and upsert into the database with embeddings."""
    configure_logging()
    asyncio.run(_upsert_profile(file))


@profile_app.command("set-resumes")
def cmd_profile_set_resumes(
    resumes: Path = typer.Option(Path("resumes"), "--resumes", help="Folder with de.md / ai.md"),
    tracks: Optional[str] = typer.Option(
        "DE,AIML",
        "--tracks",
        help="Comma-separated tracks to load (default: DE,AIML)",
    ),
) -> None:
    """Create/update track profiles by embedding resumes/de.md and resumes/ai.md."""
    configure_logging()
    wanted = [t.strip().upper() for t in (tracks or "").split(",") if t.strip()]
    # Accept "AI" as alias for AIML
    normalized = [("AIML" if t in {"AI", "AIML"} else t) for t in wanted]
    asyncio.run(_upsert_resume_profiles(resumes, normalized))


async def _upsert_resume_profiles(resumes_dir: Path, tracks: list[str]) -> None:
    from jobtracker.db.engine import get_session
    from jobtracker.enrich.track_profiles import bootstrap_track_profiles

    async with get_session() as session:
        rows = await bootstrap_track_profiles(
            session,
            resumes_dir=resumes_dir,
            tracks=tracks,
        )
    for row in rows:
        skills = row.profile_json.get("skills") or []
        typer.echo(f"Profile '{row.name}' saved ({len(skills)} skills) from {row.profile_json.get('source')}")


async def _upsert_profile(path: Path) -> None:
    from datetime import datetime

    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlmodel import select

    from jobtracker.db.engine import get_session
    from jobtracker.db.models import UserProfile
    from jobtracker.enrich.embedder import embed_profile

    with path.open() as f:
        profile_data = yaml.safe_load(f)

    bio: str = profile_data.get("bio", "")
    name: str = profile_data.get("name", "default")

    typer.echo(f"Embedding profile '{name}'…")
    vector = embed_profile(bio)

    async with get_session() as session:
        stmt = pg_insert(UserProfile).values(
            name=name,
            profile_json=profile_data,
            embedding=vector,
            updated_at=datetime.utcnow(),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={"profile_json": stmt.excluded.profile_json, "embedding": stmt.excluded.embedding, "updated_at": stmt.excluded.updated_at},
        )
        await session.execute(stmt)

    typer.echo(f"Profile '{name}' saved.")


@aliases_app.command("rebuild")
def cmd_aliases_rebuild(batch: int = typer.Option(1000, "--batch", help="Number of canonical hashes per batch")) -> None:
    """Rebuild job alias mappings from the current jobs table."""
    configure_logging()
    asyncio.run(_rebuild_aliases(batch))


@aliases_app.command("rehash")
def cmd_aliases_rehash(
    batch: int = typer.Option(500, "--batch", help="Jobs per hash update batch"),
) -> None:
    """Recompute location-agnostic canonical hashes, then rebuild aliases."""
    configure_logging()
    asyncio.run(_rehash_and_rebuild_aliases(batch))


async def _rebuild_aliases(batch: int) -> None:
    from sqlalchemy import delete, distinct, select

    from jobtracker.db.engine import get_session
    from jobtracker.db.models import Job, JobAlias
    from jobtracker.db.repo import sync_job_aliases_for_hashes

    async with get_session() as session:
        result = await session.execute(select(distinct(Job.canonical_hash)))
        hashes = [row[0] for row in result.fetchall() if row[0] is not None]

    if not hashes:
        typer.echo("No job hashes found.")
        return

    async with get_session() as session:
        await session.execute(delete(JobAlias))

    total = 0
    for i in range(0, len(hashes), batch):
        chunk = hashes[i : i + batch]
        async with get_session() as session:
            created = await sync_job_aliases_for_hashes(session, chunk)
        total += created
        typer.echo(f"Processed {min(i + batch, len(hashes))}/{len(hashes)} hashes, created/updated {created} aliases...")

    typer.echo(f"Done. Synced aliases for {len(hashes)} canonical hashes, wrote {total} alias rows.")


async def _rehash_and_rebuild_aliases(batch: int) -> None:
    from sqlalchemy import select, update

    from jobtracker.db.engine import get_session
    from jobtracker.db.models import Job
    from jobtracker.normalize.hashing import canonical_hash

    async with get_session() as session:
        result = await session.execute(
            select(
                Job.id,
                Job.title,
                Job.company,
                Job.location,
                Job.employment_type,
                Job.seniority,
                Job.canonical_hash,
            )
        )
        jobs = result.fetchall()

    changed = 0
    for i in range(0, len(jobs), batch):
        chunk = jobs[i : i + batch]
        async with get_session() as session:
            for row in chunk:
                new_hash = canonical_hash(
                    row.title,
                    row.company,
                    row.location,
                    row.employment_type,
                    row.seniority,
                )
                if new_hash == row.canonical_hash:
                    continue
                await session.execute(
                    update(Job).where(Job.id == row.id).values(canonical_hash=new_hash)
                )
                changed += 1
        typer.echo(f"Rehashed {min(i + batch, len(jobs))}/{len(jobs)} jobs ({changed} changed)...")

    typer.echo(f"Hash updates: {changed}/{len(jobs)}. Rebuilding aliases...")
    await _rebuild_aliases(batch)


@app.command("top")
def cmd_top(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of jobs to show"),
    min_keyword: float = typer.Option(0.0, "--min-keyword", help="Minimum keyword score"),
    min_vector: float = typer.Option(0.0, "--min-vector", help="Minimum vector score"),
    remote_only: bool = typer.Option(False, "--remote", help="Remote jobs only"),
) -> None:
    """Show top-N matched jobs sorted by keyword then vector score."""
    configure_logging()
    asyncio.run(_show_top(limit, min_keyword, min_vector, remote_only))


async def _show_top(limit: int, min_keyword: float, min_vector: float, remote_only: bool) -> None:
    from sqlalchemy import func, select

    from jobtracker.db.engine import get_session
    from jobtracker.db.models import Job, JobAlias, Match, UserProfile
    from jobtracker.db.repo import get_canonical_group_sizes

    async with get_session() as session:
        profile_result = await session.execute(
            select(UserProfile).order_by(UserProfile.updated_at.desc(), UserProfile.id.desc()).limit(1)
        )
        profile = profile_result.scalars().first()
        profile_id = profile.id if profile else None
        profile_years = None
        if profile is not None:
            experience_years = profile.profile_json.get("experience_years")
            if isinstance(experience_years, int):
                profile_years = experience_years

        stmt = (
            select(Job, Match)
            .join(Match, Match.job_id == Job.id)
            .outerjoin(JobAlias, JobAlias.alias_job_id == Job.id)
            .where(Match.keyword_score >= min_keyword)
            .where(Match.vector_score >= min_vector)
            .where(JobAlias.alias_job_id.is_(None))
        )
        if profile_id is not None:
            stmt = stmt.where(Match.profile_id == profile_id)
        if remote_only:
            stmt = stmt.where(Job.remote.is_(True))
        stmt = stmt.order_by(func.coalesce(Job.posted_at, Job.first_seen_at).desc(), Match.keyword_score.desc())

        result = await session.execute(stmt)
        rows = result.fetchall()
        rows = [(job, match) for job, match in rows if is_us_location(job.location, job.description_text)]
        canonical_hashes = list({job.canonical_hash for job, _ in rows if job.canonical_hash is not None})
        group_sizes = await get_canonical_group_sizes(session, canonical_hashes)

    if not rows:
        typer.echo("No matches found.")
        return

    rows = rows[:limit]

    if not rows:
        typer.echo("No US jobs found.")
        return

    for job, match in rows:
        loc = job.location or ("Remote" if job.remote else "—")
        typer.echo(
            f"\nKW {match.keyword_score:.3f}  VE {match.vector_score:.3f}  "
            f"{job.title}  —  {job.company}  ({loc})"
        )
        date_label, date_value = _job_date(job)
        if date_value:
            typer.echo(f"       {date_label}: {date_value}")
        exp_min, exp_max = _job_experience(job)
        if exp_min is not None or exp_max is not None:
            typer.echo(f"       experience {_format_experience(exp_min, exp_max)}")
        warning = _experience_warning(exp_min, profile_years)
        if warning:
            typer.echo(f"       warning: {warning}")
        if match.matched_skills:
            typer.echo(f"       matched profile: {', '.join(match.matched_skills)}")
        if match.missing_skills:
            typer.echo(f"       missing profile: {', '.join(match.missing_skills)}")
        if getattr(match, "missing_master_skills", None):
            if match.missing_master_skills:
                typer.echo(f"       missing master: {', '.join(match.missing_master_skills)}")
        merged_count = group_sizes.get(job.canonical_hash, 1)
        if merged_count > 1:
            typer.echo(f"       merged from {merged_count} postings")
        typer.echo(f"       {job.apply_url}")


def _job_experience(job) -> tuple[int | None, int | None]:
    if job.experience_min_years is not None or job.experience_max_years is not None:
        return job.experience_min_years, job.experience_max_years
    parsed = parse_experience(f"{job.title}\n{job.description_text or job.description_html or ''}")
    return parsed.min_years, parsed.max_years


def _format_experience(min_years: int | None, max_years: int | None) -> str:
    if min_years is not None and max_years is not None:
        if min_years == max_years:
            return f"{min_years} years"
        return f"{min_years}-{max_years} years"
    if min_years is not None:
        return f"{min_years}+ years"
    if max_years is not None:
        return f"up to {max_years} years"
    return "unknown"


def _experience_warning(required_min: int | None, profile_years: int | None) -> str | None:
    if required_min is None or profile_years is None:
        return None
    if profile_years >= required_min:
        return None
    return f"needs {required_min}+ years"


def _job_date(job) -> tuple[str, str | None]:
    if getattr(job, "posted_at", None) is not None:
        return "Posted", _format_dt(job.posted_at)
    if getattr(job, "first_seen_at", None) is not None:
        return "Seen", _format_dt(job.first_seen_at)
    return "Seen", None


def _format_dt(value) -> str:
    return format_pacific(value)


@sources_app.command("list")
def cmd_sources_list() -> None:
    """List all registered sources and their polling status."""
    configure_logging()
    asyncio.run(_list_sources())


async def _list_sources() -> None:
    from sqlalchemy import select

    from jobtracker.db.engine import get_session
    from jobtracker.db.models import Source

    async with get_session() as session:
        result = await session.execute(
            select(Source).order_by(Source.ats, Source.company_slug)
        )
        sources = result.scalars().all()

    if not sources:
        typer.echo("No sources registered yet.")
        return

    typer.echo(f"\n{'ATS':<15} {'Slug':<25} {'Name':<30} {'Interval':>8} {'Failures':>8} {'Last Polled'}")
    typer.echo("-" * 110)
    for s in sources:
        polled = format_pacific(s.last_polled_at) if s.last_polled_at else "never"
        typer.echo(
            f"{s.ats:<15} {s.company_slug:<25} {(s.company_name or '')[:30]:<30}"
            f" {s.poll_interval_s:>8} {s.consecutive_failures:>8} {polled}"
        )


@app.command("status")
def cmd_status() -> None:
    """Show live status of ingestor, enricher, and DB."""
    import traceback
    try:
        asyncio.run(_status())
    except Exception:
        traceback.print_exc()


async def _status() -> None:
    import json
    import os
    from datetime import datetime, timezone, timedelta

    from jobtracker.db.engine import get_session

    # ── Process check ────────────────────────────────────────────────
    def _is_running(name: str) -> bool:
        import subprocess
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-WmiObject Win32_Process | Where-Object {{ $_.CommandLine -like '*jobtracker run {name}*' }}).Count"],
            capture_output=True, text=True
        )
        try:
            return int(r.stdout.strip()) > 0
        except Exception:
            return False

    ingestor_up = _is_running("ingestor")
    enricher_up = _is_running("enricher")

    print("\n=== Process Status ===")
    print(f"  Ingestor : {'RUNNING' if ingestor_up else 'STOPPED'}")
    print(f"  Enricher : {'RUNNING' if enricher_up else 'STOPPED'}")

    # ── DB stats ─────────────────────────────────────────────────────
    from sqlalchemy import text
    async with get_session() as session:
        total_jobs = (await session.execute(text("SELECT COUNT(*) FROM jobs"))).scalar()
        scored_jobs = (await session.execute(text("SELECT COUNT(*) FROM matches"))).scalar()
        unscored = total_jobs - scored_jobs
        new_1h = (await session.execute(text(
            "SELECT COUNT(*) FROM jobs WHERE first_seen_at > NOW() - INTERVAL '1 hour'"
        ))).scalar()
        new_24h = (await session.execute(text(
            "SELECT COUNT(*) FROM jobs WHERE first_seen_at > NOW() - INTERVAL '24 hours'"
        ))).scalar()
        top = (await session.execute(text(
            "SELECT j.title, j.company, (m.vector_score * 0.7 + m.keyword_score * 0.3) AS score "
            "FROM matches m JOIN jobs j ON j.id = m.job_id "
            "ORDER BY score DESC LIMIT 3"
        ))).fetchall()

    print("\n=== Database ===")
    print(f"  Total jobs    : {total_jobs:,}")
    print(f"  Scored jobs   : {scored_jobs:,}")
    print(f"  Pending score : {unscored:,}")
    print(f"  New (1h)      : {new_1h:,}")
    print(f"  New (24h)     : {new_24h:,}")

    # ── Recent log activity ──────────────────────────────────────────
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M")
    log_path = "ingestor.log"
    done_count = err_count = new_jobs = 0
    if os.path.exists(log_path):
        with open(log_path, "rb") as f:
            for line in f:
                try:
                    j = json.loads(line)
                    if j.get("timestamp", "") >= cutoff:
                        if j.get("event") == "worker.done":
                            done_count += 1
                            new_jobs += j.get("new", 0)
                        elif j.get("event") == "worker.error":
                            err_count += 1
                except Exception:
                    pass

    print("\n=== Ingestor (last 5 min) ===")
    print(f"  Sources polled : {done_count}")
    print(f"  New jobs found : {new_jobs}")
    print(f"  Errors         : {err_count}")

    if top:
        print("\n=== Top 3 Matches ===")
        for title, company, score in top:
            print(f"  {score:.2f}  {company} — {title}")

    print("", flush=True)


@app.command("recompute")
def cmd_recompute(
    batch: int = typer.Option(500, "--batch", help="Jobs per batch"),
) -> None:
    """Recompute match scores for all embedded jobs against current profile."""
    configure_logging()
    asyncio.run(_recompute(batch))


@app.command("backfill-experience")
def cmd_backfill_experience(
    batch: int = typer.Option(100, "--batch", help="Jobs per batch"),
) -> None:
    """Fill missing experience columns by inspecting the linked job page."""
    configure_logging()
    asyncio.run(_backfill_experience(batch))


async def _recompute(batch_size: int) -> None:
    from sqlalchemy import select

    from jobtracker.db.engine import get_session
    from jobtracker.db.models import Job
    from jobtracker.enrich.matcher import compute_matches

    offset = 0
    total = 0
    while True:
        async with get_session() as session:
            result = await session.execute(
                select(Job.id)
                .where(Job.embedding.isnot(None))
                .order_by(Job.id)
                .limit(batch_size)
                .offset(offset)
            )
            ids = [row[0] for row in result.fetchall()]

        if not ids:
            break

        async with get_session() as session:
            await compute_matches(session, ids)

        total += len(ids)
        offset += batch_size
        typer.echo(f"Scored {total} jobs…")

    typer.echo(f"Done. Recomputed scores for {total} jobs.")


async def _backfill_experience(batch_size: int) -> None:
    from sqlalchemy import select, update

    from jobtracker.db.engine import get_session
    from jobtracker.db.models import Job

    last_id = 0
    scanned = 0
    updated = 0

    while True:
        async with get_session() as session:
            result = await session.execute(
                select(Job)
                .where(
                    Job.id > last_id,
                    Job.apply_url.isnot(None),
                    Job.experience_min_years.is_(None),
                    Job.experience_max_years.is_(None),
                )
                .order_by(Job.id)
                .limit(batch_size)
            )
            jobs = list(result.scalars().all())

        if not jobs:
            break

        async with get_session() as session:
            for job in jobs:
                parsed = await resolve_experience(
                    job.title,
                    job.description_text,
                    job.description_html,
                    job.apply_url,
                )
                if parsed.min_years is None and parsed.max_years is None:
                    continue
                await session.execute(
                    update(Job)
                    .where(Job.id == job.id)
                    .values(
                        experience_min_years=parsed.min_years,
                        experience_max_years=parsed.max_years,
                    )
                )
                updated += 1

        scanned += len(jobs)
        last_id = jobs[-1].id
        typer.echo(f"Scanned {scanned} jobs, updated {updated}...")

    typer.echo(f"Done. Backfilled experience for {updated} jobs.")


@app.command("web")
def cmd_web(
    port: int = typer.Option(8080, "--port", "-p", help="Port to listen on"),
) -> None:
    """Start the web UI (open http://localhost:8080 in your browser)."""
    configure_logging()
    import uvicorn
    typer.echo(f"Opening job board at http://localhost:{port}")
    uvicorn.run("jobtracker.web.app:app", host="0.0.0.0", port=port, reload=False)


@app.command("score-server")
def cmd_score_server(
    port: int = typer.Option(8765, "--port", "-p", help="Port to listen on"),
    resumes: Path = typer.Option(Path("resumes"), "--resumes", help="Folder with *.md resumes"),
) -> None:
    """Start the bookmarklet scoring server (reranker + keyword scores vs resumes/*.md)."""
    configure_logging()
    import uvicorn

    from jobtracker.score_server import create_app

    fastapi_app = create_app(resumes_dir=resumes)
    typer.echo(f"Score server on http://localhost:{port}  (resumes from {resumes}/)")
    uvicorn.run(fastapi_app, host="127.0.0.1", port=port, log_level="info")


@app.command("migrate")
def cmd_migrate() -> None:
    """Run Alembic migrations (upgrade to head)."""
    import subprocess
    result = subprocess.run(
        ["alembic", "-c", "migrations/alembic.ini", "upgrade", "head"],
        check=False,
    )
    raise typer.Exit(result.returncode)
