"use client";

import { signOut } from "next-auth/react";
import { Scale } from "./Icons";

export default function TopBar({ session }) {
  return (
    <header className="topbar">
      <div className="brand">
        <span className="mono">AP</span>
        <span className="wordmark">Advocate Profiles</span>
      </div>
      <div className="who">
        {session ? (
          <>
            <span className="email">{session.user?.email}</span>
            <button className="btn ghost small" onClick={() => signOut()}>Sign out</button>
          </>
        ) : (
          <span className="email" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <Scale size={15} /> Public eCourts records
          </span>
        )}
      </div>
    </header>
  );
}
