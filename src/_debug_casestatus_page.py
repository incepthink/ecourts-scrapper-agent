"""Fetch the Case Status page (?p=casestatus/index) and extract the
advocate-search form fields and the submit function/action/postdata.
"""

from __future__ import annotations

import asyncio
import re

from bs4 import BeautifulSoup

from bharat_courts.districtcourts import endpoints
from bharat_courts.http import RateLimitedClient

ROOT = "https://services.ecourts.gov.in"
PAGE = endpoints.BASE_URL + "/?p=casestatus/index"


async def main() -> None:
    async with RateLimitedClient() as http:
        await http.get(endpoints.BASE_URL + "/", headers={"Referer": endpoints.BASE_URL + "/"})
        html = (await http.get(PAGE, headers={"Referer": endpoints.BASE_URL + "/"})).text
        soup = BeautifulSoup(html, "lxml")

        print("=== inputs/selects near advocate (name/id/value/type) ===")
        for tag in soup.find_all(["input", "select", "textarea", "button"]):
            blob = " ".join(str(tag.get(a, "")) for a in ("name", "id", "value", "onclick", "class"))
            if re.search(r"adv|captcha|status|pend|dispos", blob, re.IGNORECASE):
                print(f"  <{tag.name}> name={tag.get('name')!r} id={tag.get('id')!r} "
                      f"type={tag.get('type')!r} value={tag.get('value')!r}")

        print("\n=== page script includes ===")
        scripts = [s.get("src") for s in soup.find_all("script") if s.get("src")]
        for s in scripts:
            print("  ", s)

        # inline scripts: search for submitAdvocate
        print("\n=== inline submitAdvocate ===")
        for m in re.finditer(r"function\s+(\w*[Aa]dvocate\w*)\s*\(", html):
            print("  inline fn:", m.group(1))

        # fetch each JS and hunt for the advocate submit
        for src in scripts:
            url = src if src.startswith("http") else (ROOT + src if src.startswith("/") else f"{endpoints.BASE_URL}/{src}")
            try:
                js = (await http.get(url, headers={"Referer": PAGE})).text
            except Exception:
                continue
            if not re.search(r"submit\w*[Aa]dvocate|advocate_name", js):
                continue
            print(f"\n############## {url} ##############")
            for m in re.finditer(r"function\s+(\w*[Aa]dvocate\w*)\s*\([^)]*\)", js):
                # print the whole function body (up to 1200 chars)
                start = m.start()
                body = js[start:start + 1400]
                body = re.sub(r"\s+", " ", body)
                print(f"\n--- {m.group(1)} ---\n{body}")
            # any submit action paths
            for a in sorted(set(re.findall(r"(?:casestatus|courtorder)/\w*[Aa]dvocate\w*", js))):
                print("ACTION:", a)


if __name__ == "__main__":
    asyncio.run(main())
