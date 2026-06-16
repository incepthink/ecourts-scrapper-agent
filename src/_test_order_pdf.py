"""Validate the order/judgment PDF chain for one disposed Nizam case:
  home/viewHistory  ->  parse displayPdf(...) order links  ->  home/display_pdf
  ->  download PDF bytes  ->  check %PDF header.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import re

from bharat_courts.districtcourts import endpoints
from bharat_courts.http import RateLimitedClient

BASE = endpoints.BASE_URL
DATA = pathlib.Path(__file__).parent.parent / "data"

# First Nizam case from the advocate-search results' View link:
# viewHistory(203600004322024,'MHTH010012242024',1,'','CScaseNumber',1,21,1010247,'CSAdvName')
CASE = dict(
    court_code="1",
    state_code="1",
    dist_code="21",
    court_complex_code="1010247",
    case_no="203600004322024",
    cino="MHTH010012242024",
    hideparty="",
    search_flag="CScaseNumber",
    search_by="CSAdvName",
)


def split_args(arg_str: str) -> list[str]:
    """Split a JS call arg list on top-level commas, stripping quotes."""
    parts = re.split(r",(?=(?:[^']*'[^']*')*[^']*$)", arg_str)
    return [p.strip().strip("'\"") for p in parts]


async def post_json(http: RateLimitedClient, action: str, data: dict) -> dict:
    payload = dict(data)
    payload["ajax_req"] = "true"
    payload["app_token"] = ""
    resp = await http.post(endpoints.ajax_url(action), data=payload,
                           headers={"Referer": BASE + "/"})
    try:
        return json.loads(resp.text)
    except json.JSONDecodeError:
        return {"_raw": resp.text}


async def main() -> None:
    async with RateLimitedClient() as http:
        await http.get(BASE + "/", headers={"Referer": BASE + "/"})

        # 1. case history
        hist = await post_json(http, "home/viewHistory", CASE)
        print("viewHistory status:", hist.get("status"), "| keys:", list(hist.keys()))
        data_list = hist.get("data_list", "")
        (DATA / "history_nizam_case1.html").write_text(data_list, encoding="utf-8")
        print(f"history HTML: {len(data_list)} chars saved")

        # 2. find order PDF links
        calls = re.findall(r"displayPdf\(([^)]*)\)", data_list)
        print(f"\ndisplayPdf links found: {len(calls)}")
        for c in calls[:8]:
            print("   ", c)
        if not calls:
            # show what order-ish text exists
            for kw in ("rder", "udgment", "Business"):
                idx = data_list.find(kw)
                if idx >= 0:
                    print(f"   context[{kw}]:", re.sub(r"\s+", " ", data_list[idx-80:idx+120]))
            return

        # 3. display_pdf for the first order
        args = split_args(calls[0])
        print("\nfirst order args:", args)
        normal_v, case_val, court_code, filename, app_flag = (args + [""] * 5)[:5]
        pdf_resp = await post_json(http, "home/display_pdf", {
            "normal_v": normal_v, "case_val": case_val, "court_code": court_code,
            "filename": filename, "appFlag": app_flag,
        })
        print("display_pdf:", {k: v for k, v in pdf_resp.items() if k != "_raw"})
        order_path = pdf_resp.get("order", "")
        if not order_path:
            print("no order path returned:", str(pdf_resp)[:300])
            return

        # 4. download the PDF
        pdf_url = f"{BASE}/{order_path.lstrip('/')}"
        print("downloading:", pdf_url)
        raw = await http.get_bytes(pdf_url, headers={"Referer": BASE + "/"})
        is_pdf = raw[:5] == b"%PDF-"
        out = DATA / "pdfs" / "nizam_case1_order.pdf"
        out.write_bytes(raw)
        print(f"\nPDF bytes={len(raw)}  is_pdf={is_pdf}  saved-> {out}")


if __name__ == "__main__":
    asyncio.run(main())
