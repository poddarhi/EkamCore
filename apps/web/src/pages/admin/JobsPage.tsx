/**
 * Admin Jobs Dashboard (S09-003)
 *
 * Shows ingestion pipeline jobs grouped by status: Active, Recently Completed,
 * Failed, Skipped. Auto-refreshes every 5 seconds via SWR. Supports retrying
 * individual failed jobs or all failed jobs at once.
 */

import { useState } from "react";
import useSWR from "swr";
import {
  ChevronDown,
  ChevronRight,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  SkipForward,
  RotateCcw,
} from "lucide-react";
import { swrFetcher, apiFetch } from "../../api/client";
import { Button, Badge } from "../../design-system/components";
import { CardSkeleton } from "../../components/CardSkeleton";
import { ErrorBanner } from "../../components/ErrorBanner";

// ── Types ──

interface Job {
  id: string;
  file_id: string;
  filename: string;
  source_name: string;
  current_stage: string;
  stages_completed: string[];
  retry_count: number;
  error_message: string | null;
  elapsed_seconds: number | null;
  created_at: string | null;
  updated_at: string | null;
}

interface JobsResponse {
  active: Job[];
  recently_completed: Job[];
  failed: Job[];
  skipped: Job[];
}

// ── Pipeline stage definitions ──

const PIPELINE_STAGES = [
  "DISCOVERED",
  "FINGERPRINTED",
  "METADATA_EXTRACTED",
  "TEXT_EXTRACTED",
  "OCR_COMPLETED",
  "EMBEDDING_QUEUED",
  "EMBEDDED",
  "COMPLETED",
];

const STAGE_LABELS: Record<string, string> = {
  DISCOVERED: "Discovered",
  FINGERPRINTED: "Fingerprinted",
  METADATA_EXTRACTED: "Metadata",
  TEXT_EXTRACTED: "Text",
  OCR_COMPLETED: "OCR",
  EMBEDDING_QUEUED: "Queued",
  EMBEDDED: "Embedded",
  COMPLETED: "Done",
  FAILED: "Failed",
  SKIPPED: "Skipped",
};

// ── Stage progress indicator ──

function StageProgress({ currentStage, stagesCompleted }: { currentStage: string; stagesCompleted: string[] }) {
  const completedSet = new Set(stagesCompleted);
  const currentIdx = PIPELINE_STAGES.indexOf(currentStage);

  return (
    <div className="flex items-center gap-1" role="progressbar" aria-label={`Stage: ${STAGE_LABELS[currentStage] ?? currentStage}`}>
      {PIPELINE_STAGES.map((stage, i) => {
        const isCompleted = completedSet.has(stage) || (currentStage === "COMPLETED" && i < PIPELINE_STAGES.length);
        const isCurrent = stage === currentStage;
        const isFuture = !isCompleted && !isCurrent;

        let dotClass = "w-2.5 h-2.5 rounded-full transition-colors duration-[var(--duration-normal)]";
        if (isCompleted) {
          dotClass += " bg-[var(--color-success)]";
        } else if (isCurrent) {
          dotClass += " bg-[var(--color-primary)] animate-pulse";
        } else {
          dotClass += " bg-[var(--color-neutral-200)]";
        }

        return (
          <div key={stage} className="flex items-center">
            {i > 0 && (
              <div
                className={`w-3 h-0.5 ${
                  isCompleted || (isCurrent && i <= currentIdx)
                    ? "bg-[var(--color-success)]"
                    : "bg-[var(--color-neutral-200)]"
                }`}
              />
            )}
            <div className={dotClass} title={STAGE_LABELS[stage] ?? stage} />
          </div>
        );
      })}
      <span className="ml-2 text-[var(--text-caption-size)] text-[var(--color-neutral-500)]">
        {STAGE_LABELS[currentStage] ?? currentStage}
      </span>
    </div>
  );
}

// ── Job row ──

function JobRow({ job, onRetry }: { job: Job; onRetry?: (id: string) => void }) {
  const isFailed = job.current_stage === "FAILED";
  const elapsed = job.elapsed_seconds != null ? `${job.elapsed_seconds}s` : "—";

  return (
    <div className="flex items-center gap-4 px-4 py-3 border-b border-[var(--color-neutral-100)] last:border-b-0 hover:bg-[var(--color-neutral-50)] transition-colors duration-[var(--duration-fast)]">
      {/* Filename + source */}
      <div className="min-w-0 flex-1">
        <p className="text-[var(--text-body-size)] font-medium text-[var(--color-neutral-900)] truncate">
          {job.filename}
        </p>
        <p className="text-[var(--text-caption-size)] text-[var(--color-neutral-500)] truncate">
          {job.source_name} · {elapsed}
          {job.retry_count > 0 && ` · ${job.retry_count} retries`}
        </p>
        {isFailed && job.error_message && (
          <p className="mt-1 text-[var(--text-caption-size)] text-[var(--color-error)] truncate" title={job.error_message}>
            {job.error_message}
          </p>
        )}
      </div>

      {/* Stage progress */}
      <div className="hidden sm:block shrink-0">
        <StageProgress currentStage={job.current_stage} stagesCompleted={job.stages_completed} />
      </div>

      {/* Retry button (for failed jobs) */}
      {isFailed && onRetry && (
        <button
          onClick={() => onRetry(job.id)}
          className="shrink-0 p-2 rounded-[var(--radius-md)] text-[var(--color-primary)] hover:bg-[var(--color-primary-surface)] transition-colors duration-[var(--duration-normal)] cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary-light)]"
          aria-label={`Retry ${job.filename}`}
        >
          <RotateCcw size={16} aria-hidden="true" />
        </button>
      )}
    </div>
  );
}

