"""Background scrape worker (RQ).

``run_scrape_job(job_id)`` is the RQ task the API enqueues (by the string
``"worker.run_scrape_job"``). It runs the existing async pipeline to completion
for one advocate in one district, **streaming progress** to Redis as it goes so
the browser's SSE connection can show "searching court i/N" and cases appearing
live, then caches the AI narrative on the advocate so page views are instant.

PDFs are intentionally skipped (``download_pdfs=False``) — the live product shows
order metadata only, and skipping downloads makes a cold scrape meaningfully
faster.

Run it (Render background worker / locally):
    PYTHONPATH=src rq worker scrapes            # Linux
    PYTHONPATH=src rq worker -w rq.worker.SimpleWorker scrapes   # Windows (no fork)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import config
import jobs
import profile_data
from advocate_search import AdvocateSearchClient
from bharat_courts.captcha.ocr import OCRCaptchaSolver
from pipeline import list_district_complexes, process_name
from store import Advocate, Job, Session

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("worker")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _progress_percent(event: dict) -> int:
    """Map a pipeline event to a 0-100 bar: search ~5-55%, enrich ~60-98%."""
    phase = event.get("phase")
    if phase == "search_complex":
        total = max(int(event.get("total", 1)), 1)
        return int(5 + 50 * (int(event.get("index", 0)) / total))
    if phase == "cases_found":
        return 58
    if phase == "case_enriched":
        total = max(int(event.get("total", 1)), 1)
        return int(60 + 38 * (int(event.get("index", 0)) / total))
    return 0


def _message(event: dict) -> str:
    phase = event.get("phase")
    if phase == "search_complex":
        return f"Searching {event.get('complex_name', 'court')} ({event.get('index')}/{event.get('total')})"
    if phase == "cases_found":
        return f"Found {event.get('unique_cases', 0)} cases — fetching details"
    if phase == "case_enriched":
        return f"Loading case details ({event.get('index')}/{event.get('total')})"
    return event.get("message", "")


def _make_progress(conn, job_id: int):
    """A sync on_progress callback: persist the job's latest state + publish the
    event (enriched with progress% and a human message) to its SSE channel."""

    def on_progress(event: dict) -> None:
        pct = _progress_percent(event)
        msg = _message(event)
        with Session() as s:
            job = s.get(Job, job_id)
            if job is not None:
                job.progress = max(job.progress or 0, pct)
                job.phase = event.get("phase", "")
                if msg:
                    job.message = msg
                s.commit()
        jobs.publish_event(conn, job_id, {**event, "progress": pct, "message": msg})

    return on_progress


async def _run(job_id: int) -> None:
    with Session() as s:
        job = s.get(Job, job_id)
        if job is None:
            logger.warning("job %s not found", job_id)
            return
        if job.status != "queued":
            # Cancelled (e.g. by the rate limiter) or already claimed — skip.
            logger.info("job %s not runnable (status=%s); skipping", job_id, job.status)
            return
        name = job.advocate_name
        state_code = job.state_code or config.STATE_CODE
        dist_code = job.dist_code
        district_name = job.district_name
        job.status = "running"
        job.message = "Connecting to court portal…"
        s.commit()

    conn = jobs.redis_conn()
    jobs.publish_event(conn, job_id, {"phase": "running", "progress": 2,
                                      "message": "Connecting to court portal…"})
    on_progress = _make_progress(conn, job_id)

    solver = OCRCaptchaSolver()
    async with AdvocateSearchClient(captcha_solver=solver) as client:
        complexes = await list_district_complexes(client, state_code, dist_code)
        result = await process_name(
            client, name,
            state_code=state_code, dist_code=dist_code, complexes=complexes,
            download_pdfs=False, on_progress=on_progress,
        )

    # Generate + cache the AI narrative once, mark the advocate freshly scraped,
    # and resolve the advocate id the frontend will load the profile by.
    advocate_id = None
    with Session() as s:
        profile = profile_data.build_profile(
            s, name, state_code=state_code, dist_code=dist_code,
            district_name=district_name, generate_ai=True,
        )
        advocate_id = profile.get("advocate_id")
        if advocate_id:
            adv = s.get(Advocate, advocate_id)
            if adv is not None:
                adv.ai_summary = profile.get("ai_summary") or ""
                adv.last_scraped_at = _now()
        job = s.get(Job, job_id)
        if job is not None:
            job.status = "done"
            job.progress = 100
            job.phase = "done"
            job.advocate_id = advocate_id
            job.message = f"Done — {result.get('unique_cases', 0)} cases"
        s.commit()

    jobs.publish_event(conn, job_id, {
        "phase": "done", "progress": 100, "advocate_id": advocate_id,
        "message": "Profile ready", "result": result,
    })
    logger.info("job %s done: %s", job_id, result)


def run_scrape_job(job_id: int) -> None:
    """RQ entrypoint (synchronous). Drives the async scrape to completion and
    records failure on the job + SSE channel so the UI can show an error."""
    try:
        asyncio.run(_run(job_id))
    except Exception as e:  # noqa: BLE001 - surface any failure to the UI
        logger.exception("job %s failed", job_id)
        msg = str(e)[:500]
        with Session() as s:
            job = s.get(Job, job_id)
            if job is not None:
                job.status = "error"
                job.message = msg
                s.commit()
        try:
            jobs.publish_event(jobs.redis_conn(), job_id,
                               {"phase": "error", "progress": 100, "message": msg})
        except Exception:  # noqa: BLE001
            pass
        raise
