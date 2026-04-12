/**
 * Transient toast notification (S11-004).
 *
 * Supports success / info / warning / error variants. Auto-dismisses
 * after 5 seconds by default. Announces via aria-live=polite so screen
 * readers pick up the message without stealing focus.
 *
 * Prefer this over ErrorToast for new call sites. ErrorToast is kept
 * for backwards compat but should be migrated in a future cleanup.
 */

import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type ToastVariant = "success" | "info" | "warning" | "error";

interface ToastProps {
  message: string;
  variant?: ToastVariant;
  /** Auto-dismiss after this many ms (default 5000). Pass 0 to disable. */
  duration?: number;
  onDismiss: () => void;
}

const VARIANT_CONFIG: Record<
  ToastVariant,
  { icon: LucideIcon; surface: string; border: string; iconColor: string }
> = {
  success: {
    icon: CheckCircle2,
    surface: "bg-[var(--color-success-surface)]",
    border: "border-[var(--color-success)]",
    iconColor: "text-[var(--color-success)]",
  },
  info: {
    icon: Info,
    surface: "bg-[var(--color-info-surface,#e6f0fb)]",
    border: "border-[var(--color-info,#0d6efd)]",
    iconColor: "text-[var(--color-info,#0d6efd)]",
  },
  warning: {
    icon: AlertTriangle,
    surface: "bg-[var(--color-warning-surface)]",
    border: "border-[var(--color-warning)]",
    iconColor: "text-[var(--color-warning)]",
  },
  error: {
    icon: XCircle,
    surface: "bg-[var(--color-error-surface)]",
    border: "border-[var(--color-error)]",
    iconColor: "text-[var(--color-error)]",
  },
};

export default function Toast({
  message,
  variant = "info",
  duration = 5000,
  onDismiss,
}: ToastProps) {
  const [visible, setVisible] = useState(true);
  const config = VARIANT_CONFIG[variant];
  const Icon = config.icon;

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
      role={variant === "error" ? "alert" : "status"}
      aria-live={variant === "error" ? "assertive" : "polite"}
      className={[
        "fixed bottom-4 right-4 z-50 max-w-sm rounded-[var(--radius-lg)] shadow-[var(--shadow-lg)]",
        "p-[var(--space-3)] flex items-start gap-[var(--space-2)]",
        "animate-[slideUp_var(--duration-normal)_var(--easing-default)]",
        "border",
        config.surface,
        config.border,
      ].join(" ")}
    >
      <Icon
        size={18}
        className={`${config.iconColor} shrink-0 mt-0.5`}
        aria-hidden="true"
      />
      <p className="flex-1 text-[var(--text-small-size)] leading-[var(--text-small-height)] text-[var(--color-neutral-900)]">
        {message}
      </p>
      <button
        onClick={() => {
          setVisible(false);
          onDismiss();
        }}
        className="shrink-0 p-1 rounded-[var(--radius-sm)] text-[var(--color-neutral-400)] hover:text-[var(--color-neutral-700)] hover:bg-[var(--color-neutral-100)] transition-colors cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary-light)]"
        aria-label="Dismiss"
      >
        <X size={14} aria-hidden="true" />
      </button>
    </div>
  );
}
