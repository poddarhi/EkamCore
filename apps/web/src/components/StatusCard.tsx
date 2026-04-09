import { Activity } from "lucide-react";
import { Card } from "../design-system/components";
import type { StatusPayload } from "../api/client";

interface StatusCardProps {
  payload: StatusPayload;
}

export default function StatusCard({ payload }: StatusCardProps) {
  const { weekday, time_of_day } = payload;
  const greeting = time_of_day === "morning"
    ? "Good morning"
    : time_of_day === "afternoon"
      ? "Good afternoon"
      : time_of_day === "evening"
        ? "Good evening"
        : "Good night";

  return (
    <Card>
      <div className="flex items-center gap-[var(--space-2)]">
        <Activity size={18} className="text-[var(--color-primary-light)] shrink-0" aria-hidden="true" />
        <span className="font-medium text-[var(--text-body-size)] leading-[var(--text-body-height)] text-[var(--color-neutral-900)]">
          {greeting}
        </span>
      </div>
      <p className="mt-[var(--space-2)] text-[var(--text-small-size)] leading-[var(--text-small-height)] text-[var(--color-neutral-600)]">
        {weekday} {time_of_day}
      </p>
    </Card>
  );
}
