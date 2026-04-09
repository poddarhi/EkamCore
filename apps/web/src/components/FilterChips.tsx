interface FilterOption<T extends string> {
  value: T;
  label: string;
}

interface FilterChipsProps<T extends string> {
  options: FilterOption<T>[];
  value: T;
  onChange: (value: T) => void;
}

export default function FilterChips<T extends string>({
  options,
  value,
  onChange,
}: FilterChipsProps<T>) {
  return (
    <div className="flex flex-wrap gap-[var(--space-2)]" role="radiogroup" aria-label="Filter">
      {options.map((opt) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            role="radio"
            aria-checked={active}
            onClick={() => onChange(opt.value)}
            className={[
              "inline-flex items-center h-8 px-[var(--space-3)]",
              "rounded-[var(--radius-full)] border",
              "text-[var(--text-small-size)] leading-[var(--text-small-height)] font-medium",
              "transition-colors duration-[var(--duration-normal)] ease-[var(--easing-default)]",
              "cursor-pointer outline-none",
              "focus-visible:ring-2 focus-visible:ring-[var(--color-primary-light)] focus-visible:ring-offset-1",
              active
                ? "bg-[var(--color-primary)] text-[var(--color-white)] border-[var(--color-primary)]"
                : "bg-[var(--color-white)] text-[var(--color-neutral-600)] border-[var(--color-neutral-200)] hover:border-[var(--color-neutral-400)]",
            ].join(" ")}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
