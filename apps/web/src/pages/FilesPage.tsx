/**
 * Files Page (G-03) — Table of indexed documents with sorting and pagination.
 * Route: /files | Flag: files_enabled
 */

import { useState } from "react";
import useSWR from "swr";
import { CheckCircle2, Loader2, AlertCircle, Scan, FileText } from "lucide-react";
import { swrFetcher, type SearchResponse, type Card } from "../api/client";
import { useAuth } from "../contexts/AuthContext";
import { useFlag } from "../contexts/FlagContext";
import { Badge, Button, FeatureComingSoon, Skeleton } from "../design-system/components";
import ErrorBanner from "../components/ErrorBanner";

function statusIcon(status?: string) {
  switch (status) {
    case "COMPLETED": return <CheckCircle2 size={16} className="text-[var(--color-success)]" />;
    case "FAILED": return <AlertCircle size={16} className="text-[var(--color-error)]" />;
    case "DISCOVERED":
    case "FINGERPRINTED":
    case "METADATA_EXTRACTED":
    case "TEXT_EXTRACTED":
      return <Loader2 size={16} className="text-[var(--color-primary)] animate-spin" />;
    default: return <Scan size={16} className="text-[var(--color-info)]" />;
  }
}

function formatSize(bytes?: number | null): string {
  if (!bytes) return "—";
  if (bytes >= 1_048_576) return `${(bytes / 1_048_576).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${bytes} B`;
}

export default function FilesPage() {
  const enabled = useFlag("files_enabled");
  const { user } = useAuth();
  const wsId = user?.workspaceIds?.[0];
  const [cursor, setCursor] = useState(0);
  const [allCards, setAllCards] = useState<Card[]>([]);

  const { data, error, isLoading, mutate } = useSWR<SearchResponse>(
    enabled && wsId ? `/api/v1/search?type=file&workspace_id=${wsId}&per_page=20&cursor=${cursor}&q=*` : null,
    swrFetcher,
    {
      onSuccess: (d) => {
        if (cursor === 0) setAllCards(d.data);
        else setAllCards((prev) => [...prev, ...d.data]);
      },
    },
  );

  if (!enabled) return <FeatureComingSoon featureName="Files" />;
  if (isLoading && cursor === 0) return <Skeleton variant="table-row" count={8} />;
  if (error) return <ErrorBanner message="Failed to load files." onRetry={() => mutate()} />;

  const cards = allCards;
  const hasMore = data?.pagination?.has_more ?? false;

  if (cards.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-[var(--space-16)] text-center">
        <div className="mb-[var(--space-4)] p-[var(--space-4)] rounded-full bg-[var(--color-neutral-100)]">
          <FileText size={32} className="text-[var(--color-neutral-400)]" aria-hidden="true" />
        </div>
        <h3 className="font-[var(--text-h3-weight)] text-[var(--text-h3-size)] text-[var(--color-neutral-900)] mb-[var(--space-2)]">
          No files indexed yet
        </h3>
        <p className="text-[var(--text-body-size)] text-[var(--color-neutral-500)]">
          Add a document folder in Settings &gt; Sources.
        </p>
      </div>
    );
  }

  return (
    <div>
      <p className="mb-[var(--space-4)] text-[var(--text-small-size)] text-[var(--color-neutral-500)]">
        Showing {cards.length} files
      </p>

      <div className="overflow-x-auto rounded-[var(--radius-lg)] border border-[var(--color-neutral-200)]">
        <table className="w-full text-[var(--text-body-size)]">
          <thead className="sticky top-0 bg-[var(--color-neutral-50)] border-b border-[var(--color-neutral-200)]">
            <tr>
              <th className="px-[var(--space-4)] py-[var(--space-3)] text-left font-[var(--text-caption-weight)] text-[var(--text-caption-size)] text-[var(--color-neutral-500)] uppercase tracking-wider">Filename</th>
              <th className="px-[var(--space-4)] py-[var(--space-3)] text-left font-[var(--text-caption-weight)] text-[var(--text-caption-size)] text-[var(--color-neutral-500)] uppercase tracking-wider">Type</th>
              <th className="px-[var(--space-4)] py-[var(--space-3)] text-left font-[var(--text-caption-weight)] text-[var(--text-caption-size)] text-[var(--color-neutral-500)] uppercase tracking-wider">Source</th>
              <th className="px-[var(--space-4)] py-[var(--space-3)] text-left font-[var(--text-caption-weight)] text-[var(--text-caption-size)] text-[var(--color-neutral-500)] uppercase tracking-wider w-16">Status</th>
            </tr>
          </thead>
          <tbody>
            {cards.map((card, i) => {
              const p = card.payload as Record<string, unknown>;
              return (
                <tr
                  key={card.id}
                  className={[
                    "border-b border-[var(--color-neutral-100)] last:border-b-0 cursor-pointer",
                    i % 2 === 1 ? "bg-[var(--color-neutral-50)]" : "bg-[var(--color-white)]",
                    "hover:bg-[var(--color-primary-surface)] transition-colors duration-[var(--duration-fast)]",
                  ].join(" ")}
                >
                  <td className="px-[var(--space-4)] py-[var(--space-3)] text-[var(--color-neutral-900)] font-medium truncate max-w-xs">
                    {String(p.filename ?? p.path ?? "—")}
                  </td>
                  <td className="px-[var(--space-4)] py-[var(--space-3)]">
                    <Badge variant="info">{String(p.mime_type ?? "unknown").split("/").pop()}</Badge>
                  </td>
                  <td className="px-[var(--space-4)] py-[var(--space-3)] text-[var(--color-neutral-600)] truncate max-w-[200px]">
                    {String(p.correspondent ?? "—")}
                  </td>
                  <td className="px-[var(--space-4)] py-[var(--space-3)]">
                    {statusIcon(String(p.status ?? ""))}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {hasMore && (
        <div className="mt-[var(--space-4)] text-center">
          <Button variant="secondary" size="sm" onClick={() => setCursor((c) => c + 20)}>
            Load More
          </Button>
        </div>
      )}
    </div>
  );
}
