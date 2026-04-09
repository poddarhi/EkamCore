import { Inbox } from "lucide-react";

interface EmptyStateProps {
  title: string;
  description?: string;
}

export default function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-[var(--space-16)] text-center">
      <Inbox
        size={48}
        className="text-[var(--color-neutral-400)] mb-[var(--space-4)]"
        aria-hidden="true"
      />
      <h3 className="text-[var(--text-h3-size)] leading-[var(--text-h3-height)] font-[var(--text-h3-weight)] text-[var(--color-neutral-700)]">
        {title}
      </h3>
      {description && (
        <p className="mt-[var(--space-2)] text-[var(--text-body-size)] leading-[var(--text-body-height)] text-[var(--color-neutral-500)]">
          {description}
        </p>
      )}
    </div>
  );
}
