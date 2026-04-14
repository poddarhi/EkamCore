/**
 * /people — trusted persons list (S13-002).
 *
 * Grid + list views, debounced search, confidence filter, cursor
 * pagination, full loading/empty/error states. Gated on
 * `face_clustering_enabled` + active face consent.
 */

import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { LayoutGrid, List as ListIcon, Search as SearchIcon } from "lucide-react";

import PersonAvatar from "../../components/people/PersonAvatar";
import EmptyState from "../../design-system/components/EmptyState";
import ErrorBanner from "../../design-system/components/ErrorBanner";
import FeatureComingSoon from "../../design-system/components/FeatureComingSoon";
import FilterChip from "../../design-system/components/FilterChip";
import Skeleton from "../../design-system/components/Skeleton";
import { useFlag } from "../../contexts/FlagContext";
import {
  useFaceConsent,
  usePeopleList,
  useReviewQueue,
} from "../../hooks/usePeople";
import { t } from "../../i18n";
import type { TrustedPerson } from "../../types/people";
import { trackPeopleEvent } from "../../utils/metrics";

type ViewMode = "grid" | "list";
type StatusFilter = "all" | "confirmed" | "pending";

function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
}

function formatSeenRange(person: TrustedPerson): string | null {
  if (!person.first_seen_at && !person.last_seen_at) return null;
  const fmt = (d: string | null | undefined) =>
    d ? new Date(d).toLocaleDateString() : "";
  const from = fmt(person.first_seen_at);
  const to = fmt(person.last_seen_at);
  if (from && to && from !== to) return `${from} – ${to}`;
  return from || to || null;
}

export default function PeopleListPage() {
  const enabled = useFlag("face_clustering_enabled");
  const { accepted, loading: consentLoading } = useFaceConsent();
  const navigate = useNavigate();

  const [view, setView] = useState<ViewMode>("grid");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [searchInput, setSearchInput] = useState("");
  const search = useDebounced(searchInput, 300);

  const { data, error, isLoading, isValidating } = usePeopleList(
    { limit: 24, search },
    { shouldRetryOnError: false },
  );

  // Pending-review count drives the "You have N suggestions" hint on
  // the empty state. Limit=100 is plenty for the badge signal.
  const { data: reviewData } = useReviewQueue(
    { limit: 100 },
    { shouldRetryOnError: false },
  );
  const pendingCount = reviewData?.items.length ?? 0;

  useEffect(() => {
    if (enabled && accepted) {
      trackPeopleEvent("people.list.viewed");
    }
  }, [enabled, accepted]);

  // Client-side status filter (the backend only supports search for
  // this story; confirmed/pending split lives on cluster_state, not
  // trusted_persons). We filter the loaded page in memory.
  const items = useMemo(() => {
    const all = data?.items ?? [];
    if (status === "all") return all;
    if (status === "confirmed") {
      return all.filter((p) => p.confirmed_at !== null);
    }
    return all.filter((p) => p.confirmed_at === null);
  }, [data, status]);

  if (!enabled) return <FeatureComingSoon featureName="People" />;
  if (consentLoading) {
    return (
      <div className="max-w-[960px] mx-auto p-6">
        <Skeleton variant="text" count={3} />
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
              className="inline-flex items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-primary)] text-[var(--color-white)] px-4 py-2 text-[var(--text-body-size)] font-medium hover:bg-[var(--color-primary-dark)]"
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
      {/* Header */}
      <div className="flex items-start justify-between gap-4 mb-6">
        <h1 className="text-[var(--text-h1-size)] leading-[var(--text-h1-height)] font-[var(--text-h1-weight)]">
          {t("people.list.title")}
        </h1>
        <ViewToggle view={view} onChange={setView} />
      </div>

      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row gap-3 mb-4">
        <SearchInput value={searchInput} onChange={setSearchInput} />
        <div className="flex gap-2" role="listbox" aria-label="Filter">
          <FilterChip
            label={t("people.list.filter.all")}
            active={status === "all"}
            onClick={() => setStatus("all")}
          />
          <FilterChip
            label={t("people.list.filter.confirmed")}
            active={status === "confirmed"}
            onClick={() => setStatus("confirmed")}
          />
          <FilterChip
            label={t("people.list.filter.pending")}
            active={status === "pending"}
            onClick={() => setStatus("pending")}
          />
        </div>
      </div>

      {/* Content */}
      {error && (
        <ErrorBanner
          message={t("error.generic")}
        />
      )}

      {isLoading && <LoadingState view={view} />}

      {!isLoading && !error && items.length === 0 && (
        <EmptyState
          title={t("people.list.empty.title")}
          description={
            pendingCount > 0
              ? t("reviewQueue.empty.description")
              : t("people.list.empty.description")
          }
          action={
            <Link
              to="/people/review"
              className="inline-flex items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-primary)] text-[var(--color-white)] px-4 py-2 text-[var(--text-body-size)] font-medium hover:bg-[var(--color-primary-dark)]"
            >
              {t("people.list.empty.cta")}
              {pendingCount > 0 ? ` (${pendingCount})` : ""}
            </Link>
          }
        />
      )}

      {!isLoading && !error && items.length > 0 && view === "grid" && (
        <PersonGrid
          items={items}
          onOpen={(id) => navigate(`/people/${id}`)}
        />
      )}

      {!isLoading && !error && items.length > 0 && view === "list" && (
        <PersonList
          items={items}
          onOpen={(id) => navigate(`/people/${id}`)}
        />
      )}

      {isValidating && !isLoading && (
        <p
          className="mt-4 text-center text-[var(--text-small-size)] text-[var(--color-neutral-500)]"
          aria-live="polite"
        >
          {t("common.loading")}
        </p>
      )}
    </div>
  );
}

// ── Subcomponents ─────────────────────────────────────────────────────────

function ViewToggle({
  view,
  onChange,
}: {
  view: ViewMode;
  onChange: (v: ViewMode) => void;
}) {
  return (
    <div
      className="inline-flex rounded-[var(--radius-md)] border border-[var(--color-neutral-200)] overflow-hidden"
      role="group"
      aria-label="View mode"
    >
      <button
        type="button"
        onClick={() => onChange("grid")}
        aria-pressed={view === "grid"}
        aria-label={t("people.list.viewToggle.grid")}
        className={[
          "p-2 flex items-center justify-center",
          view === "grid"
            ? "bg-[var(--color-primary-surface)] text-[var(--color-primary)]"
            : "text-[var(--color-neutral-600)] hover:bg-[var(--color-neutral-50)]",
        ].join(" ")}
      >
        <LayoutGrid size={18} aria-hidden="true" />
      </button>
      <button
        type="button"
        onClick={() => onChange("list")}
        aria-pressed={view === "list"}
        aria-label={t("people.list.viewToggle.list")}
        className={[
          "p-2 flex items-center justify-center border-l border-[var(--color-neutral-200)]",
          view === "list"
            ? "bg-[var(--color-primary-surface)] text-[var(--color-primary)]"
            : "text-[var(--color-neutral-600)] hover:bg-[var(--color-neutral-50)]",
        ].join(" ")}
      >
        <ListIcon size={18} aria-hidden="true" />
      </button>
    </div>
  );
}

function SearchInput({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex-1 relative">
      <SearchIcon
        size={16}
        aria-hidden="true"
        className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-neutral-400)]"
      />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={t("people.list.search.placeholder")}
        aria-label={t("people.list.search.placeholder")}
        className="w-full rounded-[var(--radius-md)] border border-[var(--color-neutral-200)] pl-9 pr-3 py-2 text-[var(--text-body-size)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary-light)]"
      />
    </div>
  );
}

