import { CheckCircle } from "lucide-react";
import { Card, Badge } from "../design-system/components";
import type { ReminderPayload } from "../api/client";

interface ReminderCardProps {
  payload: ReminderPayload;
}

function dueBadge(dueAt: string | null, isOverdue: boolean): { label: string; variant: "error" | "warning" | "info" } {
  if (isOverdue) return { label: "Overdue", variant: "error" };
  if (!dueAt) return { label: "No due date", variant: "info" };

  const due = new Date(dueAt);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const dueDay = new Date(due);
  dueDay.setHours(0, 0, 0, 0);

  if (dueDay.getTime() === today.getTime()) return { label: "Due today", variant: "warning" };
  return {
    label: due.toLocaleDateString([], { month: "short", day: "numeric" }),
    variant: "info",
  };
}

const priorityVariants: Record<string, "error" | "warning" | "info" | "success"> = {
  high: "error",
  medium: "warning",
  low: "info",
};

export default function ReminderCard({ payload }: ReminderCardProps) {
  const { title, due_at, priority, list_name, is_overdue } = payload;
  const due = dueBadge(due_at, is_overdue);

  return (
    <Card className={is_overdue ? "border-l-4 border-l-[var(--color-error)]" : ""}>
      {/* Header row */}
      <div className="flex items-center gap-[var(--space-2)]">
        <CheckCircle
          size={18}
          className={is_overdue ? "text-[var(--color-error)] shrink-0" : "text-[var(--color-success)] shrink-0"}
          aria-hidden="true"
        />
        <span className="font-medium text-[var(--text-body-size)] leading-[var(--text-body-height)] text-[var(--color-neutral-900)] truncate">
          {title}
        </span>
        <Badge variant={due.variant}>{due.label}</Badge>
      </div>

      {/* Details */}
      <div className="mt-[var(--space-2)] flex items-center gap-[var(--space-2)]">
        {priority && priority !== "none" && (
          <Badge variant={priorityVariants[priority] ?? "info"}>
            {priority.charAt(0).toUpperCase() + priority.slice(1)}
          </Badge>
        )}
        {list_name && (
          <span className="text-[var(--text-caption-size)] leading-[var(--text-caption-height)] text-[var(--color-neutral-500)]">
            {list_name}
          </span>
        )}
      </div>
    </Card>
  );
}
