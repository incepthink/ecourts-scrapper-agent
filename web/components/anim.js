// Shared framer-motion variants. Kept in one place so every surface animates
// with the same easing/timing language. Reduced-motion is handled globally in
// globals.css (transition/animation durations collapse to ~0).

export const EASE = [0.22, 0.61, 0.36, 1];

// View-to-view transition (search → progress → profile).
export const viewVariants = {
  initial: { opacity: 0, y: 14 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.4, ease: EASE } },
  exit: { opacity: 0, y: -10, transition: { duration: 0.22, ease: EASE } },
};

// Container that staggers its children in.
export const staggerParent = {
  animate: { transition: { staggerChildren: 0.06, delayChildren: 0.05 } },
};

// A single child of a staggered container.
export const fadeUp = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.38, ease: EASE } },
};

// Modal scale/fade.
export const modalVariants = {
  initial: { opacity: 0, scale: 0.94, y: 8 },
  animate: { opacity: 1, scale: 1, y: 0, transition: { duration: 0.26, ease: EASE } },
  exit: { opacity: 0, scale: 0.96, y: 6, transition: { duration: 0.16, ease: EASE } },
};

// Live case card sliding into the feed.
export const liveItem = {
  initial: { opacity: 0, x: 18, height: 0 },
  animate: { opacity: 1, x: 0, height: "auto", transition: { duration: 0.32, ease: EASE } },
};
