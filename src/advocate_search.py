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

from bharat_courts.districtcourts import endpoints
from bharat_courts.districtcourts.client import DistrictCourtClient
from bharat_courts.districtcourts.parser import parse_case_status_html
from bharat_courts.models import CaseInfo

from parse_advocate import AdvocateCaseRow
from parse_history import OrderRow

logger = logging.getLogger(__name__)


class AdvocateSearchClient(DistrictCourtClient):
    """DistrictCourtClient + advocate-name search."""

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
