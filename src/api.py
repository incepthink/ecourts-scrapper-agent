"""FastAPI backend for the advocate-profiles product.

The Next.js frontend (behind NextAuth login) calls this directly. It:
  * lists states/districts from the live court portal (cached in Redis),
  * on search, serves a cached profile or enqueues a scrape (``jobs.py``),
  * streams that scrape's live progress over SSE,
  * serves the assembled profile JSON (``profile_data.build_profile``) and the
    downloadable HTML report (``report_html``).

Auth: every data route requires a Bearer JWT minted by the Next.js app and
signed with the shared ``BACKEND_JWT_SECRET`` (HS256). New scrapes are rate
limited per user per day.

Run:  PYTHONPATH=src uvicorn api:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import date

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from jose import JWTError, jwt
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

import jobs
import profile_data
import report_html
import store
from portal_status import PORTAL_DOWN_MESSAGE, is_portal_down
from store import Advocate, Session

BACKEND_JWT_SECRET = os.environ.get("BACKEND_JWT_SECRET", "dev-secret-change-me")
FRONTEND_ORIGINS = [
    o.strip().rstrip("/")
    for o in os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000").split(",")
    if o.strip()
]
# Optional regex to also allow dynamic origins (e.g. Vercel preview deployments).
# Always allow localhost/127.0.0.1 on any port for local development, in addition
# to any custom regex supplied via FRONTEND_ORIGIN_REGEX.
_LOCALHOST_ORIGIN_REGEX = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"
_extra_regex = os.environ.get("FRONTEND_ORIGIN_REGEX")
FRONTEND_ORIGIN_REGEX = (
    f"({_LOCALHOST_ORIGIN_REGEX})|({_extra_regex})"
    if _extra_regex
    else _LOCALHOST_ORIGIN_REGEX
)
SCRAPES_PER_DAY = int(os.environ.get("ECOURTS_SCRAPES_PER_DAY", "10"))
LOC_TTL = int(os.environ.get("ECOURTS_LOC_TTL", "86400"))  # cache states/districts 24h

app = FastAPI(title="eCourts Advocate Profiles API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_origin_regex=FRONTEND_ORIGIN_REGEX,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- auth -----------------------------------------------------------------


def _decode(token: str) -> dict:
    try:
        payload = jwt.decode(token, BACKEND_JWT_SECRET, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(status_code=401, detail="invalid token")
    uid = payload.get("sub") or payload.get("email")
    if not uid:
        raise HTTPException(status_code=401, detail="token has no subject")
    return {"id": str(uid), "email": payload.get("email", "")}


def current_user(authorization: str = Header(default="")) -> dict:
    """Verify the Bearer JWT the Next.js app minted; return the user identity."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    return _decode(authorization.split(" ", 1)[1])


# ---- locations (live portal hierarchy, cached) ----------------------------


async def _list_states() -> list[dict]:
    from advocate_search import AdvocateSearchClient  # lazy: avoid heavy import at startup

    async with AdvocateSearchClient() as client:  # no CAPTCHA solver needed for hierarchy
        # list_states_live() reads the portal's live state dropdown; the codes it
        # returns match list_districts() (unlike the stale hardcoded list_states()).
        states = await client.list_states_live()
    return sorted(({"code": c, "name": n} for c, n in states.items()), key=lambda x: x["name"])


async def _list_districts(state_code: str) -> list[dict]:
    from advocate_search import AdvocateSearchClient

    async with AdvocateSearchClient() as client:
        districts = await client.list_districts(state_code)
    return sorted(({"code": c, "name": n} for c, n in districts.items()), key=lambda x: x["name"])


async def _cached_locations(key: str, builder) -> list[dict]:
    conn = jobs.redis_conn()
    cached = conn.get(key)
    if cached:
        return json.loads(cached)
    try:
        data = await builder()
    except Exception as e:  # noqa: BLE001 - distinguish a portal outage from app errors
        if is_portal_down(e):
            raise HTTPException(status_code=503, detail=PORTAL_DOWN_MESSAGE)
        raise
    conn.setex(key, LOC_TTL, json.dumps(data))
    return data


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/locations/states")
async def states(user: dict = Depends(current_user)) -> list[dict]:
    return await _cached_locations("loc:states", _list_states)


@app.get("/locations/districts")
async def districts(state_code: str = Query(...), user: dict = Depends(current_user)) -> list[dict]:
    return await _cached_locations(f"loc:districts:{state_code}", lambda: _list_districts(state_code))


# ---- search ---------------------------------------------------------------


class SearchBody(BaseModel):
    name: str
    state_code: str
    dist_code: str
    district_name: str = ""
    force: bool = False  # "refresh / fetch latest"
    notify_email: bool = False  # opt in to an email when the scrape finishes


