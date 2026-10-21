"""One-shot: recompute rerank_score for every existing match using the cross-encoder.

Uses build_rerank_query (short summary + roles + skills), not the full resume.
"""
import asyncio
import sys
import time

sys.path.insert(0, "src")

from sqlalchemy import text

from jobtracker.db.engine import get_session
from jobtracker.enrich.embedder import build_job_text
from jobtracker.enrich.reranker import rerank_pairs
from jobtracker.enrich.trim import build_rerank_query


BATCH = 200


async def main() -> None:
    async with get_session() as session:
        profiles = (
            await session.execute(
                text("SELECT id, name, profile_json FROM user_profile")
            )
        ).fetchall()
    if not profiles:
        print("no profiles")
        return

    for profile_id, name, profile_json in profiles:
        pj = profile_json if isinstance(profile_json, dict) else {}
        bio = pj.get("bio", "") if isinstance(pj.get("bio", ""), str) else ""
        skills = pj.get("skills", []) if isinstance(pj.get("skills", []), list) else []
        query = build_rerank_query(bio, skills)
        if not query:
            print(f"profile {name} ({profile_id}): empty rerank query, skipping")
            continue
        print(f"profile {name} ({profile_id}): query_chars={len(query)}")
        print(f"  query_preview={query[:180]!r}...")

        async with get_session() as session:
            ids = [
                r[0]
                for r in (
                    await session.execute(
                        text(
                            "SELECT job_id FROM matches WHERE profile_id = :pid ORDER BY job_id"
                        ),
                        {"pid": profile_id},
                    )
                ).fetchall()
            ]

        print(f"profile {name}: reranking {len(ids)} matches")
        t0 = time.monotonic()
        done = 0

        for i in range(0, len(ids), BATCH):
            chunk_ids = ids[i : i + BATCH]
            async with get_session() as session:
                jobs = (
                    await session.execute(
                        text(
                            "SELECT id, title, company, description_text FROM jobs WHERE id = ANY(:ids)"
                        ),
                        {"ids": chunk_ids},
                    )
                ).fetchall()
                jobs_by_id = {j[0]: j for j in jobs}
                ordered = [jobs_by_id[jid] for jid in chunk_ids if jid in jobs_by_id]
                docs = [build_job_text(j[1], j[2], j[3] or "") for j in ordered]
                scores = rerank_pairs(query, docs)
                for j, s in zip(ordered, scores):
                    await session.execute(
                        text(
                            "UPDATE matches SET rerank_score = :s "
                            "WHERE job_id = :jid AND profile_id = :pid"
                        ),
                        {"s": float(s), "jid": j[0], "pid": profile_id},
                    )
                await session.commit()
            done += len(ordered)
            elapsed = time.monotonic() - t0
            rate = done / elapsed if elapsed > 0 else 0
            eta = (len(ids) - done) / rate if rate > 0 else 0
            print(f"  {done}/{len(ids)}  {rate:.1f}/s  eta={eta:.0f}s")

    print("done.")


if __name__ == "__main__":
    asyncio.run(main())
