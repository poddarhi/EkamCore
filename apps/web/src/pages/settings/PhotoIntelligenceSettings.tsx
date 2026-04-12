/**
 * Photo Intelligence Settings — face clustering consent flow (S11-004).
 *
 * Wires the ConsentDialog into a State A / State B layout:
 *   - State A (consent inactive): explanation + Enable button → dialog
 *   - State B (consent active): status card + Disable button → confirm modal
 *
 * Data source: GET /api/v1/settings/face-clustering/consent (S11-003).
 *
 * Rewritten from the G-03 placeholder which used the deprecated
 * core.face_clustering_consent boolean setting that was removed in S11-002.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { Brain, ShieldCheck, ShieldOff } from "lucide-react";
import { ApiError, apiFetch, swrFetcher } from "../../api/client";
import { useFlag } from "../../contexts/FlagContext";
import {
  Button,
  FeatureComingSoon,
  Modal,
  ProgressBar,
  Skeleton,
} from "../../design-system/components";
import ErrorBanner from "../../components/ErrorBanner";
import Toast from "../../components/Toast";
import ConsentDialog from "../../components/face/ConsentDialog";
import { t } from "../../i18n";

const CONSENT_ENDPOINT = "/api/v1/settings/face-clustering/consent";
const BACKFILL_ENDPOINT = "/api/v1/settings/face-clustering/backfill";
const BACKFILL_POLL_INTERVAL_MS = 5_000;

interface ConsentStateResponse {
  accepted: boolean;
  version: string | null;
  granted_at: string | null;
  revoked_at: string | null;
  current_text_version: string;
  current_text: string;
}

interface DeleteReportResponse {
  detection_count: number;
  cluster_count: number;
  qdrant_point_count: number;
  duration_ms: number;
}

type BackfillState = "running" | "completed" | "failed" | "cancelled";

interface BackfillJobResponse {
  id: string;
  workspace_id: string;
  state: BackfillState;
  started_at: string;
  finished_at: string | null;
  total_photos: number;
  processed_photos: number;
  failed_photos: number;
  error_message: string | null;
}

type ToastState =
  | { kind: "enabled" }
  | { kind: "disabled"; detection: number; clusters: number }
  | { kind: "error"; message: string }
  | null;

export default function PhotoIntelligenceSettings() {
  const photosEnabled = useFlag("photos_enabled");

  const { data, error, isLoading, mutate } = useSWR<ConsentStateResponse>(
    CONSENT_ENDPOINT,
    swrFetcher,
  );

  const [showConsentDialog, setShowConsentDialog] = useState(false);
  const [showDisableConfirm, setShowDisableConfirm] = useState(false);
  const [disableSubmitting, setDisableSubmitting] = useState(false);
  const [toast, setToast] = useState<ToastState>(null);

  const isActive = data?.accepted === true;

  // ── Grant flow ────────────────────────────────────────────────────────
  const handleConsentAccepted = useCallback(() => {
    setShowConsentDialog(false);
    setToast({ kind: "enabled" });
    mutate();
  }, [mutate]);

  // ── Revoke flow ───────────────────────────────────────────────────────
  const handleDisableConfirm = useCallback(async () => {
    setDisableSubmitting(true);
    try {
      const report = await apiFetch<DeleteReportResponse>(CONSENT_ENDPOINT, {
        method: "DELETE",
      });
      setShowDisableConfirm(false);
      setToast({
        kind: "disabled",
        detection: report.detection_count,
        clusters: report.cluster_count,
      });
      mutate();
    } catch (err) {
      const message = (err as ApiError).message ?? t("consent.disable.error");
      setToast({ kind: "error", message });
    } finally {
      setDisableSubmitting(false);
    }
  }, [mutate]);

  // ── Feature flag gate ─────────────────────────────────────────────────
  if (!photosEnabled) {
    return <FeatureComingSoon featureName={t("settings.photoIntelligence.title")} />;
  }

  if (isLoading) return <Skeleton variant="card" count={2} />;
  if (error) {
    return (
      <ErrorBanner
        message={t("settings.photoIntelligence.error")}
        onRetry={() => mutate()}
      />
    );
  }

  return (
    <div className="space-y-[var(--space-6)]">
      <h2 className="font-[var(--text-h2-weight)] text-[var(--text-h2-size)] text-[var(--color-neutral-900)]">
        {t("settings.photoIntelligence.title")}
      </h2>

      {isActive ? <EnabledStateCard
        onDisableClick={() => setShowDisableConfirm(true)}
      /> : <DisabledStateCard
        onEnableClick={() => setShowConsentDialog(true)}
      />}

      {/* Consent dialog */}
      <ConsentDialog
        open={showConsentDialog}
        onClose={() => setShowConsentDialog(false)}
        onAccepted={handleConsentAccepted}
      />

      {/* Disable confirmation modal */}
      <Modal
        open={showDisableConfirm}
        onClose={() => !disableSubmitting && setShowDisableConfirm(false)}
        title={t("consent.disable.confirm.title")}
        size="md"
        preventClose={disableSubmitting}
      >
        <div className="space-y-[var(--space-4)]">
          <p className="text-[var(--text-body-size)] leading-[var(--text-body-height)] text-[var(--color-neutral-700)]">
            {t("consent.disable.confirm.body")}
          </p>
          <div className="flex items-center justify-end gap-[var(--space-3)]">
            <Button
              variant="secondary"
              onClick={() => setShowDisableConfirm(false)}
              disabled={disableSubmitting}
            >
              {t("consent.disable.confirm.cancelButton")}
            </Button>
            <Button
              variant="danger"
              onClick={handleDisableConfirm}
              loading={disableSubmitting}
            >
              {t("consent.disable.confirm.confirmButton")}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Toast */}
      {toast && toast.kind === "enabled" && (
        <Toast
          variant="success"
          message={t("settings.photoIntelligence.toast.enabled")}
          onDismiss={() => setToast(null)}
        />
      )}
      {toast && toast.kind === "disabled" && (
        <Toast
          variant="success"
          message={t("settings.photoIntelligence.toast.disabled", {
            detection: toast.detection,
            clusters: toast.clusters,
          })}
          onDismiss={() => setToast(null)}
        />
      )}
      {toast && toast.kind === "error" && (
        <Toast
          variant="error"
          message={toast.message}
          onDismiss={() => setToast(null)}
        />
      )}
    </div>
  );
}

