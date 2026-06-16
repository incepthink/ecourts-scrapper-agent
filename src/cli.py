"""Command-line interface for the eCourts advocate collector.

Searches every court complex in the configured district
(config.DISTRICT_NAME, resolved live to its code).

Examples:
    python src/cli.py init-db
    python src/cli.py seed "Nizam" "Patil"
    python src/cli.py run --limit 1            # process 1 pending seed name
    python src/cli.py run-name "Nizam"         # process a single name directly
    python src/cli.py stats
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from sqlalchemy import select

import config
from advocate_search import AdvocateSearchClient
from bharat_courts.captcha.ocr import OCRCaptchaSolver
from pipeline import list_district_complexes, process_name, resolve_district
from report_html import write_advocate_summary
from store import Session, SeedName, enqueue_seed, init_db, stats

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cli")


def print_stats() -> None:
    with Session() as s:
        print("\n=== DB stats ===")
        for k, v in stats(s).items():
            print(f"  {k:18}: {v}")


def cmd_seed(names: list[str]) -> None:
    init_db()
    added = 0
    with Session() as s:
        for n in names:
            if enqueue_seed(s, n, source="manual"):
                added += 1
        s.commit()
    print(f"added {added} new seed name(s)")
    print_stats()


async def _resolve_court(client):
    """Resolve the configured district to its code + the list of all its
    court complexes (once per run, before processing any names)."""
    dist_code, dist_name = await resolve_district(
        client, config.STATE_CODE, config.DISTRICT_NAME
    )
    complexes = await list_district_complexes(client, config.STATE_CODE, dist_code)
    logger.info("district %r (code %s): %d complexes", dist_name, dist_code, len(complexes))
    return dist_code, complexes


async def _process_one(client, name, dist_code, complexes, status, download_pdfs, max_cases):
    res = await process_name(
        client,
        name,
        dist_code=dist_code,
        complexes=complexes,
        status=status,
        download_pdfs=download_pdfs,
        max_cases=max_cases,
    )
    print(f"[done] {name} -> {res}")
    return res


async def cmd_run(limit, status, download_pdfs, max_cases) -> None:
    init_db()
    solver = OCRCaptchaSolver()
    processed = 0
    async with AdvocateSearchClient(captcha_solver=solver) as client:
        dist_code, complexes = await _resolve_court(client)
        while limit is None or processed < limit:
            with Session() as s:
                seed = s.scalar(
                    select(SeedName).where(SeedName.status == "pending").order_by(SeedName.id).limit(1)
                )
                if seed is None:
                    print("no pending seed names")
                    break
                name, seed_id = seed.name, seed.id
            try:
                res = await _process_one(
                    client, name, dist_code, complexes, status, download_pdfs, max_cases
                )
                st, note = "done", str(res)
                path = write_advocate_summary(name)
                print(f"[summary] {path}")
            except Exception as e:  # noqa: BLE001
                st, note = "error", repr(e)
                logger.exception("failed processing %s", name)
            with Session() as s:
                sd = s.get(SeedName, seed_id)
                sd.status, sd.note = st, note
                s.commit()
            processed += 1
    print_stats()


async def cmd_run_name(name, status, download_pdfs, max_cases) -> None:
    init_db()
    with Session() as s:
        enqueue_seed(s, name, source="manual")
        s.commit()
    solver = OCRCaptchaSolver()
    async with AdvocateSearchClient(captcha_solver=solver) as client:
        dist_code, complexes = await _resolve_court(client)
        await _process_one(client, name, dist_code, complexes, status, download_pdfs, max_cases)
    # mark the seed done
    with Session() as s:
        from store import normalize_name

        sd = s.scalar(select(SeedName).where(SeedName.name_norm == normalize_name(name)))
        if sd:
            sd.status = "done"
            s.commit()
    path = write_advocate_summary(name)
    print(f"[summary] {path}")
    print_stats()


def main() -> None:
    p = argparse.ArgumentParser(description="eCourts advocate collector")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db")
    sub.add_parser("stats")

    ps = sub.add_parser("seed")
    ps.add_argument("names", nargs="+")

    common = dict()
    pr = sub.add_parser("run")
    pr.add_argument("--limit", type=int, default=None, help="max seed names to process")
    pr.add_argument("--status", default=config.DEFAULT_STATUS, choices=["Disposed", "Pending", "Both"])
    pr.add_argument("--no-pdf", action="store_true", help="skip downloading order PDFs")
    pr.add_argument("--max-cases", type=int, default=None, help="max cases per name")

    prn = sub.add_parser("run-name")
    prn.add_argument("name")
    prn.add_argument("--status", default=config.DEFAULT_STATUS, choices=["Disposed", "Pending", "Both"])
    prn.add_argument("--no-pdf", action="store_true")
    prn.add_argument("--max-cases", type=int, default=None)

    prh = sub.add_parser("report-html", help="regenerate one advocate's summary HTML from the DB")
    prh.add_argument("name")

    args = p.parse_args()

    if args.cmd == "init-db":
        init_db()
        print(f"DB ready at {config.DB_URL}")
        print_stats()
    elif args.cmd == "stats":
        print_stats()
    elif args.cmd == "seed":
        cmd_seed(args.names)
    elif args.cmd == "run":
        asyncio.run(cmd_run(args.limit, args.status, not args.no_pdf, args.max_cases))
    elif args.cmd == "run-name":
        asyncio.run(cmd_run_name(args.name, args.status, not args.no_pdf, args.max_cases))
    elif args.cmd == "report-html":
        path = write_advocate_summary(args.name)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
