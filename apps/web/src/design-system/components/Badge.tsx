import type { ReactNode } from "react";

type BadgeVariant = "high" | "medium" | "low" | "info" | "success" | "warning" | "error";

interface BadgeProps {
  variant: BadgeVariant;
  children: ReactNode;
}

const variantStyles: Record<BadgeVariant, string> = {
  high: "bg-[var(--color-confidence-high-bg)] text-[var(--color-confidence-high-text)] border-[var(--color-confidence-high-border)]",
  medium:
    "bg-[var(--color-confidence-medium-bg)] text-[var(--color-confidence-medium-text)] border-[var(--color-confidence-medium-border)]",
  low: "bg-[var(--color-confidence-low-bg)] text-[var(--color-confidence-low-text)] border-[var(--color-confidence-low-border)]",
  info: "bg-[var(--color-info-surface)] text-[var(--color-info)] border-[var(--color-info)]",
  success:
    "bg-[var(--color-success-surface)] text-[var(--color-success)] border-[var(--color-success)]",
  warning:
    "bg-[var(--color-warning-surface)] text-[var(--color-warning)] border-[var(--color-warning)]",
  error:
    "bg-[var(--color-error-surface)] text-[var(--color-error)] border-[var(--color-error)]",
};

export default function Badge({ variant, children }: BadgeProps) {
  return (
    <span
      className={[
        "inline-flex items-center h-6 px-[var(--space-1)]",
        "rounded-[var(--radius-sm)] border",
        "text-[var(--text-caption-size)] leading-[var(--text-caption-height)] font-[var(--text-caption-weight)]",
        "whitespace-nowrap select-none",
        variantStyles[variant],
      ].join(" ")}
    >
      {children}
    </span>
  );
}
