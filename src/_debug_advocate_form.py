"""Discover the advocate-search form: field names, the submit JS function,
and the AJAX action it posts to. Looks in the landing page HTML and any
referenced JS files.
"""

from __future__ import annotations

import asyncio
import re

from bs4 import BeautifulSoup

from bharat_courts.districtcourts import endpoints
from bharat_courts.http import RateLimitedClient


async def main() -> None:
    async with RateLimitedClient() as http:
        resp = await http.get(endpoints.BASE_URL + "/", headers={"Referer": endpoints.BASE_URL + "/"})
        html = resp.text
        soup = BeautifulSoup(html, "lxml")

        print("=== form fields with 'advoc' in name/id ===")
        for tag in soup.find_all(["input", "select", "textarea", "button"]):
            attrs = " ".join(str(tag.get(a, "")) for a in ("name", "id", "value", "onclick"))
            if "advoc" in attrs.lower():
                print(f"  <{tag.name}> name={tag.get('name')!r} id={tag.get('id')!r} "
                      f"value={tag.get('value')!r} type={tag.get('type')!r}")

        print("\n=== HTML mentions of 'submitAdvocate' / advocate AJAX ===")
        for m in re.finditer(r"submit\w*[Aa]dvocate\w*", html):
            print("  fn:", m.group(0))
        for m in re.finditer(r"casestatus/\w*[Aa]dvocate\w*", html):
            print("  action:", m.group(0))

        print("\n=== <script src> includes ===")
        scripts = [s.get("src") for s in soup.find_all("script") if s.get("src")]
        for s in scripts:
            print("  ", s)

        # Fetch likely JS bundles and search them for the advocate submit fn
        print("\n=== searching JS files for advocate submit ===")
        for src in scripts:
            if not src:
                continue
            url = src if src.startswith("http") else (endpoints.BASE_URL.rsplit("/", 1)[0] + src if src.startswith("/") else f"{endpoints.BASE_URL}/{src}")
            try:
                js = (await http.get(url, headers={"Referer": endpoints.BASE_URL + "/"})).text
            except Exception as e:
                print(f"   skip {url}: {e}")
                continue
            if re.search(r"[Aa]dvocate", js):
                print(f"\n   --- {url} mentions advocate ---")
                for m in re.finditer(r"function\s+(\w*[Aa]dvocate\w*)\s*\(", js):
                    print("     function:", m.group(1))
                for m in re.finditer(r"['\"]([^'\"]*casestatus/[^'\"]*[Aa]dvocate[^'\"]*)['\"]", js):
                    print("     posts to:", m.group(1))
                for m in re.finditer(r"(advocate_name|adv_name|adv_captcha\w*|f\b)\s*[:=]", js):
                    print("     param-ish:", m.group(0))


if __name__ == "__main__":
    asyncio.run(main())
