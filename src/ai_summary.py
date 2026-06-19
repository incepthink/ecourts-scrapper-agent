"""AI-written narrative profile for an advocate, via OpenAI.

Mirrors the call shape of the sibling `ai-agent-appointment-booking` project
(`client.chat.completions.create(model, messages, temperature=0.3)` with graceful
fallback): on a missing key, a disabled flag, or any API error this returns
``None`` so the advocate summary still renders without the AI section.

The numbers (won/lost/total/courts) are computed deterministically by the caller
and passed in — the model only narrates them, it does not count.
"""

from __future__ import annotations

import json
import logging

import config

logger = logging.getLogger(__name__)

# Cap the per-case detail fed to the model so token use stays bounded on
# advocates with very large portfolios; aggregate counts in `stats` still cover
# the whole portfolio.
MAX_CASE_DIGESTS = 60

_SYSTEM_PROMPT = (
    "You are a legal analyst writing a factual profile of an Indian advocate from "
    "public eCourts district-court records. Your reader is a prospective client "
    "deciding whether to engage this advocate for a specific matter, so write to "
    "help that decision. You are given pre-computed aggregate statistics, "
    "deterministic breakdowns (case-type mix, courts, active years, frequent "
    "co-advocates), and a sample of the advocate's cases. "
    "Write a clear narrative of 4-6 short paragraphs that foregrounds, in roughly "
    "this order: (1) the advocate's primary practice areas / case-type "
    "specialisation and what kinds of matters they handle; (2) the courts and "
    "jurisdiction where they appear (and the judges, if telling); (3) depth of "
    "experience — case volume and the span of years active, and how recently they "
    "have been active; (4) current workload — the balance of pending vs disposed "
    "matters; (5) observable outcome patterns; and (6) a few notable or "
    "representative cases. Where useful, name concrete case numbers, case types, "
    "and courts from the data so the reader can gauge fit for their own matter. "
    "Rules: rely only on the data provided — never invent cases, outcomes, names, "
    "or numbers, and do not contradict the supplied statistics. State clearly that "
    "outcomes are derived from each case's 'Nature of Disposal', which reflects the "
    "case result and not necessarily a win for this advocate (they may represent "
    "either the petitioner or the respondent), and that coverage is limited to the "
    "configured district's public records. Be measured; do not overclaim a 'win "
    "rate' or guarantee suitability. Output plain text only (no markdown headings "
    "or tables)."
)


# Lazily constructed so importing this module never requires the key / SDK.
_client = None


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI  # imported lazily so the dep is optional

        _client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _client


def generate_advocate_summary(
    advocate_name: str,
    stats: dict,
    case_digests: list[dict],
    *,
    aggregates: dict | None = None,
    district: str | None = None,
) -> str | None:
    """Return an AI narrative for one advocate, or ``None`` if unavailable.

    ``stats`` is the deterministic aggregate dict, ``case_digests`` is a list of
    compact per-case dicts, and ``aggregates`` holds richer deterministic
    breakdowns (case-type mix, courts, active years, top co-advocates) — all
    produced by ``report_html``. Any failure — disabled flag, missing key,
    network/API error — degrades to ``None``.
    """
    if not config.AI_SUMMARY_ENABLED:
        logger.info("AI summary disabled (ECOURTS_AI_SUMMARY=0); skipping")
        return None
    if not config.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set; skipping AI summary")
        return None
    if not case_digests:
        return None

    payload = {
        "advocate_name": advocate_name,
        "district": district or config.DISTRICT_NAME,
        "statistics": stats,
        "breakdowns": aggregates or {},
        "cases_shown": min(len(case_digests), MAX_CASE_DIGESTS),
        "total_cases": stats.get("total", len(case_digests)),
        "cases": case_digests[:MAX_CASE_DIGESTS],
    }
    user_msg = (
        "Write the advocate profile from this data (JSON):\n\n"
        + json.dumps(payload, ensure_ascii=False, default=str)
    )

    try:
        completion = _get_client().chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
        )
    except Exception as e:  # noqa: BLE001 - degrade gracefully, never break the report
        logger.warning("OpenAI call failed; rendering summary without AI: %s", e)
        return None

    text = (completion.choices[0].message.content or "").strip()
    if not text:
        return None
    logger.info("AI summary generated for %r (model=%s)", advocate_name, config.OPENAI_MODEL)
    return text
