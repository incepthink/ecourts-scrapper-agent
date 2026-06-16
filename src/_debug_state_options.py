"""Extract the live State dropdown options from the landing page,
so we can find the CORRECT code for Maharashtra (the hardcoded map is stale).
"""

from __future__ import annotations

import asyncio

from bs4 import BeautifulSoup

from bharat_courts.districtcourts import endpoints
from bharat_courts.http import RateLimitedClient


async def main() -> None:
    async with RateLimitedClient() as http:
        resp = await http.get(endpoints.BASE_URL + "/", headers={"Referer": endpoints.BASE_URL + "/"})
        soup = BeautifulSoup(resp.text, "lxml")

        # Find every <select> and report those whose options look like states
        for sel in soup.find_all("select"):
            opts = sel.find_all("option")
            texts = [o.get_text(strip=True) for o in opts]
            joined = " ".join(texts).lower()
            if "maharashtra" in joined or "karnataka" in joined or "select state" in joined:
                sid = sel.get("id") or sel.get("name") or "?"
                print(f"\n=== <select id/name={sid}> ({len(opts)} options) ===")
                for o in opts:
                    val = o.get("value", "").strip()
                    txt = o.get_text(strip=True)
                    print(f"   {val!r:>6} -> {txt}")


if __name__ == "__main__":
    asyncio.run(main())
