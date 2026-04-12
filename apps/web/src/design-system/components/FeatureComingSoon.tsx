import { Rocket } from "lucide-react";
import { t } from "../../i18n";

interface FeatureComingSoonProps {
  featureName: string;
}

export default function FeatureComingSoon({ featureName }: FeatureComingSoonProps) {
  return (
    <div className="flex flex-col items-center justify-center py-[var(--space-16)] px-[var(--space-4)] text-center">
      <div className="mb-[var(--space-4)] p-[var(--space-5)] rounded-full bg-[var(--color-primary-surface)]">
        <Rocket size={40} className="text-[var(--color-primary)]" aria-hidden="true" />
      </div>
      <h2 className="font-[var(--text-h2-weight)] text-[var(--text-h2-size)] text-[var(--color-neutral-900)] mb-[var(--space-2)]">
        {t("feature.comingSoon.heading", { feature: featureName })}
      </h2>
      <p className="max-w-md text-[var(--text-body-size)] text-[var(--color-neutral-500)]">
        {t("feature.comingSoon.description", { feature: featureName.toLowerCase() })}
      </p>
    </div>
  );
}
