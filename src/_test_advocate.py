"""Validate advocate search against live Thane: 'Nizam' / Disposed.
Screenshot reference expects ~19 cases across 3 establishments.
"""

from __future__ import annotations

import asyncio
import logging
import pathlib

from bharat_courts.captcha.ocr import OCRCaptchaSolver

from advocate_search import (
    MAHARASHTRA,
    THANE_DS_COMPLEX,
    THANE_DIST,
    AdvocateSearchClient,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


async def main() -> None:
    solver = OCRCaptchaSolver()
    async with AdvocateSearchClient(captcha_solver=solver) as client:
        cases, raw_html = await client.advocate_search(
            state_code=MAHARASHTRA,
            dist_code=THANE_DIST,
            court_complex_code=THANE_DS_COMPLEX,
            est_code="",
            advocate_name="Nizam",
            status_filter="Disposed",
        )
        print(f"\n=== advocate 'Nizam' (Disposed) returned {len(cases)} parsed cases ===")
        for c in cases:
            print(f"  {c.case_number} | {c.petitioner} vs {c.respondent} | cnr={c.cnr_number}")

        # Save raw HTML for inspecting establishment grouping / column layout
        out = pathlib.Path(__file__).parent.parent / "data" / "advocate_nizam_raw.html"
        out.write_text(raw_html, encoding="utf-8")
        print(f"\nraw adv_data HTML ({len(raw_html)} chars) saved -> {out}")


if __name__ == "__main__":
    asyncio.run(main())
