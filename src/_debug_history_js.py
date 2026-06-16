"""Find how the 'View' button opens case history and where order/judgment
PDF links come from. Searches the portal JS for viewHistory + order/PDF actions.
"""

from __future__ import annotations

import asyncio
import re

from bharat_courts.districtcourts import endpoints
from bharat_courts.http import RateLimitedClient

ROOT = "https://services.ecourts.gov.in"
JS_FILES = [
    "/ecourtindia_v6/js/components.js",
    "/ecourtindia_v6/js/searchByCaseStatus.js",
    "/ecourtindia_v6/js/home.js",
    "/ecourtindia_v6/js/myscript.js",
]
TERMS = ["viewHistory", "view_history", "o_civil_case_history", "display_pdf", "/order", "orderpdf",
         "filename", "viewBusiness", "case_history", "court_order", "submitCaseNo"]


async def main() -> None:
    async with RateLimitedClient() as http:
        for path in JS_FILES:
            try:
                js = (await http.get(ROOT + path, headers={"Referer": endpoints.BASE_URL + "/"})).text
            except Exception:
                continue
            actions = sorted(set(re.findall(r"(?:casestatus|courtorder|cases|home)/\w+", js)))
            hit_terms = [t for t in TERMS if t.lower() in js.lower()]
            if not hit_terms and not actions:
                continue
            print(f"\n############## {path} ##############")
            print("ACTIONS:", actions)
            print("TERM HITS:", hit_terms)
            for term in ("viewHistory", "case_history", "display_pdf", "court_order"):
                for m in re.finditer(re.escape(term), js, re.IGNORECASE):
                    snip = re.sub(r"\s+", " ", js[max(0, m.start() - 150): m.start() + 250])
                    print(f"   [{term}] ...{snip}...")
                    break  # one sample per term per file


if __name__ == "__main__":
    asyncio.run(main())
