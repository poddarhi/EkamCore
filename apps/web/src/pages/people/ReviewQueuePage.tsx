/**
 * /people/review — review queue (S13-001 stub).
 *
 * Full review UI lands in S13-003. Stub wires flag, consent, and
 * SWR data so subsequent stories can flesh out the card grid.
 */

import { useEffect } from "react";

import EmptyState from "../../design-system/components/EmptyState";
import FeatureComingSoon from "../../design-system/components/FeatureComingSoon";
import Skeleton from "../../design-system/components/Skeleton";
import { useFlag } from "../../contexts/FlagContext";
import { useFaceConsent, useReviewQueue } from "../../hooks/usePeople";
import { t } from "../../i18n";
import { trackPeopleEvent } from "../../utils/metrics";

export default function ReviewQueuePage() {
  const enabled = useFlag("face_clustering_enabled");
  const { accepted, loading } = useFaceConsent();
  const { data, error, isLoading } = useReviewQueue(
    { limit: 20 },
    { shouldRetryOnError: false },
  );

  useEffect(() => {
    if (enabled && accepted) {
      trackPeopleEvent("reviewQueue.viewed");
    }
  }, [enabled, accepted]);

  if (!enabled) return <FeatureComingSoon featureName="People Review Queue" />;
  if (loading)
    return (
      <div className="max-w-[960px] mx-auto p-6">
        <Skeleton className="h-8 w-40 mb-4" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  if (!accepted) {
    return (
      <div className="max-w-[960px] mx-auto p-6">
        <EmptyState
          title={t("people.list.empty.title")}
          description={t("people.list.empty.description")}
        />
      </div>
    );
  }

  return (
    <div className="max-w-[960px] mx-auto p-6">
      <h1 className="text-2xl font-semibold mb-4">{t("reviewQueue.title")}</h1>
      {isLoading && <Skeleton className="h-24 w-full" />}
      {error && <p className="text-[var(--color-danger)]">{t("error.generic")}</p>}
      {data && data.items.length === 0 && (
        <EmptyState
          title={t("reviewQueue.empty.title")}
          description={t("reviewQueue.empty.description")}
        />
      )}
      {data && data.items.length > 0 && (
        <p className="text-sm text-[var(--color-neutral-600)]">
          {data.items.length} pending
        </p>
      )}
    </div>
  );
}
