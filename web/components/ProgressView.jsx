"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { liveItem, fadeUp, EASE } from "./anim";
import { Check, Loader, Mail } from "./Icons";

// Stage pipeline. `currentStage` is derived from the latest SSE phase + counters
// in `deriveStage` below; "Summarizing" has no backend event — it's the gap
// between the last enrich and the `done` event.
const STAGES = [
  { key: "connect", title: "Connecting to court portal", meta: () => "Establishing a secure session" },
  {
    key: "search",
    title: "Searching court records",
    meta: (j) => (j.searchTotal ? `Court ${j.searchIndex || 0} of ${j.searchTotal}` : "Scanning court complexes"),
  },
  {
    key: "found",
    title: "Locating cases",
    meta: (j) => (j.casesFound != null ? `${j.casesFound} cases found` : "Collating matching filings"),
  },
  {
    key: "enrich",
    title: "Loading case details",
    meta: (j) => (j.enrichTotal ? `${j.enrichIndex || 0} of ${j.enrichTotal}` : "Fetching parties, courts & outcomes"),
  },
  { key: "summary", title: "Summarizing the portfolio", meta: () => "Compiling stats & narrative" },
  { key: "done", title: "Profile ready", meta: () => "Opening profile…" },
];

function deriveStage(j) {
  const phase = j.phase || "";
  if (phase === "done") return 5;
  if (phase === "case_enriched") {
    if (j.enrichTotal > 0 && (j.enrichIndex || 0) >= j.enrichTotal) return 4; // summarizing
    return 3;
  }
  if (phase === "cases_found") return 2;
  if (phase === "search_complex") return 1;
  return 0; // running / queued
}

export default function ProgressView({ job = {}, liveCases = [], email, notify = false, onEnableNotify }) {
  const progress = Math.max(2, Math.round(job.progress || 0));
  const current = deriveStage(job);
  const isDone = job.phase === "done";
  const enriched = job.enrichIndex || liveCases.length;

  const [sending, setSending] = useState(false);
  const [enableError, setEnableError] = useState(false);

  async function handleEnable() {
    setSending(true);
    setEnableError(false);
    try {
      await onEnableNotify();
    } catch (_) {
      setEnableError(true);
    } finally {
      setSending(false);
    }
  }

  // Only meaningful while the scrape is still running and we know the user's email.
  const showEmailBar = email && !isDone;

  return (
    <motion.div className="wrap" variants={fadeUp} initial="initial" animate="animate">
      <div className="hero-head">
        <span className="eyebrow"><span className="dot" /> Live from public court records</span>
        <h1 className="hero-title">Building this profile…</h1>
        <p className="hero-sub">
          We're fetching everything live — this can take a few minutes. You can watch it happen below.
        </p>
      </div>

      {showEmailBar && (
        <AnimatePresence mode="wait" initial={false}>
          {notify ? (
            <motion.div
              key="email-on"
              className="email-bar"
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.3, ease: EASE }}
            >
              <span className="eb-ic"><Mail size={18} /></span>
              <span className="eb-text">
                We'll email your report to <b>{email}</b> when it's ready — you can safely close this tab.
              </span>
              <span className="eb-badge"><Check size={13} /> Email on</span>
            </motion.div>
          ) : (
            <motion.div
              key="email-off"
              className="email-bar cta"
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.3, ease: EASE }}
            >
              <span className="eb-ic"><Mail size={18} /></span>
              <span className="eb-text">
                {enableError
                  ? "Couldn't enable email just now — please try again."
                  : <>In no rush? We'll email the finished report to <b>{email}</b> so you don't have to wait here.</>}
              </span>
              <button className="btn small" type="button" onClick={handleEnable} disabled={sending}>
                {sending ? <><Loader size={14} className="spin" /> Enabling…</> : "Email it to me"}
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      )}

      <div className="progress-grid">
        {/* left: progress + stepper */}
        <div className="prog-panel">
          <div className="prog-top">
            <div>
              <div className="prog-pct">{progress}%</div>
              <div className="prog-msg">{job.message || "Starting…"}</div>
            </div>
          </div>
          <div className="bar">
            <motion.span
              animate={{ width: `${progress}%` }}
              transition={{ duration: 0.5, ease: EASE }}
            />
          </div>

          <div className="stepper">
            {STAGES.map((stage, i) => {
              const state = isDone || i < current ? "done" : i === current ? "active" : "pending";
              return (
                <div className={`step ${state}`} key={stage.key}>
                  <div className="marker">
                    <span className="dot">
                      {state === "done" ? (
                        <Check size={14} />
                      ) : state === "active" ? (
                        <Loader size={13} className="spin" />
                      ) : (
                        <span style={{ fontSize: 11, fontWeight: 700 }}>{i + 1}</span>
                      )}
                    </span>
                    <span className="conn" />
                  </div>
                  <div className="body">
                    <div className="st-title">{stage.title}</div>
                    <div className="st-meta">{stage.meta(job)}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* right: live feed */}
        <div className="live-panel">
          <div className="live-head">
            <h3><span className="live-pulse" /> Live case feed</h3>
            <span className="live-count">
              {job.casesFound != null && <><b>{job.casesFound}</b> found · </>}
              <b>{enriched}</b> loaded
            </span>
          </div>

          {liveCases.length === 0 ? (
            <div className="live-empty">Cases will appear here as we load them…</div>
          ) : (
            <div className="live-list">
              <AnimatePresence initial={false}>
                {liveCases.map((c) => (
                  <motion.div
                    className="live-item"
                    key={c.cnr}
                    layout
                    variants={liveItem}
                    initial="initial"
                    animate="animate"
                  >
                    <div>
                      <span className="li-no">{c.case_number || c.cnr}</span>
                      {c.petitioner ? (
                        <span className="li-parties"> — {c.petitioner} vs {c.respondent || "—"}</span>
                      ) : null}
                    </div>
                    {c.court ? <div className="li-court">{c.court}</div> : null}
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}
