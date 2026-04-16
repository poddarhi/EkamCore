import { useRef } from "react";
import useSWR from "swr";
import { swrFetcher, type ResponseEnvelope, type ApiError } from "../api/client";
import { useFlag } from "../contexts/FlagContext";
import CardRenderer from "../components/CardRenderer";
import CardSkeleton from "../components/CardSkeleton";
import ErrorBanner from "../components/ErrorBanner";
import EmptyState from "../components/EmptyState";
import { t } from "../i18n";

function timeAgo(ts: number): string {
  const seconds = Math.floor((Date.now() - ts) / 1000);
  if (seconds < 60) return t("common.time.justNow");
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return t("common.time.minutesAgo", { count: minutes });
  const hours = Math.floor(minutes / 60);
  return t("common.time.hoursAgo", { count: hours });
}

export default function TodayPage() {
  const todayEnabled = useFlag("today_enabled");
  const fetchedAtRef = useRef(0);
  const { data, error, isLoading, mutate } = useSWR<ResponseEnvelope>(
    todayEnabled ? "/api/v1/today" : null,
    (url: string) => {
      const p = swrFetcher<ResponseEnvelope>(url);
      p.then(() => { fetchedAtRef.current = Date.now(); });
      return p;
    },
    { refreshInterval: 300_000 },
  );

  if (!todayEnabled) {
    return <EmptyState title={t("today.title")} description={t("today.comingSoon")} />;
  }

  if (isLoading) return <CardSkeleton count={5} />;

  if (error) {
    const apiErr = error as ApiError;
    return (
      <ErrorBanner
        message={apiErr.message ?? t("today.error")}
        correlationId={apiErr.correlationId}
        onRetry={() => mutate()}
      />
    );
  }

  if (!data?.cards.length) {
    return <EmptyState title={t("today.empty.title")} description={t("today.empty.description")} />;
  }

  const today = new Date();
  const dateStr = today.toLocaleDateString([], {
    weekday: "long",
    month: "long",
    day: "numeric",
  });

  return (
    <div>
      {/* Header */}
      <div className="mb-[var(--space-6)]">
        <div className="flex items-baseline gap-[var(--space-3)]">
          <h2 className="text-[var(--text-display-size)] leading-[var(--text-display-height)] font-[var(--text-display-weight)] text-[var(--color-neutral-900)]">
            {t("today.title")}
          </h2>
          {fetchedAtRef.current > 0 && (
            <span className="text-[var(--text-caption-size)] leading-[var(--text-caption-height)] text-[var(--color-neutral-400)]">
              {t("today.updated", { time: timeAgo(fetchedAtRef.current) })}
            </span>
          )}
        </div>
        <p className="mt-[var(--space-1)] text-[var(--text-body-size)] leading-[var(--text-body-height)] text-[var(--color-neutral-500)]">
          {dateStr}
        </p>
      </div>

      {/* Cards */}
      <div className="space-y-[var(--space-3)]">
        {data.cards.map((card) => (
          <CardRenderer
            key={card.id}
            card={card}
            surface="today"
            onPackCardAcknowledged={() => void mutate()}
          />
        ))}
      </div>
    </div>
  );
}
