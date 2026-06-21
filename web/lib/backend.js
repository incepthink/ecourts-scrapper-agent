// Browser-side helper for talking to the FastAPI backend.
// Fetches a short-lived backend JWT from our /api/token route, caches it, and
// attaches it as a Bearer token (or, for SSE, a query param).

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

let _token = null;
let _tokenExp = 0;

export async function getToken() {
  if (_token && Date.now() < _tokenExp) return _token;
  const r = await fetch("/api/token");
  if (!r.ok) throw new Error("Not signed in");
  const { token } = await r.json();
  _token = token;
  _tokenExp = Date.now() + 55 * 60 * 1000; // refresh a bit before the 1h expiry
  return token;
}

async function request(path, options = {}) {
  const token = await getToken();
  const r = await fetch(API + path, {
    ...options,
    headers: {
      ...(options.headers || {}),
      Authorization: `Bearer ${token}`,
    },
  });
  if (!r.ok) {
    let detail = r.statusText;
    try {
      detail = (await r.json()).detail || detail;
    } catch (_) {}
    const err = new Error(detail);
    err.status = r.status;
    throw err;
  }
  return r.json();
}

export const getStates = () => request("/locations/states");
export const getDistricts = (stateCode) =>
  request(`/locations/districts?state_code=${encodeURIComponent(stateCode)}`);

export const search = (body) =>
  request("/search", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });

// Opt in to the completion email for an already-running scrape (the loading-page
// "email it to me" button). The address is taken from the JWT server-side.
export const enableJobNotify = (jobId) =>
  request(`/jobs/${jobId}/notify`, { method: "POST" });

export const getProfile = (advocateId, { state_code = "", dist_code = "", district_name = "" } = {}) =>
  request(
    `/advocates/${advocateId}/profile?state_code=${encodeURIComponent(state_code)}` +
      `&dist_code=${encodeURIComponent(dist_code)}&district_name=${encodeURIComponent(district_name)}`
  );

// Fetch the rendered report HTML with the Bearer header attached. The caller
// prints it from a hidden iframe (see Profile.jsx), so the token never lands in
// a URL and no new tab is opened.
export async function fetchReportHtml(advocateId) {
  const token = await getToken();
  const r = await fetch(`${API}/advocates/${advocateId}/report.html`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!r.ok) {
    let detail = r.statusText;
    try {
      detail = (await r.json()).detail || detail;
    } catch (_) {}
    const err = new Error(detail);
    err.status = r.status;
    throw err;
  }
  return r.text();
}

// Open an SSE stream for a scrape job. `onEvent(eventName, data)` is called for
// each progress event. Returns the EventSource so the caller can close it.
export async function streamJob(jobId, onEvent) {
  const token = await getToken();
  const url = `${API}/jobs/${jobId}/stream?access_token=${encodeURIComponent(token)}`;
  const es = new EventSource(url);
  const events = [
    "snapshot", "running", "search_complex", "cases_found",
    "case_enriched", "done", "error", "cancelled",
  ];
  for (const ev of events) {
    es.addEventListener(ev, (e) => {
      let data = {};
      try { data = JSON.parse(e.data || "{}"); } catch (_) {}
      onEvent(ev, data);
    });
  }
  return es;
}
