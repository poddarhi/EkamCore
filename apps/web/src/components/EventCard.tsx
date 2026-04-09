import { Calendar, MapPin, Users } from "lucide-react";
import { Card, Badge } from "../design-system/components";
import type { EventPayload } from "../api/client";

interface EventCardProps {
  payload: EventPayload;
  priorityScore: number;
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function confidenceVariant(score: number): "high" | "medium" | "low" {
  if (score >= 0.8) return "high";
  if (score >= 0.5) return "medium";
  return "low";
}

export default function EventCard({ payload, priorityScore }: EventCardProps) {
  const { title, start_at, end_at, is_all_day, location, calendar_name, participants } = payload;

  const timeLabel = is_all_day
    ? "All day"
    : end_at
      ? `${formatTime(start_at)} – ${formatTime(end_at)}`
      : formatTime(start_at);

  return (
    <Card>
      {/* Header row */}
      <div className="flex items-center gap-[var(--space-2)]">
        <Calendar size={18} className="text-[var(--color-primary-light)] shrink-0" aria-hidden="true" />
        <span className="font-medium text-[var(--text-body-size)] leading-[var(--text-body-height)] text-[var(--color-neutral-900)] truncate">
          {title}
        </span>
        <Badge variant="info">{timeLabel}</Badge>
        <Badge variant={confidenceVariant(priorityScore)}>
          {Math.round(priorityScore * 100)}%
        </Badge>
      </div>

      {/* Details */}
      <div className="mt-[var(--space-2)] space-y-[var(--space-1)]">
        {location && (
          <div className="flex items-center gap-[var(--space-2)] text-[var(--text-small-size)] leading-[var(--text-small-height)] text-[var(--color-neutral-600)]">
            <MapPin size={14} className="shrink-0" aria-hidden="true" />
            <span className="truncate">{location}</span>
          </div>
        )}
        {participants.length > 0 && (
          <div className="flex items-center gap-[var(--space-2)] text-[var(--text-small-size)] leading-[var(--text-small-height)] text-[var(--color-neutral-600)]">
            <Users size={14} className="shrink-0" aria-hidden="true" />
            <span>{participants.length} participant{participants.length !== 1 ? "s" : ""}</span>
          </div>
        )}
        {calendar_name && (
          <p className="text-[var(--text-caption-size)] leading-[var(--text-caption-height)] text-[var(--color-neutral-500)]">
            {calendar_name}
          </p>
        )}
      </div>
    </Card>
  );
}
