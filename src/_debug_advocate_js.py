"""Pull the portal JS and extract everything about advocate search:
the submit function, the AJAX action path, and the form field names.
"""

from __future__ import annotations

import asyncio
import re

from bharat_courts.districtcourts import endpoints
from bharat_courts.http import RateLimitedClient

JS_FILES = [
    "/ecourtindia_v6/js/components.js",
    "/ecourtindia_v6/js/common_header.js",
    "/ecourtindia_v6/js/home.js",
    "/ecourtindia_v6/js/myscript.js",
]
ROOT = "https://services.ecourts.gov.in"


async def main() -> None:
    async with RateLimitedClient() as http:
        for path in JS_FILES:
            url = ROOT + path
            try:
                js = (await http.get(url, headers={"Referer": endpoints.BASE_URL + "/"})).text
            except Exception as e:
                print(f"skip {url}: {e}")
                continue
            if "advocate" not in js.lower():
                continue
            print(f"\n############## {path} (len={len(js)}) ##############")

            # All casestatus/ or courtorder/ action strings
            actions = sorted(set(re.findall(r"(?:casestatus|courtorder|cause_list)/\w+", js)))
            print("ACTIONS:", actions)

            # function definitions mentioning advocate
            for m in re.finditer(r"function\s+(\w+)\s*\([^)]*\)\s*\{", js):
                name = m.group(1)
                if "advocate" in name.lower() or "Advocate" in name:
                    print("FUNCTION:", name)

            # Print ~700-char windows around each 'advocate' (case-insensitive),
            # de-duplicated by coarse position.
            seen = set()
            for m in re.finditer(r"advocate", js, re.IGNORECASE):
                bucket = m.start() // 600
                if bucket in seen:
                    continue
                seen.add(bucket)
                snippet = js[max(0, m.start() - 250): m.start() + 350]
                snippet = re.sub(r"\s+", " ", snippet)
                print(f"\n   @{m.start()}: ...{snippet}...")


if __name__ == "__main__":
    asyncio.run(main())
