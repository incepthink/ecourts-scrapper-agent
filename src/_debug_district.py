"""Dump the raw fillDistrict AJAX response for Maharashtra (state_code=27)
to diagnose why list_districts returns the wrong data.
"""

from __future__ import annotations

import asyncio
import json

from bharat_courts.districtcourts import endpoints
from bharat_courts.districtcourts.client import DistrictCourtClient

MAHARASHTRA = "27"


async def main() -> None:
    async with DistrictCourtClient() as client:
        await client._init_session()
        print("app_token after init:", (client._app_token or "")[:16], "...")

        # Raw fillDistrict for MH
        form = endpoints.fill_district_form(state_code=MAHARASHTRA)
        print("POST form:", form)
        result = await client._post_ajax("casestatus/fillDistrict", form)
        print("\n=== keys in result ===")
        print(list(result.keys()))
        print("\n=== full result (truncated 3000 chars) ===")
        print(json.dumps(result, indent=2)[:3000])


if __name__ == "__main__":
    asyncio.run(main())
