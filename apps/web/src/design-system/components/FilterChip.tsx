interface FilterChipProps {
  label: string;
  count?: number;
  active?: boolean;
  onClick: () => void;
}

export default function FilterChip({
  label,
  count,
  active = false,
  onClick,
}: FilterChipProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      role="option"
      aria-selected={active}
      className={[
        "inline-flex items-center gap-1.5 px-[var(--space-3)] py-[var(--space-1)] rounded-[var(--radius-full)]",
        "text-[var(--text-small-size)] font-medium whitespace-nowrap",
        "transition-colors duration-[var(--duration-normal)] ease-[var(--easing-default)]",
        "cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary-light)]",
        active
          ? "bg-[var(--color-primary-surface)] text-[var(--color-primary)] border border-[var(--color-primary-light)]"
          : "bg-[var(--color-neutral-100)] text-[var(--color-neutral-600)] border border-transparent hover:bg-[var(--color-neutral-200)]",
      ].join(" ")}
    >
      {label}
      {typeof count === "number" && (
        <span
          className={[
            "inline-flex items-center justify-center h-5 min-w-5 px-1 rounded-[var(--radius-full)]",
            "text-[var(--text-caption-size)]",
            active ? "bg-[var(--color-primary)] text-white" : "bg-[var(--color-neutral-200)] text-[var(--color-neutral-500)]",
          ].join(" ")}
        >
          {count}
        </span>
      )}
    </button>
  );
}
