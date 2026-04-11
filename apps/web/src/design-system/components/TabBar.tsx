interface Tab {
  key: string;
  label: string;
  count?: number;
  badge?: string;
}

interface TabBarProps {
  tabs: Tab[];
  activeTab: string;
  onChange: (key: string) => void;
}

export default function TabBar({ tabs, activeTab, onChange }: TabBarProps) {
  return (
    <div
      role="tablist"
      className="flex border-b border-[var(--color-neutral-200)] gap-[var(--space-1)]"
    >
      {tabs.map((tab) => {
        const active = tab.key === activeTab;
        return (
          <button
            key={tab.key}
            role="tab"
            aria-selected={active}
            aria-controls={`panel-${tab.key}`}
            onClick={() => onChange(tab.key)}
            className={[
              "relative px-[var(--space-4)] py-[var(--space-3)] text-[var(--text-body-size)]",
              "transition-colors duration-[var(--duration-normal)]",
              "cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--color-primary-light)]",
              active
                ? "text-[var(--color-primary)] font-medium"
                : "text-[var(--color-neutral-500)] hover:text-[var(--color-neutral-700)]",
            ].join(" ")}
          >
            <span className="inline-flex items-center gap-[var(--space-2)]">
              {tab.label}
              {typeof tab.count === "number" && (
                <span
                  className={[
                    "inline-flex items-center justify-center h-5 min-w-5 px-1 rounded-[var(--radius-full)] text-[var(--text-caption-size)]",
                    active
                      ? "bg-[var(--color-primary)] text-white"
                      : "bg-[var(--color-neutral-200)] text-[var(--color-neutral-500)]",
                  ].join(" ")}
                >
                  {tab.count}
                </span>
              )}
              {tab.badge && (
                <span className="px-1.5 py-0.5 rounded-[var(--radius-sm)] bg-[var(--color-info-surface)] text-[var(--color-info)] text-[var(--text-caption-size)] font-medium">
                  {tab.badge}
                </span>
              )}
            </span>
            {/* Active underline */}
            {active && (
              <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-[var(--color-primary)] rounded-full" />
            )}
          </button>
        );
      })}
    </div>
  );
}
