import { ChevronRight } from "lucide-react";

interface BreadcrumbItem {
  label: string;
  href?: string;
}

interface BreadcrumbProps {
  items: BreadcrumbItem[];
}

export default function Breadcrumb({ items }: BreadcrumbProps) {
  return (
    <nav aria-label="Breadcrumb">
      <ol className="flex items-center gap-[var(--space-1)] text-[var(--text-small-size)]">
        {items.map((item, i) => {
          const isLast = i === items.length - 1;
          return (
            <li key={i} className="flex items-center gap-[var(--space-1)]">
              {i > 0 && (
                <ChevronRight size={14} className="text-[var(--color-neutral-400)]" aria-hidden="true" />
              )}
              {isLast || !item.href ? (
                <span
                  className={
                    isLast
                      ? "font-medium text-[var(--color-neutral-900)]"
                      : "text-[var(--color-neutral-500)]"
                  }
                  aria-current={isLast ? "page" : undefined}
                >
                  {item.label}
                </span>
              ) : (
                <a
                  href={item.href}
                  className="text-[var(--color-primary)] hover:underline outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary-light)] rounded"
                >
                  {item.label}
                </a>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
