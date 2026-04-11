import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Inbox } from "lucide-react";

interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: ReactNode;
}

export default function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-[var(--space-16)] px-[var(--space-4)] text-center">
      <div className="mb-[var(--space-4)] p-[var(--space-4)] rounded-full bg-[var(--color-neutral-100)]">
        <Icon size={32} className="text-[var(--color-neutral-400)]" aria-hidden="true" />
      </div>
      <h3 className="font-[var(--text-h3-weight)] text-[var(--text-h3-size)] text-[var(--color-neutral-900)] mb-[var(--space-2)]">
        {title}
      </h3>
      {description && (
        <p className="max-w-sm text-[var(--text-body-size)] text-[var(--color-neutral-500)] mb-[var(--space-4)]">
          {description}
        </p>
      )}
      {action}
    </div>
  );
}
