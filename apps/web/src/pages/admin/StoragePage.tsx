/**
 * Storage Monitoring Admin Dashboard (S09-004)
 *
 * Shows storage breakdown across PostgreSQL, Qdrant, Paperless, thumbnails.
 * Includes file/photo counts, disk free space, and warning banners.
 * Auto-refreshes every 30 seconds.
 */

import useSWR from "swr";
import {
  Database,
  HardDrive,
  FileText,
  Image,
  Archive,
  AlertTriangle,
  AlertCircle,
  Users,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { swrFetcher } from "../../api/client";
import { Badge } from "../../design-system/components";
import CardSkeleton from "../../components/CardSkeleton";
import ErrorBanner from "../../components/ErrorBanner";

// ── Types ──

interface StorageResponse {
  postgres_size_mb: number;
  qdrant_size_mb: number;
  paperless_size_mb: number;
  thumbnails_size_mb: number;
  file_counts: {
    total: number;
    by_mime_type: Record<string, number>;
  };
  photo_counts: {
    total: number;
    with_gps: number;
  };
  // S11-008: only populated when at least one workspace has active consent.
  face_counts: {
    total_detections: number;
    total_clusters: number;
    photos_processed: number;
    consent_active_workspaces: number;
  } | null;
  total_disk_mb: number;
  available_disk_mb: number;
  free_space_pct: number;
  free_space_warning: boolean;
  free_space_critical: boolean;
}

// ── Helpers ──

function formatSize(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  if (mb >= 1) return `${mb.toFixed(1)} MB`;
  return `${(mb * 1024).toFixed(0)} KB`;
}

// ── Storage breakdown bar ──

interface BreakdownSegment {
  label: string;
  sizeMb: number;
  color: string;
}

function BreakdownBar({ segments, totalMb }: { segments: BreakdownSegment[]; totalMb: number }) {
  if (totalMb <= 0) return null;

  return (
    <div className="space-y-2">
      {/* Bar */}
      <div className="h-6 rounded-[var(--radius-md)] overflow-hidden flex bg-[var(--color-neutral-100)]" role="img" aria-label="Storage breakdown">
        {segments.map((seg) => {
          const pct = (seg.sizeMb / totalMb) * 100;
          if (pct < 0.5) return null;
          return (
            <div
              key={seg.label}
              className="h-full transition-all duration-[var(--duration-slow)]"
              style={{ width: `${pct}%`, backgroundColor: seg.color }}
              title={`${seg.label}: ${formatSize(seg.sizeMb)} (${pct.toFixed(1)}%)`}
            />
          );
        })}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {segments.map((seg) => (
          <div key={seg.label} className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: seg.color }} />
            <span className="text-[var(--text-caption-size)] text-[var(--color-neutral-600)]">
              {seg.label}: {formatSize(seg.sizeMb)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Stat card ──

function StatCard({
  icon: Icon,
  label,
  value,
  subtitle,
  iconColor = "text-[var(--color-primary)]",
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  subtitle?: string;
  iconColor?: string;
}) {
  return (
    <div className="bg-[var(--color-white)] rounded-[var(--radius-md)] border border-[var(--color-neutral-200)] p-4 shadow-[var(--shadow-sm)]">
      <div className="flex items-start gap-3">
        <div className={`p-2 rounded-[var(--radius-md)] bg-[var(--color-neutral-50)] ${iconColor}`}>
          <Icon size={20} aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[var(--text-caption-size)] text-[var(--color-neutral-500)] font-medium uppercase tracking-wider">
            {label}
          </p>
          <p className="mt-0.5 text-[var(--text-h2-size)] font-[var(--text-h2-weight)] text-[var(--color-neutral-900)]">
            {value}
          </p>
          {subtitle && (
            <p className="mt-0.5 text-[var(--text-caption-size)] text-[var(--color-neutral-400)]">
              {subtitle}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Warning banner ──

function SpaceBanner({ warning, critical, freePct, availableMb }: {
  warning: boolean;
  critical: boolean;
  freePct: number;
  availableMb: number;
}) {
  if (!warning && !critical) return null;

  const isCritical = critical;
  const bg = isCritical ? "bg-[var(--color-error-surface)]" : "bg-[var(--color-warning-surface)]";
  const border = isCritical ? "border-[var(--color-error)]" : "border-[var(--color-warning)]";
  const textColor = isCritical ? "text-[var(--color-error)]" : "text-[var(--color-warning)]";
  const Icon = isCritical ? AlertCircle : AlertTriangle;

  return (
    <div className={`${bg} border ${border} rounded-[var(--radius-md)] p-4 flex items-start gap-3`} role="alert">
      <Icon size={20} className={`${textColor} shrink-0 mt-0.5`} aria-hidden="true" />
      <div>
        <p className={`font-medium text-[var(--text-body-size)] ${textColor}`}>
          {isCritical ? "Critical: Disk space very low" : "Warning: Disk space running low"}
        </p>
        <p className="mt-1 text-[var(--text-small-size)] text-[var(--color-neutral-700)]">
          {formatSize(availableMb)} free ({freePct}%).
          {isCritical
            ? " Ingestion and sync will fail soon. Free up disk space immediately or expand your volume."
            : " Consider cleaning up old backups or expanding your volume."
          }
        </p>
      </div>
    </div>
  );
}

// ── Page ──

export default function StoragePage() {
  const { data, error, isLoading, mutate } = useSWR<StorageResponse>(
    "/api/v1/admin/storage",
    swrFetcher,
    { refreshInterval: 30_000 },
  );

  if (isLoading) return <CardSkeleton count={5} />;
  if (error) return <ErrorBanner message="Failed to load storage stats." onRetry={() => mutate()} />;
  if (!data) return null;

  const usedMb = data.postgres_size_mb + data.qdrant_size_mb + data.paperless_size_mb + data.thumbnails_size_mb;

  const segments: BreakdownSegment[] = [
    { label: "PostgreSQL", sizeMb: data.postgres_size_mb, color: "var(--color-primary)" },
    { label: "Qdrant", sizeMb: data.qdrant_size_mb, color: "var(--color-info)" },
    { label: "Paperless", sizeMb: data.paperless_size_mb, color: "var(--color-success)" },
    { label: "Thumbnails", sizeMb: data.thumbnails_size_mb, color: "var(--color-warning)" },
  ];

  const topMimeTypes = Object.entries(data.file_counts.by_mime_type)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 5);

  return (
    <div className="space-y-6">
      {/* Warning banner */}
      <SpaceBanner
        warning={data.free_space_warning}
        critical={data.free_space_critical}
        freePct={data.free_space_pct}
        availableMb={data.available_disk_mb}
      />

      {/* Header summary */}
      <div className="bg-[var(--color-white)] rounded-[var(--radius-md)] border border-[var(--color-neutral-200)] p-5 shadow-[var(--shadow-sm)]">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-[var(--text-h2-size)] font-[var(--text-h2-weight)] text-[var(--color-neutral-900)]">
              Storage Overview
            </h2>
            <p className="mt-1 text-[var(--text-small-size)] text-[var(--color-neutral-500)]">
              {formatSize(usedMb)} used of {formatSize(data.total_disk_mb)} total ·{" "}
              {formatSize(data.available_disk_mb)} free ({data.free_space_pct}%)
            </p>
          </div>
          <Badge variant={data.free_space_critical ? "error" : data.free_space_warning ? "warning" : "success"}>
            {data.free_space_critical ? "Critical" : data.free_space_warning ? "Low" : "Healthy"}
          </Badge>
        </div>

        <BreakdownBar segments={segments} totalMb={usedMb} />
      </div>

      {/* Stat cards grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <StatCard
          icon={Database}
          label="PostgreSQL"
          value={formatSize(data.postgres_size_mb)}
          subtitle="Primary database"
          iconColor="text-[var(--color-primary)]"
        />
        <StatCard
          icon={HardDrive}
          label="Qdrant Vectors"
          value={formatSize(data.qdrant_size_mb)}
          subtitle="Embeddings storage"
          iconColor="text-[var(--color-info)]"
        />
        <StatCard
          icon={Archive}
          label="Paperless"
          value={formatSize(data.paperless_size_mb)}
          subtitle="Document management"
          iconColor="text-[var(--color-success)]"
        />
        <StatCard
          icon={FileText}
          label="Documents"
          value={String(data.file_counts.total)}
          subtitle={topMimeTypes.map(([m, c]) => `${m}: ${c}`).join(", ") || "No files"}
          iconColor="text-[var(--color-neutral-600)]"
        />
        <StatCard
          icon={Image}
          label="Photos"
          value={String(data.photo_counts.total)}
          subtitle={`${data.photo_counts.with_gps} with GPS`}
          iconColor="text-[var(--color-warning)]"
        />
        {data.face_counts && (
          <StatCard
            icon={Users}
            label="Face Data"
            value={`${data.face_counts.total_detections} faces`}
            subtitle={`${data.face_counts.total_clusters} groups · ${data.face_counts.photos_processed} photos processed`}
            iconColor="text-[var(--color-info)]"
          />
        )}
        <StatCard
          icon={HardDrive}
          label="Disk Available"
          value={formatSize(data.available_disk_mb)}
          subtitle={`${data.free_space_pct}% free`}
          iconColor={
            data.free_space_critical
              ? "text-[var(--color-error)]"
              : data.free_space_warning
                ? "text-[var(--color-warning)]"
                : "text-[var(--color-success)]"
          }
        />
      </div>
    </div>
  );
}
