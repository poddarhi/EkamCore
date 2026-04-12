/**
 * General Settings (G-03) — date/time format, theme.
 */

import { useCallback, useEffect, useState } from "react";
import useSWR from "swr";
import { swrFetcher, apiFetch } from "../../api/client";
import { Button, Dropdown, Skeleton } from "../../design-system/components";
import ErrorBanner from "../../components/ErrorBanner";
import { t } from "../../i18n";

interface SettingsResponse {
  settings: Record<string, unknown>;
  registry: Record<string, { type: string; options?: string[]; default: unknown }>;
}

export default function GeneralSettings() {
  const { data, error, isLoading, mutate } = useSWR<SettingsResponse>("/api/v1/settings", swrFetcher);
  const [dateFormat, setDateFormat] = useState("");
  const [timeFormat, setTimeFormat] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (data) {
      setDateFormat(String(data.settings.date_format ?? ""));
      setTimeFormat(String(data.settings.time_format ?? ""));
    }
  }, [data]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setSaved(false);
    try {
      await apiFetch("/api/v1/settings", {
        method: "PATCH",
        body: JSON.stringify({ settings: { date_format: dateFormat, time_format: timeFormat } }),
      });
      mutate();
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } finally {
      setSaving(false);
    }
  }, [dateFormat, timeFormat, mutate]);

  if (isLoading) return <Skeleton variant="card" count={3} />;
  if (error) return <ErrorBanner message={t("settings.general.error")} onRetry={() => mutate()} />;

  const dateOptions = (data?.registry.date_format?.options ?? []).map((o) => ({ value: o, label: o }));
  const timeOptions = (data?.registry.time_format?.options ?? []).map((o) => ({ value: o, label: o === "12h" ? t("settings.general.timeFormat.12h") : t("settings.general.timeFormat.24h") }));

  return (
    <div className="space-y-[var(--space-6)]">
      <h2 className="font-[var(--text-h2-weight)] text-[var(--text-h2-size)] text-[var(--color-neutral-900)]">
        {t("settings.general.title")}
      </h2>

      <div className="space-y-[var(--space-4)] max-w-md">
        <div>
          <label className="block mb-[var(--space-1)] text-[var(--text-small-size)] font-medium text-[var(--color-neutral-700)]">
            {t("settings.general.dateFormat")}
          </label>
          <Dropdown options={dateOptions} value={dateFormat} onChange={setDateFormat} />
        </div>

        <div>
          <label className="block mb-[var(--space-1)] text-[var(--text-small-size)] font-medium text-[var(--color-neutral-700)]">
            {t("settings.general.timeFormat")}
          </label>
          <Dropdown options={timeOptions} value={timeFormat} onChange={setTimeFormat} />
        </div>

        <div>
          <label className="block mb-[var(--space-1)] text-[var(--text-small-size)] font-medium text-[var(--color-neutral-700)]">
            {t("settings.general.theme")}
          </label>
          <Dropdown
            options={[{ value: "light", label: t("settings.general.theme.light") }]}
            value="light"
            onChange={() => {}}
            disabled
          />
          <p className="mt-[var(--space-1)] text-[var(--text-caption-size)] text-[var(--color-neutral-400)]">
            {t("settings.general.theme.hint")}
          </p>
        </div>

        <Button onClick={handleSave} loading={saving} disabled={saving}>
          {saved ? t("settings.general.saved") : t("settings.general.save")}
        </Button>
      </div>
    </div>
  );
}
