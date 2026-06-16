"""End-to-end test of the existing party-name search against live Thane,
using OCR captcha + corrected hierarchy codes. Proves captcha/token/parse work.
"""

from __future__ import annotations

import asyncio
import logging

from bharat_courts.captcha.ocr import OCRCaptchaSolver
from bharat_courts.districtcourts.client import DistrictCourtClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

# Corrected live codes for the Thane pilot
STATE = "1"            # Maharashtra
DIST = "21"            # Thane
COMPLEX = "1010247"    # Thane, District and Sessions Court


async def main() -> None:
    solver = OCRCaptchaSolver()
    async with DistrictCourtClient(captcha_solver=solver) as client:
        try:
            cases = await client.case_status_by_party(
                state_code=STATE,
                dist_code=DIST,
                court_complex_code=COMPLEX,
                est_code="",
                party_name="Patil",
                year="2024",
                status_filter="Disposed",
            )
            print(f"\n=== party search returned {len(cases)} cases ===")
            for c in cases[:10]:
                print(f"  {c.case_number} | {c.petitioner} vs {c.respondent} | cnr={c.cnr_number} | status={c.status}")
        except Exception as e:
            print(f"\n!! party search failed: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
