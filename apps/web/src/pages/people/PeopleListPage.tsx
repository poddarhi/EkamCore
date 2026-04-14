/**
 * /people — list of trusted persons (S13-001 stub).
 *
 * Full list UI lands in S13-002. This stub proves the routing,
 * flag gating, consent wiring, and SWR data flow are correct.
 */

import { useEffect } from "react";
import { Link } from "react-router-dom";

import FeatureComingSoon from "../../design-system/components/FeatureComingSoon";
import EmptyState from "../../design-system/components/EmptyState";
import Skeleton from "../../design-system/components/Skeleton";
import { useFlag } from "../../contexts/FlagContext";
import { useFaceConsent, usePeopleList } from "../../hooks/usePeople";
import { t } from "../../i18n";
import { trackPeopleEvent } from "../../utils/metrics";

export default function PeopleListPage() {
  const enabled = useFlag("face_clustering_enabled");
  const { accepted, loading: consentLoading } = useFaceConsent();
  const { data, error, isLoading } = usePeopleList(
    { limit: 20 },
    { shouldRetryOnError: false },
  );

  useEffect(() => {
    if (enabled && accepted) {
      trackPeopleEvent("people.list.viewed");
    }
  }, [enabled, accepted]);

  if (!enabled) {
    return <FeatureComingSoon featureName="People" />;
  }
  if (consentLoading) {
    return (
      <div className="max-w-[960px] mx-auto p-6">
        <Skeleton className="h-8 w-40 mb-4" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }
  if (!accepted) {
    return (
      <div className="max-w-[960px] mx-auto p-6">
        <EmptyState
          title={t("people.list.empty.title")}
          description={t("people.list.empty.description")}
          action={
            <Link
              to="/settings/photo-intelligence"
              className="text-[var(--color-primary)] underline"
            >
              {t("people.list.empty.cta")}
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <div className="max-w-[960px] mx-auto p-6">
      <h1 className="text-2xl font-semibold mb-4">{t("people.list.title")}</h1>
      {isLoading && <Skeleton className="h-24 w-full" />}
      {error && (
        <p className="text-[var(--color-danger)]">{t("error.generic")}</p>
      )}
      {data && data.items.length === 0 && (
        <EmptyState
          title={t("people.list.empty.title")}
          description={t("people.list.empty.description")}
          action={
            <Link
              to="/people/review"
              className="text-[var(--color-primary)] underline"
            >
              {t("people.list.empty.cta")}
            </Link>
          }
        />
      )}
      {data && data.items.length > 0 && (
        <ul className="space-y-2">
          {data.items.map((p) => (
            <li key={p.id}>
              <Link
                to={`/people/${p.id}`}
                className="block rounded border border-[var(--color-neutral-200)] p-3 hover:bg-[var(--color-neutral-50)]"
              >
                {p.display_name}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
