"use client";

import Modal from "./Modal";
import { MapPin, Clock } from "./Icons";

function initials(name) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] || "") + (parts[1]?.[0] || "")).toUpperCase() || "?";
}

export default function ConfirmModal({ name, distName, stateName, onCancel, onConfirm }) {
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
      <div className="modal-actions">
        <button className="btn secondary" type="button" onClick={onCancel}>Cancel</button>
        <button className="btn" type="button" onClick={onConfirm}>Yes, search</button>
      </div>
    </Modal>
  );
}
