import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import useSWR from "swr";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { swrFetcher, type ResponseEnvelope, type ApiError, type Card } from "../api/client";
import { useFlag } from "../contexts/FlagContext";
import CardRenderer from "../components/CardRenderer";
import CardSkeleton from "../components/CardSkeleton";
import ErrorBanner from "../components/ErrorBanner";
import EmptyState from "../components/EmptyState";

type Period = "daily" | "weekly";

// ── Date helpers ──

function toISODate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function parseDate(s: string): Date {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function yesterday(): string {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return toISODate(d);
}

function shiftDate(dateStr: string, days: number): string {
  const d = parseDate(dateStr);
  d.setDate(d.getDate() + days);
  return toISODate(d);
}

function formatDailyDate(dateStr: string): string {
  const d = parseDate(dateStr);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(d);
  target.setHours(0, 0, 0, 0);

  const diff = Math.round((today.getTime() - target.getTime()) / 86400000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  return d.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" });
}

function formatWeeklyDate(dateStr: string): string {
  const end = parseDate(dateStr);
  const start = new Date(end);
  start.setDate(start.getDate() - 6);
  const fmt = (d: Date) => d.toLocaleDateString([], { month: "short", day: "numeric" });
  return `${fmt(start)} – ${fmt(end)}`;
}

// ── Card grouping ──

interface CardGroups {
  events: Card[];
  completed: Card[];
  overdue: Card[];
}

function groupCards(cards: Card[]): CardGroups {
  const events: Card[] = [];
  const completed: Card[] = [];
  const overdue: Card[] = [];

  for (const card of cards) {
    if (card.type === "event") {
      events.push(card);
    } else if (card.type === "reminder") {
      const payload = card.payload as { is_overdue?: boolean; completed_at?: string };
      if (payload.is_overdue) {
        overdue.push(card);
      } else {
        completed.push(card);
      }
    }
  }

  return { events, completed, overdue };
}

// ── Section component ──

function CardSection({ title, cards }: { title: string; cards: Card[] }) {
  if (cards.length === 0) return null;
  return (
    <div className="mb-[var(--space-6)]">
      <h3 className="text-[var(--text-h3-size)] leading-[var(--text-h3-height)] font-[var(--text-h3-weight)] text-[var(--color-neutral-700)] mb-[var(--space-3)]">
        {title}
        <span className="ml-[var(--space-2)] text-[var(--text-caption-size)] font-normal text-[var(--color-neutral-400)]">
          {cards.length}
        </span>
      </h3>
      <div className="space-y-[var(--space-3)]">
        {cards.map((card) => (
          <CardRenderer key={card.id} card={card} />
        ))}
      </div>
    </div>
  );
}

// ── Main page ──

export default function RecapPage() {
  const recapEnabled = useFlag("recap_enabled");
  const [searchParams, setSearchParams] = useSearchParams();

  const period = (searchParams.get("period") as Period) || "daily";
  const dateParam = searchParams.get("date") || yesterday();

  const setParams = useCallback(
    (newPeriod: Period, newDate: string) => {
      setSearchParams({ period: newPeriod, date: newDate }, { replace: true });
    },
    [setSearchParams],
  );

  // Build SWR key
  const swrKey = recapEnabled
    ? `/api/v1/recap?workspace_id=00000000-0000-0000-0000-000000000000&period=${period}&date=${dateParam}`
    : null;

  const { data, error, isLoading, mutate } = useSWR<ResponseEnvelope>(
    swrKey,
    swrFetcher,
    { refreshInterval: 3600_000 }, // 1 hour
  );

  const groups = useMemo(
    () => groupCards(data?.cards ?? []),
    [data?.cards],
  );

  const totalCards = data?.cards.length ?? 0;
  const completedCount = groups.completed.length;
  const overdueCount = groups.overdue.length;

  // Navigation
  const step = period === "weekly" ? 7 : 1;

  function handlePrev() {
    setParams(period, shiftDate(dateParam, -step));
  }

  function handleNext() {
    const next = shiftDate(dateParam, step);
    // Don't navigate into the future
    if (next <= toISODate(new Date())) {
      setParams(period, next);
    }
  }

  function handlePeriodChange(newPeriod: Period) {
    setParams(newPeriod, dateParam);
  }

  const canGoNext = shiftDate(dateParam, step) <= toISODate(new Date());

  if (!recapEnabled) {
    return <EmptyState title="Recap" description="Coming in a future update" />;
  }

  return (
    <div>
      {/* Header */}
      <h2 className="text-[var(--text-display-size)] leading-[var(--text-display-height)] font-[var(--text-display-weight)] text-[var(--color-neutral-900)] mb-[var(--space-4)]">
        Recap
      </h2>

      {/* Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-[var(--space-4)] mb-[var(--space-6)]">
        {/* Period toggle */}
        <div className="inline-flex rounded-[var(--radius-md)] border border-[var(--color-neutral-200)] overflow-hidden" role="radiogroup" aria-label="Period">
          {(["daily", "weekly"] as const).map((p) => (
            <button
              key={p}
              role="radio"
              aria-checked={period === p}
              onClick={() => handlePeriodChange(p)}
              className={[
                "px-[var(--space-4)] py-[var(--space-2)] text-[var(--text-small-size)] font-medium",
                "transition-colors duration-[var(--duration-normal)] cursor-pointer outline-none",
                "focus-visible:ring-2 focus-visible:ring-[var(--color-primary-light)] focus-visible:ring-inset",
                period === p
                  ? "bg-[var(--color-primary)] text-[var(--color-white)]"
                  : "bg-[var(--color-white)] text-[var(--color-neutral-600)] hover:bg-[var(--color-neutral-100)]",
              ].join(" ")}
            >
              {p === "daily" ? "Daily" : "Weekly"}
            </button>
          ))}
        </div>

        {/* Date navigation */}
        <div className="inline-flex items-center gap-[var(--space-2)]">
          <button
            onClick={handlePrev}
            className="p-[var(--space-2)] rounded-[var(--radius-md)] text-[var(--color-neutral-600)] hover:bg-[var(--color-neutral-100)] transition-colors cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary-light)]"
            aria-label="Previous period"
          >
            <ChevronLeft size={18} aria-hidden="true" />
          </button>
          <span className="min-w-[200px] text-center text-[var(--text-body-size)] leading-[var(--text-body-height)] font-medium text-[var(--color-neutral-900)]">
            {period === "daily" ? formatDailyDate(dateParam) : formatWeeklyDate(dateParam)}
          </span>
          <button
            onClick={handleNext}
            disabled={!canGoNext}
            className={[
              "p-[var(--space-2)] rounded-[var(--radius-md)] transition-colors outline-none",
              "focus-visible:ring-2 focus-visible:ring-[var(--color-primary-light)]",
              canGoNext
                ? "text-[var(--color-neutral-600)] hover:bg-[var(--color-neutral-100)] cursor-pointer"
                : "text-[var(--color-neutral-300)] cursor-not-allowed",
            ].join(" ")}
            aria-label="Next period"
          >
            <ChevronRight size={18} aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* Loading */}
      {isLoading && <CardSkeleton count={5} />}

      {/* Error */}
      {error && !isLoading && (
        <ErrorBanner
          message={(error as ApiError).message ?? "Failed to load recap."}
          correlationId={(error as ApiError).correlationId}
          onRetry={() => mutate()}
        />
      )}

      {/* Empty */}
      {!isLoading && !error && totalCards === 0 && (
        <EmptyState
          title="Nothing to recap for this period"
          description="Try a different date or switch between daily and weekly."
        />
      )}

      {/* Content */}
      {!isLoading && !error && totalCards > 0 && (
        <>
          {/* Summary */}
          <div className="flex items-center gap-[var(--space-6)] mb-[var(--space-6)] text-[var(--text-small-size)] leading-[var(--text-small-height)] text-[var(--color-neutral-500)]">
            <span>{totalCards} total item{totalCards !== 1 ? "s" : ""}</span>
            {completedCount > 0 && (
              <span className="text-[var(--color-success)]">
                {completedCount} completed
              </span>
            )}
            {overdueCount > 0 && (
              <span className="text-[var(--color-error)]">
                {overdueCount} overdue
              </span>
            )}
          </div>

          {/* Sections */}
          <CardSection title="Events" cards={groups.events} />
          <CardSection title="Reminders Completed" cards={groups.completed} />
          <CardSection title="New Overdue" cards={groups.overdue} />
        </>
      )}
    </div>
  );
}
