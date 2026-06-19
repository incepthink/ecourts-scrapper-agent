# Advocate Profiles — frontend (Next.js)

Next.js (App Router) UI for the eCourts advocate-profiles product. Users sign in
with Google, pick a state + district, search an advocate, and see their full case
portfolio. Cold (uncached) searches stream live scrape progress over SSE.

It talks to the FastAPI backend in this repo (`src/api.py`). Auth: NextAuth issues
a session; `/api/token` mints a short-lived HS256 JWT (signed with
`BACKEND_JWT_SECRET`) that the backend verifies.

## Setup

```bash
cd web
cp .env.local.example .env.local   # fill in Google OAuth + secrets
npm install
npm run dev                        # http://localhost:3000
```

Required env (`.env.local`):
- `NEXT_PUBLIC_API_URL` — backend base URL (e.g. `http://localhost:8000`).
- `NEXTAUTH_URL`, `NEXTAUTH_SECRET` — NextAuth basics.
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` — Google OAuth credentials
  (authorized redirect URI: `http://localhost:3000/api/auth/callback/google`).
- `BACKEND_JWT_SECRET` — **must match** the FastAPI side.

## Backend (separate process)

```bash
# from repo root
cp .env.example .env               # set BACKEND_JWT_SECRET (same value), REDIS_URL, OPENAI_API_KEY
PYTHONPATH=src uvicorn api:app --reload --port 8000     # API
PYTHONPATH=src rq worker scrapes                        # scrape worker (needs Redis)
# Windows worker (no fork): PYTHONPATH=src rq worker -w rq.worker.SimpleWorker scrapes
```

Redis is required for search/scrape; a local Redis (e.g. via Docker
`docker run -p 6379:6379 redis`) works.

## Deploy

- Frontend → Vercel (set the same env vars; `NEXTAUTH_URL` = your Vercel URL).
- Backend (API + worker + Postgres + Redis) → Render via `../render.yaml`.
