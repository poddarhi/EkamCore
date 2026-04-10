import { FileText, ExternalLink } from "lucide-react";
import { Card, Badge } from "../../design-system/components";
import type { FilePayload } from "../../api/client";

interface FileCardProps {
  id: string;
  payload: FilePayload;
  query: string;
}

/** Highlight every occurrence of query in text with <mark>. */
function highlight(text: string, query: string): React.ReactNode {
  if (!query || !text) return text;
  const parts = text.split(new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi"));
  return parts.map((part, i) =>
    part.toLowerCase() === query.toLowerCase() ? (
      <mark
        key={i}
        className="bg-[var(--color-warning-surface)] text-inherit rounded-[var(--radius-sm)] px-0.5"
      >
        {part}
      </mark>
    ) : (
      part
    ),
  );
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
}

const TAG_COLORS = [
  "bg-[var(--color-primary-surface)] text-[var(--color-primary)]",
  "bg-[var(--color-success-surface)] text-[var(--color-success)]",
  "bg-[var(--color-info-surface)] text-[var(--color-info)]",
  "bg-[var(--color-warning-surface)] text-[var(--color-warning)]",
];

export default function FileCard({ id: _id, payload, query }: FileCardProps) {
  const filename = payload.filename ?? "Untitled document";
  const paperlessUrl = payload.paperless_id
    ? `https://localhost/paperless/documents/${payload.paperless_id}/`
    : null;

  function handleFilenameClick(e: React.MouseEvent) {
    e.stopPropagation();
    if (paperlessUrl) window.open(paperlessUrl, "_blank", "noopener,noreferrer");
  }

  return (
    <Card>
      {/* Header row: icon + filename + external link */}
      <div className="flex items-start gap-[var(--space-3)]">
        <FileText
          size={18}
          className="text-[var(--color-primary-light)] shrink-0 mt-0.5"
          aria-hidden="true"
        />
        <div className="min-w-0 flex-1">
          {/* Filename — acts as link to Paperless */}
          <button
            onClick={handleFilenameClick}
            className={[
              "inline-flex items-center gap-1 text-left",
              "font-semibold text-[var(--text-body-size)] leading-[var(--text-body-height)]",
              paperlessUrl
                ? "text-[var(--color-primary-light)] hover:underline cursor-pointer"
                : "text-[var(--color-neutral-900)] cursor-default",
            ].join(" ")}
            disabled={!paperlessUrl}
            aria-label={paperlessUrl ? `Open ${filename} in Paperless` : filename}
          >
            {highlight(filename, query)}
            {paperlessUrl && (
              <ExternalLink size={13} className="shrink-0 opacity-60" aria-hidden="true" />
            )}
          </button>

          {/* Content snippet */}
          {payload.snippet && (
            <p className="mt-[var(--space-1)] text-[var(--text-small-size)] leading-[var(--text-small-height)] text-[var(--color-neutral-600)] line-clamp-2">
              {highlight(payload.snippet, query)}
            </p>
          )}

          {/* Metadata row */}
          <div className="mt-[var(--space-2)] flex flex-wrap items-center gap-x-[var(--space-3)] gap-y-[var(--space-1)]">
            {payload.correspondent && (
              <span className="text-[var(--text-caption-size)] text-[var(--color-neutral-500)]">
                {payload.correspondent}
              </span>
            )}
            {payload.document_type && (
              <Badge variant="info">{payload.document_type}</Badge>
            )}
            {payload.modified_date && (
              <span className="text-[var(--text-caption-size)] text-[var(--color-neutral-400)]">
                {formatDate(payload.modified_date)}
              </span>
            )}
            {payload.tags && payload.tags.length > 0 && (
              <div className="flex flex-wrap gap-[var(--space-1)]">
                {payload.tags.slice(0, 5).map((tag, i) => (
                  <span
                    key={tag}
                    className={`inline-flex items-center h-5 px-[var(--space-2)] rounded-[var(--radius-full)] text-[var(--text-caption-size)] font-medium ${TAG_COLORS[i % TAG_COLORS.length]}`}
                  >
                    {tag}
                  </span>
                ))}
                {payload.tags.length > 5 && (
                  <span className="text-[var(--text-caption-size)] text-[var(--color-neutral-400)]">
                    +{payload.tags.length - 5}
                  </span>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}
