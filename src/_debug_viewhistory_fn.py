"""Dump the full viewHistory() and displayPdf() function bodies from components.js."""

from __future__ import annotations

import asyncio
import re

from bharat_courts.districtcourts import endpoints
from bharat_courts.http import RateLimitedClient

URL = "https://services.ecourts.gov.in/ecourtindia_v6/js/components.js"


def dump_fn(js: str, name: str) -> None:
    m = re.search(rf"function\s+{name}\s*\(", js)
    if not m:
        print(f"{name}: not found")
        return
    start = m.start()
    # crude brace matching to capture the body
    i = js.index("{", start)
    depth = 0
    for j in range(i, min(len(js), i + 4000)):
        if js[j] == "{":
            depth += 1
        elif js[j] == "}":
            depth -= 1
            if depth == 0:
                body = js[start:j + 1]
                print(f"\n===== {name} ({len(body)} chars) =====")
                print(re.sub(r"[ \t]+", " ", body))
                return
    print(f"{name}: body too long / unbalanced")


async def main() -> None:
    async with RateLimitedClient() as http:
        js = (await http.get(URL, headers={"Referer": endpoints.BASE_URL + "/"})).text
        for fn in ("viewHistory", "displayPdf"):
            dump_fn(js, fn)


if __name__ == "__main__":
    asyncio.run(main())
