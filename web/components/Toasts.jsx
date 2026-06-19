"use client";

import { motion, AnimatePresence } from "framer-motion";
import { AlertCircle, CheckCircle, Info, X } from "./Icons";

const ICONS = { error: AlertCircle, info: Info, success: CheckCircle };

export default function Toasts({ toasts, onDismiss }) {
  return (
    <div className="toast-wrap">
      <AnimatePresence initial={false}>
        {toasts.map((t) => {
          const Icon = ICONS[t.type] || AlertCircle;
          return (
            <motion.div
              key={t.id}
              className={`toast ${t.type}`}
              role="alert"
              layout
              initial={{ opacity: 0, x: 24, scale: 0.96 }}
              animate={{ opacity: 1, x: 0, scale: 1 }}
              exit={{ opacity: 0, x: 24, scale: 0.96, transition: { duration: 0.18 } }}
              transition={{ duration: 0.26, ease: [0.22, 0.61, 0.36, 1] }}
            >
              <span className="tic"><Icon size={18} /></span>
              <span className="toast-msg">{t.message}</span>
              <button className="toast-close" aria-label="Dismiss" onClick={() => onDismiss(t.id)}>
                <X size={16} />
              </button>
              {!t.sticky && (
                <motion.span
                  className="timer"
                  initial={{ width: "100%" }}
                  animate={{ width: "0%" }}
                  transition={{ duration: 5, ease: "linear" }}
                />
              )}
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
