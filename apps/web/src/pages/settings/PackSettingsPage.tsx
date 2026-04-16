/**
 * /settings/pack — Personal Life Assistant settings (S14-010).
 *
 * Three visual states:
 * 1. face_clustering_enabled OFF → prerequisite banner.
 * 2. pla_pack_enabled OFF → description + enable CTA.
 * 3. pla_pack_enabled ON → status card, workflow toggles,
 *    schedule config, run history.
 */

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import useSWR from "swr";

import Button from "../../design-system/components/Button";
import ErrorBanner from "../../design-system/components/ErrorBanner";
import Modal from "../../design-system/components/Modal";
import Skeleton from "../../design-system/components/Skeleton";
import Toast, { type ToastVariant } from "../../components/Toast";
import { useFlag } from "../../contexts/FlagContext";
import { apiFetch, swrFetcher } from "../../api/client";
import { t } from "../../i18n";

type ToastState = { message: string; variant: ToastVariant } | null;

export default function PackSettingsPage() {
  const faceEnabled = useFlag("face_clustering_enabled");
  const plaEnabled = useFlag("pla_pack_enabled");

  const {
    data: settingsData,
    mutate: mutateSettings,
  } = useSWR<{ settings: Record<string, unknown> }>(
    "/api/v1/settings",
    swrFetcher,
    { shouldRetryOnError: false },
  );

  const {
    data: runsData,
  } = useSWR<{ items: Array<Record<string, unknown>> }>(
    plaEnabled ? "/api/v1/admin/packs/pla/runs?workspace_id=default&limit=10" : null,
    swrFetcher,
    { shouldRetryOnError: false },
  );

  const [toast, setToast] = useState<ToastState>(null);
  const [disableModalOpen, setDisableModalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const settings = settingsData?.settings ?? {};

  const patchSetting = useCallback(
    async (key: string, value: unknown) => {
      try {
        await apiFetch("/api/v1/settings", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ settings: { [key]: value } }),
        });
        await mutateSettings();
      } catch {
        setToast({ message: t("error.generic"), variant: "error" });
      }
    },
    [mutateSettings],
  );

  const enablePla = async () => {
    setSubmitting(true);
    await patchSetting("pla_pack_enabled", true);
    setSubmitting(false);
    setToast({ message: t("settings.pack.enabled.title"), variant: "success" });
  };

  const disablePla = async () => {
    setSubmitting(true);
    await patchSetting("pla_pack_enabled", false);
    setDisableModalOpen(false);
    setSubmitting(false);
    setToast({ message: t("settings.pack.disabled.title"), variant: "success" });
  };

  // ── Prerequisite: face clustering required ──
  if (!faceEnabled) {
    return (
      <div>
        <h2 className="text-xl font-semibold mb-4">
          {t("settings.pack.title")}
        </h2>
        <div className="rounded-[var(--radius-lg)] border border-[var(--color-neutral-200)] p-6">
          <p className="text-sm text-[var(--color-neutral-700)] mb-3">
            {t("settings.pack.disabled.prereq")}
          </p>
          <Link
            to="/settings/photo-intelligence"
            className="text-sm text-[var(--color-primary)] hover:underline"
          >
            Go to Photo Intelligence Settings
          </Link>
        </div>
        {toast && (
          <Toast
            message={toast.message}
            variant={toast.variant}
            onDismiss={() => setToast(null)}
          />
        )}
      </div>
    );
  }

  // ── PLA disabled ──
  if (!plaEnabled) {
    return (
      <div>
        <h2 className="text-xl font-semibold mb-4">
          {t("settings.pack.title")}
        </h2>
        <div className="rounded-[var(--radius-lg)] border border-[var(--color-neutral-200)] p-6">
          <p className="font-medium mb-1">
            {t("settings.pack.disabled.title")}
          </p>
          <p className="text-sm text-[var(--color-neutral-600)] mb-4">
            {t("settings.pack.disabled.body")}
          </p>
          <Button
            variant="primary"
            loading={submitting}
            onClick={() => void enablePla()}
          >
            {t("settings.pack.disabled.cta")}
          </Button>
        </div>
        {toast && (
          <Toast
            message={toast.message}
            variant={toast.variant}
            onDismiss={() => setToast(null)}
          />
        )}
      </div>
    );
  }

  // ── PLA enabled — full config ──

  const followUpsOn = !!settings["pla_follow_ups_enabled"];
  const weeklyOn = !!settings["pla_weekly_summary_enabled"];
  const relationshipOn = !!settings["pla_relationship_reminders_enabled"];
  const lookbackDays = Number(settings["pack.pla.follow_up_lookback_days"] ?? 7);
  const inactiveDays = Number(
    settings["pack.pla.relationship_inactive_days"] ?? 30,
  );
  const maxSuggestions = Number(
    settings["pack.pla.max_suggestions_per_day"] ?? 5,
  );
  const dailyTime = String(settings["pack.pla.daily_run_time"] ?? "06:00");
  const weeklyDay = String(settings["pack.pla.weekly_run_day"] ?? "monday");
  const weeklyTime = String(settings["pack.pla.weekly_run_time"] ?? "08:00");

  const runs = runsData?.items ?? [];

  return (
    <div>
      <h2 className="text-xl font-semibold mb-4" data-testid="pack-settings-title">
        {t("settings.pack.title")}
      </h2>

      {/* Status + disable */}
      <div className="rounded-[var(--radius-lg)] border border-[var(--color-neutral-200)] p-5 mb-6">
        <div className="flex items-center justify-between">
          <p className="font-medium text-[var(--color-success)]">
            {t("settings.pack.enabled.title")}
          </p>
          <Button
            variant="danger"
            size="sm"
            onClick={() => setDisableModalOpen(true)}
          >
            {t("settings.pack.enabled.disableButton")}
          </Button>
        </div>
      </div>

      {/* Workflow toggles */}
      <div className="space-y-4 mb-6">
        <ToggleRow
          label={t("settings.pack.followUps.label")}
          description={t("settings.pack.followUps.description")}
          checked={followUpsOn}
          onChange={(v) => void patchSetting("pla_follow_ups_enabled", v)}
        />
        {followUpsOn && (
          <RangeRow
            label={t("settings.pack.followUps.lookbackLabel")}
            value={lookbackDays}
            min={3}
            max={30}
            onChange={(v) => void patchSetting("pack.pla.follow_up_lookback_days", v)}
          />
        )}

        <ToggleRow
          label={t("settings.pack.weeklySummary.label")}
          description={t("settings.pack.weeklySummary.description")}
          checked={weeklyOn}
          onChange={(v) => void patchSetting("pla_weekly_summary_enabled", v)}
        />
        {weeklyOn && (
          <div className="flex gap-3 pl-6">
            <label className="flex flex-col gap-1 text-xs">
              <span>{t("settings.pack.weeklySummary.dayLabel")}</span>
              <select
                value={weeklyDay}
                onChange={(e) =>
                  void patchSetting("pack.pla.weekly_run_day", e.target.value)
                }
                className="border border-[var(--color-neutral-200)] rounded p-1 text-sm"
              >
                {[
                  "monday",
                  "tuesday",
                  "wednesday",
                  "thursday",
                  "friday",
                  "saturday",
                  "sunday",
                ].map((d) => (
                  <option key={d} value={d}>
                    {d.charAt(0).toUpperCase() + d.slice(1)}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs">
              <span>{t("settings.pack.weeklySummary.timeLabel")}</span>
              <input
                type="time"
                value={weeklyTime}
                onChange={(e) =>
                  void patchSetting("pack.pla.weekly_run_time", e.target.value)
                }
                className="border border-[var(--color-neutral-200)] rounded p-1 text-sm"
              />
            </label>
          </div>
        )}

        <ToggleRow
          label={t("settings.pack.relationshipReminders.label")}
          description={t("settings.pack.relationshipReminders.description")}
          checked={relationshipOn}
          onChange={(v) =>
            void patchSetting("pla_relationship_reminders_enabled", v)
          }
        />
        {relationshipOn && (
          <RangeRow
            label={t("settings.pack.relationshipReminders.inactiveDaysLabel")}
            value={inactiveDays}
            min={14}
            max={90}
            onChange={(v) =>
              void patchSetting("pack.pla.relationship_inactive_days", v)
            }
          />
        )}
      </div>

      {/* General settings */}
      <div className="space-y-3 mb-6">
        <label className="flex items-center gap-3 text-sm">
          <span>{t("settings.pack.runTimeLabel")}</span>
          <input
            type="time"
            value={dailyTime}
            onChange={(e) =>
              void patchSetting("pack.pla.daily_run_time", e.target.value)
            }
            className="border border-[var(--color-neutral-200)] rounded p-1 text-sm"
          />
        </label>
        <RangeRow
          label={t("settings.pack.maxSuggestionsLabel")}
          value={maxSuggestions}
          min={1}
          max={20}
          onChange={(v) =>
            void patchSetting("pack.pla.max_suggestions_per_day", v)
          }
        />
      </div>

      {/* Run history */}
      {runs.length > 0 && (
        <details className="mb-6">
          <summary className="text-sm font-medium cursor-pointer">
            Run history ({runs.length})
          </summary>
          <table className="w-full mt-2 text-xs" data-testid="run-history">
            <thead>
              <tr className="text-left text-[var(--color-neutral-500)] border-b">
                <th className="py-1">Date</th>
                <th>Trigger</th>
                <th>State</th>
                <th>Cards</th>
                <th>Duration</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr
                  key={String(r.id)}
                  className={[
                    "border-b",
                    r.state === "failed" || r.state === "timeout"
                      ? "text-[var(--color-error)]"
                      : "",
                  ].join(" ")}
                >
                  <td className="py-1">
                    {r.started_at
                      ? new Date(String(r.started_at)).toLocaleString()
                      : "—"}
                  </td>
                  <td>{String(r.trigger)}</td>
                  <td>{String(r.state)}</td>
                  <td>{String(r.cards_produced ?? 0)}</td>
                  <td>{String(r.duration_ms ?? "—")}ms</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}

      {/* Disable confirm */}
      <Modal
        open={disableModalOpen}
        onClose={() => setDisableModalOpen(false)}
        title="Disable Personal Life Assistant?"
        size="sm"
      >
        <p className="text-sm text-[var(--color-neutral-700)] mb-4">
          Follow-up suggestions, weekly summaries, and relationship
          reminders will stop. Your existing cards will remain visible
          until dismissed.
        </p>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setDisableModalOpen(false)}>
            Cancel
          </Button>
          <Button
            variant="danger"
            loading={submitting}
            onClick={() => void disablePla()}
          >
            Disable PLA
          </Button>
        </div>
      </Modal>

      {toast && (
        <Toast
          message={toast.message}
          variant={toast.variant}
          onDismiss={() => setToast(null)}
        />
      )}
    </div>
  );
}

// ── Helpers ──────────────────────────────────────────────────────────────

function ToggleRow({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-start gap-3 cursor-pointer">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-1 shrink-0"
      />
      <div>
        <span className="text-sm font-medium">{label}</span>
        <p className="text-xs text-[var(--color-neutral-600)]">
          {description}
        </p>
      </div>
    </label>
  );
}

function RangeRow({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex items-center gap-3 pl-6">
      <label className="text-xs whitespace-nowrap">{label}</label>
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-valuetext={`${value}`}
        className="flex-1"
      />
      <span className="text-xs w-8 text-right tabular-nums">{value}</span>
    </div>
  );
}
