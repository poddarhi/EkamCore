import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import useSWRInfinite from "swr/infinite";
import { Search, X, ChevronDown, ChevronUp } from "lucide-react";
import { swrFetcher, type SearchResponse, type SearchType, type Card } from "../api/client";
import { useFlag } from "../contexts/FlagContext";
import SearchResultCard from "../components/SearchResultCard";
import FilterChips from "../components/FilterChips";
import CardSkeleton from "../components/CardSkeleton";
import ErrorBanner from "../components/ErrorBanner";
import EmptyState from "../components/EmptyState";

const PER_PAGE = 20;
const DEBOUNCE_MS = 300;

const TYPE_OPTIONS: { value: SearchType; label: string }[] = [
  { value: "all", label: "All" },
  { value: "calendar", label: "Calendar" },
  { value: "reminder", label: "Reminders" },
  { value: "contact", label: "Contacts" },
];

// Hardcoded workspace_id — will come from AuthContext in a future sprint
function useWorkspaceId(): string | null {
  // Read from JWT claims via AuthContext. For now, return null to skip fetch
  // until we can extract it. The search endpoint requires a workspace_id param.
  return null;
}

export default function SearchPage() {
  const searchEnabled = useFlag("search_enabled");
  const [searchParams, setSearchParams] = useSearchParams();

  // State from URL params
  const [inputValue, setInputValue] = useState(searchParams.get("q") ?? "");
  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const [typeFilter, setTypeFilter] = useState<SearchType>(
    (searchParams.get("type") as SearchType) ?? "all",
  );
  const [dateFrom, setDateFrom] = useState(searchParams.get("from") ?? "");
  const [dateTo, setDateTo] = useState(searchParams.get("to") ?? "");
  const [showDateFilter, setShowDateFilter] = useState(
    !!(searchParams.get("from") || searchParams.get("to")),
  );

  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  // Debounce input → query
  useEffect(() => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => {
      setQuery(inputValue);
    }, DEBOUNCE_MS);
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
    };
  }, [inputValue]);

  // Sync state → URL params
  useEffect(() => {
    const params: Record<string, string> = {};
    if (query) params.q = query;
    if (typeFilter !== "all") params.type = typeFilter;
    if (dateFrom) params.from = dateFrom;
    if (dateTo) params.to = dateTo;
    setSearchParams(params, { replace: true });
  }, [query, typeFilter, dateFrom, dateTo, setSearchParams]);

  // Build SWR key
  const getKey = useCallback(
    (pageIndex: number, previousPageData: SearchResponse | null) => {
      if (!query) return null;
      if (previousPageData && !previousPageData.pagination.has_more) return null;

      const cursor = previousPageData ? previousPageData.pagination.cursor : 0;
      const params = new URLSearchParams({
        q: query,
        workspace_id: "00000000-0000-0000-0000-000000000000", // placeholder
        type: typeFilter,
        per_page: String(PER_PAGE),
        cursor: String(cursor),
      });
      if (dateFrom) params.set("date_from", new Date(dateFrom).toISOString());
      if (dateTo) params.set("date_to", new Date(dateTo).toISOString());

      return `/api/v1/search?${params.toString()}`;
    },
    [query, typeFilter, dateFrom, dateTo],
  );

  const {
    data: pages,
    error,
    isLoading,
    isValidating,
    size,
    setSize,
    mutate,
  } = useSWRInfinite<SearchResponse>(getKey, swrFetcher, {
    revalidateFirstPage: false,
  });

  // Flatten pages into cards
  const allCards: Card[] = pages ? pages.flatMap((p) => p.data) : [];
  const hasMore = pages ? pages[pages.length - 1]?.pagination.has_more ?? false : false;
  const facets = pages?.[0]?.facets ?? {};

  // Infinite scroll via IntersectionObserver
  useEffect(() => {
    if (!sentinelRef.current || !hasMore) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !isValidating && hasMore) {
          setSize((s) => s + 1);
        }
      },
      { rootMargin: "200px" },
    );

    observer.observe(sentinelRef.current);
    return () => observer.disconnect();
  }, [hasMore, isValidating, setSize]);

  function handleClear() {
    setInputValue("");
    setQuery("");
  }

  if (!searchEnabled) {
    return <EmptyState title="Search" description="Coming in a future update" />;
  }

  return (
    <div>
      {/* Header */}
      <h2 className="text-[var(--text-display-size)] leading-[var(--text-display-height)] font-[var(--text-display-weight)] text-[var(--color-neutral-900)] mb-[var(--space-6)]">
        Search
      </h2>

      {/* Search input */}
      <div className="max-w-[600px] mb-[var(--space-4)]">
        <div className="relative">
          <Search
            size={20}
            className="absolute left-[var(--space-4)] top-1/2 -translate-y-1/2 text-[var(--color-neutral-400)] pointer-events-none"
            aria-hidden="true"
          />
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="Search across your calendar, reminders, and contacts..."
            className="w-full h-12 pl-12 pr-10 rounded-[var(--radius-lg)] border-2 border-[var(--color-neutral-200)] bg-[var(--color-white)] text-[var(--text-body-size)] leading-[var(--text-body-height)] text-[var(--color-neutral-900)] placeholder:text-[var(--color-neutral-400)] outline-none transition-colors duration-[var(--duration-normal)] focus:border-[var(--color-primary-light)]"
            aria-label="Search"
          />
          {inputValue && (
            <button
              onClick={handleClear}
              className="absolute right-[var(--space-3)] top-1/2 -translate-y-1/2 p-1 rounded-[var(--radius-sm)] text-[var(--color-neutral-400)] hover:text-[var(--color-neutral-700)] hover:bg-[var(--color-neutral-100)] transition-colors cursor-pointer"
              aria-label="Clear search"
            >
              <X size={18} aria-hidden="true" />
            </button>
          )}
        </div>
      </div>

      {/* Filter chips */}
      <div className="flex items-center gap-[var(--space-4)] mb-[var(--space-4)]">
        <FilterChips options={TYPE_OPTIONS} value={typeFilter} onChange={setTypeFilter} />
        <button
          onClick={() => setShowDateFilter((v) => !v)}
          className="inline-flex items-center gap-1 text-[var(--text-small-size)] text-[var(--color-neutral-500)] hover:text-[var(--color-neutral-700)] cursor-pointer transition-colors"
          aria-expanded={showDateFilter}
        >
          Date range
          {showDateFilter ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
      </div>

      {/* Date range (collapsible) */}
      {showDateFilter && (
        <div className="flex items-center gap-[var(--space-3)] mb-[var(--space-4)] max-w-[600px]">
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="h-9 px-[var(--space-3)] rounded-[var(--radius-md)] border border-[var(--color-neutral-200)] text-[var(--text-small-size)] text-[var(--color-neutral-700)] outline-none focus:border-[var(--color-primary-light)]"
            aria-label="From date"
          />
          <span className="text-[var(--text-small-size)] text-[var(--color-neutral-400)]">to</span>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="h-9 px-[var(--space-3)] rounded-[var(--radius-md)] border border-[var(--color-neutral-200)] text-[var(--text-small-size)] text-[var(--color-neutral-700)] outline-none focus:border-[var(--color-primary-light)]"
            aria-label="To date"
          />
        </div>
      )}

      {/* Facets */}
      {query && Object.keys(facets).length > 0 && (
        <p className="text-[var(--text-caption-size)] leading-[var(--text-caption-height)] text-[var(--color-neutral-500)] mb-[var(--space-4)]">
          {Object.entries(facets)
            .map(([type, count]) => `${count} ${type}${count !== 1 ? "s" : ""}`)
            .join(" · ")}
        </p>
      )}

      {/* States */}
      {!query && (
        <EmptyState
          title="Search across your calendar, reminders, and contacts"
          description="Type a query above to get started."
        />
      )}

      {query && isLoading && <CardSkeleton count={5} />}

      {query && error && !isLoading && (
        <ErrorBanner
          message={(error as { message?: string }).message ?? "Search failed."}
          onRetry={() => mutate()}
        />
      )}

      {query && !isLoading && !error && allCards.length === 0 && (
        <EmptyState
          title={`No results for "${query}"`}
          description="Try different keywords or broaden your filters."
        />
      )}

      {/* Results */}
      {allCards.length > 0 && (
        <div className="space-y-[var(--space-3)]">
          {allCards.map((card) => (
            <SearchResultCard key={card.id} card={card} query={query} />
          ))}

          {/* Infinite scroll sentinel */}
          {hasMore && (
            <div ref={sentinelRef} className="flex justify-center py-[var(--space-4)]">
              {isValidating && (
                <div className="animate-spin h-6 w-6 border-2 border-[var(--color-primary-light)] border-t-transparent rounded-full" />
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
