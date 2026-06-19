"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence, animate } from "framer-motion";
import { fetchReportHtml } from "../lib/backend";
import { fadeUp, staggerParent, EASE } from "./anim";
import {
  FileText, CheckCircle, Clock, Check, X, Landmark, Scale, Users,
  Sparkles, Activity, Download, Plus, SearchIcon,
} from "./Icons";

function pct(n, total) {
  return total > 0 ? Math.round((n / total) * 100) : 0;
}

function initials(name) {
  const parts = (name || "").trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] || "") + (parts[1]?.[0] || "")).toUpperCase() || "?";
}

// Animated number that counts up from 0 on mount.
function CountUp({ value }) {
  const [display, setDisplay] = useState(0);
  useEffect(() => {
    const controls = animate(0, value || 0, {
      duration: 0.9,
      ease: "easeOut",
      onUpdate: (v) => setDisplay(Math.round(v)),
    });
    return () => controls.stop();
  }, [value]);
  return <>{display}</>;
}

function StatCards({ stats }) {
  const items = [
    ["Total cases", stats.total, FileText, true],
    ["Disposed", stats.disposed, CheckCircle],
    ["Pending", stats.pending, Clock],
    ["Granted", stats.allowed_granted, Check],
    ["Dismissed", stats.rejected_dismissed, X],
    ["Courts", stats.courts_establishments, Landmark, true],
  ];
  return (
    <motion.div className="cards" variants={staggerParent} initial="initial" animate="animate">
      {items.map(([label, n, Icon, feature]) => (
        <motion.div className={`stat ${feature ? "feature-stat" : ""}`} key={label} variants={fadeUp}>
          <div className="n"><CountUp value={n} /></div>
          <div className="l">{label}</div>
          <span className="st-ic" aria-hidden="true"><Icon size={48} /></span>
        </motion.div>
      ))}
    </motion.div>
  );
}

function OutcomeViz({ stats }) {
  const t = stats.total;
  const unknown = Math.max(t - stats.disposed - stats.pending, 0);
  const dispPct = pct(stats.disposed, t);

  const statusRows = [
    ["Disposed", pct(stats.disposed, t), "fill-won", "#2e7d57"],
    ["Pending", pct(stats.pending, t), "fill-gold", "#c8a24b"],
    ["Unknown", pct(unknown, t), "fill-other", "#7a839a"],
  ];
  const outcomeRows = [
    ["Granted", pct(stats.allowed_granted, t), "fill-won"],
    ["Dismissed", pct(stats.rejected_dismissed, t), "fill-lost"],
    ["Other", pct(stats.other_unknown, t), "fill-other"],
  ];

  return (
    <div className="section">
      <h2 className="section-title"><span className="tk"><Activity size={18} /></span> At a glance</h2>

      <div className="glance-head">
        <motion.div
          className="ring"
          initial={{ "--p": 0 }}
          animate={{ "--p": dispPct }}
          transition={{ duration: 0.9, ease: EASE }}
          style={{ "--p": dispPct }}
        >
          <div className="ring-in">
            <div className="rn">{dispPct}%</div>
            <div className="rl">Disposed</div>
          </div>
        </motion.div>
        <div className="glance-legend">
          {statusRows.map(([label, p, , color]) => (
            <div className="legend-row" key={label}>
              <span className="sw" style={{ background: color }} />
              {label} — <b>{p}%</b>
            </div>
          ))}
        </div>
      </div>

      <div className="viz-group">
        <div className="viz-group-title">Case status</div>
        {statusRows.map(([label, p, cls]) => <VizRow key={label} label={label} p={p} cls={cls} />)}
      </div>
      <div className="viz-group">
        <div className="viz-group-title">Outcomes</div>
        {outcomeRows.map(([label, p, cls]) => <VizRow key={label} label={label} p={p} cls={cls} />)}
      </div>
    </div>
  );
}

function VizRow({ label, p, cls }) {
  return (
    <div className="viz-row">
      <span className="label">{label}</span>
      <span className="track">
        <motion.span
          className={cls}
          initial={{ width: 0 }}
          whileInView={{ width: `${p}%` }}
          viewport={{ once: true }}
          transition={{ duration: 0.8, ease: EASE }}
        />
      </span>
      <span className="vv">{p}%</span>
    </div>
  );
}

