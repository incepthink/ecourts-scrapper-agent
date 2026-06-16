"""Render a single self-contained HTML summary for one advocate.

Everything the scraper learns about an advocate already lives in the DB
(advocates / cases / case_advocates / orders). This module aggregates it into
*one* human-readable page — their full case portfolio, outcomes, courts/judges,
orders (linked to the downloaded PDFs) and frequent co-advocates — replacing the
pile of per-complex / per-case intermediate HTML files.

Kept dependency-light (no network / bharat-courts imports) so it runs standalone:
    python src/report_html.py "Tanveer Nizam"
"""

from __future__ import annotations

import html
import os
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

import ai_summary
import config
from store import Advocate, Case, CaseAdvocate, Order, Session, normalize_name


def _slug(text: str) -> str:
    """Filesystem-safe slug (matches pipeline._slug)."""
    s = re.sub(r"[^A-Za-z0-9]+", "_", (text or "").strip().lower()).strip("_")
    return s or "x"


def _e(value) -> str:
    """HTML-escape any value (None -> '')."""
    return html.escape(str(value) if value is not None else "")


def _outcome_class(nature_of_disposal: str) -> str:
    """Bucket a nature-of-disposal string into a coarse win/loss signal."""
    low = (nature_of_disposal or "").lower()
    if any(w in low for w in ("allow", "grant", "decree", "in favour")):
        return "won"
    if any(w in low for w in ("reject", "dismiss", "refus", "against")):
        return "lost"
    return "other"


_OUTCOME_LABEL = {"won": "Allowed / Granted", "lost": "Rejected / Dismissed", "other": "Other / Unknown"}


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


def _pdf_href(pdf_local_path: str) -> str | None:
    """A link relative to DATA_DIR (where the summary lives), or None."""
    if not pdf_local_path:
        return None
    try:
        rel = os.path.relpath(pdf_local_path, config.DATA_DIR)
    except ValueError:  # e.g. different drive on Windows
        rel = pdf_local_path
    return rel.replace(os.sep, "/")


# ---- data assembly --------------------------------------------------------


def _matching_advocates(session, advocate_name: str) -> list[Advocate]:
    """Every advocate node whose name contains ``advocate_name`` as a whole-word
    phrase — so searching ``MARIAM TANVEER NIZAM`` also folds in a combined entry
    like ``ADV MARIAM TANVEER NIZAM AND AKHANDPRATAP SINGH`` (but ``NIZAM`` is not
    matched inside ``NIZAMUDDIN``).

    Normalized names are uppercase, single-spaced and punctuation-stripped (see
    ``store.normalize_name``), so space-padding both sides makes a plain ``in``
    check a reliable word-boundary test without regex.
    """
    norm = normalize_name(advocate_name)
    if not norm:
        return []
    candidates = session.scalars(
        select(Advocate).where(Advocate.name_norm.like(f"%{norm}%"))
    ).all()
    needle = f" {norm} "
    return [a for a in candidates if needle in f" {a.name_norm} "]


