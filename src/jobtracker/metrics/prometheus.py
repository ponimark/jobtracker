"""Prometheus metrics for ingestor and enricher."""
from prometheus_client import Counter, Gauge, Histogram, start_http_server

FETCH_DURATION = Histogram(
    "jobtracker_fetch_duration_seconds",
    "HTTP fetch duration per source",
    labelnames=["ats", "slug"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

NEW_JOBS_COUNTER = Counter(
    "jobtracker_new_jobs_total",
    "Total new jobs ingested",
    labelnames=["ats"],
)

CHANGED_JOBS_COUNTER = Counter(
    "jobtracker_changed_jobs_total",
    "Total jobs updated (description changed)",
    labelnames=["ats"],
)

LAST_NEW_JOB_TS = Gauge(
    "jobtracker_last_new_job_timestamp_seconds",
    "Unix timestamp of the last new job for this source",
    labelnames=["source"],
)

EMBED_DURATION = Histogram(
    "jobtracker_embed_duration_seconds",
    "Time to embed a batch of jobs",
    buckets=[0.05, 0.1, 0.5, 1.0, 5.0, 10.0],
)

KEYWORD_SCORE = Histogram(
    "jobtracker_keyword_score",
    "Distribution of keyword match scores",
    buckets=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
)

VECTOR_SCORE = Histogram(
    "jobtracker_vector_score",
    "Distribution of vector similarity scores",
    buckets=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
)

NOTIFY_COUNTER = Counter(
    "jobtracker_notifications_total",
    "Total notifications sent",
    labelnames=["channel"],
)


def start_metrics_server(port: int) -> None:
    start_http_server(port)
