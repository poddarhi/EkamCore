import { AlertTriangle } from "lucide-react";

interface DegradedBannerProps {
  message: string;
  persistent?: boolean;
  onDismiss?: () => void;
}

export default function DegradedBanner({
  message,
  persistent = false,
  onDismiss,
}: DegradedBannerProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center gap-[var(--space-3)] bg-[var(--color-warning-surface)] border border-[var(--color-warning)] rounded-[var(--radius-lg)] px-[var(--space-4)] py-[var(--space-3)]"
    >
      <AlertTriangle size={18} className="text-[var(--color-warning)] shrink-0" aria-hidden="true" />
      <p className="flex-1 text-[var(--text-small-size)] text-[var(--color-neutral-900)]">{message}</p>
      {!persistent && onDismiss && (
        <button
          onClick={onDismiss}
          className="shrink-0 text-[var(--text-small-size)] text-[var(--color-neutral-500)] hover:text-[var(--color-neutral-700)] cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-warning)]"
          aria-label="Dismiss"
        >
          Dismiss
        </button>
      )}
    </div>
  );
}
