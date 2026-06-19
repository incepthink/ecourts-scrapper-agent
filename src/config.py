"""Project configuration.

SQLite by default (zero-config pilot). To use MySQL instead, set:
    ECOURTS_DB_URL=mysql+pymysql://user:password@localhost:3306/ecourts
Nothing else changes — the models are SQLAlchemy and backend-agnostic.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
PDF_DIR = DATA_DIR / "pdfs"
HTML_DIR = DATA_DIR / "html"
DATA_DIR.mkdir(parents=True, exist_ok=True)
PDF_DIR.mkdir(parents=True, exist_ok=True)
HTML_DIR.mkdir(parents=True, exist_ok=True)

DB_URL = os.environ.get("ECOURTS_DB_URL", f"sqlite:///{(DATA_DIR / 'ecourts.db').as_posix()}")
# Managed Postgres (Render/Heroku) hands out a bare ``postgres://`` / ``postgresql://``
# URL; SQLAlchemy 2.0 needs an explicit driver. Normalize to psycopg (v3).
if DB_URL.startswith("postgres://"):
    DB_URL = "postgresql+psycopg://" + DB_URL[len("postgres://"):]
elif DB_URL.startswith("postgresql://"):
    DB_URL = "postgresql+psycopg://" + DB_URL[len("postgresql://"):]

# Target district. The scraper resolves DISTRICT_NAME -> district code live
# against the portal dropdown (bharat-courts' hardcoded state map is stale),
# then searches *every* court complex in that district.
# DISTRICT_NAME is matched case-insensitively as a substring, so it must be
# specific enough to match exactly one district (e.g. "Mumbai" alone is
# ambiguous — it matches 4 Mumbai districts).
STATE_CODE = "1"                      # Maharashtra
DISTRICT_NAME = "Mumbai CMM Courts"   # Mumbai Chief Metropolitan Magistrate courts (dist code 23)
# Pending | Disposed | Both. "Both" so a search captures pending *and* disposed
# cases — a "Disposed"-only query silently drops pending cases from the portal
# (the row never reaches the parser/DB), making them impossible to recover later.
DEFAULT_STATUS = "Both"

# By default a run emits only the DB + the one consolidated advocate-summary HTML.
# Set ECOURTS_SAVE_RAW_HTML=1 to also keep the raw per-complex search HTML and
# per-case history HTML (useful for debugging / re-parsing without re-scraping).
SAVE_RAW_HTML = os.environ.get("ECOURTS_SAVE_RAW_HTML", "") not in ("", "0", "false")

# ---- AI summary (OpenAI) --------------------------------------------------
# The advocate summary HTML can include an AI-written narrative profile.
# Credentials/model mirror the sibling `ai-agent-appointment-booking` project
# (OPENAI_API_KEY / OPENAI_MODEL=gpt-4o-mini). We load a local `.env` first,
# then fall back to that project's `.env` so the existing key is reused without
# copying it. `load_dotenv` never overrides an already-set env var, so an
# explicit env var or a local `.env` always wins over the shared fallback.
load_dotenv(PROJECT_ROOT / ".env")
_SHARED_ENV = os.environ.get(
    "OPENAI_ENV_FILE",
    str(PROJECT_ROOT.parent / "ai-agent-appointment-booking" / ".env"),
)
if os.path.exists(_SHARED_ENV):
    load_dotenv(_SHARED_ENV)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
# Set ECOURTS_AI_SUMMARY=0 to skip the OpenAI call (offline / free runs); the
# report still renders, just without the AI profile section.
AI_SUMMARY_ENABLED = os.environ.get("ECOURTS_AI_SUMMARY", "1") not in ("", "0", "false")
