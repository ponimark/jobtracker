from datetime import datetime
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class Source(SQLModel, table=True):
    __tablename__ = "sources"

    id: Optional[int] = Field(default=None, primary_key=True)
    ats: str = Field(index=True)
    company_slug: str
    company_name: Optional[str] = None
    base_url: str
    poll_interval_s: int = 60
    enabled: bool = True
    last_polled_at: Optional[datetime] = None
    last_etag: Optional[str] = None
    last_modified: Optional[str] = None
    last_status: Optional[int] = None
    consecutive_failures: int = 0

    class Config:
        arbitrary_types_allowed = True


class Job(SQLModel, table=True):
    __tablename__ = "jobs"

    id: Optional[int] = Field(default=None, primary_key=True)
    source_id: int = Field(foreign_key="sources.id", index=True)
    external_id: str
    canonical_hash: bytes
    content_hash: bytes
    title: str
    company: str
    location: Optional[str] = None
    remote: Optional[bool] = None
    employment_type: Optional[str] = None
    seniority: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: Optional[str] = None
    description_html: Optional[str] = None
    description_text: Optional[str] = None
    apply_url: str
    posted_at: Optional[datetime] = None
    experience_min_years: Optional[int] = None
    experience_max_years: Optional[int] = None
    applied_at: Optional[datetime] = None
    first_seen_at: datetime = Field(default_factory=datetime.utcnow)
    last_seen_at: datetime = Field(default_factory=datetime.utcnow)
    removed_at: Optional[datetime] = None

    # pgvector column — not a standard SQLModel field, added via __table_args__
    embedding: Optional[list[float]] = Field(
        default=None,
        sa_column=Column(Vector(384), nullable=True),
    )
    embedded_at: Optional[datetime] = None

    class Config:
        arbitrary_types_allowed = True

    __table_args__ = (
        Index("jobs_canonical_hash_idx", "canonical_hash"),
        Index("jobs_first_seen_idx", "first_seen_at"),
        # HNSW index created via migration (requires pgvector extension)
    )


class JobRaw(SQLModel, table=True):
    __tablename__ = "jobs_raw"

    job_id: int = Field(foreign_key="jobs.id", primary_key=True)
    fetched_at: datetime = Field(default_factory=datetime.utcnow, primary_key=True)
    payload: dict = Field(sa_column=Column("payload", JSONB, nullable=False))

    class Config:
        arbitrary_types_allowed = True


class JobAlias(SQLModel, table=True):
    __tablename__ = "job_aliases"

    alias_job_id: int = Field(foreign_key="jobs.id", primary_key=True)
    canonical_job_id: int = Field(foreign_key="jobs.id", index=True)
    canonical_hash: bytes
    created_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (
        Index("job_aliases_canonical_idx", "canonical_job_id"),
        Index("job_aliases_hash_idx", "canonical_hash"),
    )

    class Config:
        arbitrary_types_allowed = True


class UserProfile(SQLModel, table=True):
    __tablename__ = "user_profile"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    profile_json: dict = Field(sa_column=Column("profile_json", JSONB, nullable=False))
    embedding: list[float] = Field(sa_column=Column(Vector(384), nullable=False))
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        arbitrary_types_allowed = True


class Match(SQLModel, table=True):
    __tablename__ = "matches"

    job_id: int = Field(foreign_key="jobs.id", primary_key=True)
    profile_id: int = Field(foreign_key="user_profile.id", primary_key=True)
    keyword_score: float = 0.0
    vector_score: float = 0.0
    rerank_score: Optional[float] = None
    matched_skills: list[str] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    missing_skills: list[str] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    missing_master_skills: list[str] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    computed_at: datetime = Field(default_factory=datetime.utcnow)
    notified_at: Optional[datetime] = None

    __table_args__ = (
        Index("matches_keyword_idx", "profile_id", "keyword_score"),
        Index("matches_vector_idx", "profile_id", "vector_score"),
        Index("matches_rerank_idx", "profile_id", "rerank_score"),
    )

    class Config:
        arbitrary_types_allowed = True


class FetchLog(SQLModel, table=True):
    __tablename__ = "fetch_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    source_id: Optional[int] = Field(default=None, foreign_key="sources.id")
    started_at: datetime = Field(default_factory=datetime.utcnow)
    duration_ms: Optional[int] = None
    status: Optional[int] = None
    new_jobs: int = 0
    changed_jobs: int = 0
    error: Optional[str] = None
