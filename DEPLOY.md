# Deployment

Frontend (`web/`) on **Vercel**; backend (API + worker + Redis + Postgres) on a
single **AWS VM** via Docker Compose, with HTTPS terminated by Caddy on a
subdomain of your domain.

```
Browser ──► Vercel (Next.js, NextAuth/Google)
              │  mints short-lived HS256 JWT (BACKEND_JWT_SECRET)
              ▼
        https://api.<yourdomain>  ──►  Caddy ──► api (uvicorn :8000)
                                                    │           ▲ SSE progress
                                                    ▼           │
                                              Redis (queue + pub/sub)
                                                    ▼
                                              worker (rq) ──► Postgres
```

## 1. Provision the VM (AWS Lightsail or EC2)

- Ubuntu 22.04, **4 GB RAM / 2 vCPU** (onnxruntime CAPTCHA OCR + Postgres + Redis).
- Attach a **static IP** (Lightsail static IP / EC2 Elastic IP).
- Open ports **22, 80, 443** only. Leave 5432/6379 closed (internal to Compose).
- Install Docker + Compose plugin:
  ```bash
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker $USER && newgrp docker
  ```

## 2. DNS (GoDaddy)

Add an **A record**: host `api` → the VM's static IP.

## 3. Backend up

```bash
git clone <repo> ecourts-scraper && cd ecourts-scraper
cp .env.deploy.example .env
# edit .env: set API_DOMAIN, POSTGRES_PASSWORD (+ matching ECOURTS_DB_URL),
# BACKEND_JWT_SECRET, FRONTEND_ORIGIN, OPENAI_API_KEY
docker compose up -d --build
docker compose ps                 # all healthy
curl localhost:8000/health        # {"ok":true}
curl https://api.<yourdomain>/health   # once DNS resolves + Caddy issues the cert
```

## 4. Frontend on Vercel

New project, **Root Directory = `web/`**. Env vars (Production):

| Var | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | `https://api.<yourdomain>` |
| `NEXTAUTH_URL` | the Vercel URL (or custom app domain) |
| `NEXTAUTH_SECRET` | random |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | from Google console |
| `BACKEND_JWT_SECRET` | **same value as the VM `.env`** |

## 5. Google OAuth

In the OAuth client add: JS origin `https://<vercel-url>` and redirect URI
`https://<vercel-url>/api/auth/callback/google`.

## 6. Verify end-to-end

1. `https://api.<yourdomain>/health` → `{"ok":true}` over HTTPS.
2. Unauthenticated `POST /search` → 401.
3. Log in with Google on the Vercel site.
4. State/district dropdowns populate.
5. Search an uncached advocate → live SSE progress → profile renders
   (`docker compose logs -f worker` shows the job). Re-search → instant cache hit.

## Operations

- **Logs:** `docker compose logs -f api worker`
- **Update:** `git pull && docker compose up -d --build`
- **Backups (no managed DB here):** schedule a dump, e.g. daily cron —
  ```bash
  docker compose exec -T postgres pg_dump -U ecourts ecourts | gzip > backup-$(date +%F).sql.gz
  ```
