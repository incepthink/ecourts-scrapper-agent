"""Collector pipeline: advocate name -> cases -> history -> order PDFs,
persisted to the DB, with self-expanding seed-name harvesting.
"""

from __future__ import annotations

import hashlib
import logging
import re

from sqlalchemy import select

import config
import store
from advocate_search import AdvocateSearchClient
from bharat_courts.districtcourts.parser import parse_complex_value
from parse_advocate import parse_advocate_results
from parse_history import parse_case_history
from store import (
    Case,
    CaseAdvocate,
    Order,
    Session,
    enqueue_seed,
    get_or_create_advocate,
)

logger = logging.getLogger(__name__)


def _slug(text: str) -> str:
    """Filesystem-safe slug for advocate names / court codes."""
    s = re.sub(r"[^A-Za-z0-9]+", "_", (text or "").strip().lower()).strip("_")
    return s or "x"


# ---- court hierarchy resolution (no CAPTCHA) ------------------------------


async def resolve_district(
    client: AdvocateSearchClient, state_code: str, district_name: str
) -> tuple[str, str]:
    """Resolve a district *name* to its code via the live portal dropdown.

    Matches ``district_name`` case-insensitively as a substring against the
    state's districts. Returns ``(dist_code, full_name)``. Raises ValueError
    (listing candidates) if zero or more than one district matches, so an
    ambiguous name fails loudly instead of silently scraping the wrong court.
    """
    districts = await client.list_districts(state_code)
    needle = district_name.strip().lower()
    matches = {c: n for c, n in districts.items() if needle in n.lower()}
    if len(matches) == 1:
        code, name = next(iter(matches.items()))
        return code, name
    if not matches:
        raise ValueError(
            f"no district matches {district_name!r} in state {state_code}. "
            f"Available: {sorted(districts.values())}"
        )
    raise ValueError(
        f"district name {district_name!r} is ambiguous in state {state_code} - "
        f"matches {list(matches.values())}. Use a more specific name."
    )


async def list_district_complexes(
    client: AdvocateSearchClient, state_code: str, dist_code: str
) -> list[tuple[str, list[str], bool, str]]:
    """List every court complex in a district as
    ``(complex_code, est_codes, needs_est, name)`` tuples."""
    raw = await client.list_complexes(state_code, dist_code)
    complexes = []
    for value, name in raw.items():
        code, est_codes, needs_est = parse_complex_value(value)
        complexes.append((code, est_codes, needs_est, name))
    return complexes


def _upsert_results(name: str, rows) -> list:
    """Persist advocates/cases/links from search rows. Returns unique rows
    (deduped by CNR) that still need history enrichment."""
    need_history = {}
    with Session() as session:
        search_adv = get_or_create_advocate(session, name)  # the search term, as an advocate
        for row in rows:
            if not row.cino:
                continue
            case = session.scalar(select(Case).where(Case.cnr == row.cino))
            if case is None:
                case = Case(cnr=row.cino)
                session.add(case)
            case.internal_case_no = row.case_no
            case.court_code = row.court_code
            case.establishment = row.establishment
            case.case_number_full = row.case_number_full
            case.case_type = row.case_type
            case.registration_number = row.registration_number
            case.year = row.year
            case.petitioner = row.petitioner
            case.respondent = row.respondent
            case.state_code = row.state_code
            case.dist_code = row.dist_code
            case.complex_code = row.complex_code
            session.flush()

            # Link the searched name to every case its search returned, plus each
            # advocate parsed from the row. The portal often spells the searched
            # advocate differently in the results column (e.g. "Tanveer Nizam" ->
            # "MARIAM TANVEER NIZAM"), so linking the canonical search node here is
            # what guarantees the per-advocate summary sees its full portfolio.
            def _link(adv):
                exists = session.scalar(
                    select(CaseAdvocate.id).where(
                        CaseAdvocate.case_id == case.id,
                        CaseAdvocate.advocate_id == adv.id,
                    )
                )
                if not exists:
                    session.add(CaseAdvocate(case_id=case.id, advocate_id=adv.id))

            _link(search_adv)
            for adv_name in row.advocates:
                adv = get_or_create_advocate(session, adv_name)
                _link(adv)
                enqueue_seed(session, adv_name, source="harvest")

            if not case.history_fetched and row.cino not in need_history:
                need_history[row.cino] = row
        session.commit()
    return list(need_history.values())


