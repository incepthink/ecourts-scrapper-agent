"""Advocate profile data layer — the single source of truth.

This module owns all the *data* work for an advocate profile: which advocate
nodes are the same person, loading their cases (optionally scoped to one
state+district), the deterministic outcome/disposition buckets, the portfolio
stats, and the richer aggregates fed to the AI summary.

Two consumers share it, so the numbers can never disagree:
  * ``report_html.py`` renders the self-contained HTML dossier from these helpers.
  * ``api.py`` serves ``build_profile()`` as JSON to the Next.js frontend (live
    view + final profile).

Kept dependency-light (only store/config/ai_summary) so it imports cleanly in the
API process without pulling in the scraper/bharat-courts stack.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime

from sqlalchemy import select

import ai_summary
import config
from store import Advocate, Case, CaseAdvocate, Order, normalize_name


# ---- outcome / disposition buckets ----------------------------------------


def _outcome_class(nature_of_disposal: str) -> str:
    """Bucket a nature-of-disposal string into a coarse win/loss signal."""
    low = (nature_of_disposal or "").lower()
    if any(w in low for w in ("allow", "grant", "decree", "in favour")):
        return "won"
    if any(w in low for w in ("reject", "dismiss", "refus", "against")):
        return "lost"
    return "other"


_OUTCOME_LABEL = {
    "won": "Allowed / Granted",
    "lost": "Rejected / Dismissed",
    "other": "Other / Unknown",
}


def _disposition(case) -> str:
    """Coarse disposed/pending label for a case.

    The raw ``case_status`` string is unreliable for pending cases — the eCourts
    history page omits the "Case Status" row when a case is pending, so the field
    is empty. Instead derive it from the disposal fields, which are only populated
    once a case is disposed: ``Disposed`` if any disposal signal is present,
    ``Pending`` once the case has been enriched without one, else ``Unknown``.
    """
    if (case.nature_of_disposal or case.decision_date
            or "dispos" in (case.case_status or "").lower()):
        return "Disposed"
    if not case.history_fetched:
        return "Unknown"
    return "Pending"


# ---- "same person" matching -----------------------------------------------

# Leading titles dropped before comparing names, so "ADV MARIAM TANVEER NIZAM"
# is judged by its actual identity ("MARIAM TANVEER NIZAM").
_HONORIFICS = {"ADV", "ADVOCATE", "MR", "MRS", "MS", "SMT", "SHRI", "SRI", "KUM", "DR", "M S"}
# Tokens that mark a genuine joint/combined filing led by the searched advocate.
_JOIN_WORDS = {"AND", "ALIAS"}


def _name_tokens(name_norm: str) -> list[str]:
    """Significant tokens of a normalized name, with any leading honorifics dropped."""
    toks = name_norm.split()
    while toks and toks[0] in _HONORIFICS:
        toks.pop(0)
    return toks


def _matching_advocates(session, advocate_name: str) -> list[Advocate]:
    """Advocate nodes that are genuinely the *same person* as ``advocate_name``.

    The searched name must be the *leading* identity of a candidate — its tokens
    (after dropping honorifics like ``ADV``) must equal, or be a prefix of, the
    candidate's tokens. So for ``TANVEER NIZAM``:

    * ``TANVEER NIZAM`` → exact → kept (the canonical record).
    * ``MARIAM TANVEER NIZAM`` → searched name is a *suffix*, not a prefix →
      dropped (a different person — e.g. a spouse who shares a surname).
    * ``ADV MARIAM TANVEER NIZAM AND AKHANDPRATAP SINGH`` → after dropping ``ADV``
      it starts with ``MARIAM``, not ``TANVEER`` → dropped (not this advocate).

    A prefix match is only folded in when the very next token is a join word
    (``AND``/``ALIAS``), i.e. a combined entry this advocate genuinely leads
    (``TANVEER NIZAM AND …``) — not a longer different name (``TANVEER NIZAM KHAN``).
    """
    norm = normalize_name(advocate_name)
    if not norm:
        return []
    want = _name_tokens(norm)
    if not want:
        return []
    # Cheap SQL prefilter; the precise person test runs in Python on the small
    # candidate set.
    candidates = session.scalars(
        select(Advocate).where(Advocate.name_norm.like(f"%{norm}%"))
    ).all()

    def _is_same_person(cand: Advocate) -> bool:
        have = _name_tokens(cand.name_norm)
        if have == want:
            return True
        if have[: len(want)] == want and len(have) > len(want):
            return have[len(want)] in _JOIN_WORDS
        return False

    return [a for a in candidates if _is_same_person(a)]


# ---- case loading + aggregates --------------------------------------------


def _load_cases(
    session,
    advocate_ids: list[int],
    *,
    state_code: str = "",
    dist_code: str = "",
) -> list[dict]:
    """All cases linked to any of the advocate ids, each with its orders +
    co-advocates. ``advocate_ids`` are the variant spellings folded into one
    summary; a case linking to several of them is returned once.

    When ``state_code``/``dist_code`` are given, scope the portfolio to that one
    district (the same lawyer can appear in several districts, and the product
    scrapes/searches one district at a time)."""
    stmt = (
        select(Case)
        .join(CaseAdvocate, CaseAdvocate.case_id == Case.id)
        .where(CaseAdvocate.advocate_id.in_(advocate_ids))
    )
    if state_code:
        stmt = stmt.where(Case.state_code == state_code)
    if dist_code:
        stmt = stmt.where(Case.dist_code == dist_code)
    cases = session.scalars(
        stmt.distinct().order_by(Case.decision_date.desc(), Case.id.desc())
    ).all()

    out: list[dict] = []
    for c in cases:
        co_advocates = session.scalars(
            select(Advocate.name)
            .join(CaseAdvocate, CaseAdvocate.advocate_id == Advocate.id)
            .where(CaseAdvocate.case_id == c.id, Advocate.id.not_in(advocate_ids))
            .distinct()
            .order_by(Advocate.name)
        ).all()
        orders = session.scalars(
            select(Order).where(Order.case_id == c.id).order_by(Order.order_number)
        ).all()
        out.append({"case": c, "co_advocates": list(co_advocates), "orders": list(orders)})
    return out


def _compute_stats(cases: list[dict]) -> dict:
    """Deterministic portfolio aggregates. Single source of truth for both the
    stat cards and the AI summary payload — the model never recomputes these."""
    outcomes: dict[str, int] = {"won": 0, "lost": 0, "other": 0}
    for x in cases:
        outcomes[_outcome_class(x["case"].nature_of_disposal)] += 1
    establishments = {x["case"].establishment for x in cases if x["case"].establishment}
    return {
        "total": len(cases),
        "disposed": sum(1 for x in cases if _disposition(x["case"]) == "Disposed"),
        "pending": sum(1 for x in cases if _disposition(x["case"]) == "Pending"),
        "allowed_granted": outcomes["won"],
        "rejected_dismissed": outcomes["lost"],
        "other_unknown": outcomes["other"],
        "courts_establishments": len(establishments),
    }


def _case_year(case) -> int | None:
    """Best-effort 4-digit year for a case: prefer the decision date, fall back to
    the registration year. Both are free-form portal strings, so extract a year
    with a regex rather than parsing a date."""
    for src in (case.decision_date, case.year):
        m = re.search(r"\b(19|20)\d{2}\b", src or "")
        if m:
            return int(m.group(0))
    return None


def _ai_aggregates(cases: list[dict]) -> dict:
    """Richer, fully deterministic breakdowns for the AI payload so the model can
    speak to specialisation, jurisdiction and recency without inventing anything.
    Computed from the already-loaded ``cases`` — no extra DB work."""
    case_types = Counter(
        x["case"].case_type.strip() for x in cases if (x["case"].case_type or "").strip()
    )
    courts = Counter(
        x["case"].establishment.strip()
        for x in cases
        if (x["case"].establishment or "").strip()
    )
    co_adv = Counter(
        name for x in cases for name in x["co_advocates"] if (name or "").strip()
    )
    years = [y for y in (_case_year(x["case"]) for x in cases) if y]
    recent_cutoff = datetime.now().year - 3
    return {
        "case_type_counts": dict(case_types.most_common(8)),
        "court_counts": dict(courts.most_common(8)),
        "top_co_advocates": dict(co_adv.most_common(8)),
        "years_active": {
            "earliest": min(years) if years else None,
            "latest": max(years) if years else None,
            "cases_in_last_3_years": sum(1 for y in years if y >= recent_cutoff),
            "cases_with_known_year": len(years),
        },
    }


def _case_digests(cases: list[dict]) -> list[dict]:
    """Compact per-case dicts for the AI payload (ordered most-recent first, as
    loaded by ``_load_cases``)."""
    out: list[dict] = []
    for x in cases:
        c = x["case"]
        out.append(
            {
                "case_number": c.case_number_full,
                "case_type": c.case_type,
                "petitioner": c.petitioner,
                "respondent": c.respondent,
                "court": c.establishment,
                "judge": c.judge,
                "status": _disposition(c),
                "nature_of_disposal": c.nature_of_disposal,
                "outcome_class": _outcome_class(c.nature_of_disposal),
                "decision_date": c.decision_date,
                "co_advocates": x["co_advocates"],
            }
        )
    return out


# ---- JSON profile (what the API serves) -----------------------------------


def _co_advocate_counts(cases: list[dict], top: int = 12) -> list[dict]:
    """Frequent co-advocates with their shared-case counts, most first."""
    counter = Counter(
        name for x in cases for name in x["co_advocates"] if (name or "").strip()
    )
    return [{"name": n, "count": k} for n, k in counter.most_common(top)]


def _case_to_dict(x: dict) -> dict:
    """Fully serializable view of one loaded case (no ORM objects, no PDF files
    — order metadata only, since the live product doesn't store PDFs)."""
    c = x["case"]
    oc = _outcome_class(c.nature_of_disposal)
    return {
        "cnr": c.cnr,
        "case_number": c.case_number_full,
        "case_type": c.case_type,
        "year": c.year,
        "petitioner": c.petitioner,
        "respondent": c.respondent,
        "court": c.establishment,
        "judge": c.judge,
        "status": _disposition(c),
        "nature_of_disposal": c.nature_of_disposal,
        "outcome_class": oc,
        "outcome_label": _OUTCOME_LABEL[oc],
        "decision_date": c.decision_date,
        "filing_date": c.filing_date,
        "co_advocates": x["co_advocates"],
        "orders": [
            {"order_number": o.order_number, "order_date": o.order_date, "label": o.label}
            for o in x["orders"]
        ],
    }


def _canonical_match(matches: list[Advocate], advocate_name: str) -> Advocate:
    """The advocate row to treat as canonical for the searched name — the exact
    normalized match if present, else the first (shortest-name) candidate."""
    norm = normalize_name(advocate_name)
    for a in matches:
        if a.name_norm == norm:
            return a
    return matches[0]


def _cached_ai_text(matches: list[Advocate], advocate_name: str) -> str:
    """Reuse a previously generated AI narrative if one is stored on any matched
    advocate node (prefer the canonical record)."""
    canonical = _canonical_match(matches, advocate_name)
    if (canonical.ai_summary or "").strip():
        return canonical.ai_summary
    for a in matches:
        if (a.ai_summary or "").strip():
            return a.ai_summary
    return ""


def empty_stats() -> dict:
    return {
        "total": 0, "disposed": 0, "pending": 0, "allowed_granted": 0,
        "rejected_dismissed": 0, "other_unknown": 0, "courts_establishments": 0,
    }


def build_profile(
    session,
    advocate_name: str,
    *,
    state_code: str = "",
    dist_code: str = "",
    district_name: str = "",
    generate_ai: bool = False,
) -> dict:
    """Assemble the full, JSON-serializable profile for one advocate.

    By default the AI narrative is the cached one stored on the advocate (cheap,
    no OpenAI call) — set ``generate_ai=True`` (the worker does, once per scrape)
    to (re)generate it. Returns ``{"found": False, ...}`` with empty stats when no
    matching advocate exists yet (the frontend then triggers a scrape)."""
    district_label = district_name or config.DISTRICT_NAME
    matches = _matching_advocates(session, advocate_name)
    if not matches:
        return {
            "found": False,
            "name": advocate_name,
            "name_variants": [],
            "advocate_id": None,
            "state_code": state_code,
            "dist_code": dist_code,
            "district": district_label,
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "stats": empty_stats(),
            "ai_summary": "",
            "aggregates": _ai_aggregates([]),
            "cases": [],
            "co_advocates": [],
        }

    cases = _load_cases(session, [a.id for a in matches], state_code=state_code, dist_code=dist_code)
    stats = _compute_stats(cases)
    aggregates = _ai_aggregates(cases)
    if generate_ai:
        ai_text = ai_summary.generate_advocate_summary(
            advocate_name, stats, _case_digests(cases),
            aggregates=aggregates, district=district_label,
        ) or ""
    else:
        ai_text = _cached_ai_text(matches, advocate_name)

    return {
        "found": True,
        "name": advocate_name,
        "name_variants": [a.name for a in matches],
        "advocate_id": _canonical_match(matches, advocate_name).id,
        "state_code": state_code,
        "dist_code": dist_code,
        "district": district_label,
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "stats": stats,
        "ai_summary": ai_text,
        "aggregates": aggregates,
        "cases": [_case_to_dict(x) for x in cases],
        "co_advocates": _co_advocate_counts(cases),
    }
