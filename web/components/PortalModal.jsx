"use client";

import { PORTAL_DOWN_MSG } from "../lib/constants";
import Modal from "./Modal";
import VerifyButton from "./VerifyButton";
import { AlertTriangle } from "./Icons";

// Explainer dialog raised when a running scrape fails because the source portal
// is down. Reassures the user it's the official site, not their connection.
export default function PortalModal({ onClose }) {
  return (
    <Modal className="alert" onClose={onClose}>
      <div className="alert-icon" aria-hidden="true"><AlertTriangle size={26} /></div>
      <h2>Court portal is unavailable</h2>
      <p className="alert-msg">{PORTAL_DOWN_MSG}</p>
      <p className="alert-sub">
        This is an issue with the official eCourts website, not your connection.
        Verify it's down, then try again in a little while.
      </p>
      <div className="modal-actions">
        <button className="btn secondary" type="button" onClick={onClose}>Close</button>
        <VerifyButton className="btn" />
      </div>
    </Modal>
  );
}
