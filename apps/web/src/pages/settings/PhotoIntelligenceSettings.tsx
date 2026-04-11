/**
 * Photo Intelligence Settings (G-03) — face clustering consent.
 */

import { useCallback, useState } from "react";
import useSWR from "swr";
import { Brain, ShieldCheck, ShieldOff } from "lucide-react";
import { swrFetcher, apiFetch } from "../../api/client";
import { useFlag } from "../../contexts/FlagContext";
import { Button, FeatureComingSoon, Skeleton } from "../../design-system/components";
import ErrorBanner from "../../components/ErrorBanner";

interface SettingsResponse {
  settings: Record<string, unknown>;
}

export default function PhotoIntelligenceSettings() {
  const photosEnabled = useFlag("photos_enabled");
  const { data, error, isLoading, mutate } = useSWR<SettingsResponse>("/api/v1/settings", swrFetcher);
  const [saving, setSaving] = useState(false);

  const consent = data?.settings?.face_clustering_consent === true;

  const toggleConsent = useCallback(async () => {
    setSaving(true);
    try {
      await apiFetch("/api/v1/settings", {
        method: "PATCH",
        body: JSON.stringify({ settings: { face_clustering_consent: !consent } }),
      });
      mutate();
    } finally {
      setSaving(false);
    }
  }, [consent, mutate]);

  if (!photosEnabled) return <FeatureComingSoon featureName="Photo Intelligence" />;
  if (isLoading) return <Skeleton variant="card" count={2} />;
  if (error) return <ErrorBanner message="Failed to load settings." onRetry={() => mutate()} />;

  return (
    <div className="space-y-[var(--space-6)]">
      <h2 className="font-[var(--text-h2-weight)] text-[var(--text-h2-size)] text-[var(--color-neutral-900)]">
        Photo Intelligence
      </h2>

      <div className="bg-[var(--color-white)] rounded-[var(--radius-lg)] border border-[var(--color-neutral-200)] p-[var(--space-6)]">
        <div className="flex items-start gap-[var(--space-4)]">
          <div className={`p-[var(--space-3)] rounded-[var(--radius-lg)] ${consent ? "bg-[var(--color-success-surface)]" : "bg-[var(--color-neutral-100)]"}`}>
            {consent ? (
              <ShieldCheck size={24} className="text-[var(--color-success)]" aria-hidden="true" />
            ) : (
              <Brain size={24} className="text-[var(--color-neutral-400)]" aria-hidden="true" />
            )}
          </div>
          <div className="flex-1">
            <h3 className="font-medium text-[var(--text-body-size)] text-[var(--color-neutral-900)]">
              Face Clustering
            </h3>
            <p className="mt-[var(--space-1)] text-[var(--text-small-size)] text-[var(--color-neutral-500)]">
              {consent
                ? "Face clustering is enabled. EkamCore groups photos by the people in them — all processing happens locally on your Mac."
                : "Enable face clustering to automatically group photos by the people in them. All processing happens locally — no images are sent anywhere."
              }
            </p>
            <div className="mt-[var(--space-4)]">
              <Button
                variant={consent ? "danger" : "primary"}
                size="sm"
                onClick={toggleConsent}
                loading={saving}
              >
                {consent ? (
                  <>
                    <ShieldOff size={14} className="mr-1.5" aria-hidden="true" />
                    Disable Face Clustering
                  </>
                ) : (
                  "Enable Face Clustering"
                )}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