// ── Collapsible section ──

function JobSection({
  title,
  icon,
  jobs,
  defaultOpen = false,
  onRetry,
  variant = "default",
}: {
  title: string;
  icon: React.ReactNode;
  jobs: Job[];
  defaultOpen?: boolean;
  onRetry?: (id: string) => void;
  variant?: "default" | "error" | "success";
}) {
  const [open, setOpen] = useState(defaultOpen);

  const borderColor =
    variant === "error"
      ? "border-l-[var(--color-error)]"
      : variant === "success"
        ? "border-l-[var(--color-success)]"
        : "border-l-[var(--color-primary-light)]";

  return (
    <div className={`bg-[var(--color-white)] rounded-[var(--radius-md)] border border-[var(--color-neutral-200)] border-l-[3px] ${borderColor} shadow-[var(--shadow-sm)]`}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-3 w-full px-4 py-3 text-left cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--color-primary-light)]"
        aria-expanded={open}
      >
        {open ? <ChevronDown size={18} aria-hidden="true" /> : <ChevronRight size={18} aria-hidden="true" />}
        <span className="flex items-center gap-2 flex-1">
          {icon}
          <span className="font-medium text-[var(--text-body-size)] text-[var(--color-neutral-900)]">
            {title}
          </span>
        </span>
        <Badge variant={jobs.length > 0 ? (variant === "error" ? "error" : "info") : "info"}>
          {jobs.length}
        </Badge>
      </button>

      {open && (
        <div className="border-t border-[var(--color-neutral-100)]">
          {jobs.length === 0 ? (
            <p className="px-4 py-6 text-center text-[var(--text-small-size)] text-[var(--color-neutral-400)]">
              No jobs in this category.
            </p>
          ) : (
            jobs.map((job) => <JobRow key={job.id} job={job} onRetry={onRetry} />)
          )}
        </div>
      )}
    </div>
  );
}

// ── Page ──

export default function JobsPage() {
  const { data, error, isLoading, mutate } = useSWR<JobsResponse>(
    "/api/v1/admin/jobs",
    swrFetcher,
    { refreshInterval: 5_000 },
  );

  const [retrying, setRetrying] = useState(false);

  async function handleRetry(jobId: string) {
    await apiFetch(`/api/v1/admin/jobs/${jobId}/retry`, { method: "POST" });
    mutate();
  }

  async function handleRetryAll() {
    setRetrying(true);
    try {
      await apiFetch("/api/v1/admin/jobs/retry-all-failed", { method: "POST" });
      mutate();
    } finally {
      setRetrying(false);
    }
  }

  if (isLoading) return <CardSkeleton count={4} />;
  if (error) return <ErrorBanner message="Failed to load ingestion jobs." onRetry={() => mutate()} />;
  if (!data) return null;

  const failedCount = data.failed.length;

  return (
    <div className="space-y-4">
      {/* Header with bulk action */}
      {failedCount > 0 && (
        <div className="flex items-center justify-between">
          <p className="text-[var(--text-small-size)] text-[var(--color-neutral-600)]">
            {failedCount} failed job{failedCount !== 1 ? "s" : ""}
          </p>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleRetryAll}
            disabled={retrying}
          >
            {retrying ? (
              <Loader2 size={14} className="animate-spin mr-1.5" aria-hidden="true" />
            ) : (
              <RefreshCw size={14} className="mr-1.5" aria-hidden="true" />
            )}
            Retry All Failed
          </Button>
        </div>
      )}

      {/* Job sections */}
      <JobSection
        title="Active"
        icon={<Loader2 size={16} className="text-[var(--color-primary)] animate-spin" aria-hidden="true" />}
        jobs={data.active}
        defaultOpen={true}
      />

      <JobSection
        title="Failed"
        icon={<AlertTriangle size={16} className="text-[var(--color-error)]" aria-hidden="true" />}
        jobs={data.failed}
        defaultOpen={failedCount > 0}
        onRetry={handleRetry}
        variant="error"
      />

      <JobSection
        title="Recently Completed"
        icon={<CheckCircle2 size={16} className="text-[var(--color-success)]" aria-hidden="true" />}
        jobs={data.recently_completed}
        variant="success"
      />

      <JobSection
        title="Skipped"
        icon={<SkipForward size={16} className="text-[var(--color-neutral-400)]" aria-hidden="true" />}
        jobs={data.skipped}
      />
    </div>
  );
}