function CaseCard({ c, index }) {
  const status = (c.status || "Unknown").toLowerCase();
  return (
    <motion.div
      className="case"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, ease: EASE, delay: Math.min(index, 12) * 0.03 }}
    >
      <div className="row1">
        <div>
          <span className="cno">{c.case_number || c.cnr}</span>
          {c.case_type ? <div className="ctype">{c.case_type}</div> : null}
        </div>
        <span className={`status-badge ${status}`}>{c.status}</span>
      </div>
      <div className="parties">
        {c.petitioner || "—"} <span className="vs">vs</span> {c.respondent || "—"}
      </div>
      <div className="metas">
        {c.court ? <span className="tag">{c.court}</span> : null}
        {c.judge ? <span className="tag">{c.judge}</span> : null}
        {c.decision_date ? <span className="tag">{c.decision_date}</span> : null}
        {c.nature_of_disposal ? (
          <span className={`tag ${c.outcome_class}`}>{c.nature_of_disposal}</span>
        ) : null}
      </div>
      {c.co_advocates && c.co_advocates.length ? (
        <div className="co"><Users size={13} className="ci" /> {c.co_advocates.join(", ")}</div>
      ) : null}
    </motion.div>
  );
}

function CasesSection({ cases }) {
  const [filter, setFilter] = useState("all");
  const [q, setQ] = useState("");

  const filtered = useMemo(() => {
    return cases.filter((c) => {
      if (filter === "disposed" && c.status !== "Disposed") return false;
      if (filter === "pending" && c.status !== "Pending") return false;
      if (filter === "won" && c.outcome_class !== "won") return false;
      if (filter === "lost" && c.outcome_class !== "lost") return false;
      if (q) {
        const hay = `${c.case_number} ${c.petitioner} ${c.respondent} ${c.court} ${c.judge} ${c.nature_of_disposal}`.toLowerCase();
        if (!hay.includes(q.toLowerCase())) return false;
      }
      return true;
    });
  }, [cases, filter, q]);

  const chips = [
    ["all", "All"],
    ["disposed", "Disposed"],
    ["pending", "Pending"],
    ["won", "Granted"],
    ["lost", "Dismissed"],
  ];

  return (
    <div className="section">
      <h2 className="section-title"><span className="tk"><FileText size={18} /></span> Cases ({filtered.length})</h2>
      <div className="cases-toolbar">
        <div className="filters">
          {chips.map(([k, label]) => (
            <button key={k} className={`chip ${filter === k ? "active" : ""}`} onClick={() => setFilter(k)}>
              {filter === k && <motion.span layoutId="chip-bg" className="chip-bg" transition={{ duration: 0.25, ease: EASE }} />}
              <span className="lbl">{label}</span>
            </button>
          ))}
        </div>
        <div className="searchbox-wrap">
          <span className="sic"><SearchIcon size={16} /></span>
          <input
            className="searchbox"
            placeholder="Search case number, parties, court, judge…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
      </div>
      {filtered.length === 0 ? (
        <div className="empty">No matching cases.</div>
      ) : (
        filtered.map((c, i) => <CaseCard key={c.cnr} c={c} index={i} />)
      )}
    </div>
  );
}

function CoAdvocates({ coAdvocates }) {
  if (!coAdvocates || !coAdvocates.length) return null;
  const max = Math.max(...coAdvocates.map((x) => x.count), 1);
  return (
    <div className="section">
      <h2 className="section-title"><span className="tk"><Users size={18} /></span> Frequent co-advocates</h2>
      {coAdvocates.map((x) => (
        <div className="coadv" key={x.name}>
          <span className="name">{x.name}</span>
          <span className="track">
            <motion.span
              initial={{ width: 0 }}
              whileInView={{ width: `${(x.count / max) * 100}%` }}
              viewport={{ once: true }}
              transition={{ duration: 0.7, ease: EASE }}
            />
          </span>
          <span className="ct">{x.count}</span>
        </div>
      ))}
    </div>
  );
}

