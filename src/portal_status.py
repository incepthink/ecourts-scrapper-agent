"""Detection + messaging for when the official eCourts portal is unavailable.

Single source of truth shared by the API (``api.py``) and the scrape worker
(``worker.py``). The portal is "down" when it answers with a 5xx (it serves a
503 during maintenance/overload) or can't be reached at all — surfaced by the
shared HTTP client as ``httpx.HTTPStatusError`` (status >= 500) or an
``httpx.TransportError`` (connect/read/timeout).
"""

from __future__ import annotations

import httpx

# Public URL the user can open to confirm the source site is really down.
ECOURTS_PORTAL_URL = "https://services.ecourts.gov.in/ecourtindia_v6/"

PORTAL_DOWN_MESSAGE = (
    "The official eCourts portal (services.ecourts.gov.in) is currently "
    "unavailable, so we can't fetch court data right now. Please try again shortly."
)


def is_portal_down(exc: Exception) -> bool:
    """True if ``exc`` (or anything in its cause chain) is a 5xx / connection
    failure talking to the eCourts portal."""
    seen: set[int] = set()
    e: BaseException | None = exc
    while e is not None and id(e) not in seen:
        seen.add(id(e))
        if isinstance(e, httpx.HTTPStatusError) and e.response.status_code >= 500:
            return True
        if isinstance(e, httpx.TransportError):  # ConnectError / timeouts / read errors
            return True
        e = e.__cause__ or e.__context__
    return False
