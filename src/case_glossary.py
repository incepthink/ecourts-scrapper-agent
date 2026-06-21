"""Plain-English decode of eCourts case-type codes.

The portal stores a case's type as a terse internal abbreviation — ``SS CASES S``,
``Cri.Bail Appln.``, ``PWDVA Appln.``, ``Marriage Petn.`` — which is meaningless to
the layperson the advocate profile is written for. ``decode_case_type`` turns one of
these into a readable label plus a coarse practice-area *category* so every case row,
and the "Practice areas" breakdown, speak in words a prospective client understands.

Pure and dependency-free (just ``re``) so it imports cleanly in the API process.
The matching is deliberately fuzzy: codes arrive in many spellings/casings
(``SS CASES S``, ``Ss case SS``, ``Summons cases SS``) so we normalize then match an
*ordered* list of keyword rules, first hit wins.
"""

from __future__ import annotations

import re

# Coarse practice-area buckets surfaced in the UI. Keep this list small and
# client-legible; the frontend color-keys pills off these exact strings.
CRIMINAL = "Criminal"
BAIL = "Bail"
CIVIL = "Civil"
FAMILY = "Family"
OTHER = "Other"

CATEGORIES = (CRIMINAL, BAIL, CIVIL, FAMILY, OTHER)

# Ordered (keyword, label, category) rules — first match wins, so more specific
# patterns (bail, domestic violence) must precede broader ones (criminal, misc).
# Keywords are tested against the normalized type (lowercased, punctuation -> space).
_RULES: list[tuple[str, str, str]] = [
    ("bail", "Bail application", BAIL),
    ("anticipatory", "Anticipatory bail application", BAIL),
    ("pwdva", "Domestic violence petition (PWDVA)", FAMILY),
    ("domestic violence", "Domestic violence petition (PWDVA)", FAMILY),
    ("d v case", "Domestic violence petition (PWDVA)", FAMILY),
    ("marriage", "Matrimonial petition", FAMILY),
    ("matri", "Matrimonial petition", FAMILY),
    ("divorce", "Divorce petition", FAMILY),
    ("hma", "Matrimonial petition", FAMILY),
    ("maintenance", "Maintenance petition", FAMILY),
    ("guardian", "Guardianship petition", FAMILY),
    ("cri m a", "Criminal misc. application", CRIMINAL),
    ("criminal misc", "Criminal misc. application", CRIMINAL),
    ("cri appeal", "Criminal appeal", CRIMINAL),
    ("criminal appeal", "Criminal appeal", CRIMINAL),
    ("cri revision", "Criminal revision", CRIMINAL),
    ("ss case", "Summary criminal case", CRIMINAL),
    ("summons", "Summary criminal case", CRIMINAL),
    ("summary", "Summary criminal case", CRIMINAL),
    ("warrant", "Warrant case", CRIMINAL),
    ("notice", "Notice case", CRIMINAL),
    ("complaint", "Criminal complaint", CRIMINAL),
    ("c c", "Criminal case", CRIMINAL),
    ("r c a", "Civil appeal", CIVIL),
    ("civil appeal", "Civil appeal", CIVIL),
    ("civil m a", "Civil misc. application", CIVIL),
    ("civil misc", "Civil misc. application", CIVIL),
    ("rent", "Rent matter", CIVIL),
    ("r a e", "Rent matter", CIVIL),
    ("suit", "Civil suit", CIVIL),
    ("execution", "Execution petition", CIVIL),
    ("darkhast", "Execution petition", CIVIL),
    ("special civil", "Civil suit", CIVIL),
    ("regular civil", "Civil suit", CIVIL),
    ("misc", "Miscellaneous case", OTHER),
]


def _normalize(case_type: str) -> str:
    """Lowercase, drop punctuation to spaces, collapse runs of whitespace.

    ``Cri.Bail Appln.`` -> ``cri bail appln``; ``SS CASES S`` -> ``ss cases s``.
    Keeps single letters intact so abbreviations like ``c c`` / ``r c a`` match.
    """
    low = re.sub(r"[^a-z0-9]+", " ", (case_type or "").lower())
    return re.sub(r"\s+", " ", low).strip()


def _title(raw: str) -> str:
    """Best-effort readable fallback label for an unrecognized code."""
    cleaned = re.sub(r"\s+", " ", (raw or "").strip())
    return cleaned.title() if cleaned else "Court case"


def decode_case_type(case_type: str) -> dict:
    """Return ``{"label": <plain English>, "category": <coarse bucket>}``.

    Never blank and never raises: an unrecognized code falls back to a
    title-cased version of itself under the ``Other`` category.
    """
    norm = _normalize(case_type)
    for keyword, label, category in _RULES:
        if keyword in norm:
            return {"label": label, "category": category}
    return {"label": _title(case_type), "category": OTHER}
