"use client";

// Small accessible on/off switch (track + sliding knob). Controlled: pass `on`
// and `onChange(next)`. Styled by `.switch` in globals.css (gold when on).
export default function Toggle({ on, onChange, id, label, disabled = false }) {
  return (
    <button
      type="button"
      role="switch"
      id={id}
      aria-checked={on}
      aria-label={label}
      className="switch"
      disabled={disabled}
      onClick={() => onChange(!on)}
    >
      <span className="switch-knob" />
    </button>
  );
}
