/**
 * /people/operations — merge/split/rename/delete history (S13-001 stub).
 * Full drawer UI lands in S13-006 (UndoDrawer).
 */

import FeatureComingSoon from "../../design-system/components/FeatureComingSoon";
import Skeleton from "../../design-system/components/Skeleton";
import { useFlag } from "../../contexts/FlagContext";
import { useFaceConsent, usePersonOperations } from "../../hooks/usePeople";
import { t } from "../../i18n";

export default function OperationsHistoryPage() {
  const enabled = useFlag("face_clustering_enabled");
  const { accepted, loading } = useFaceConsent();
  const { data, isLoading } = usePersonOperations(50);

  if (!enabled) return <FeatureComingSoon featureName="People history" />;
  if (loading || isLoading) {
    return (
      <div className="max-w-[960px] mx-auto p-6">
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }
  if (!accepted) {
    return (
      <div className="max-w-[960px] mx-auto p-6">
        <p className="text-[var(--color-neutral-600)]">
          {t("undo.drawer.empty")}
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-[960px] mx-auto p-6">
      <h1 className="text-2xl font-semibold mb-4">{t("undo.drawer.title")}</h1>
      {data && data.items.length === 0 ? (
        <p className="text-[var(--color-neutral-600)]">
          {t("undo.drawer.empty")}
        </p>
      ) : (
        <ul className="space-y-2">
          {data?.items.map((op) => (
            <li
              key={op.id}
              className="rounded border border-[var(--color-neutral-200)] p-3"
            >
              <span className="font-medium">{op.operation_type}</span>
              <span className="ml-2 text-sm text-[var(--color-neutral-600)]">
                {op.undone_at ? t("undo.drawer.undoneLabel") : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
