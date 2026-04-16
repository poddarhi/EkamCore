/**
 * WeeklySummaryCard — PLA LLM-generated weekly recap (S14-009).
 */

import { Calendar, Sparkles, X } from "lucide-react";

import { Card } from "../../design-system/components";
import PersonAvatar from "../people/PersonAvatar";
import { packCardsApi } from "../../api/packCards";
import { t } from "../../i18n";
import { trackPeopleEvent } from "../../utils/metrics";

interface WeeklySummaryCardProps {
  cardId: string;
  payload: Record<string, unknown>;
  onAcknowledged?: () => void;
}

export default function WeeklySummaryCard({
  cardId,
  payload,
  onAcknowledged,
}: WeeklySummaryCardProps) {
  const summary = (payload.summary_text as string) ?? "";
  const start = (payload.week_start as string) ?? "";
  const end = (payload.week_end as string) ?? "";
  const stats = (payload.stats as Record<string, number>) ?? {};
  const topPersons = (payload.top_persons as Array<Record<string, unknown>>) ?? [];
  const llmGenerated = !!payload.llm_generated;

  const dismiss = async () => {
    try {
      await packCardsApi.acknowledge(cardId, "dismissed");
      trackPeopleEvent("packCard.weekly_summary.dismissed" as never, { card_id: cardId });
      onAcknowledged?.();
    } catch { /* swallow */ }
  };

  return (
    <Card>
      <div role="article" aria-label={t("packCard.weeklySummary.title")}>
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <Calendar size={20} className="text-[var(--color-primary)]" aria-hidden="true" />
            <div>
              <p className="font-semibold text-[var(--text-body-size)]">
                {t("packCard.weeklySummary.title")}
              </p>
              <p className="text-[var(--text-caption-size)] text-[var(--color-neutral-500)]">
                {t("packCard.weeklySummary.subtitle", { startDate: start, endDate: end })}
              </p>
            </div>
          </div>
          <button type="button" onClick={() => void dismiss()} aria-label="Dismiss" className="p-1 rounded hover:bg-[var(--color-neutral-100)]">
            <X size={14} aria-hidden="true" />
          </button>
        </div>

        <p className="mt-3 text-sm text-[var(--color-neutral-700)] leading-relaxed">
          {summary}
        </p>

        {llmGenerated && (
          <span className="inline-flex items-center gap-1 mt-2 px-2 py-0.5 rounded-full bg-[var(--color-info-surface)] text-[var(--color-info)] text-[var(--text-caption-size)]">
            <Sparkles size={10} aria-hidden="true" /> AI-generated
          </span>
        )}

        <div className="flex gap-4 mt-3 text-xs text-[var(--color-neutral-600)]">
          {typeof stats.events_count === "number" && <span>{stats.events_count} events</span>}
          {typeof stats.persons_seen === "number" && <span>{stats.persons_seen} people</span>}
          {typeof stats.reminders_completed === "number" && <span>{stats.reminders_completed} reminders done</span>}
        </div>

        {topPersons.length > 0 && (
          <div className="flex gap-2 mt-3 overflow-x-auto">
            {topPersons.map((p) => (
              <PersonAvatar
                key={String(p.person_id)}
                person={{ id: String(p.person_id), display_name: String(p.name ?? "") }}
                size="sm"
                showName
              />
            ))}
          </div>
        )}
      </div>
    </Card>
  );
}