async def _enrich_case(client: AdvocateSearchClient, row, download_pdfs: bool) -> None:
    """Fetch history for one case, store status/disposal + orders, download PDFs."""
    html = await client.case_history(row)
    if config.SAVE_RAW_HTML:
        html_path = config.HTML_DIR / f"{row.cino}_history.html"
        html_path.write_text(html, encoding="utf-8")
        logger.info("saved HTML %s (%d bytes)", html_path.name, len(html))
    detail = parse_case_history(html)

    with Session() as session:
        case = session.scalar(select(Case).where(Case.cnr == row.cino))
        if case is None:
            return
        case.case_status = detail.case_status
        case.nature_of_disposal = detail.nature_of_disposal
        case.decision_date = detail.decision_date
        case.filing_date = detail.filing_date
        case.judge = detail.judge
        case.history_fetched = True

        order_objs = []
        for o in detail.orders:
            existing = session.scalar(
                select(Order).where(Order.case_id == case.id, Order.order_number == o.order_number)
            )
            if existing is None:
                existing = Order(case_id=case.id, order_number=o.order_number)
                session.add(existing)
            existing.order_date = o.order_date
            existing.label = o.label
            session.flush()
            order_objs.append((existing.id, o))
        session.commit()

    if not download_pdfs:
        return

    for order_id, o in order_objs:
        if not o.filename:
            continue
        pdf = await client.fetch_order_pdf(o)
        if pdf is None:
            logger.warning("could not download PDF for %s order %s", row.cino, o.order_number)
            continue
        path = config.PDF_DIR / f"{row.cino}_order{o.order_number}.pdf"
        path.write_bytes(pdf)
        sha = hashlib.sha256(pdf).hexdigest()
        with Session() as session:
            order = session.get(Order, order_id)
            order.downloaded = True
            order.pdf_local_path = str(path)
            order.sha256 = sha
            session.commit()
        logger.info("saved PDF %s (%d bytes)", path.name, len(pdf))


async def _search_one(
    client: AdvocateSearchClient,
    *,
    state_code: str,
    dist_code: str,
    complex_code: str,
    est_code: str,
    name: str,
    status: str,
    attempts: int = 3,
) -> list | None:
    """One advocate search with a small retry loop. Returns parsed rows, or
    ``None`` if every attempt failed.

    Each ``advocate_search_raw`` already retries internally on CAPTCHA *status*
    failures, but the portal sometimes rejects a CAPTCHA via an ``errormsg``
    envelope (surfaced as ServerError) which that loop doesn't catch. Across
    16+ complexes per name such transient failures are likely, so we retry the
    whole call (fresh session + CAPTCHA each time) and skip the complex rather
    than aborting the entire district crawl.
    """
    last_err: Exception | None = None
    for attempt in range(attempts):
        try:
            html = await client.advocate_search_raw(
                state_code=state_code,
                dist_code=dist_code,
                court_complex_code=complex_code,
                est_code=est_code,
                advocate_name=name,
                status_filter=status,
            )
            if config.SAVE_RAW_HTML:
                est_tag = _slug(est_code) if est_code else "all"
                html_path = config.HTML_DIR / f"search_{_slug(name)}_{_slug(complex_code)}_{est_tag}.html"
                html_path.write_text(html, encoding="utf-8")
                logger.info("saved HTML %s (%d bytes)", html_path.name, len(html))
            return parse_advocate_results(html)
        except Exception as e:  # noqa: BLE001 - transient portal/CAPTCHA errors; retry then skip
            last_err = e
            logger.warning(
                "search failed complex=%s est=%r attempt %d/%d: %s",
                complex_code, est_code, attempt + 1, attempts, e,
            )
    logger.error("giving up on complex=%s est=%r: %s", complex_code, est_code, last_err)
    return None


