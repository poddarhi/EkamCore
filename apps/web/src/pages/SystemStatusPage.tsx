import { useCallback, useRef, useState } from "react";
import useSWR from "swr";
import { RefreshCw, ChevronDown, ChevronUp, Server } from "lucide-react";
import { swrFetcher, type HealthResponse } from "../api/client";
import { StatusIndicator } from "../design-system/components";
import { Card } from "../design-system/components";
import CardSkeleton from "../components/CardSkeleton";
import ErrorBanner from "../components/ErrorBanner";

type StatusType = "healthy" | "degraded" | "error" | "unknown";

function mapStatus(serviceStatus: string | undefined): StatusType {
  if (serviceStatus === "healthy") return "healthy";
  if (serviceStatus === "unhealthy") return "error";
  return "unknown";
}

function mapOverallStatus(status: string | undefined): StatusType {
  if (status === "healthy") return "healthy";
  if (status === "degraded") return "degraded";
  return "error";
}

function timeAgo(ts: number): string {
  const seconds = Math.floor((Date.now() - ts) / 1000);
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ago`;
}

const SERVICE_LABELS: Record<string, string> = {
  postgres: "PostgreSQL",
  redis: "Redis",
  qdrant: "Qdrant",
  paperless: "Paperless",
  ollama: "Ollama",
};

const SERVICE_DESCRIPTIONS: Record<string, string> = {
  postgres: "Primary database",
  redis: "Cache & sessions",
  qdrant: "Vector search",
  paperless: "Document management (optional)",
  ollama: "Local LLM inference (optional)",
};

interface ServiceTileProps {
  name: string;
  status: StatusType;
  error?: string;
  expanded: boolean;
  onToggle: () => void;
}

function ServiceTile({ name, status, error, expanded, onToggle }: ServiceTileProps) {
  const label = SERVICE_LABELS[name] ?? name;
  const description = SERVICE_DESCRIPTIONS[name] ?? "";

  return (
    <Card>
      <button
        onClick={onToggle}
        className="w-full text-left cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary-light)] rounded-[var(--radius-md)]"
        aria-expanded={expanded}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-[var(--space-3)]">
            <Server size={18} className="text-[var(--color-neutral-500)] shrink-0" aria-hidden="true" />
            <div>
              <div className="font-medium text-[var(--text-body-size)] leading-[var(--text-body-height)] text-[var(--color-neutral-900)]">
                {label}
              </div>
              <div className="text-[var(--text-caption-size)] leading-[var(--text-caption-height)] text-[var(--color-neutral-500)]">
                {description}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-[var(--space-3)]">
            <StatusIndicator status={status} />
            {expanded ? (
              <ChevronUp size={16} className="text-[var(--color-neutral-400)]" aria-hidden="true" />
            ) : (
              <ChevronDown size={16} className="text-[var(--color-neutral-400)]" aria-hidden="true" />
            )}
          </div>
        </div>
      </button>

      {expanded && (
        <div className="mt-[var(--space-3)] pt-[var(--space-3)] border-t border-[var(--color-neutral-200)]">
          <dl className="space-y-[var(--space-2)] text-[var(--text-small-size)] leading-[var(--text-small-height)]">
            <div className="flex justify-between">
              <dt className="text-[var(--color-neutral-500)]">Status</dt>
              <dd className="text-[var(--color-neutral-900)] font-medium">{status}</dd>
            </div>
            {error && (
              <div className="flex justify-between">
                <dt className="text-[var(--color-neutral-500)]">Error</dt>
                <dd className="text-[var(--color-error)]">{error}</dd>
              </div>
            )}
            <div className="flex justify-between">
              <dt className="text-[var(--color-neutral-500)]">Type</dt>
              <dd className="text-[var(--color-neutral-700)]">
                {["paperless", "ollama"].includes(name) ? "Optional" : "Core"}
              </dd>
            </div>
          </dl>
        </div>
      )}
    </Card>
  );
}

export default function SystemStatusPage() {
  const fetchedAtRef = useRef(0);
  const [expandedService, setExpandedService] = useState<string | null>(null);

  const { data, error, isLoading, mutate } = useSWR<HealthResponse>(
    "/health",
    (url: string) => {
      const p = swrFetcher<HealthResponse>(url);
      p.then(() => { fetchedAtRef.current = Date.now(); });
      return p;
    },
    { refreshInterval: 30_000 },
  );

  const handleToggle = useCallback((name: string) => {
    setExpandedService((prev) => (prev === name ? null : name));
  }, []);

  if (isLoading) return <CardSkeleton count={5} />;

  if (error) {
    return (
      <ErrorBanner
        message="Failed to load system status."
        onRetry={() => mutate()}
      />
    );
  }

  const services = data?.services ?? {};
  const overallStatus = mapOverallStatus(data?.status);

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-[var(--space-6)]">
        <div>
          <div className="flex items-center gap-[var(--space-3)]">
            <h2 className="text-[var(--text-display-size)] leading-[var(--text-display-height)] font-[var(--text-display-weight)] text-[var(--color-neutral-900)]">
              System Status
            </h2>
            <StatusIndicator status={overallStatus} />
          </div>
          {fetchedAtRef.current > 0 && (
            <p className="mt-[var(--space-1)] text-[var(--text-caption-size)] leading-[var(--text-caption-height)] text-[var(--color-neutral-400)]">
              Last checked {timeAgo(fetchedAtRef.current)} · v{data?.version ?? "?"}
            </p>
          )}
        </div>
        <button
          onClick={() => mutate()}
          className="inline-flex items-center gap-[var(--space-2)] px-[var(--space-3)] py-[var(--space-2)] rounded-[var(--radius-md)] border border-[var(--color-neutral-200)] text-[var(--text-small-size)] text-[var(--color-neutral-600)] hover:bg-[var(--color-neutral-100)] transition-colors duration-[var(--duration-normal)] cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary-light)]"
          aria-label="Refresh status"
        >
          <RefreshCw size={14} aria-hidden="true" />
          Refresh
        </button>
      </div>

      {/* Service tiles grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-[var(--space-4)]">
        {Object.entries(services).map(([name, svc]) => (
          <ServiceTile
            key={name}
            name={name}
            status={mapStatus(svc.status)}
            error={svc.error}
            expanded={expandedService === name}
            onToggle={() => handleToggle(name)}
          />
        ))}
      </div>

      {/* Info note */}
      {data?.note && (
        <p className="mt-[var(--space-6)] text-[var(--text-caption-size)] leading-[var(--text-caption-height)] text-[var(--color-neutral-400)]">
          {data.note}
        </p>
      )}
    </div>
  );
}
