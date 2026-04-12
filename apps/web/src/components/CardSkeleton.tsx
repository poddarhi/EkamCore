import { t } from "../i18n";

interface CardSkeletonProps {
  count?: number;
}

function SingleSkeleton() {
  return (
    <div
      className="bg-[var(--color-white)] border border-[var(--color-neutral-200)] rounded-[var(--radius-lg)] p-[var(--space-4)] animate-pulse"
      aria-hidden="true"
    >
      <div className="flex items-center gap-[var(--space-3)]">
        <div className="w-5 h-5 rounded bg-[var(--color-neutral-200)]" />
        <div className="h-4 w-40 rounded bg-[var(--color-neutral-200)]" />
        <div className="ml-auto h-5 w-16 rounded-[var(--radius-sm)] bg-[var(--color-neutral-100)]" />
      </div>
      <div className="mt-[var(--space-3)] space-y-[var(--space-2)]">
        <div className="h-3 w-56 rounded bg-[var(--color-neutral-100)]" />
        <div className="h-3 w-32 rounded bg-[var(--color-neutral-100)]" />
      </div>
    </div>
  );
}

export default function CardSkeleton({ count = 5 }: CardSkeletonProps) {
  return (
    <div className="space-y-[var(--space-3)]" role="status" aria-label={t("common.loading")}>
      {Array.from({ length: count }, (_, i) => (
        <SingleSkeleton key={i} />
      ))}
    </div>
  );
}