async def _search_complexes(
    client: AdvocateSearchClient,
    *,
    state_code: str,
    dist_code: str,
    complexes: list[tuple[str, list[str], bool, str]],
    name: str,
    status: str,
    on_progress=None,
) -> tuple[list, list[str]]:
    """Run the advocate search across every complex in the district. Returns
    ``(all_rows, failed)`` where ``all_rows`` includes duplicates (deduped
    later by CNR on upsert) and ``failed`` lists complex/est that never
    succeeded.

    For a complex flagged ``needs_est`` (establishment selection mandatory) we
    search each establishment separately to guarantee coverage; otherwise a
    single blank-establishment search spans the whole complex.

    ``on_progress`` (optional sync callback) is invoked once per complex so the
    web worker can stream live "searching court i/N" updates.
    """
    all_rows: list = []
    failed: list[str] = []
    total = len(complexes)
    for i, (complex_code, est_codes, needs_est, cname) in enumerate(complexes, 1):
        if on_progress:
            on_progress({
                "phase": "search_complex", "index": i, "total": total,
                "complex_name": cname, "rows_so_far": len(all_rows),
            })
        if needs_est:
            ests = await client.list_establishments(state_code, dist_code, complex_code)
            est_iter = list(ests) or est_codes or [""]
        else:
            est_iter = [""]
        for est_code in est_iter:
            rows = await _search_one(
                client,
                state_code=state_code,
                dist_code=dist_code,
                complex_code=complex_code,
                est_code=est_code,
                name=name,
                status=status,
            )
            if rows is None:
                failed.append(f"{complex_code}/{est_code}")
                continue
            logger.info("  complex %s (%s) est=%r -> %d rows", complex_code, cname, est_code, len(rows))
            all_rows.extend(rows)
    return all_rows, failed


async def process_name(
    client: AdvocateSearchClient,
    name: str,
    *,
    state_code: str = config.STATE_CODE,
    dist_code: str,
    complexes: list[tuple[str, list[str], bool, str]],
    status: str = config.DEFAULT_STATUS,
    download_pdfs: bool = True,
    max_cases: int | None = None,
    on_progress=None,
) -> dict:
    """Search one advocate name across every court complex in the district and
    fully ingest the resulting cases.

    ``on_progress`` (optional sync callback) receives structured events
    (``search_complex`` / ``cases_found`` / ``case_enriched``) so the web worker
    can stream live progress + partial cases to the browser. CLI callers omit it.
    """
    rows, failed = await _search_complexes(
        client, state_code=state_code, dist_code=dist_code, complexes=complexes,
        name=name, status=status, on_progress=on_progress,
    )
    unique_rows = _upsert_results(name, rows)
    if max_cases is not None:
        unique_rows = unique_rows[:max_cases]
    if on_progress:
        on_progress({"phase": "cases_found", "unique_cases": len(unique_rows)})

    enriched = 0
    total = len(unique_rows)
    for row in unique_rows:
        await _enrich_case(client, row, download_pdfs)
        enriched += 1
        if on_progress:
            on_progress({
                "phase": "case_enriched", "index": enriched, "total": total,
                "cnr": row.cino, "case_number": row.case_number_full,
                "case_type": row.case_type, "petitioner": row.petitioner,
                "respondent": row.respondent, "court": row.establishment,
            })

    return {
        "complexes_searched": len(complexes),
        "complexes_failed": len(failed),
        "rows": len(rows),
        "unique_cases": len(unique_rows),
        "enriched": enriched,
    }
