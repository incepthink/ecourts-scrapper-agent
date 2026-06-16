"""Find where the current portal puts the app_token.

Dumps the landing page HTML and the raw getCaptcha response, then greps
for any 'token' occurrences so we can fix the rotation logic.
"""

from __future__ import annotations

import asyncio
import re

from bharat_courts.districtcourts import endpoints
from bharat_courts.http import RateLimitedClient


def show_token_hits(label: str, text: str) -> None:
    print(f"\n===== {label} (len={len(text)}) =====")
    hits = [m.start() for m in re.finditer(r"token", text, re.IGNORECASE)]
    print(f"'token' occurrences: {len(hits)}")
    for pos in hits[:20]:
        snippet = text[max(0, pos - 80): pos + 80].replace("\n", " ")
        print(f"  ...{snippet}...")


async def main() -> None:
    async with RateLimitedClient() as http:
        # 1. Landing page
        resp = await http.get(endpoints.BASE_URL + "/", headers={"Referer": endpoints.BASE_URL + "/"})
        land = resp.text
        show_token_hits("LANDING PAGE", land)
        # Look for hidden inputs named app_token
        for m in re.finditer(r"<input[^>]*app_token[^>]*>", land, re.IGNORECASE):
            print("  INPUT:", m.group(0))
        # JS var assignments
        for m in re.finditer(r"app_token\s*=\s*['\"][^'\"]*['\"]", land):
            print("  JSVAR:", m.group(0))

        # 2. getCaptcha raw
        resp2 = await http.post(
            endpoints.ajax_url("casestatus/getCaptcha"),
            data={"ajax_req": "true", "app_token": ""},
            headers={"Referer": endpoints.BASE_URL + "/"},
        )
        cap = resp2.text
        show_token_hits("getCaptcha RESPONSE", cap)
        print("\n--- getCaptcha first 1500 chars ---")
        print(cap[:1500])


if __name__ == "__main__":
    asyncio.run(main())
