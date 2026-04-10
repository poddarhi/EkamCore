import { Calendar, CheckCircle, User } from "lucide-react";
import { Card, Badge } from "../design-system/components";
import type { Card as CardType, EventPayload, ReminderPayload, FilePayload, PhotoPayload } from "../api/client";
import FileCard from "./cards/FileCard";
import PhotoCard from "./cards/PhotoCard";

interface SearchResultCardProps {
  card: CardType;
  query: string;
}

/** Highlight matching substring with <mark>. */
function highlightMatch(text: string, query: string): React.ReactNode {
  if (!query || !text) return text;
  const idx = text.toLowerCase().indexOf(query.toLowerCase());
  if (idx === -1) return text;
  return (
    <>
      {text.slice(0, idx)}
      <mark className="bg-[var(--color-warning-surface)] text-inherit rounded-[var(--radius-sm)] px-0.5">
        {text.slice(idx, idx + query.length)}
      </mark>
      {text.slice(idx + query.length)}
    </>
  );
}

const TYPE_ICONS = {
  event: Calendar,
  reminder: CheckCircle,
  person: User,
} as const;

const TYPE_LABELS: Record<string, string> = {
  event: "Event",
  reminder: "Reminder",
  person: "Contact",
};

const TYPE_COLORS: Record<string, string> = {
  event: "text-[var(--color-primary-light)]",
  reminder: "text-[var(--color-success)]",
  person: "text-[var(--color-info)]",
};

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

export default function SearchResultCard({ card, query }: SearchResultCardProps) {
  if (card.type === "file") {
    return <FileCard id={card.id} payload={card.payload as FilePayload} query={query} />;
  }
  if (card.type === "photo") {
    return <PhotoCard id={card.id} payload={card.payload as PhotoPayload} />;
  }

  const Icon = TYPE_ICONS[card.type as keyof typeof TYPE_ICONS] ?? Calendar;
  const typeLabel = TYPE_LABELS[card.type] ?? card.type;
  const iconColor = TYPE_COLORS[card.type] ?? "text-[var(--color-neutral-500)]";

  const title = (card.payload as { title?: string; display_name?: string }).title
    ?? (card.payload as { display_name?: string }).display_name
    ?? "Untitled";

  function handleClick() {
    // Placeholder: detail view comes in a later sprint
    console.log("Open detail:", card.type, card.id);
  }

  return (
    <Card onClick={handleClick}>
      <div className="flex items-center gap-[var(--space-2)]">
        <Icon size={18} className={`${iconColor} shrink-0`} aria-hidden="true" />
        <span className="font-medium text-[var(--text-body-size)] leading-[var(--text-body-height)] text-[var(--color-neutral-900)] truncate">
          {highlightMatch(title, query)}
        </span>
        <Badge variant="info">{typeLabel}</Badge>
      </div>

      {/* Type-specific details */}
      <div className="mt-[var(--space-2)] text-[var(--text-small-size)] leading-[var(--text-small-height)] text-[var(--color-neutral-600)]">
        {card.type === "event" && (() => {
          const p = card.payload as EventPayload;
          return (
            <div className="flex items-center gap-[var(--space-3)]">
              <span>
                {p.is_all_day
                  ? "All day"
                  : p.end_at
                    ? `${formatTime(p.start_at)} – ${formatTime(p.end_at)}`
                    : formatTime(p.start_at)}
              </span>
              {p.location && <span className="truncate">{p.location}</span>}
            </div>
          );
        })()}
        {card.type === "reminder" && (() => {
          const p = card.payload as ReminderPayload;
          return (
            <div className="flex items-center gap-[var(--space-3)]">
              {p.due_at && (
                <span>
                  {p.is_overdue ? "Overdue" : `Due ${new Date(p.due_at).toLocaleDateString([], { month: "short", day: "numeric" })}`}
                </span>
              )}
              {p.list_name && <span>{p.list_name}</span>}
            </div>
          );
        })()}
        {card.type === "person" && (() => {
          const p = card.payload as Record<string, unknown>;
          return (
            <div className="flex items-center gap-[var(--space-3)]">
              {typeof p.organization === "string" && <span>{p.organization}</span>}
              {typeof p.job_title === "string" && <span>{p.job_title}</span>}
            </div>
          );
        })()}
      </div>
    </Card>
  );
}
