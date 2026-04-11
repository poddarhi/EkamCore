/**
 * Transient error toast (S10-002).
 *
 * Auto-dismisses after 5 seconds. Used for transient service errors
 * (LLM timeout, rate limit, etc.) that don't need a full-page banner.
 */

import { useEffect, useState } from "react";
import { AlertTriangle, X } from "lucide-react";

interface ErrorToastProps {
  message: string;
  /** Auto-dismiss after this many ms (default 5000). Pass 0 to disable. */
  duration?: number;
  onDismiss: () => void;
}

export default function ErrorToast({ message, duration = 5000, onDismiss }: ErrorToastProps) {
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    if (duration <= 0) return;
    const timer = setTimeout(() => {
      setVisible(false);
      onDismiss();
    }, duration);
    return () => clearTimeout(timer);
  }, [duration, onDismiss]);

  if (!visible) return null;

  return (
    <div
      role="alert"
      aria-live="polite"
      className="fixed bottom-4 right-4 z-50 max-w-sm bg-[var(--color-warning-surface)] border border-[var(--color-warning)] rounded-[var(--radius-lg)] shadow-[var(--shadow-lg)] p-[var(--space-3)] flex items-start gap-[var(--space-2)] animate-[slideUp_var(--duration-normal)_var(--easing-default)]"
    >
      <AlertTriangle size={18} className="text-[var(--color-warning)] shrink-0 mt-0.5" aria-hidden="true" />
      <p className="flex-1 text-[var(--text-small-size)] leading-[var(--text-small-height)] text-[var(--color-neutral-900)]">
        {message}
      </p>
      <button
        onClick={() => { setVisible(false); onDismiss(); }}
        className="shrink-0 p-1 rounded-[var(--radius-sm)] text-[var(--color-neutral-400)] hover:text-[var(--color-neutral-700)] hover:bg-[var(--color-neutral-100)] transition-colors cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-warning)]"
        aria-label="Dismiss"
      >
        <X size={14} aria-hidden="true" />
      </button>
    </div>
  );
}