def _load_cases(session, advocate_ids: list[int]) -> list[dict]:
    """All cases linked to any of the advocate ids, each with its orders +
    co-advocates. ``advocate_ids`` are the variant spellings folded into one
    summary; a case linking to several of them is returned once."""
    cases = session.scalars(
        select(Case)
        .join(CaseAdvocate, CaseAdvocate.case_id == Case.id)
        .where(CaseAdvocate.advocate_id.in_(advocate_ids))
        .distinct()
        .order_by(Case.decision_date.desc(), Case.id.desc())
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
        out.append({"case": c, "co_advocates": co_advocates, "orders": orders})
    return out


# ---- rendering ------------------------------------------------------------

_STYLE = """
* { box-sizing: border-box; }
body { font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 0;
       color: #1b1f24; background: #f6f8fa; }
.wrap { max-width: 1180px; margin: 0 auto; padding: 24px; }
header h1 { margin: 0 0 4px; font-size: 26px; }
header .meta { color: #57606a; font-size: 13px; }
.cards { display: flex; flex-wrap: wrap; gap: 12px; margin: 20px 0; }
.card { background: #fff; border: 1px solid #d0d7de; border-radius: 10px;
        padding: 14px 18px; min-width: 130px; }
.card .n { font-size: 24px; font-weight: 700; }
.card .l { font-size: 12px; color: #57606a; text-transform: uppercase; letter-spacing: .03em; }
h2 { font-size: 17px; margin: 28px 0 10px; border-bottom: 1px solid #d0d7de; padding-bottom: 6px; }
table { width: 100%; border-collapse: collapse; background: #fff;
        border: 1px solid #d0d7de; border-radius: 10px; overflow: hidden; font-size: 13px; }
th, td { text-align: left; padding: 9px 11px; border-bottom: 1px solid #eaeef2; vertical-align: top; }
th { background: #f6f8fa; font-weight: 600; white-space: nowrap; }
tr:last-child td { border-bottom: 0; }
.parties { min-width: 220px; }
.vs { color: #8c959f; font-style: italic; }
.tag { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 600; }
.tag.won { background: #dafbe1; color: #1a7f37; }
.tag.lost { background: #ffebe9; color: #cf222e; }
.tag.other { background: #eaeef2; color: #57606a; }
.tag.disposed { background: #ddf4ff; color: #0969da; }
.tag.pending { background: #fff8c5; color: #9a6700; }
.tag.unknown { background: #eaeef2; color: #57606a; }
.raw-status { display: block; color: #8c959f; font-size: 11px; margin-top: 3px; }
.orders a { display: inline-block; margin: 1px 0; color: #0969da; text-decoration: none; }
.orders a:hover { text-decoration: underline; }
.orders .nopdf { color: #57606a; }
.co { color: #57606a; font-size: 12px; }
.muted { color: #8c959f; }
footer { color: #8c959f; font-size: 12px; margin: 30px 0 10px; text-align: center; }
.ai { background: #fff; border: 1px solid #d0d7de; border-radius: 10px; padding: 16px 20px; margin: 20px 0; }
.ai h2 { margin: 0 0 8px; border: 0; padding: 0; }
.ai-badge { font-size: 11px; font-weight: 600; color: #6639ba; background: #fbefff;
            border: 1px solid #e7c7ff; border-radius: 999px; padding: 2px 8px;
            vertical-align: middle; margin-left: 6px; }
.ai-body p { margin: 0 0 10px; line-height: 1.55; }
.ai-body p:last-child { margin-bottom: 0; }
.ai-note { color: #8c959f; font-size: 12px; margin: 10px 0 0; }
"""


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


def _stat_cards(stats: dict) -> str:
    cards = [
        ("Total cases", stats["total"]),
        ("Disposed", stats["disposed"]),
        ("Pending", stats["pending"]),
        ("Allowed / Granted", stats["allowed_granted"]),
        ("Rejected / Dismissed", stats["rejected_dismissed"]),
        ("Courts / establishments", stats["courts_establishments"]),
    ]
    return "".join(
        f'<div class="card"><div class="n">{n}</div><div class="l">{_e(label)}</div></div>'
        for label, n in cards
    )


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


def _ai_section(ai_text: str) -> str:
    """Render the AI narrative as a styled section. Splits on blank lines into
    paragraphs and HTML-escapes the model output."""
    paras = []
    for p in re.split(r"\n\s*\n", ai_text.strip()):
        p = p.strip()
        if p:
            paras.append("<p>" + _e(p).replace("\n", "<br>") + "</p>")
    if not paras:
        return ""
    return (
        '<section class="ai">'
        '<h2>AI profile<span class="ai-badge">OpenAI</span></h2>'
        f'<div class="ai-body">{"".join(paras)}</div>'
        '<p class="ai-note">AI-generated from the case data below and may contain '
        "errors. Outcomes reflect each case&rsquo;s nature of disposal, not "
        "necessarily a win for this advocate.</p>"
        "</section>"
    )


def _orders_cell(orders) -> str:
    if not orders:
        return '<span class="muted">—</span>'
    bits = []
    for o in orders:
        label = _e(f"{o.label or 'Order'} ({o.order_date})") if o.order_date else _e(o.label or "Order")
        href = _pdf_href(o.pdf_local_path) if o.downloaded else None
        if href:
            bits.append(f'<a href="{_e(href)}" target="_blank">📄 {label}</a>')
        else:
            bits.append(f'<span class="nopdf">{label}</span>')
    return "<br>".join(bits)


def _cases_table(cases: list[dict]) -> str:
    if not cases:
        return '<p class="muted">No cases found for this advocate in the database.</p>'
    rows = []
    for x in cases:
        c = x["case"]
        oc = _outcome_class(c.nature_of_disposal)
        disposal = (
            f'<span class="tag {oc}">{_e(c.nature_of_disposal)}</span>'
            if c.nature_of_disposal
            else '<span class="muted">—</span>'
        )
        disp = _disposition(c)
        raw = (
            f'<span class="raw-status">{_e(c.case_status)}</span>'
            if c.case_status and c.case_status.lower() != disp.lower()
            else ""
        )
        status = f'<span class="tag {disp.lower()}">{disp}</span>{raw}'
        co = ", ".join(x["co_advocates"]) or "—"
        rows.append(
            "<tr>"
            f"<td>{_e(c.case_number_full)}</td>"
            f'<td class="parties">{_e(c.petitioner)}<br><span class="vs">vs</span><br>{_e(c.respondent)}</td>'
            f"<td>{_e(c.establishment)}</td>"
            f"<td>{_e(c.judge)}</td>"
            f"<td>{status}</td>"
            f"<td>{disposal}</td>"
            f"<td>{_e(c.decision_date) or '—'}</td>"
            f'<td class="co">{_e(co)}</td>'
            f'<td class="orders">{_orders_cell(x["orders"])}</td>'
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>Case number</th><th>Parties</th><th>Court / establishment</th><th>Judge</th>"
        "<th>Status</th><th>Disposal</th><th>Decided</th><th>Co-advocates</th><th>Orders</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def _co_advocate_section(cases: list[dict]) -> str:
    counts: dict[str, int] = {}
    for x in cases:
        for name in x["co_advocates"]:
            counts[name] = counts.get(name, 0) + 1
    if not counts:
        return ""
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    items = "".join(
        f"<tr><td>{_e(name)}</td><td>{n}</td></tr>" for name, n in ordered
    )
    return (
        "<h2>Frequent co-advocates</h2>"
        "<table><thead><tr><th>Advocate</th><th>Shared cases</th></tr></thead>"
        f"<tbody>{items}</tbody></table>"
    )


def render_advocate_summary(session, advocate_name: str) -> str:
    """Return a self-contained HTML page summarizing one advocate."""
    matches = _matching_advocates(session, advocate_name)
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    if not matches:
        body = (
            f"<header><h1>{_e(advocate_name)}</h1>"
            f'<div class="meta">No matching advocate found in the database.</div></header>'
        )
        cases: list[dict] = []
    else:
        cases = _load_cases(session, [a.id for a in matches])
        variants = (
            f" &middot; {len(matches)} name variants" if len(matches) > 1 else ""
        )
        stats = _compute_stats(cases)
        ai_text = ai_summary.generate_advocate_summary(
            advocate_name, stats, _case_digests(cases)
        )
        ai_html = _ai_section(ai_text) if ai_text else ""
        body = (
            f"<header><h1>{_e(advocate_name)}</h1>"
            f'<div class="meta">{_e(config.DISTRICT_NAME)} &middot; '
            f'{len(cases)} case(s){variants} &middot; generated {_e(generated)}</div></header>'
            f'<div class="cards">{_stat_cards(stats)}</div>'
            f"{ai_html}"
            "<h2>Cases</h2>"
            f"{_cases_table(cases)}"
            f"{_co_advocate_section(cases)}"
        )

    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>Advocate summary — {_e(advocate_name)}</title>"
        f"<style>{_STYLE}</style></head><body><div class='wrap'>"
        f"{body}"
        "<footer>Generated by ecourts-scraper from data/ecourts.db</footer>"
        "</div></body></html>"
    )


def write_advocate_summary(advocate_name: str) -> Path:
    """Render and write the summary to data/<slug>_summary.html. Returns its path."""
    with Session() as session:
        out_html = render_advocate_summary(session, advocate_name)
    path = config.DATA_DIR / f"{_slug(advocate_name)}_summary.html"
    path.write_text(out_html, encoding="utf-8")
    return path


def main() -> None:
    import sys

    if len(sys.argv) < 2:
        print('usage: python src/report_html.py "<advocate name>"')
        raise SystemExit(2)
    name = " ".join(sys.argv[1:])
    path = write_advocate_summary(name)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
