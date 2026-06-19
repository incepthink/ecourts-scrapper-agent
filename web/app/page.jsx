"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { signIn, signOut, useSession } from "next-auth/react";
import { getStates, getDistricts, search, getProfile, streamJob } from "../lib/backend";
import Profile from "../components/Profile";

// Persisted across refreshes so the user keeps their state/district selection.
const STATE_KEY = "ap.stateCode";
const DIST_KEY = "ap.distCode";

function TopBar({ session }) {
  return (
    <div className="topbar">
      <div className="brand">
        <span className="mono">AP</span>
        <span>Advocate Profiles</span>
      </div>
      <div className="who">
        {session ? (
          <>
            <span>{session.user?.email}</span>
            <button className="btn ghost small" onClick={() => signOut()}>Sign out</button>
          </>
        ) : null}
      </div>
    </div>
  );
}

function SignIn() {
  return (
    <div className="center">
      <div>
        <h1 className="serif">Know your advocate before you hire</h1>
        <p>
          Search any advocate by name and district and see their full case portfolio —
          outcomes, courts, and history — compiled from public eCourts records.
        </p>
        <button className="btn" onClick={() => signIn("google")}>Sign in with Google</button>
      </div>
    </div>
  );
}

function SearchView({ onResult, notify }) {
  const [states, setStates] = useState([]);
  const [districts, setDistricts] = useState([]);
  const [stateCode, setStateCode] = useState("");
  const [distCode, setDistCode] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    getStates().then(setStates).catch((e) => notify(e.message));
  }, [notify]);

  // Restore the saved selection once, after mount (client-only — never read
  // localStorage during render). District-clearing lives in the state onChange,
  // so a restored district survives while its options load.
  useEffect(() => {
    const savedState = localStorage.getItem(STATE_KEY) || "";
    const savedDist = localStorage.getItem(DIST_KEY) || "";
    if (savedState) setStateCode(savedState);
    if (savedDist) setDistCode(savedDist);
  }, []);

  // Load districts for the current state (no clearing here — see onStateChange).
  useEffect(() => {
    setDistricts([]);
    if (stateCode) getDistricts(stateCode).then(setDistricts).catch((e) => notify(e.message));
  }, [stateCode, notify]);

  function onStateChange(e) {
    const v = e.target.value;
    setStateCode(v);
    setDistCode(""); // changing state invalidates the previous district
    if (v) localStorage.setItem(STATE_KEY, v);
    else localStorage.removeItem(STATE_KEY);
    localStorage.removeItem(DIST_KEY);
  }

  function onDistChange(e) {
    const v = e.target.value;
    setDistCode(v);
    if (v) localStorage.setItem(DIST_KEY, v);
    else localStorage.removeItem(DIST_KEY);
  }

  const distName = districts.find((d) => d.code === distCode)?.name || "";
  const stateName = states.find((s) => s.code === stateCode)?.name || "";

  function submit(e) {
    e.preventDefault();
    if (!name.trim() || !stateCode || !distCode) {
      notify("Pick a state, a district, and enter an advocate name.");
      return;
    }
    setConfirming(true); // confirm the name before committing to a scrape
  }

  async function runSearch() {
    setConfirming(false);
    setBusy(true);
    try {
      const res = await search({ name, state_code: stateCode, dist_code: distCode, district_name: distName });
      onResult(res, { name, state_code: stateCode, dist_code: distCode, district_name: distName });
    } catch (err) {
      notify(err.message);
      setBusy(false);
    }
  }

  return (
    <div className="wrap">
      <h1 className="hero-title">Find an advocate</h1>
      <p className="hero-sub">Select where they practise, then search by name.</p>
      <form className="search-card" onSubmit={submit}>
        <div className="field">
          <label>State</label>
          <select value={stateCode} onChange={onStateChange}>
            <option value="">Select state…</option>
            {states.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
          </select>
        </div>
        <div className="field">
          <label>District</label>
          <select value={distCode} onChange={onDistChange} disabled={!stateCode}>
            <option value="">{stateCode ? "Select district…" : "Pick a state first"}</option>
            {districts.map((d) => <option key={d.code} value={d.code}>{d.name}</option>)}
          </select>
        </div>
        <div className="field full">
          <label>Advocate name</label>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Tanveer Nizam" />
        </div>
        <div className="notice">
          If we don’t already have this advocate, we fetch their record live from the court
          portal — this can take several minutes. You’ll see progress as it runs.
        </div>
        <div className="full">
          <button className="btn" type="submit" disabled={busy}>
            {busy ? "Searching…" : "Search advocate"}
          </button>
        </div>
      </form>

      {confirming && (
        <div className="modal-backdrop" onClick={() => setConfirming(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Search this advocate?</h2>
            <p>We’ll compile the case portfolio for:</p>
            <div className="confirm-name">{name.trim()}</div>
            <div className="confirm-meta">
              Practising before {distName || "—"}{stateName ? `, ${stateName}` : ""}
            </div>
            <div className="confirm-note">
              If we don’t already have this advocate, we fetch their record live from the
              court portal — this can take several minutes.
            </div>
            <div className="modal-actions">
              <button className="btn secondary" type="button" onClick={() => setConfirming(false)}>
                Cancel
              </button>
              <button className="btn" type="button" onClick={runSearch}>
                Yes, search
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ProgressView({ job, liveCases }) {
  return (
    <div className="wrap">
      <h1 className="hero-title">Building this profile…</h1>
      <p className="hero-sub">Fetching live from public court records. This can take a few minutes.</p>
      <div className="panel">
        <div className="bar"><span style={{ width: `${job.progress || 2}%` }} /></div>
        <div className="prog-msg">{job.message || "Starting…"}</div>
        {liveCases.length ? (
          <div className="live-list">
            {liveCases.map((c) => (
              <div className="live-item" key={c.cnr}>
                <b>{c.case_number || c.cnr}</b>
                {c.petitioner ? ` — ${c.petitioner} vs ${c.respondent || "—"}` : ""}
                {c.court ? ` · ${c.court}` : ""}
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default function Page() {
  const { data: session, status } = useSession();
  const [view, setView] = useState("search"); // search | progress | profile
  const [job, setJob] = useState({ progress: 0, message: "" });
  const [liveCases, setLiveCases] = useState([]);
  const [profile, setProfile] = useState(null);
  const [toasts, setToasts] = useState([]);
  const esRef = useRef(null);
  const scopeRef = useRef(null);
  const toastId = useRef(0);

  const dismiss = useCallback((id) => {
    setToasts((t) => t.filter((x) => x.id !== id));
  }, []);

  // Transient top-right notification that auto-dismisses after 5s.
  const notify = useCallback((message, type = "error") => {
    const id = ++toastId.current;
    setToasts((t) => [...t, { id, message, type }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5000);
  }, []);

  function reset() {
    if (esRef.current) { esRef.current.close(); esRef.current = null; }
    setView("search");
    setJob({ progress: 0, message: "" });
    setLiveCases([]);
    setProfile(null);
  }

  async function loadProfile(advocateId, scope) {
    const p = await getProfile(advocateId, scope);
    setProfile(p);
    setView("profile");
  }

  async function onResult(res, scope) {
    scopeRef.current = scope;
    if (res.status === "ready") {
      await loadProfile(res.advocate_id, scope);
      return;
    }
    // scraping: stream live progress
    setView("progress");
    setJob({ progress: 2, message: "Queued…" });
    setLiveCases([]);
    const es = await streamJob(res.job_id, (ev, data) => {
      if (ev === "case_enriched") {
        setLiveCases((prev) => [data, ...prev].slice(0, 200));
      }
      if (data && typeof data.progress === "number") {
        setJob((j) => ({ progress: Math.max(j.progress, data.progress), message: data.message || j.message }));
      }
      if ((ev === "snapshot" && data.status === "done") || ev === "done") {
        if (es) es.close();
        loadProfile(data.advocate_id, scopeRef.current).catch((e) => notify(e.message));
      }
      // Only abort on a real server-sent error (it carries a message). The
      // browser also fires a generic, data-less "error" on transient reconnects
      // — ignore those so the stream can recover.
      if ((ev === "error" || ev === "cancelled") && data && data.message) {
        if (es) es.close();
        notify(data.message);
        setView("search");
      }
    });
    esRef.current = es;
  }

  useEffect(() => () => { if (esRef.current) esRef.current.close(); }, []);

  if (status === "loading") return <div className="center">Loading…</div>;
  if (!session) {
    return (<><TopBar session={null} /><SignIn /></>);
  }

  return (
    <>
      <TopBar session={session} />
      <div className="toast-wrap">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.type}`} onClick={() => dismiss(t.id)}>
            {t.message}
          </div>
        ))}
      </div>
      {view === "search" && <SearchView onResult={onResult} notify={notify} />}
      {view === "progress" && <ProgressView job={job} liveCases={liveCases} />}
      {view === "profile" && (
        <div className="wrap"><Profile profile={profile} onReset={reset} /></div>
      )}
    </>
  );
}
