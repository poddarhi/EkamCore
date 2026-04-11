import { AlertTriangle, RefreshCw, X } from "lucide-react";

interface ErrorBannerProps {
  message: string;
  onRetry?: () => void;
  onDismiss?: () => void;
  correlationId?: string;
}

export default function ErrorBanner({
  message,
  onRetry,
  onDismiss,
  correlationId,
}: ErrorBannerProps) {
  return (
    <div
      role="alert"
      className="flex items-start gap-[var(--space-3)] bg-[var(--color-error-surface)] border border-[var(--color-error)] rounded-[var(--radius-lg)] p-[var(--space-4)]"
    >
      <AlertTriangle size={20} className="text-[var(--color-error)] shrink-0 mt-0.5" aria-hidden="true" />
      <div className="flex-1 min-w-0">
        <p className="text-[var(--text-body-size)] text-[var(--color-neutral-900)]">{message}</p>
        {correlationId && (
          <p className="mt-1 text-[var(--text-caption-size)] text-[var(--color-neutral-500)]">
            Reference: {correlationId}
          </p>
        )}
      </div>
      <div className="flex items-center gap-[var(--space-2)] shrink-0">
        {onRetry && (
          <button
            onClick={onRetry}
            className="inline-flex items-center gap-1 px-[var(--space-3)] py-[var(--space-1)] rounded-[var(--radius-md)] border border-[var(--color-error)] text-[var(--color-error)] text-[var(--text-small-size)] hover:bg-[var(--color-error)] hover:text-white transition-colors cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-error)]"
            aria-label="Retry"
          >
            <RefreshCw size={14} aria-hidden="true" />
            Retry
          </button>
        )}
        {onDismiss && (
          <button
            onClick={onDismiss}
            className="p-1 rounded-[var(--radius-sm)] text-[var(--color-neutral-400)] hover:text-[var(--color-neutral-700)] cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-error)]"
            aria-label="Dismiss error"
          >
            <X size={16} aria-hidden="true" />
          </button>
        )}
      </div>
    </div>
  );
}
