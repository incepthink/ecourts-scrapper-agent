"""Print full district lists for candidate state codes 1 and 8;
identify which contains Thane and report its district code.
"""

from __future__ import annotations

import asyncio

from bharat_courts.districtcourts import endpoints
from bharat_courts.districtcourts.parser import parse_option_tags
from bharat_courts.http import RateLimitedClient


async def fill(http, code: str) -> dict[str, str]:
    r = await http.post(
        endpoints.ajax_url("casestatus/fillDistrict"),
        data={"state_code": code, "ajax_req": "true", "app_token": ""},
        headers={"Referer": endpoints.BASE_URL + "/"},
    )
    import json
    raw = json.loads(r.text).get("dist_list", "")
    return parse_option_tags(raw)


async def main() -> None:
    async with RateLimitedClient() as http:
        await http.get(endpoints.BASE_URL + "/", headers={"Referer": endpoints.BASE_URL + "/"})
        for code in ("1", "8"):
            d = await fill(http, code)
            thane = {c: n for c, n in d.items() if "thane" in n.lower()}
            print(f"\n=== state_code={code} ({len(d)} districts) — Thane: {thane} ===")
            print(", ".join(f"{c}:{n}" for c, n in list(d.items())[:40]))


if __name__ == "__main__":
    asyncio.run(main())
