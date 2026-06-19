"""Advocate-name search for the District Courts portal.

bharat-courts does not implement advocate search, so we add it here by
subclassing DistrictCourtClient and reusing its session / token / CAPTCHA
machinery. The endpoint + field names were reverse-engineered from the
portal's searchByCaseStatus.js (submit_adv_name -> casestatus/submitAdvName,
results returned in the JSON `adv_data` field).
"""

from __future__ import annotations

import asyncio
import logging

from bs4 import BeautifulSoup

from bharat_courts.districtcourts import endpoints
from bharat_courts.districtcourts.client import DistrictCourtClient
from bharat_courts.districtcourts.parser import parse_case_status_html, parse_option_tags
from bharat_courts.models import CaseInfo

from parse_advocate import AdvocateCaseRow
from parse_history import OrderRow

logger = logging.getLogger(__name__)

# The state dropdown is rendered on the case-status page, not the portal root.
STATES_PAGE = "casestatus/index"

# Authoritative state code -> name map, captured live from the portal's
# `sess_state_code` dropdown. Used ONLY as a fallback if the live fetch fails.
# Do NOT use bharat_courts.endpoints.DISTRICT_STATES here: its codes are stale
# (e.g. it maps Maharashtra to "27", which the live portal now uses for
# Chandigarh) and that mismatch is the bug this fallback guards against.
STATES_FALLBACK: dict[str, str] = {
    "1": "Maharashtra",
    "2": "Andhra Pradesh",
    "3": "Karnataka",
    "4": "Kerala",
    "5": "Himachal Pradesh",
    "6": "Assam",
    "7": "Jharkhand",
    "8": "Bihar",
    "9": "Rajasthan",
    "10": "Tamil Nadu",
    "11": "Odisha",
    "12": "Jammu and Kashmir",
    "13": "Uttar Pradesh",
    "14": "Haryana",
    "15": "Uttarakhand",
    "16": "West Bengal",
    "17": "Gujarat",
    "18": "Chhattisgarh",
    "19": "Mizoram",
    "20": "Tripura",
    "21": "Meghalaya",
    "22": "Punjab",
    "23": "Madhya Pradesh",
    "24": "Sikkim",
    "25": "Manipur",
    "26": "Delhi",
    "27": "Chandigarh",
    "28": "Andaman and Nicobar",
    "29": "Telangana",
    "30": "Goa",
    "33": "Ladakh",
    "34": "Nagaland",
    "35": "Puducherry",
    "36": "Arunachal Pradesh",
    "37": "Lakshadweep",
    "38": "The Dadra And Nagar Haveli And Daman And Diu",
}


