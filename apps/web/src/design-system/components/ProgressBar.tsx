type ProgressVariant = "default" | "success" | "warning";

interface ProgressBarProps {
  value: number;
  label?: string;
  variant?: ProgressVariant;
}

const variantColors: Record<ProgressVariant, string> = {
  default: "bg-[var(--color-primary)]",
  success: "bg-[var(--color-success)]",
  warning: "bg-[var(--color-warning)]",
};

export default function ProgressBar({
  value,
  label,
  variant = "default",
}: ProgressBarProps) {
  const clamped = Math.max(0, Math.min(100, value));

  return (
    <div>
      {label && (
        <div className="flex items-center justify-between mb-[var(--space-1)]">
          <span className="text-[var(--text-caption-size)] text-[var(--color-neutral-600)]">{label}</span>
          <span className="text-[var(--text-caption-size)] text-[var(--color-neutral-500)]">{Math.round(clamped)}%</span>
        </div>
      )}
      <div
        className="h-2 rounded-[var(--radius-full)] bg-[var(--color-neutral-100)] overflow-hidden"
        role="progressbar"
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label ?? "Progress"}
      >
        <div
          className={[
            "h-full rounded-[var(--radius-full)] transition-all duration-[var(--duration-slow)] ease-[var(--easing-default)]",
            variantColors[variant],
          ].join(" ")}
          style={{ width: `${clamped}%` }}
        />
      </div>
    </div>
  );
}
