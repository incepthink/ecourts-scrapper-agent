"use client";

import { signIn } from "next-auth/react";
import { motion } from "framer-motion";
import { staggerParent, fadeUp, EASE } from "./anim";
import { GoogleMark, SearchIcon, Activity, Landmark } from "./Icons";

const FEATURES = [
  { icon: SearchIcon, t: "Search by name", d: "Find any advocate in a district and pull their full filing history." },
  { icon: Activity, t: "See outcomes", d: "Disposed vs pending, allowed vs dismissed — at a glance." },
  { icon: Landmark, t: "Verify the source", d: "Every figure is compiled from public eCourts records." },
];

export default function SignIn() {
  return (
    <div className="landing">
      <motion.div
        className="landing-grid"
        variants={staggerParent}
        initial="initial"
        animate="animate"
      >
        <motion.div variants={fadeUp}>
          <span className="eyebrow"><span className="dot" /> Know who you're hiring</span>
          <h1>
            Know your advocate <br />
            <span className="accent">before</span> you hire
          </h1>
          <p className="lede">
            Search any advocate by name and district and see their full case
            portfolio — outcomes, courts, and history — compiled from public
            eCourts records.
          </p>
          <div className="landing-cta">
            <button className="btn btn-google lg" onClick={() => signIn("google", { callbackUrl: window.location.href })}>
              <GoogleMark /> Continue with Google
            </button>
            <span className="trust">Free · No data stored on your behalf</span>
          </div>

          <motion.div className="features" variants={staggerParent}>
            {FEATURES.map(({ icon: Icon, t, d }) => (
              <motion.div className="feature" key={t} variants={fadeUp}>
                <div className="ft">{t}</div>
                <div className="fd">{d}</div>
                <span className="fic" aria-hidden="true"><Icon size={46} /></span>
              </motion.div>
            ))}
          </motion.div>
        </motion.div>

        <motion.div
          variants={fadeUp}
          initial={{ opacity: 0, y: 24, rotate: -1 }}
          animate={{ opacity: 1, y: 0, rotate: 0, transition: { duration: 0.6, ease: EASE, delay: 0.15 } }}
        >
          <PreviewCard />
        </motion.div>
      </motion.div>
    </div>
  );
}

// A faux profile card that previews what users get — purely illustrative.
function PreviewCard() {
  const bars = [
    ["Disposed", 80],
    ["Pending", 20],
    ["Allowed", 60],
  ];
  return (
    <div className="preview-card">
      <span className="preview-tag">Sample</span>
      <div className="pc-name">Tanveer Nizam</div>
      <div className="pc-sub">Mumbai CMM Courts · 10 cases</div>
      <div className="pc-stats">
        <div className="pc-stat"><div className="n">10</div><div className="l">Total</div></div>
        <div className="pc-stat"><div className="n">8</div><div className="l">Disposed</div></div>
        <div className="pc-stat"><div className="n">4</div><div className="l">Courts</div></div>
      </div>
      <div className="pc-bars">
        {bars.map(([l, w]) => (
          <div className="pc-bar" key={l}>
            <span className="lbl">{l}</span>
            <span className="trk">
              <motion.span
                initial={{ width: 0 }}
                animate={{ width: `${w}%` }}
                transition={{ duration: 0.9, ease: EASE, delay: 0.5 }}
              />
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
