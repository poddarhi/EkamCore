/**
 * Sources Settings (G-03) — manage data sources.
 */

import useSWR from "swr";
import { Plus, FolderOpen } from "lucide-react";
import { swrFetcher } from "../../api/client";
import { useAuth } from "../../contexts/AuthContext";
import { Badge, Button, Skeleton } from "../../design-system/components";
import ErrorBanner from "../../components/ErrorBanner";

interface Source {
  id: string;
  name: string;
  type: string;
  path: string | null;
  status: string;
  last_sync_at: string | null;
}

interface SourcesResponse {
  sources: Source[];
}

export default function SourcesSettings() {
  const { user } = useAuth();
  const wsId = user?.workspaceIds?.[0];
  const { data, error, isLoading, mutate } = useSWR<SourcesResponse>(
    wsId ? `/api/v1/sources?workspace_id=${wsId}` : null,
    swrFetcher,
  );

  if (isLoading) return <Skeleton variant="table-row" count={4} />;
  if (error) return <ErrorBanner message="Failed to load sources." onRetry={() => mutate()} />;

  const sources = data?.sources ?? [];

  return (
    <div className="space-y-[var(--space-4)]">
      <div className="flex items-center justify-between">
        <h2 className="font-[var(--text-h2-weight)] text-[var(--text-h2-size)] text-[var(--color-neutral-900)]">
          Sources
        </h2>
        <Button size="sm" disabled>
          <Plus size={14} className="mr-1" aria-hidden="true" />
          Add Source
        </Button>
      </div>

      {sources.length === 0 ? (
        <div className="flex flex-col items-center py-[var(--space-10)] text-center">
          <FolderOpen size={32} className="text-[var(--color-neutral-400)] mb-[var(--space-3)]" />
          <p className="text-[var(--text-body-size)] text-[var(--color-neutral-500)]">
            No sources configured yet.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-[var(--radius-lg)] border border-[var(--color-neutral-200)]">
          <table className="w-full text-[var(--text-body-size)]">
            <thead className="bg-[var(--color-neutral-50)] border-b border-[var(--color-neutral-200)]">
              <tr>
                <th className="px-[var(--space-4)] py-[var(--space-3)] text-left font-[var(--text-caption-weight)] text-[var(--text-caption-size)] text-[var(--color-neutral-500)] uppercase tracking-wider">Name</th>
                <th className="px-[var(--space-4)] py-[var(--space-3)] text-left font-[var(--text-caption-weight)] text-[var(--text-caption-size)] text-[var(--color-neutral-500)] uppercase tracking-wider">Type</th>
                <th className="px-[var(--space-4)] py-[var(--space-3)] text-left font-[var(--text-caption-weight)] text-[var(--text-caption-size)] text-[var(--color-neutral-500)] uppercase tracking-wider">Status</th>
                <th className="px-[var(--space-4)] py-[var(--space-3)] text-left font-[var(--text-caption-weight)] text-[var(--text-caption-size)] text-[var(--color-neutral-500)] uppercase tracking-wider">Last Sync</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((src, i) => (
                <tr key={src.id} className={i % 2 === 1 ? "bg-[var(--color-neutral-50)]" : ""}>
                  <td className="px-[var(--space-4)] py-[var(--space-3)] font-medium text-[var(--color-neutral-900)]">{src.name}</td>
                  <td className="px-[var(--space-4)] py-[var(--space-3)]"><Badge variant="info">{src.type}</Badge></td>
                  <td className="px-[var(--space-4)] py-[var(--space-3)]">
                    <Badge variant={src.status === "active" ? "success" : src.status === "error" ? "error" : "warning"}>
                      {src.status}
                    </Badge>
                  </td>
                  <td className="px-[var(--space-4)] py-[var(--space-3)] text-[var(--color-neutral-500)]">
                    {src.last_sync_at ? new Date(src.last_sync_at).toLocaleString() : "Never"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