def _rate_limit(user_id: str) -> None:
    """Soft per-user daily scrape cap. Raises 429 once exceeded."""
    conn = jobs.redis_conn()
    key = f"rl:scrape:{user_id}:{date.today().isoformat()}"
    count = conn.incr(key)
    if count == 1:
        conn.expire(key, 86400)
    if count > SCRAPES_PER_DAY:
        raise HTTPException(status_code=429,
                            detail=f"Daily scrape limit ({SCRAPES_PER_DAY}) reached. Try again tomorrow.")


@app.post("/search")
def search(body: SearchBody, user: dict = Depends(current_user)) -> dict:
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    # The opt-in is just a flag; the address always comes from the verified JWT,
    # never from the client (so a user can't have results mailed to someone else).
    res = jobs.enqueue_scrape(
        body.name, body.state_code, body.dist_code, body.district_name,
        user_id=user["id"], force=body.force,
        notify_to=(user["email"] if body.notify_email else ""),
    )
    # Count only genuinely new scrapes against the user's quota.
    if res["status"] == "scraping" and not res.get("reused"):
        try:
            _rate_limit(user["id"])
        except HTTPException:
            jobs.cancel_job(res["job_id"], message="Daily scrape limit reached")
            raise
    return res


@app.get("/jobs/{job_id}")
def job(job_id: int, user: dict = Depends(current_user)) -> dict:
    with Session() as s:
        snap = jobs.job_snapshot(s, job_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="job not found")
    return snap


@app.post("/jobs/{job_id}/notify")
def enable_job_notify(job_id: int, user: dict = Depends(current_user)) -> dict:
    """Opt in to the completion email for an already-running scrape (the "email it
    to me" button on the loading screen). The worker reads ``notify_email`` when the
    job finishes, so this works any time before completion."""
    with Session() as s:
        job = s.get(store.Job, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        if job.status in ("done", "error", "cancelled"):
            return {"status": job.status, "updated": False}  # too late / nothing to do
        job.notify_email = user["email"]
        s.commit()
        return {"status": job.status, "updated": True}


@app.get("/jobs/{job_id}/stream")
async def job_stream(job_id: int, access_token: str = Query(default="")) -> EventSourceResponse:
    # EventSource can't send Authorization headers, so the SSE token arrives as a
    # query param. Validated the same way as the Bearer header.
    _decode(access_token)

    async def gen():
        conn = jobs.redis_conn()
        with Session() as s:
            snap = jobs.job_snapshot(s, job_id)
        if snap is None:
            yield {"event": "error", "data": json.dumps({"message": "job not found"})}
            return
        yield {"event": "snapshot", "data": json.dumps(snap)}
        if snap["status"] in ("done", "error", "cancelled"):
            yield {"event": snap["status"], "data": json.dumps(snap)}
            return

        pubsub = conn.pubsub()
        pubsub.subscribe(jobs.channel(job_id))
        try:
            while True:
                msg = await asyncio.to_thread(
                    pubsub.get_message, timeout=1.0, ignore_subscribe_messages=True
                )
                if msg is None:
                    yield {"event": "ping", "data": "{}"}  # heartbeat / disconnect check
                    continue
                data = msg["data"]
                if isinstance(data, bytes):
                    data = data.decode()
                event = json.loads(data)
                phase = event.get("phase", "progress")
                yield {"event": phase, "data": data}
                if phase in ("done", "error"):
                    break
        finally:
            pubsub.close()

    return EventSourceResponse(gen())


# ---- profile + report -----------------------------------------------------


@app.get("/advocates/{advocate_id}/profile")
def advocate_profile(
    advocate_id: int,
    state_code: str = Query(default=""),
    dist_code: str = Query(default=""),
    district_name: str = Query(default=""),
    user: dict = Depends(current_user),
) -> dict:
    with Session() as s:
        adv = s.get(Advocate, advocate_id)
        if adv is None:
            raise HTTPException(status_code=404, detail="advocate not found")
        return profile_data.build_profile(
            s, adv.name, state_code=state_code, dist_code=dist_code, district_name=district_name,
        )


@app.get("/advocates/{advocate_id}/report.html", response_class=HTMLResponse)
def advocate_report(advocate_id: int, user: dict = Depends(current_user)) -> HTMLResponse:
    # Fetched by the frontend with the Bearer header (then printed from a hidden
    # iframe), so the standard header auth applies — no query-param token needed.
    with Session() as s:
        adv = s.get(Advocate, advocate_id)
        if adv is None:
            raise HTTPException(status_code=404, detail="advocate not found")
        html = report_html.render_advocate_summary(s, adv.name, ai_text=adv.ai_summary or "")
    return HTMLResponse(content=html)


@app.on_event("startup")
def _startup() -> None:
    store.init_db()
