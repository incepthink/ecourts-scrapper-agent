"""Connectivity check: resolve Maharashtra -> Thane -> court complexes.

Uses only the no-CAPTCHA hierarchy endpoints to prove the session +
rotating app_token machinery works against the live portal, and to
discover the real district/complex codes we need for the Thane pilot.
"""

from __future__ import annotations

import asyncio
import logging

from bharat_courts.districtcourts.client import DistrictCourtClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

MAHARASHTRA = "27"


async def main() -> None:
    async with DistrictCourtClient() as client:
        states = await client.list_states()
        print(f"\n[states] count={len(states)}  Maharashtra={states.get('Maharashtra') or '?'}")
        # states maps name->code per implementation? print a couple
        mh_name = [k for k, v in states.items() if v == MAHARASHTRA]
        print(f"[states] code 27 -> {mh_name}")

        districts = await client.list_districts(MAHARASHTRA)
        print(f"\n[districts of MH] count={len(districts)}")
        thane = {c: n for c, n in districts.items() if "thane" in n.lower()}
        print(f"[districts] Thane matches: {thane}")

        if not thane:
            print("!! Thane not found; dumping all districts:")
            for c, n in districts.items():
                print(f"   {c}: {n}")
            return

        thane_code = next(iter(thane))
        complexes = await client.list_complexes(MAHARASHTRA, thane_code)
        print(f"\n[complexes of Thane dist={thane_code}] count={len(complexes)}")
        for c, n in complexes.items():
            print(f"   {c}  ->  {n}")


if __name__ == "__main__":
    asyncio.run(main())