function LoadingState({ view }: { view: ViewMode }) {
  if (view === "grid") {
    return (
      <div
        className="grid gap-4"
        style={{ gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))" }}
        data-testid="people-loading-grid"
      >
        <Skeleton variant="card" count={12} />
      </div>
    );
  }
  return (
    <div data-testid="people-loading-list">
      <Skeleton variant="table-row" count={10} />
    </div>
  );
}

function PersonGrid({
  items,
  onOpen,
}: {
  items: TrustedPerson[];
  onOpen: (id: string) => void;
}) {
  return (
    <ul
      className="grid gap-4"
      style={{ gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))" }}
      data-testid="people-grid"
    >
      {items.map((p) => {
        const seen = formatSeenRange(p);
        const faces = p.face_count ?? 0;
        return (
          <li key={p.id}>
            <button
              type="button"
              onClick={() => onOpen(p.id)}
              className="w-full text-left rounded-[var(--radius-lg)] border border-[var(--color-neutral-200)] bg-[var(--color-white)] p-4 flex flex-col items-center gap-3 hover:shadow-sm hover:border-[var(--color-neutral-300)] transition cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary-light)]"
              aria-label={p.display_name}
            >
              <PersonAvatar person={p} size="lg" />
              <span className="truncate w-full text-center text-[var(--text-body-size)] font-medium text-[var(--color-neutral-900)]">
                {p.display_name}
              </span>
              <span className="text-[var(--text-caption-size)] text-[var(--color-neutral-500)]">
                {t(
                  faces === 1
                    ? "people.list.faceCount"
                    : "people.list.faceCountPlural",
                  { count: faces },
                )}
              </span>
              {seen && (
                <span className="text-[var(--text-caption-size)] text-[var(--color-neutral-400)]">
                  {seen}
                </span>
              )}
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function PersonList({
  items,
  onOpen,
}: {
  items: TrustedPerson[];
  onOpen: (id: string) => void;
}) {
  return (
    <ul
      className="divide-y divide-[var(--color-neutral-200)] rounded-[var(--radius-lg)] border border-[var(--color-neutral-200)] bg-[var(--color-white)]"
      data-testid="people-list"
    >
      {items.map((p) => {
        const seen = formatSeenRange(p);
        const faces = p.face_count ?? 0;
        return (
          <li key={p.id}>
            <button
              type="button"
              onClick={() => onOpen(p.id)}
              className="w-full px-4 py-3 flex items-center gap-4 text-left hover:bg-[var(--color-neutral-50)] transition cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary-light)]"
            >
              <PersonAvatar person={p} size="sm" />
              <span className="flex-1 truncate text-[var(--text-body-size)] font-medium text-[var(--color-neutral-900)]">
                {p.display_name}
              </span>
              <span className="text-[var(--text-caption-size)] text-[var(--color-neutral-500)]">
                {t(
                  faces === 1
                    ? "people.list.faceCount"
                    : "people.list.faceCountPlural",
                  { count: faces },
                )}
              </span>
              {seen && (
                <span className="text-[var(--text-caption-size)] text-[var(--color-neutral-400)] min-w-[8rem] text-right">
                  {seen}
                </span>
              )}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
