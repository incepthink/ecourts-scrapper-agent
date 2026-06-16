"""Broad probe: (a) list all <select> on landing page, (b) check if
'Maharashtra' text appears, (c) brute-force state codes via fillDistrict
to find which code returns Maharashtra districts (Mumbai/Pune/Thane/Nagpur).
"""

from __future__ import annotations

import asyncio
import re

from bs4 import BeautifulSoup

from bharat_courts.districtcourts import endpoints
from bharat_courts.http import RateLimitedClient

MH_MARKERS = ("mumbai", "pune", "thane", "nagpur", "nashik", "aurangabad")


async def main() -> None:
    async with RateLimitedClient() as http:
        resp = await http.get(endpoints.BASE_URL + "/", headers={"Referer": endpoints.BASE_URL + "/"})
        html = resp.text
        print("landing has 'Maharashtra':", "maharashtra" in html.lower())
        soup = BeautifulSoup(html, "lxml")
        sels = soup.find_all("select")
        print(f"total <select> on page: {len(sels)}")
        for sel in sels:
            sid = sel.get("id") or sel.get("name") or "?"
            print(f"   select id/name={sid!r} options={len(sel.find_all('option'))}")

        print("\n=== brute-forcing state codes 1..40 via fillDistrict ===")
        for code in range(1, 41):
            r = await http.post(
                endpoints.ajax_url("casestatus/fillDistrict"),
                data={"state_code": str(code), "ajax_req": "true", "app_token": ""},
                headers={"Referer": endpoints.BASE_URL + "/"},
            )
            low = r.text.lower()
            n_opts = low.count("<option")
            hit = any(m in low for m in MH_MARKERS)
            flag = "  <<< MAHARASHTRA?" if hit else ""
            # show first district name for orientation
            m = re.search(r"<option value=\d+\s*>([^<]+)</option>", r.text)
            first = m.group(1) if m else "-"
            print(f"   code={code:>2}  districts~{n_opts-1:>2}  first={first[:22]:<22}{flag}")


if __name__ == "__main__":
    asyncio.run(main())
