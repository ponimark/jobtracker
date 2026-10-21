"""Discord webhook notifier."""
import httpx

from jobtracker.config import settings
from jobtracker.db.models import Job, Match
from jobtracker.logging import get_logger
from jobtracker.metrics.prometheus import NOTIFY_COUNTER

log = get_logger(__name__)


async def send_discord_notification(job: Job, match: Match) -> bool:
    """Send a job match notification to Discord. Returns True on success."""
    if not settings.discord_webhook_url:
        return False

    salary_str = ""
    if job.salary_min and job.salary_max:
        salary_str = f"${job.salary_min // 1000}k–${job.salary_max // 1000}k"
    elif job.salary_min:
        salary_str = f"${job.salary_min // 1000}k+"

    location_str = job.location or ("Remote" if job.remote else "Unknown")

    embed = {
        "title": f"{job.title} @ {job.company}",
        "url": job.apply_url,
        "color": _score_to_color(match.keyword_score),
        "fields": [
            {"name": "Keyword Score", "value": f"{match.keyword_score:.2f}", "inline": True},
            {"name": "Vector Score", "value": f"{match.vector_score:.2f}", "inline": True},
            {"name": "Location", "value": location_str, "inline": True},
            *([{"name": "Matched Skills", "value": ", ".join(match.matched_skills), "inline": False}] if match.matched_skills else []),
            *([{"name": "Missing Profile", "value": ", ".join(match.missing_skills), "inline": False}] if match.missing_skills else []),
            *([{"name": "Missing Master", "value": ", ".join(getattr(match, "missing_master_skills", [])), "inline": False}] if getattr(match, "missing_master_skills", []) else []),
            *([{"name": "Salary", "value": salary_str, "inline": True}] if salary_str else []),
        ],
        "footer": {"text": f"via jobtracker | {job.company}"},
    }

    payload = {"embeds": [embed]}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(settings.discord_webhook_url, json=payload)
            response.raise_for_status()
        NOTIFY_COUNTER.labels(channel="discord").inc()
        log.info("notify.discord.sent", job_id=job.id, keyword_score=match.keyword_score, vector_score=match.vector_score)
        return True
    except Exception as exc:
        log.error("notify.discord.error", error=str(exc))
        return False


def _score_to_color(score: float) -> int:
    if score >= 0.85:
        return 0x00FF00  # green
    if score >= 0.75:
        return 0xFFFF00  # yellow
    return 0xFF8C00  # orange
