"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSession } from "next-auth/react";
import { AnimatePresence, motion } from "framer-motion";
import { getProfile, search, streamJob } from "../lib/backend";
import { SESSION_EXPIRED_MSG, isAuthError } from "../lib/constants";
import { viewVariants } from "../components/anim";
import { Loader } from "../components/Icons";
import TopBar from "../components/TopBar";
import SignIn from "../components/SignIn";
import SearchView from "../components/SearchView";
import ProgressView from "../components/ProgressView";
import Profile from "../components/Profile";
import Toasts from "../components/Toasts";
import PortalBanner from "../components/PortalBanner";
import PortalModal from "../components/PortalModal";

// The profile a user is viewing is encoded in the URL as query params so the page
// survives a reload and the link can be shared. Only the advocate id + scope are
// needed; build_profile rebuilds the identical page from them.
//   /?adv=<id>&sc=<state_code>&dc=<dist_code>&dn=<district_name>
function writeProfileUrl(advocateId, scope = {}) {
  const qs = new URLSearchParams({ adv: String(advocateId) });
  if (scope.state_code) qs.set("sc", scope.state_code);
  if (scope.dist_code) qs.set("dc", scope.dist_code);
  if (scope.district_name) qs.set("dn", scope.district_name);
  // replaceState (not push) so the back button doesn't cycle through every profile.
  window.history.replaceState(null, "", `?${qs.toString()}`);
}

function clearProfileUrl() {
  window.history.replaceState(null, "", window.location.pathname);
}

