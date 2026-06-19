"use client";

import { useMemo, useState } from "react";
import { reportUrl } from "../lib/backend";

function pct(n, total) {
  return total > 0 ? Math.round((n / total) * 100) : 0;
}

function StatCards({ stats }) {
  const items = [
    ["Total cases", stats.total],
    ["Disposed", stats.disposed],
    ["Pending", stats.pending],
    ["Allowed / Granted", stats.allowed_granted],
    ["Rejected / Dismissed", stats.rejected_dismissed],
    ["Courts", stats.courts_establishments],
  ];
  return (
    <div className="cards">
      {items.map(([label, n]) => (
        <div className="stat" key={label}>
          <div className="n">{n}</div>
          <div className="l">{label}</div>
        </div>
      ))}
    </div>
  );
}

function OutcomeViz({ stats }) {
  const t = stats.total;
  const unknown = Math.max(t - stats.disposed - stats.pending, 0);
  const rows = [
    ["Disposed", pct(stats.disposed, t), "fill-won"],
    ["Pending", pct(stats.pending, t), "fill-gold"],
    ["Unknown", pct(unknown, t), "fill-other"],
    ["Allowed / Granted", pct(stats.allowed_granted, t), "fill-won"],
    ["Rejected / Dismissed", pct(stats.rejected_dismissed, t), "fill-lost"],
    ["Other", pct(stats.other_unknown, t), "fill-other"],
  ];
  return (
    <div className="section">
      <h2>At a glance</h2>
      {rows.map(([label, p, cls]) => (
        <div className="viz-row" key={label}>
          <span className="label">{label}</span>
          <span className="track"><span className={cls} style={{ width: `${p}%` }} /></span>
          <span style={{ width: 38, textAlign: "right", color: "var(--muted)" }}>{p}%</span>
        </div>
      ))}
    </div>
  );
}

function CaseCard({ c }) {
  const status = (c.status || "Unknown").toLowerCase();
  return (
    <div className="case">
      <div className="row1">
        <span className="cno">{c.case_number || c.cnr}</span>
        <span className={`tag ${status}`}>{c.status}</span>
      </div>
      {c.case_type ? <div style={{ color: "var(--muted)", fontSize: 13 }}>{c.case_type}</div> : null}
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
        <div className="co">With: {c.co_advocates.join(", ")}</div>
      ) : null}
    </div>
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
    ["won", "Allowed / Granted"],
    ["lost", "Rejected / Dismissed"],
  ];

  return (
    <div className="section">
      <h2>Cases ({filtered.length})</h2>
      <div className="filters">
        {chips.map(([k, label]) => (
          <button key={k} className={`chip ${filter === k ? "active" : ""}`} onClick={() => setFilter(k)}>
            {label}
          </button>
        ))}
      </div>
      <input
        className="searchbox"
        placeholder="Search case number, parties, court, judge…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      {filtered.length === 0 ? (
        <div className="empty">No matching cases.</div>
      ) : (
        filtered.map((c) => <CaseCard key={c.cnr} c={c} />)
      )}
    </div>
  );
}

function CoAdvocates({ coAdvocates }) {
  if (!coAdvocates || !coAdvocates.length) return null;
  const max = Math.max(...coAdvocates.map((x) => x.count), 1);
  return (
    <div className="section">
      <h2>Frequent co-advocates</h2>
      {coAdvocates.map((x) => (
        <div className="coadv" key={x.name}>
          <span className="name">{x.name}</span>
          <span className="track"><span style={{ width: `${(x.count / max) * 100}%` }} /></span>
          <span className="ct">{x.count}</span>
        </div>
      ))}
    </div>
  );
}

export default function Profile({ profile, onReset }) {
  if (!profile) return null;

  if (!profile.found) {
    return (
      <div className="panel">
        <div className="empty">
          <h2 className="serif">No records found</h2>
          <p>No matching advocate for “{profile.name}” in {profile.district} yet.</p>
          <button className="btn" onClick={onReset}>New search</button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="profile-hero">
        <h1>{profile.name}</h1>
        <div className="meta">
          Practising before {profile.district} · {profile.stats.total} cases · compiled {profile.generated}
        </div>
        {profile.name_variants && profile.name_variants.length > 1 ? (
          <div className="variants">Includes filings as: {profile.name_variants.join(" · ")}</div>
        ) : null}
      </div>

      <StatCards stats={profile.stats} />
      <OutcomeViz stats={profile.stats} />

      {profile.ai_summary ? (
        <div className="section">
          <h2>Profile summary</h2>
          <div className="ai-text">
            {profile.ai_summary.split(/\n\n+/).map((p, i) => <p key={i}>{p}</p>)}
          </div>
        </div>
      ) : null}

      <CasesSection cases={profile.cases} />
      <CoAdvocates coAdvocates={profile.co_advocates} />

      <div style={{ display: "flex", gap: 10, marginTop: 18 }}>
        <a className="btn" href={reportUrl(profile.advocate_id)} target="_blank" rel="noreferrer">
          Download as PDF
        </a>
        <button className="btn ghost" style={{ color: "var(--navy)", borderColor: "var(--line)" }} onClick={onReset}>
          New search
        </button>
      </div>

      <div className="footnote">
        Auto-generated from public eCourts district-court records. Coverage is limited to the
        selected district. Verify independently before relying on this profile.
      </div>
    </div>
  );
}
