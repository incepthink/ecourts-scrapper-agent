"""Does the portal honor state_code on fillDistrict, or ignore it (token/session issue)?

Calls fillDistrict for several states and prints the raw dist_list.
"""

from __future__ import annotations

import asyncio

from bharat_courts.districtcourts import endpoints
from bharat_courts.http import RateLimitedClient

STATES = {"27": "Maharashtra", "7": "Delhi", "3": "Karnataka"}


async def call_fill_district(http: RateLimitedClient, state_code: str, app_token: str = "") -> str:
    resp = await http.post(
        endpoints.ajax_url("casestatus/fillDistrict"),
        data={"state_code": state_code, "ajax_req": "true", "app_token": app_token},
        headers={"Referer": endpoints.BASE_URL + "/"},
    )
    return resp.text


async def main() -> None:
    async with RateLimitedClient() as http:
        # establish session cookie first
        await http.get(endpoints.BASE_URL + "/", headers={"Referer": endpoints.BASE_URL + "/"})
        for code, name in STATES.items():
            raw = await call_fill_district(http, code)
            print(f"\n=== state_code={code} ({name}) ===")
            print(raw[:600])


if __name__ == "__main__":
    asyncio.run(main())