export default function Page() {
  const { data: session, status } = useSession();
  const [view, setView] = useState("search"); // search | progress | profile
  // True when the URL already names a profile (a reload or shared link). Known on
  // the very first render so we can hold the loading screen instead of flashing the
  // search view before the async restore finishes. Hydration-safe: SSG has no
  // window (-> false), and the first client render shows the spinner regardless
  // because status === "loading".
  const [restoring, setRestoring] = useState(
    () => typeof window !== "undefined" && new URLSearchParams(window.location.search).has("adv")
  );
  const [job, setJob] = useState({ progress: 0, message: "" });
  const [liveCases, setLiveCases] = useState([]);
  const [profile, setProfile] = useState(null);
  const [toasts, setToasts] = useState([]);
  const [portalDown, setPortalDown] = useState(false);
  const [portalModalOpen, setPortalModalOpen] = useState(false);
  const esRef = useRef(null);
  const scopeRef = useRef(null);
  const toastId = useRef(0);
  const restoredRef = useRef(false);

  const dismiss = useCallback((id) => {
    setToasts((t) => t.filter((x) => x.id !== id));
  }, []);

  // Top-right notification. Non-auth errors auto-dismiss after 5s; auth/session
  // errors are rewritten to a clear instruction and stay until the user closes
  // them. Toasts are de-duplicated by message so repeat failures (e.g. the same
  // 401 firing twice) only ever show one notification.
  const notify = useCallback((message, type = "error") => {
    let msg = message;
    let sticky = false;
    if (isAuthError(message)) {
      msg = SESSION_EXPIRED_MSG;
      sticky = true;
    }
    const id = ++toastId.current;
    setToasts((t) => (t.some((x) => x.message === msg) ? t : [...t, { id, message: msg, type, sticky }]));
    if (!sticky) {
      setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5000);
    }
  }, []);

  // The source eCourts portal is down (503). Always raises the persistent top
  // banner; ``modal`` also pops the explainer dialog and ``redirect`` sends the
  // user back to the homepage (used when a running scrape fails mid-stream).
  const handlePortalDown = useCallback((opts = {}) => {
    setPortalDown(true);
    if (opts.modal) setPortalModalOpen(true);
    if (opts.redirect) {
      if (esRef.current) { esRef.current.close(); esRef.current = null; }
      setView("search");
    }
  }, []);

  function reset() {
    if (esRef.current) { esRef.current.close(); esRef.current = null; }
    clearProfileUrl();
    setView("search");
    setJob({ progress: 0, message: "" });
    setLiveCases([]);
    setProfile(null);
    // The "New search" button at the foot of a long profile fires this while the
    // window is scrolled far down. The shorter SearchView mounts at the top of
    // <main>, so without resetting scroll the viewport sits in empty space below
    // it and the search form looks like it never rendered.
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  const loadProfile = useCallback(async (advocateId, scope) => {
    const p = await getProfile(advocateId, scope);
    setProfile(p);
    setView("profile");
    // Encode the (canonical) profile in the URL so a reload restores it and the
    // link is shareable. Skip the "not found" placeholder — there's nothing to share.
    if (p.found) writeProfileUrl(p.advocate_id ?? advocateId, scope);
  }, []);

  async function onResult(res, scope) {
    scopeRef.current = scope;
    if (res.status === "ready") {
      await loadProfile(res.advocate_id, scope);
      return;
    }
    // scraping: stream live progress
    setView("progress");
    setJob({ progress: 2, message: "Queued…", phase: "running" });
    setLiveCases([]);
    const es = await streamJob(res.job_id, (ev, data) => {
      if (ev === "case_enriched") {
        setLiveCases((prev) => [data, ...prev].slice(0, 200));
      }
      // Enrich the job state so the staged timeline + counters can render.
      setJob((j) => {
        const next = { ...j };
        if (typeof data.progress === "number") next.progress = Math.max(j.progress || 0, data.progress);
        if (data.message) next.message = data.message;
        if (data.phase) next.phase = data.phase;
        if (ev === "search_complex") { next.searchIndex = data.index; next.searchTotal = data.total; }
        if (ev === "cases_found") next.casesFound = data.unique_cases;
        if (ev === "case_enriched") { next.enrichIndex = data.index; next.enrichTotal = data.total; }
        if (ev === "done" || (ev === "snapshot" && data.status === "done")) {
          next.phase = "done";
          next.progress = 100;
          if (data.result?.unique_cases != null) next.casesFound = data.result.unique_cases;
        }
        return next;
      });
      if ((ev === "snapshot" && data.status === "done") || ev === "done") {
        if (es) es.close();
        loadProfile(data.advocate_id, scopeRef.current).catch((e) => notify(e.message));
      }
      // Source portal is down: redirect home, raise the banner + explainer modal.
      if (ev === "error" && data && data.portal_down) {
        if (es) es.close();
        handlePortalDown({ modal: true, redirect: true });
        return;
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

  // On first authenticated load, restore the profile named in the URL (a reload or
  // a shared link). Runs once; the normal fresh-search flow has no ``adv`` param so
  // this is a no-op there. A logged-out recipient hits <SignIn /> first, then this
  // fires after they sign back in (their query string survives via callbackUrl).
  useEffect(() => {
    if (status !== "authenticated" || restoredRef.current) return;
    const params = new URLSearchParams(window.location.search);
    const adv = params.get("adv");
    if (!adv) { setRestoring(false); return; }
    restoredRef.current = true;
    const scope = {
      state_code: params.get("sc") || "",
      dist_code: params.get("dc") || "",
      district_name: params.get("dn") || "",
    };
    scopeRef.current = scope;
    loadProfile(Number(adv), scope)
      .catch((e) => {
        notify(e.message);
        clearProfileUrl();
        setView("search");
      })
      // Drop the restore gate once it settles: on success ``view`` is already
      // "profile"; on failure this lets the search view render with the error toast.
      .finally(() => setRestoring(false));
  }, [status, loadProfile, notify]);

  // Hold the loading screen through a pending profile restore so the search view
  // never flashes before the shared/reloaded profile is ready. ``session &&`` keeps
  // a logged-out recipient on <SignIn /> below; ``view !== "profile"`` drops the
  // spinner the instant the profile is set (it then animates in normally).
  if (status === "loading" || (session && restoring && view !== "profile")) {
    return (
      <>
        <TopBar session={session} />
        <div className="center">
          <div style={{ color: "var(--muted)", display: "grid", placeItems: "center", gap: 12 }}>
            <span className="spin"><Loader size={26} /></span>
            Loading…
          </div>
        </div>
      </>
    );
  }
  if (!session) {
    return (<><TopBar session={null} /><SignIn /></>);
  }

  return (
    <>
      <TopBar session={session} />
      <AnimatePresence>{portalDown && <PortalBanner key="banner" />}</AnimatePresence>
      <Toasts toasts={toasts} onDismiss={dismiss} />

      <main>
        <AnimatePresence mode="wait">
          {view === "search" && (
            <motion.div key="search" variants={viewVariants} initial="initial" animate="animate" exit="exit">
              <SearchView onResult={onResult} notify={notify} onPortalDown={handlePortalDown} />
            </motion.div>
          )}
          {view === "progress" && (
            <motion.div key="progress" variants={viewVariants} initial="initial" animate="animate" exit="exit">
              <ProgressView job={job} liveCases={liveCases} />
            </motion.div>
          )}
          {view === "profile" && (
            <motion.div key="profile" variants={viewVariants} initial="initial" animate="animate" exit="exit">
              <Profile profile={profile} onReset={reset} />
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      <AnimatePresence>
        {portalModalOpen && <PortalModal key="portal-modal" onClose={() => setPortalModalOpen(false)} />}
      </AnimatePresence>
    </>
  );
}
