import { AlertCircle, RefreshCw } from "lucide-react";

interface ErrorBannerProps {
  message: string;
  correlationId?: string;
  onRetry?: () => void;
}

export default function ErrorBanner({ message, correlationId, onRetry }: ErrorBannerProps) {
  return (
    <div
      role="alert"
      className="flex items-start gap-[var(--space-3)] bg-[var(--color-error-surface)] border border-[var(--color-error)] rounded-[var(--radius-lg)] p-[var(--space-4)]"
    >
      <AlertCircle size={20} className="text-[var(--color-error)] shrink-0 mt-0.5" aria-hidden="true" />
      <div className="flex-1 min-w-0">
        <p className="text-[var(--text-body-size)] leading-[var(--text-body-height)] text-[var(--color-neutral-900)]">
          {message}
        </p>
        {correlationId && (
          <p className="mt-1 text-[var(--text-caption-size)] leading-[var(--text-caption-height)] text-[var(--color-neutral-500)]">
            Reference ID: {correlationId}
          </p>
        )}
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="shrink-0 inline-flex items-center gap-[var(--space-1)] px-[var(--space-3)] py-[var(--space-1)] rounded-[var(--radius-md)] border border-[var(--color-error)] text-[var(--color-error)] text-[var(--text-small-size)] hover:bg-[var(--color-error)] hover:text-[var(--color-white)] transition-colors duration-[var(--duration-normal)] cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-error)]"
          aria-label="Retry loading"
        >
          <RefreshCw size={14} aria-hidden="true" />
          Retry
        </button>
      )}
    </div>
  );
}
