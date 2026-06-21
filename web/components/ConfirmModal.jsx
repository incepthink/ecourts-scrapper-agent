"use client";

import { useState } from "react";
import Modal from "./Modal";
import Toggle from "./Toggle";
import { MapPin, Clock, Mail } from "./Icons";

function initials(name) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] || "") + (parts[1]?.[0] || "")).toUpperCase() || "?";
}

export default function ConfirmModal({ name, distName, stateName, email, onCancel, onConfirm }) {
  // Opt-in to a completion email. Off by default — explicit opt-in.
  const [notify, setNotify] = useState(false);

  return (
    <Modal onClose={onCancel}>
      <h2>Search this advocate?</h2>
      <p>We'll compile the case portfolio for:</p>
      <div className="confirm-id">
        <span className="avatar">{initials(name)}</span>
        <div>
          <div className="confirm-name">{name.trim()}</div>
          <div className="confirm-meta">
            <span className="pill"><MapPin size={12} /> {distName || "—"}</span>
            {stateName ? <span className="pill">{stateName}</span> : null}
          </div>
        </div>
      </div>
      <div className="confirm-note">
        <Clock size={16} className="nic" />
        <span>
          If we don't already have this advocate, we fetch their record live from the
          court portal — this can take several minutes.
        </span>
      </div>

      {email ? (
        <div className="opt-in">
          <span className="opt-ic"><Mail size={17} /></span>
          <label className="opt-text" htmlFor="notify-email">
            <span className="opt-title">Email me when it's ready</span>
            <span className="opt-sub">No need to wait — we'll send it to {email}</span>
          </label>
          <Toggle
            id="notify-email"
            on={notify}
            onChange={setNotify}
            label="Email me when the report is ready"
          />
        </div>
      ) : null}

      <div className="modal-actions">
        <button className="btn secondary" type="button" onClick={onCancel}>Cancel</button>
        <button className="btn" type="button" onClick={() => onConfirm(notify)}>Yes, search</button>
      </div>
    </Modal>
  );
}
