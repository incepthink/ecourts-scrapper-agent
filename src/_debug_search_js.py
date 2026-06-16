"""Extract the advocate submit action + postdata from searchByCaseStatus.js."""

from __future__ import annotations

import asyncio
import re

from bharat_courts.districtcourts import endpoints
from bharat_courts.http import RateLimitedClient

URL = "https://services.ecourts.gov.in/ecourtindia_v6/js/searchByCaseStatus.js"


async def main() -> None:
    async with RateLimitedClient() as http:
        js = (await http.get(URL, headers={"Referer": endpoints.BASE_URL + "/"})).text
        print(f"len={len(js)}")

        print("\n=== all submit* function names ===")
        for m in re.finditer(r"function\s+(submit\w+|\w*[Aa]dv\w*)\s*\(", js):
            print("  fn:", m.group(1))

        print("\n=== all casestatus/courtorder action strings ===")
        for a in sorted(set(re.findall(r"(?:casestatus|courtorder|cause_list)/\w+", js))):
            print("  ", a)

        print("\n=== windows around 'advocate_name' ===")
        for m in re.finditer(r"advocate_name", js):
            snip = re.sub(r"\s+", " ", js[max(0, m.start() - 400): m.start() + 500])
            print(f"\n  @{m.start()}: ...{snip}...")

        print("\n=== windows around 'adv_captcha_code' ===")
        for m in re.finditer(r"adv_captcha_code", js):
            snip = re.sub(r"\s+", " ", js[max(0, m.start() - 300): m.start() + 300])
            print(f"\n  @{m.start()}: ...{snip}...")


if __name__ == "__main__":
    asyncio.run(main())