class AdvocateSearchClient(DistrictCourtClient):
    """DistrictCourtClient + advocate-name search."""

    async def list_states_live(self) -> dict[str, str]:
        """Return ``{state_code: name}`` read live from the portal.

        bharat_courts' ``list_states()`` returns a hardcoded map whose codes are
        stale and no longer match the live ``fillDistrict`` endpoint (it sends
        Maharashtra as "27", which now returns Chandigarh's districts). Reading
        the live ``sess_state_code`` dropdown guarantees the codes are consistent
        with :meth:`list_districts`. No CAPTCHA/token needed — it's a plain GET.
        """
        resp = await self._http.get(
            endpoints.ajax_url(STATES_PAGE), headers={"Referer": endpoints.BASE_URL + "/"}
        )
        soup = BeautifulSoup(resp.text, "lxml")
        sel = soup.find("select", id="sess_state_code")
        if sel is None:
            # Markup changed: pick the <select> whose options look like states.
            for cand in soup.find_all("select"):
                txt = cand.get_text(" ", strip=True).lower()
                if "maharashtra" in txt or "karnataka" in txt:
                    sel = cand
                    break
        states = parse_option_tags(str(sel)) if sel is not None else {}
        if not states:
            logger.warning("live state dropdown empty; using captured fallback map")
            return dict(STATES_FALLBACK)
        return states

    async def advocate_search(
        self,
        *,
        state_code: str,
        dist_code: str,
        court_complex_code: str,
        est_code: str = "",
        advocate_name: str,
        status_filter: str = "Disposed",
    ) -> tuple[list[CaseInfo], str]:
        """Search cases by advocate name.

        Returns (parsed cases, raw adv_data HTML). The raw HTML is returned
        too because it carries the per-establishment grouping/counts that the
        flat CaseInfo list drops.
        """

        def build_form(captcha: str) -> dict:
            return {
                "radAdvt": "1",  # 1 = Advocate Name (2 = Bar Code, 3 = Today's list)
                "advocate_name": advocate_name,
                "case_status": status_filter,  # Pending | Disposed | Both
                "adv_captcha_code": captcha,
                "state_code": state_code,
                "dist_code": dist_code,
                "court_complex_code": court_complex_code,
                "est_code": est_code,
            }

        result = await self._post_with_captcha_retry(
            "casestatus/submitAdvName",
            build_form,
            state_code=state_code,
            dist_code=dist_code,
            court_complex_code=court_complex_code,
            est_code=est_code,
        )
        html = result.get("adv_data", "")
        return parse_case_status_html(html), html

    async def advocate_search_raw(
        self,
        *,
        state_code: str,
        dist_code: str,
        court_complex_code: str,
        est_code: str = "",
        advocate_name: str,
        status_filter: str = "Disposed",
    ) -> str:
        """Same as advocate_search but returns only the raw adv_data HTML
        (so the richer parse_advocate.parse_advocate_results can be used)."""
        _, html = await self.advocate_search(
            state_code=state_code,
            dist_code=dist_code,
            court_complex_code=court_complex_code,
            est_code=est_code,
            advocate_name=advocate_name,
            status_filter=status_filter,
        )
        return html

    # ---- case history + order PDF (no CAPTCHA needed) ---------------------

    async def case_history(self, row: AdvocateCaseRow) -> str:
        """Fetch a case's history HTML (data_list) via home/viewHistory."""
        form = {
            "court_code": row.court_code,
            "state_code": row.state_code,
            "dist_code": row.dist_code,
            "court_complex_code": row.complex_code,
            "case_no": row.case_no,
            "cino": row.cino,
            "hideparty": "",
            "search_flag": row.search_flag,
            "search_by": row.search_by,
        }
        result = await self._post_ajax("home/viewHistory", form)
        return result.get("data_list", "")

    async def fetch_order_pdf(self, order: OrderRow, *, retries: int = 4) -> bytes | None:
        """Resolve an order to its PDF via home/display_pdf and download it.

        The portal generates the report file on the display_pdf call, so the
        first GET can 404 before it's written — retry the whole round-trip.
        Returns PDF bytes (validated %PDF) or None.
        """
        form = {
            "normal_v": order.normal_v,
            "case_val": order.case_val,
            "court_code": order.court_code,
            "filename": order.filename,
            "appFlag": order.app_flag,
        }
        for attempt in range(retries):
            try:
                result = await self._post_ajax("home/display_pdf", form)
                order_path = result.get("order", "")
                if not order_path:
                    logger.warning("display_pdf returned no path: %s", result)
                    await asyncio.sleep(1.5)
                    continue
                url = f"{endpoints.BASE_URL}/{order_path.lstrip('/')}"
                raw = await self._http.get_bytes(url, headers={"Referer": endpoints.BASE_URL + "/"})
                if raw[:5] == b"%PDF-":
                    return raw
                logger.warning("downloaded file is not a PDF (attempt %d)", attempt + 1)
            except Exception as e:  # noqa: BLE001 - transient portal/timing errors
                logger.warning("order PDF fetch attempt %d failed: %s", attempt + 1, e)
            await asyncio.sleep(1.5)
        return None
