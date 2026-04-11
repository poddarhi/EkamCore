type SkeletonVariant = "text" | "card" | "avatar" | "table-row";

interface SkeletonProps {
  variant?: SkeletonVariant;
  count?: number;
}

const shimmer =
  "animate-pulse bg-gradient-to-r from-[var(--color-neutral-100)] via-[var(--color-neutral-200)] to-[var(--color-neutral-100)] bg-[length:200%_100%]";

function SkeletonItem({ variant }: { variant: SkeletonVariant }) {
  if (variant === "avatar") {
    return <div className={`w-10 h-10 rounded-full ${shimmer}`} />;
  }

  if (variant === "card") {
    return (
      <div className={`rounded-[var(--radius-lg)] border border-[var(--color-neutral-200)] p-[var(--space-4)] ${shimmer}`}>
        <div className="h-4 w-3/4 rounded bg-[var(--color-neutral-200)] mb-[var(--space-3)]" />
        <div className="h-3 w-1/2 rounded bg-[var(--color-neutral-200)] mb-[var(--space-2)]" />
        <div className="h-3 w-2/3 rounded bg-[var(--color-neutral-200)]" />
      </div>
    );
  }

  if (variant === "table-row") {
    return (
      <div className="flex gap-[var(--space-4)] py-[var(--space-3)] px-[var(--space-4)]">
        <div className={`h-4 w-1/4 rounded ${shimmer}`} />
        <div className={`h-4 w-1/3 rounded ${shimmer}`} />
        <div className={`h-4 w-1/6 rounded ${shimmer}`} />
      </div>
    );
  }

  // text
  return <div className={`h-4 w-full rounded ${shimmer}`} />;
}

export default function Skeleton({ variant = "text", count = 1 }: SkeletonProps) {
  return (
    <div className="space-y-[var(--space-3)]" role="status" aria-label="Loading">
      {Array.from({ length: count }, (_, i) => (
        <SkeletonItem key={i} variant={variant} />
      ))}
    </div>
  );
}
