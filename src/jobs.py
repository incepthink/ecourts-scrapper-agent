"""Scrape-job orchestration: cache check, in-flight dedup, and enqueue.

This is the seam between the API and the worker. The API (``api.py``) calls
``enqueue_scrape`` on every search; this module decides whether the advocate is
already cached (return immediately), a scrape is already running for that
name+district (reuse it — never start a duplicate), or a fresh job must be
queued onto Redis/RQ.

Deliberately light: it imports ``profile_data`` + ``store`` + redis/rq only, NOT
the scraper (``pipeline``/``advocate_search``/bharat-courts). The heavy work runs
in the separate worker process, which RQ reaches by the string
``"worker.run_scrape_job"`` so this module never imports it.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from redis import Redis
from rq import Queue
from sqlalchemy import select

import profile_data
import store
from store import Job, Session

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
QUEUE_NAME = os.environ.get("ECOURTS_QUEUE", "scrapes")
JOB_TIMEOUT = int(os.environ.get("ECOURTS_JOB_TIMEOUT", "3600"))  # seconds (scrapes are long)
# Treat a previously scraped advocate as fresh for this many days (used only by
# an explicit "refresh"; a normal search always serves an existing cache).
CACHE_FRESH_DAYS = int(os.environ.get("ECOURTS_CACHE_FRESH_DAYS", "30"))

_ACTIVE = ("queued", "running")


def redis_conn() -> Redis:
    return Redis.from_url(REDIS_URL)


def queue() -> Queue:
    return Queue(QUEUE_NAME, connection=redis_conn())


# ---- live progress pub/sub (shared channel name for worker + API) ---------


def channel(job_id: int) -> str:
    return f"job:{job_id}:events"


def publish_event(conn: Redis, job_id: int, event: dict) -> None:
    """Publish one progress event to the job's channel (worker -> SSE)."""
    conn.publish(channel(job_id), json.dumps(event))


# ---- cache check ----------------------------------------------------------


def _cached_advocate(session, name: str, state_code: str, dist_code: str):
    """Return the canonical Advocate if we already hold cases for this
    name+state+district, else None."""
    matches = profile_data._matching_advocates(session, name)
    if not matches:
        return None
    cases = profile_data._load_cases(
        session, [a.id for a in matches], state_code=state_code, dist_code=dist_code
    )
    if not cases:
        return None
    return profile_data._canonical_match(matches, name)


def _is_fresh(advocate) -> bool:
    ts = getattr(advocate, "last_scraped_at", None)
    if ts is None:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - ts < timedelta(days=CACHE_FRESH_DAYS)


# ---- enqueue --------------------------------------------------------------


def enqueue_scrape(
    name: str,
    state_code: str,
    dist_code: str,
    district_name: str,
    user_id: str = "",
    *,
    force: bool = False,
) -> dict:
    """Decide what to do for a search and act on it.

    Returns one of:
      * ``{"status": "ready", "advocate_id": id, "job_id": None}`` — cached.
      * ``{"status": "scraping", "job_id": id, "reused": bool}`` — a job is
        running/queued (``reused`` True when an in-flight duplicate was joined).

    ``force=True`` (the "refresh / fetch latest" action) skips the cache and
    always queues a new scrape unless one is already in flight.
    """
    norm = store.normalize_name(name)
    with Session() as session:
        if not force:
            cached = _cached_advocate(session, name, state_code, dist_code)
            if cached is not None:
                return {"status": "ready", "advocate_id": cached.id, "job_id": None}

        # Dedup: never run two scrapes for the same name+district at once.
        existing = session.scalar(
            select(Job)
            .where(
                Job.name_norm == norm,
                Job.state_code == state_code,
                Job.dist_code == dist_code,
                Job.status.in_(_ACTIVE),
            )
            .order_by(Job.id.desc())
        )
        if existing is not None:
            return {"status": "scraping", "job_id": existing.id, "reused": True}

        job = Job(
            advocate_name=name.strip(),
            name_norm=norm,
            state_code=state_code,
            dist_code=dist_code,
            district_name=district_name,
            status="queued",
            user_id=str(user_id or ""),
        )
        session.add(job)
        session.commit()
        job_id = job.id

    queue().enqueue("worker.run_scrape_job", job_id, job_timeout=JOB_TIMEOUT)
    return {"status": "scraping", "job_id": job_id, "reused": False}


def cancel_job(job_id: int, message: str = "cancelled") -> None:
    """Mark a queued/running job cancelled (e.g. rejected by the rate limiter).
    The worker skips any job that is not still ``queued`` when it claims it."""
    with Session() as session:
        job = session.get(Job, job_id)
        if job is not None and job.status in _ACTIVE:
            job.status = "cancelled"
            job.message = message
            session.commit()


def job_snapshot(session, job_id: int) -> dict | None:
    """Current persisted state of a job (for the API to return / SSE late-join)."""
    job = session.get(Job, job_id)
    if job is None:
        return None
    return {
        "job_id": job.id,
        "status": job.status,
        "progress": job.progress,
        "phase": job.phase,
        "message": job.message,
        "advocate_id": job.advocate_id,
        "advocate_name": job.advocate_name,
        "state_code": job.state_code,
        "dist_code": job.dist_code,
        "district_name": job.district_name,
    }
