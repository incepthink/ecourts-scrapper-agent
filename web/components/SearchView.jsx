"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { motion, AnimatePresence } from "framer-motion";
import { getStates, getDistricts, search } from "../lib/backend";
import { staggerParent, fadeUp } from "./anim";
import ConfirmModal from "./ConfirmModal";
import { MapPin, Building, UserIcon, Clock, FileText, Activity, Users, Download } from "./Icons";

// Persisted across refreshes so the user keeps their state/district selection.
const STATE_KEY = "ap.stateCode";
const DIST_KEY = "ap.distCode";

const GETS = [
  { icon: FileText, t: "Full case list", d: "Every filing with parties, court, judge and dates." },
  { icon: Activity, t: "Outcome breakdown", d: "Disposed, pending, allowed and dismissed at a glance." },
  { icon: Users, t: "Frequent co-advocates", d: "Who they most often appear alongside." },
  { icon: Download, t: "Downloadable report", d: "Export the whole portfolio as a PDF." },
];

export default function SearchView({ onResult, notify, onPortalDown }) {
  const { data: session } = useSession();
  const [states, setStates] = useState([]);
  const [districts, setDistricts] = useState([]);
  const [stateCode, setStateCode] = useState("");
  const [distCode, setDistCode] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [statesLoading, setStatesLoading] = useState(true);
  const [statesError, setStatesError] = useState(false);
  const [distLoading, setDistLoading] = useState(false);
  const [distError, setDistError] = useState(false);

  useEffect(() => {
    setStatesLoading(true);
    setStatesError(false);
    getStates()
      .then(setStates)
      .catch((e) => {
        setStatesError(true);
        if (e.status === 503) onPortalDown();
        else notify(e.message);
      })
      .finally(() => setStatesLoading(false));
  }, [notify, onPortalDown]);

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
    setDistError(false);
    if (!stateCode) return;
    setDistLoading(true);
    getDistricts(stateCode)
      .then(setDistricts)
      .catch((e) => {
        setDistError(true);
        if (e.status === 503) onPortalDown();
        else notify(e.message);
      })
      .finally(() => setDistLoading(false));
  }, [stateCode, notify, onPortalDown]);

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

  async function runSearch(notifyEmail) {
    setConfirming(false);
    setBusy(true);
    try {
      const res = await search({
        name, state_code: stateCode, dist_code: distCode, district_name: distName,
        notify_email: !!notifyEmail,
      });
      onResult(res, { name, state_code: stateCode, dist_code: distCode, district_name: distName }, !!notifyEmail);
    } catch (err) {
      if (err.status === 503) onPortalDown({ modal: true });
      else notify(err.message);
      setBusy(false);
    }
  }

  return (
    <div className="wrap">
      <motion.div className="hero-head" variants={fadeUp} initial="initial" animate="animate">
        <span className="eyebrow"><span className="dot" /> Step 1 of 1</span>
        <h1 className="hero-title">Find an advocate</h1>
        <p className="hero-sub">Select where they practise, then search by name.</p>
      </motion.div>

      <div className="search-grid">
        <motion.form
          className="search-card"
          onSubmit={submit}
          variants={staggerParent}
          initial="initial"
          animate="animate"
        >
          <motion.div className="step-label" variants={fadeUp}>
            <span className="num">1</span> Where do they practise?
            <span className="ln" />
          </motion.div>

          <motion.div className="field" variants={fadeUp}>
            <span className="lbl"><MapPin size={13} className="ix" /> State</span>
            {statesLoading ? (
              <div className="skeleton" style={{ height: 44, borderRadius: 12, width: "100%" }} />
            ) : (
              <select value={stateCode} onChange={onStateChange}>
                <option value="">{statesError ? "Error loading states" : "Select state…"}</option>
                {states.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
              </select>
            )}
          </motion.div>

          <motion.div className="field" variants={fadeUp}>
            <span className="lbl"><Building size={13} className="ix" /> District</span>
            {distLoading ? (
              <div className="skeleton" style={{ height: 44, borderRadius: 12, width: "100%" }} />
            ) : (
              <select value={distCode} onChange={onDistChange} disabled={!stateCode}>
                <option value="">
                  {!stateCode ? "Pick a state first" : distError ? "Error loading districts" : "Select district…"}
                </option>
                {districts.map((d) => <option key={d.code} value={d.code}>{d.name}</option>)}
              </select>
            )}
          </motion.div>

          <motion.div className="step-label" variants={fadeUp}>
            <span className="num">2</span> Who are you looking for?
            <span className="ln" />
          </motion.div>

          <motion.div className="field full has-icon" variants={fadeUp}>
            <span className="lbl"><UserIcon size={13} className="ix" /> Advocate name</span>
            <span className="field-ic"><UserIcon size={16} /></span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Tanveer Nizam"
            />
          </motion.div>

          {/* <motion.div className="notice" variants={fadeUp}>
            <Clock size={16} className="nic" />
            <span>
              If we don't already have this advocate, we fetch their record live from the court
              portal — this can take several minutes. You'll see live progress as it runs.
            </span>
          </motion.div> */}

          <motion.div className="full" variants={fadeUp}>
            <button className="btn lg block" type="submit" disabled={busy}>
              {busy ? "Searching…" : "Search advocate"}
            </button>
          </motion.div>
        </motion.form>

        <motion.aside
          className="aside-card"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0, transition: { delay: 0.18, duration: 0.4 } }}
        >
          <h3>What you'll get</h3>
          <p className="as-sub">A complete, source-linked portfolio for the advocate.</p>
          <div className="as-list">
            {GETS.map(({ icon: Icon, t, d }) => (
              <div className="as-item" key={t}>
                <span className="ck"><Icon size={13} /></span>
                <div>
                  <div className="tt">{t}</div>
                  <div className="dd">{d}</div>
                </div>
              </div>
            ))}
          </div>
        </motion.aside>
      </div>

      <AnimatePresence>
        {confirming && (
          <ConfirmModal
            name={name}
            distName={distName}
            stateName={stateName}
            email={session?.user?.email}
            onCancel={() => setConfirming(false)}
            onConfirm={runSearch}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