export default function Profile({ profile, onReset }) {
  if (!profile) return null;

  async function openReport(e) {
    e.preventDefault();
    // Fetch the report HTML authenticated (Bearer header) and print it from a
    // hidden iframe in this tab. The report's own @media print stylesheet turns
    // it into a clean PDF, so the user just picks "Save as PDF" — no new tab and
    // no token in any URL.
    let html;
    try {
      html = await fetchReportHtml(profile.advocate_id);
    } catch (err) {
      alert("Please sign in again to download the report.");
      return;
    }

    const iframe = document.createElement("iframe");
    iframe.style.position = "fixed";
    iframe.style.right = "0";
    iframe.style.bottom = "0";
    iframe.style.width = "0";
    iframe.style.height = "0";
    iframe.style.border = "0";
    document.body.appendChild(iframe);

    let cleaned = false;
    const cleanup = () => {
      if (cleaned) return;
      cleaned = true;
      iframe.remove();
    };

    iframe.onload = async () => {
      const win = iframe.contentWindow;
      // Wait for the report's webfonts so the printed layout isn't measured
      // against fallback metrics; fall back to a short timeout if unsupported.
      try {
        await Promise.race([
          win.document.fonts?.ready,
          new Promise((r) => setTimeout(r, 300)),
        ]);
      } catch (_) {}
      win.focus();
      win.onafterprint = cleanup;
      win.print();
      // Safety net in case onafterprint never fires (some browsers).
      setTimeout(cleanup, 60000);
    };

    const doc = iframe.contentWindow.document;
    doc.open();
    doc.write(html);
    doc.close();
  }

  if (!profile.found) {
    return (
      <div className="wrap">
        <div className="section">
          <div className="empty">
            <div className="alert-icon" style={{ margin: "0 auto 16px", background: "var(--surface-3)", color: "var(--muted)", border: "1px solid var(--line)", width: 54, height: 54, borderRadius: "50%", display: "grid", placeItems: "center" }}>
              <SearchIcon size={24} />
            </div>
            <h2 className="serif">No records found</h2>
            <p>No matching advocate for "{profile.name}" in {profile.district} yet.</p>
            <button className="btn" onClick={onReset} style={{ marginTop: 14 }}><Plus size={16} /> New search</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="wrap">
      <motion.div className="profile-hero" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: EASE }}>
        <div className="ph-row">
          <span className="ph-avatar">{initials(profile.name)}</span>
          <div className="ph-main">
            <h1>{profile.name}</h1>
            <div className="ph-meta">
              <span className="pill"><Scale size={12} /> {profile.district}</span>
              <span className="pill">{profile.stats.total} cases</span>
              <span className="pill">Compiled {profile.generated}</span>
            </div>
            {profile.name_variants && profile.name_variants.length > 1 ? (
              <div className="ph-variants">Includes filings as: {profile.name_variants.join(" · ")}</div>
            ) : null}
          </div>
          <div className="ph-actions">
            <a className="btn" href="#" onClick={openReport}><Download size={16} /> Download PDF</a>
            <button className="btn ghost" onClick={onReset}><Plus size={16} /> New search</button>
          </div>
        </div>
      </motion.div>

      <div className="profile-layout">
        <aside className="profile-rail">
          <StatCards stats={profile.stats} />
        </aside>

        <div className="profile-main">
          <OutcomeViz stats={profile.stats} />

          {profile.ai_summary ? (
            <div className="section">
              <h2 className="section-title"><span className="tk"><Sparkles size={18} /></span> Profile summary</h2>
              <div className="ai-text">
                {profile.ai_summary.split(/\n\n+/).map((p, i) => <p key={i}>{p}</p>)}
              </div>
            </div>
          ) : null}

          <CasesSection cases={profile.cases} />
          <CoAdvocates coAdvocates={profile.co_advocates} />
          <div className="profile-foot-action">
            <button className="btn" onClick={onReset}><Plus size={16} /> New search</button>
          </div>
        </div>
      </div>

      <div className="footnote">
        Auto-generated from public eCourts district-court records. Coverage is limited to the
        selected district. Verify independently before relying on this profile.
      </div>
    </div>
  );
}
