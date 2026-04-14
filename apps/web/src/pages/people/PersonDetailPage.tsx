/**
 * /people/:personId — trusted person detail (S13-001 stub).
 * Full detail UI lands in S13-004.
 */

import { useEffect } from "react";
import { useParams } from "react-router-dom";

import FeatureComingSoon from "../../design-system/components/FeatureComingSoon";
import Skeleton from "../../design-system/components/Skeleton";
import { useFlag } from "../../contexts/FlagContext";
import { useFaceConsent, usePerson } from "../../hooks/usePeople";
import { t } from "../../i18n";
import { trackPeopleEvent } from "../../utils/metrics";

export default function PersonDetailPage() {
  const enabled = useFlag("face_clustering_enabled");
  const { accepted, loading: consentLoading } = useFaceConsent();
  const { personId } = useParams<{ personId: string }>();
  const { data, error, isLoading } = usePerson(personId);

  useEffect(() => {
    if (enabled && accepted && personId) {
      trackPeopleEvent("people.detail.viewed", { person_id: personId });
    }
  }, [enabled, accepted, personId]);

  if (!enabled) return <FeatureComingSoon featureName="People" />;
  if (consentLoading || isLoading) {
    return (
      <div className="max-w-[960px] mx-auto p-6">
        <Skeleton className="h-8 w-40 mb-4" />
      </div>
    );
  }
  if (!accepted || error || !data) {
    return (
      <div className="max-w-[960px] mx-auto p-6">
        <p className="text-[var(--color-neutral-600)]">
          {t("error.generic")}
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-[960px] mx-auto p-6">
      <h1 className="text-2xl font-semibold">{data.display_name}</h1>
      <p className="text-sm text-[var(--color-neutral-600)] mt-1">
        {t("person.detail.confirmed")}
      </p>
    </div>
  );
}
