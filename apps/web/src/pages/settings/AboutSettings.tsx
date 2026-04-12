/**
 * About Settings (G-03) — version, system info, links.
 */

import useSWR from "swr";
import { Info, ExternalLink } from "lucide-react";
import { swrFetcher, type HealthResponse } from "../../api/client";
import { Card, Skeleton } from "../../design-system/components";
import { t } from "../../i18n";

export default function AboutSettings() {
  const { data } = useSWR<HealthResponse>("/health", swrFetcher);

  return (
    <div className="space-y-[var(--space-6)]">
      <h2 className="font-[var(--text-h2-weight)] text-[var(--text-h2-size)] text-[var(--color-neutral-900)]">
        {t("settings.about.title")}
      </h2>

      <Card>
        <div className="flex items-start gap-[var(--space-4)]">
          <div className="p-[var(--space-3)] rounded-[var(--radius-lg)] bg-[var(--color-primary-surface)]">
            <Info size={20} className="text-[var(--color-primary)]" aria-hidden="true" />
          </div>
          <div className="space-y-[var(--space-2)]">
            <dl className="space-y-[var(--space-2)] text-[var(--text-small-size)]">
              <div className="flex gap-[var(--space-4)]">
                <dt className="text-[var(--color-neutral-500)] w-32 shrink-0">{t("settings.about.version")}</dt>
                <dd className="text-[var(--color-neutral-900)] font-medium">{data?.version ?? "—"}</dd>
              </div>
              <div className="flex gap-[var(--space-4)]">
                <dt className="text-[var(--color-neutral-500)] w-32 shrink-0">{t("settings.about.ramMode")}</dt>
                <dd className="text-[var(--color-neutral-900)]">{data?.ram_mode ?? "—"}</dd>
              </div>
              <div className="flex gap-[var(--space-4)]">
                <dt className="text-[var(--color-neutral-500)] w-32 shrink-0">{t("settings.about.architecture")}</dt>
                <dd className="text-[var(--color-neutral-900)]">{t("settings.about.architectureValue")}</dd>
              </div>
            </dl>
          </div>
        </div>
      </Card>

      <div className="space-y-[var(--space-2)]">
        <a
          href="https://github.com/ekamcore/ekamcore"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-[var(--space-2)] text-[var(--text-small-size)] text-[var(--color-primary)] hover:underline"
        >
          <ExternalLink size={14} aria-hidden="true" />
          {t("settings.about.documentation")}
        </a>
        <a
          href="https://github.com/ekamcore/ekamcore/blob/main/LICENSE"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-[var(--space-2)] text-[var(--text-small-size)] text-[var(--color-primary)] hover:underline"
        >
          <ExternalLink size={14} aria-hidden="true" />
          {t("settings.about.licenses")}
        </a>
      </div>
    </div>
  );
}