// ── State A: consent inactive ───────────────────────────────────────────

function DisabledStateCard({ onEnableClick }: { onEnableClick: () => void }) {
  return (
    <div className="bg-[var(--color-white)] rounded-[var(--radius-lg)] border border-[var(--color-neutral-200)] p-[var(--space-6)]">
      <div className="flex items-start gap-[var(--space-4)]">
        <div className="p-[var(--space-3)] rounded-[var(--radius-lg)] bg-[var(--color-neutral-100)]">
          <Brain
            size={24}
            className="text-[var(--color-neutral-400)]"
            aria-hidden="true"
          />
        </div>
        <div className="flex-1">
          <h3 className="font-medium text-[var(--text-body-size)] text-[var(--color-neutral-900)]">
            {t("settings.photoIntelligence.disabled.title")}
          </h3>
          <p className="mt-[var(--space-1)] text-[var(--text-small-size)] text-[var(--color-neutral-500)]">
            {t("settings.photoIntelligence.disabled.body")}
          </p>
          <div className="mt-[var(--space-4)]">
            <Button variant="primary" size="sm" onClick={onEnableClick}>
              {t("settings.photoIntelligence.disabled.cta")}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── State B: consent active ─────────────────────────────────────────────

function EnabledStateCard({
  onDisableClick,
}: {
  onDisableClick: () => void;
}) {
  // Face count / cluster count come from GET /api/v1/face/status which
  // will be built in S11-008. Until then, show placeholders.
  const faceCount = 0;
  const clusterCount = 0;

  return (
    <div className="bg-[var(--color-white)] rounded-[var(--radius-lg)] border border-[var(--color-neutral-200)] p-[var(--space-6)]">
      <div className="flex items-start gap-[var(--space-4)]">
        <div className="p-[var(--space-3)] rounded-[var(--radius-lg)] bg-[var(--color-success-surface)]">
          <ShieldCheck
            size={24}
            className="text-[var(--color-success)]"
            aria-hidden="true"
          />
        </div>
        <div className="flex-1">
          <h3 className="font-medium text-[var(--text-body-size)] text-[var(--color-neutral-900)]">
            {t("settings.photoIntelligence.enabled.title")}
          </h3>
          <dl className="mt-[var(--space-2)] flex flex-wrap gap-[var(--space-4)] text-[var(--text-small-size)] text-[var(--color-neutral-500)]">
            <div>
              <dt className="sr-only">Faces processed</dt>
              <dd>
                {t("settings.photoIntelligence.enabled.faceCount", {
                  count: faceCount,
                })}
              </dd>
            </div>
            <div>
              <dt className="sr-only">Groups</dt>
              <dd>
                {t("settings.photoIntelligence.enabled.clusterCount", {
                  count: clusterCount,
                })}
              </dd>
            </div>
          </dl>
          <BackfillControls />
          <div className="mt-[var(--space-4)] flex flex-wrap items-center gap-[var(--space-3)]">
            <Button variant="danger" size="sm" onClick={onDisableClick}>
              <ShieldOff size={14} className="mr-1.5" aria-hidden="true" />
              {t("settings.photoIntelligence.enabled.disableButton")}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Backfill controls (S11-007) ─────────────────────────────────────────
//
// Fetches the latest face_backfill_jobs row for the workspace, shows
// the right control surface for its state, and polls every 5s while
// a job is running. Polling stops automatically when the job reaches
// a terminal state, so a settled page is quiet.

function BackfillControls() {
  const { data, error, mutate } = useSWR<BackfillJobResponse | null>(
    BACKFILL_ENDPOINT,
    swrFetcher,
  );

  const [starting, setStarting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const isRunning = data?.state === "running";

  // Poll while running. We use a manual setInterval rather than SWR's
  // refreshInterval so the cadence is exactly what we want and the
  // interval clears the instant the job settles.
  const mutateRef = useRef(mutate);
  useEffect(() => {
    mutateRef.current = mutate;
  }, [mutate]);

  useEffect(() => {
    if (!isRunning) return;
    const h = setInterval(() => {
      mutateRef.current();
    }, BACKFILL_POLL_INTERVAL_MS);
    return () => clearInterval(h);
  }, [isRunning]);

  const handleStart = useCallback(async () => {
    setStarting(true);
    setLocalError(null);
    try {
      await apiFetch<BackfillJobResponse>(BACKFILL_ENDPOINT, {
        method: "POST",
      });
      mutate();
    } catch (err) {
      const e = err as ApiError;
      setLocalError(
        e.message ?? t("settings.photoIntelligence.backfill.startError"),
      );
    } finally {
      setStarting(false);
    }
  }, [mutate]);

  const handleCancel = useCallback(async () => {
    setCancelling(true);
    setLocalError(null);
    try {
      await apiFetch<BackfillJobResponse>(BACKFILL_ENDPOINT, {
        method: "DELETE",
      });
      mutate();
    } catch (err) {
      const e = err as ApiError;
      setLocalError(
        e.message ?? t("settings.photoIntelligence.backfill.cancelError"),
      );
    } finally {
      setCancelling(false);
    }
  }, [mutate]);

  // Loading SWR: render nothing until first response lands. Error on
  // fetch (e.g. consent was revoked in another tab): fail silently
  // — the surrounding disabled state will catch it on the next mutate.
  if (error) return null;

  // RUNNING — show progress bar + cancel button
  if (isRunning && data) {
    const pct =
      data.total_photos === 0
        ? 100
        : (data.processed_photos / data.total_photos) * 100;
    return (
      <div className="mt-[var(--space-4)] space-y-[var(--space-2)]">
        <ProgressBar
          value={pct}
          label={t("settings.photoIntelligence.backfill.progressLabel", {
            processed: data.processed_photos,
            total: data.total_photos,
          })}
        />
        <Button
          variant="secondary"
          size="sm"
          onClick={handleCancel}
          loading={cancelling}
        >
          {t("settings.photoIntelligence.backfill.cancelButton")}
        </Button>
      </div>
    );
  }

  // COMPLETED — show a summary + a "Run again" affordance
  if (data?.state === "completed") {
    return (
      <div className="mt-[var(--space-4)] space-y-[var(--space-2)]">
        <p className="text-[var(--text-small-size)] text-[var(--color-neutral-500)]">
          {t("settings.photoIntelligence.backfill.completedSummary", {
            processed: data.processed_photos,
            total: data.total_photos,
          })}
        </p>
        <Button
          variant="secondary"
          size="sm"
          onClick={handleStart}
          loading={starting}
        >
          {t("settings.photoIntelligence.backfill.runAgainButton")}
        </Button>
        {localError && (
          <p className="text-[var(--text-caption-size)] text-[var(--color-danger)]">
            {localError}
          </p>
        )}
      </div>
    );
  }

  // DEFAULT / first-run / cancelled / failed — show the start button
  return (
    <div className="mt-[var(--space-4)] space-y-[var(--space-2)]">
      <Button
        variant="secondary"
        size="sm"
        onClick={handleStart}
        loading={starting}
      >
        {t("settings.photoIntelligence.enabled.processHistorical")}
      </Button>
      {data?.state === "cancelled" && (
        <p className="text-[var(--text-caption-size)] text-[var(--color-neutral-500)]">
          {t("settings.photoIntelligence.backfill.cancelledSummary", {
            processed: data.processed_photos,
          })}
        </p>
      )}
      {data?.state === "failed" && (
        <p className="text-[var(--text-caption-size)] text-[var(--color-danger)]">
          {t("settings.photoIntelligence.backfill.failedSummary")}
        </p>
      )}
      {localError && (
        <p className="text-[var(--text-caption-size)] text-[var(--color-danger)]">
          {localError}
        </p>
      )}
    </div>
  );
}
