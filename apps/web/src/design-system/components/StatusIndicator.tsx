type StatusType = "healthy" | "degraded" | "error" | "unknown";

interface StatusIndicatorProps {
  status: StatusType;
  label?: string;
}

const statusColors: Record<StatusType, string> = {
  healthy: "bg-[var(--color-success)]",
  degraded: "bg-[var(--color-warning)]",
  error: "bg-[var(--color-error)]",
  unknown: "bg-[var(--color-neutral-400)]",
};

const statusLabels: Record<StatusType, string> = {
  healthy: "Healthy",
  degraded: "Degraded",
  error: "Error",
  unknown: "Unknown",
};

export default function StatusIndicator({
  status,
  label,
}: StatusIndicatorProps) {
  const displayLabel = label ?? statusLabels[status];

  return (
    <span className="inline-flex items-center gap-[var(--space-2)]">
      <span
        className={[
          "inline-block w-2.5 h-2.5 rounded-full shrink-0",
          statusColors[status],
          status === "healthy" && "animate-[pulse-dot_2s_ease-in-out_infinite]",
        ]
          .filter(Boolean)
          .join(" ")}
        aria-hidden="true"
      />
      <span
        className="text-[var(--text-small-size)] leading-[var(--text-small-height)] text-[var(--color-neutral-600)]"
        role="status"
      >
        {displayLabel}
      </span>
    </span>
  );
}
