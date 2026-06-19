"use client";

import { useEffect } from "react";
import { motion } from "framer-motion";
import { modalVariants } from "./anim";

// Shared modal shell: blurred backdrop (click to close) + animated card.
// `onClose` fires on backdrop click and Escape. Extra className lets callers
// opt into the `.alert` variant.
export default function Modal({ onClose, className = "", children }) {
  useEffect(() => {
    function onKey(e) {
      if (e.key === "Escape") onClose?.();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <motion.div
      className="modal-backdrop"
      onClick={onClose}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
    >
      <motion.div
        className={`modal ${className}`}
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
        variants={modalVariants}
        initial="initial"
        animate="animate"
        exit="exit"
      >
        {children}
      </motion.div>
    </motion.div>
  );
}
