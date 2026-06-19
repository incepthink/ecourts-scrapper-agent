// Shared copy/constants surfaced in more than one component.

// The official portal we scrape from. Surfaced so users can confirm an outage
// themselves when it returns 503. Keep in sync with src/portal_status.py.
export const ECOURTS_URL = "https://services.ecourts.gov.in/ecourtindia_v6/";

export const PORTAL_DOWN_MSG =
  "The official eCourts portal (services.ecourts.gov.in) is currently unavailable, " +
  "so we can't fetch court data right now. Please try again shortly.";

// Shown when the backend rejects our token (e.g. "invalid token", 401). The fix
// is to re-authenticate, so we spell that out instead of surfacing the raw error.
export const SESSION_EXPIRED_MSG =
  "Your session has expired. Please sign out and sign in again to continue.";

export function isAuthError(message) {
  const m = (message || "").toLowerCase();
  return m.includes("invalid token") || m.includes("not signed in") || m.includes("unauthorized");
}
