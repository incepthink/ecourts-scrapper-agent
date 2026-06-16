"""Get court complexes for Maharashtra(1) / Thane(21) and show raw values
(code@ests@flag) so we can identify the District & Sessions Court complex.
"""

from __future__ import annotations

import asyncio
import json

from bharat_courts.districtcourts import endpoints
from bharat_courts.districtcourts.parser import parse_complex_value, parse_option_tags
from bharat_courts.http import RateLimitedClient

STATE = "1"   # Maharashtra (live code)
DIST = "21"   # Thane


async def main() -> None:
    async with RateLimitedClient() as http:
        await http.get(endpoints.BASE_URL + "/", headers={"Referer": endpoints.BASE_URL + "/"})
        # fillDistrict first (mirror library order), then fillcomplex
        await http.post(
            endpoints.ajax_url("casestatus/fillDistrict"),
            data={"state_code": STATE, "ajax_req": "true", "app_token": ""},
            headers={"Referer": endpoints.BASE_URL + "/"},
        )
        r = await http.post(
            endpoints.ajax_url("casestatus/fillcomplex"),
            data={"state_code": STATE, "dist_code": DIST, "ajax_req": "true", "app_token": ""},
            headers={"Referer": endpoints.BASE_URL + "/"},
        )
        data = json.loads(r.text)
        print("keys:", list(data.keys()))
        complex_html = data.get("complex_list", "")
        complexes = parse_option_tags(complex_html)
        print(f"\n{len(complexes)} complexes for Thane:")
        for value, name in complexes.items():
            code, ests, needs_est = parse_complex_value(value)
            print(f"   value={value!r}")
            print(f"      name={name}")
            print(f"      -> complex_code={code} est_codes={ests} needs_est={needs_est}")


if __name__ == "__main__":
    asyncio.run(main())
