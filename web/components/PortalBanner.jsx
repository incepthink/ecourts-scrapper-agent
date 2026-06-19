"use client";

import { motion } from "framer-motion";
import { PORTAL_DOWN_MSG } from "../lib/constants";
import VerifyButton from "./VerifyButton";

// Persistent (non-dismissible) banner shown while the source portal is down.
export default function PortalBanner() {
  return (
    <motion.div
      className="portal-banner"
      role="alert"
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <div className="pb-text">
        <span className="pb-dot" aria-hidden="true">●</span>
        <span>{PORTAL_DOWN_MSG}</span>
      </div>
      <div className="pb-actions">
        <VerifyButton className="pb-btn" />
        <button className="pb-btn" onClick={() => window.location.reload()}>Refresh</button>
      </div>
    </motion.div>
  );
}
