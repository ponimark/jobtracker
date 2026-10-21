# jobtracker

A personal job finder. It polls company career pages and job boards, normalizes and de-duplicates the postings, scores each job against your resumes with embeddings, and shows the ranked results in a small web UI.

I built it to run my own entry-level data engineering and ML job search. It replaces checking dozens of career pages by hand.

## What it does

- **Ingests from many sources.** Adapters for Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Workday, a few company career-site APIs (Amazon, Microsoft, JPMorgan), community GitHub new-grad lists (README tables), and aggregator searches. Sources are listed in `config/sources.yaml`.
- **Normalizes.** Titles, companies, locations, seniority, salary and years of experience.
- **De-duplicates.** A Redis seen-ID cache skips jobs already fetched, and a canonical hash (title, company, seniority) in PostgreSQL merges the same job posted on several sites.
- **Scores.** Each job is embedded with BGE-small (`BAAI/bge-small-en-v1.5`) into pgvector with an HNSW index. The match score is `0.7 x vector similarity + 0.3 x keyword overlap` against each resume track, and a cross-encoder reranker can re-score the top candidates.
- **Filters.** Title include and exclude keywords, a company blocklist, and US-location filtering live in `config/title_filters.yaml`.
- **Shows results.** A FastAPI page with live search, filters, sorting, and one-click "Applied" tracking.
- **Schedules adaptively.** Quiet sources are polled less often and speed up again when new jobs appear.

## Architecture

```
sources.yaml -> adapters -> normalize -> dedupe (Redis + Postgres) -> jobs table
                                                              |
                                                     NOTIFY new_job
                                                              v
                                       enricher: embed -> match (pgvector) -> web UI
```

Three processes: the **ingestor** (`scripts/ingestor.py`), the **enricher** (`scripts/enricher.py`), and the **web UI** (`scripts/web.py`). PostgreSQL (pgvector) and Redis run in Docker.

## Setup

Requires Python 3.12+, Docker, and about 1 GB of disk for the embedding model.

```bash
git clone <this repo> && cd jobtracker
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[api,dev]"

cp .env.example .env
cp config/profile.example.yaml config/profile.yaml   # edit for yourself
cp resumes/example.md resumes/de.md                   # put your own resume text here

docker compose up postgres redis -d
alembic upgrade head
python -m jobtracker profile set-resumes

python scripts/ingestor.py &
python scripts/enricher.py &
python scripts/web.py          # http://localhost:8080
```

Your resumes and `config/profile.yaml` stay local (they are in `.gitignore`).

## Configuration

- `config/sources.yaml`: which companies and boards to poll, and how often.
- `config/title_filters.yaml`: title keywords, soft SWE rules, and `exclude_companies`.
- `config/profile.yaml`: your target titles, skills and bio (start from `profile.example.yaml`).
- `.env`: database, Redis and optional API keys (for example Adzuna).

## Tests

```bash
pytest tests/unit
```

Integration tests need the Docker services running. A few tests cover Windows-only process helpers and are skipped on other platforms.

## Layout

```
src/jobtracker/
  sources/     one adapter per ATS or board
  ingest/      scheduler and per-source fetch, normalize, upsert pipeline
  normalize/   titles, companies, locations, salary, experience, hashing
  enrich/      embeddings, matching, reranking
  web/         FastAPI app and templates
  db/          models and queries (Alembic migrations in migrations/)
scripts/       process entry points and maintenance helpers
```

## Notes

- Be polite to the sites you poll: the adapters rate-limit per host and use conditional requests (ETag) where available. Check each site's terms before scraping, especially job boards.
- This is a personal project, so expect rough edges.

## License

MIT, see `LICENSE`.
