import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import useSWR from "swr";
import useSWRInfinite from "swr/infinite";
import { Search, X, ChevronDown, ChevronUp, Info } from "lucide-react";
import { swrFetcher, type SearchResponse, type SearchType, type Card } from "../api/client";
import { useFlag } from "../contexts/FlagContext";
import SearchResultCard from "../components/SearchResultCard";
import FilterChips from "../components/FilterChips";
import CardSkeleton from "../components/CardSkeleton";
import ErrorBanner from "../components/ErrorBanner";
import EmptyState from "../components/EmptyState";

const PER_PAGE = 20;
const DEBOUNCE_MS = 300;

type SearchMode = "hybrid" | "semantic" | "exact";

const TYPE_OPTIONS: { value: SearchType; label: string }[] = [
  { value: "all", label: "All" },
  { value: "calendar", label: "Calendar" },
  { value: "reminder", label: "Reminders" },
  { value: "contact", label: "Contacts" },
  { value: "file", label: "Documents" },
  { value: "photo", label: "Photos" },
];

const SEARCH_MODE_OPTIONS: { value: SearchMode; label: string }[] = [
  { value: "hybrid", label: "Hybrid" },
  { value: "semantic", label: "Semantic" },
  { value: "exact", label: "Exact" },
];

const SEARCH_MODE_DESCRIPTIONS: Record<SearchMode, string> = {
  hybrid: "Combines keyword and semantic search for the most relevant results.",
  semantic: "Finds results by meaning, even without exact keyword matches.",
  exact: "Only returns results containing the exact words you typed.",
};

export default function SearchPage() {
  const searchEnabled = useFlag("search_enabled");
  const filesEnabled = useFlag("files_enabled");
  const photosEnabled = useFlag("photos_enabled");
  const [searchParams, setSearchParams] = useSearchParams();

  // State from URL params
  const [inputValue, setInputValue] = useState(searchParams.get("q") ?? "");
  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const [typeFilter, setTypeFilter] = useState<SearchType>(
    (searchParams.get("type") as SearchType) ?? "all",
  );
  const [searchMode, setSearchMode] = useState<SearchMode>(
    (searchParams.get("mode") as SearchMode) ?? "hybrid",
  );
  const [dateFrom, setDateFrom] = useState(searchParams.get("from") ?? "");
  const [dateTo, setDateTo] = useState(searchParams.get("to") ?? "");
  const [correspondent, setCorrespondent] = useState(searchParams.get("correspondent") ?? "");
  const [tagsInput, setTagsInput] = useState(searchParams.get("tags") ?? "");
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(
    !!(searchParams.get("from") || searchParams.get("to") || searchParams.get("correspondent") || searchParams.get("tags")),
  );
  const [showModeTooltip, setShowModeTooltip] = useState(false);

  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  // Fetch Paperless correspondents for dropdown (falls back to free-text if unavailable)
  const { data: correspondentsData } = useSWR<{ results: Array<{ id: number; name: string }> }>(
    filesEnabled ? "/api/v1/paperless/correspondents" : null,
    swrFetcher,
    { shouldRetryOnError: false, revalidateOnFocus: false },
  );
  const correspondentOptions = correspondentsData?.results ?? null;

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
    if (searchMode !== "hybrid") params.mode = searchMode;
    if (dateFrom) params.from = dateFrom;
    if (dateTo) params.to = dateTo;
    if (correspondent) params.correspondent = correspondent;
    if (tagsInput) params.tags = tagsInput;
    setSearchParams(params, { replace: true });
  }, [query, typeFilter, searchMode, dateFrom, dateTo, correspondent, tagsInput, setSearchParams]);

  // Build SWR key
  const getKey = useCallback(
    (_pageIndex: number, previousPageData: SearchResponse | null) => {
      if (!query) return null;
      if (previousPageData && !previousPageData.pagination.has_more) return null;

      const cursor = previousPageData ? previousPageData.pagination.cursor : 0;
      const params = new URLSearchParams({
        q: query,
        workspace_id: "00000000-0000-0000-0000-000000000000", // placeholder
        type: typeFilter,
        mode: searchMode,
        per_page: String(PER_PAGE),
        cursor: String(cursor),
      });
      if (dateFrom) params.set("date_from", new Date(dateFrom).toISOString());
      if (dateTo) params.set("date_to", new Date(dateTo).toISOString());
      if (correspondent) params.set("correspondent", correspondent);
      if (tagsInput) {
        tagsInput.split(",").map((t) => t.trim()).filter(Boolean).forEach((tag) => {
          params.append("tags", tag);
        });
      }

      return `/api/v1/search?${params.toString()}`;
    },
    [query, typeFilter, searchMode, dateFrom, dateTo, correspondent, tagsInput],
  );

  const {
    data: pages,
    error,
    isLoading,
    isValidating,
    setSize,
    mutate,
  } = useSWRInfinite<SearchResponse>(getKey, swrFetcher, {
    revalidateFirstPage: false,
  });

  // Flatten pages into cards
  const allCards: Card[] = pages ? pages.flatMap((p) => p.data) : [];
  const hasMore = pages ? pages[pages.length - 1]?.pagination.has_more ?? false : false;
  const totalCount = pages?.[0]?.facets
    ? Object.values(pages[0].facets).reduce((sum, n) => sum + n, 0)
    : null;

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

  // Filter type options based on flags
  const visibleTypeOptions = TYPE_OPTIONS.filter((opt) => {
    if (opt.value === "file") return filesEnabled;
    if (opt.value === "photo") return photosEnabled;
    return true;
  });

  function handleClear() {
    setInputValue("");
    setQuery("");
  }

  function getEmptyStateTitle(): string {
    if (typeFilter === "file") return "Search your documents";
    if (typeFilter === "photo") return "Search your photos";
    return "Search across your data";
  }

  function getEmptyStateDescription(): string {
    if (typeFilter === "file") return "Find documents by name, content, tags, or correspondent.";
    if (typeFilter === "photo") return "Find photos by date, location, or camera.";
    return "Type a query above to search calendar, reminders, contacts, documents, and photos.";
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
            placeholder="Search across your data..."
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

      {/* Filter chips + search mode */}
      <div className="flex items-center gap-[var(--space-4)] mb-[var(--space-4)] flex-wrap">
        <FilterChips options={visibleTypeOptions} value={typeFilter} onChange={setTypeFilter} />

        {/* Search mode selector */}
        <div className="flex items-center gap-[var(--space-2)]">
          <select
            value={searchMode}
            onChange={(e) => setSearchMode(e.target.value as SearchMode)}
            className="h-8 pl-[var(--space-3)] pr-[var(--space-6)] rounded-[var(--radius-full)] border border-[var(--color-neutral-200)] bg-[var(--color-white)] text-[var(--text-small-size)] text-[var(--color-neutral-600)] outline-none focus:border-[var(--color-primary-light)] cursor-pointer appearance-none"
            aria-label="Search mode"
          >
            {SEARCH_MODE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <div className="relative">
            <button
              onMouseEnter={() => setShowModeTooltip(true)}
              onMouseLeave={() => setShowModeTooltip(false)}
              onFocus={() => setShowModeTooltip(true)}
              onBlur={() => setShowModeTooltip(false)}
              className="p-0.5 text-[var(--color-neutral-400)] hover:text-[var(--color-neutral-600)] cursor-pointer transition-colors"
              aria-label="Search mode info"
              type="button"
            >
              <Info size={14} aria-hidden="true" />
            </button>
            {showModeTooltip && (
              <div className="absolute left-0 top-6 z-10 w-48 p-[var(--space-2)] rounded-[var(--radius-md)] bg-[var(--color-neutral-900)] text-white text-[var(--text-caption-size)] leading-[var(--text-caption-height)] shadow-lg">
                {SEARCH_MODE_DESCRIPTIONS[searchMode]}
              </div>
            )}
          </div>
        </div>

        {/* Advanced filters toggle */}
        <button
          onClick={() => setShowAdvancedFilters((v) => !v)}
          className="inline-flex items-center gap-1 text-[var(--text-small-size)] text-[var(--color-neutral-500)] hover:text-[var(--color-neutral-700)] cursor-pointer transition-colors"
          aria-expanded={showAdvancedFilters}
        >
          Filters
          {showAdvancedFilters ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
      </div>

      {/* Advanced filters (collapsible) */}
      {showAdvancedFilters && (
        <div className="mb-[var(--space-4)] max-w-[600px] space-y-[var(--space-3)] p-[var(--space-4)] rounded-[var(--radius-lg)] border border-[var(--color-neutral-200)] bg-[var(--color-neutral-50)]">
          {/* Date range */}
          <div>
            <label className="block text-[var(--text-caption-size)] text-[var(--color-neutral-500)] mb-[var(--space-1)] font-medium">
              Date range
            </label>
            <div className="flex items-center gap-[var(--space-3)]">
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="h-9 px-[var(--space-3)] rounded-[var(--radius-md)] border border-[var(--color-neutral-200)] bg-white text-[var(--text-small-size)] text-[var(--color-neutral-700)] outline-none focus:border-[var(--color-primary-light)]"
                aria-label="From date"
              />
              <span className="text-[var(--text-small-size)] text-[var(--color-neutral-400)]">to</span>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="h-9 px-[var(--space-3)] rounded-[var(--radius-md)] border border-[var(--color-neutral-200)] bg-white text-[var(--text-small-size)] text-[var(--color-neutral-700)] outline-none focus:border-[var(--color-primary-light)]"
                aria-label="To date"
              />
            </div>
          </div>

          {/* Correspondent (documents) */}
          {(typeFilter === "file" || typeFilter === "all") && (
            <div>
              <label className="block text-[var(--text-caption-size)] text-[var(--color-neutral-500)] mb-[var(--space-1)] font-medium">
                Correspondent
              </label>
              {correspondentOptions ? (
                <select
                  value={correspondent}
                  onChange={(e) => setCorrespondent(e.target.value)}
                  className="w-full h-9 px-[var(--space-3)] rounded-[var(--radius-md)] border border-[var(--color-neutral-200)] bg-white text-[var(--text-small-size)] text-[var(--color-neutral-700)] outline-none focus:border-[var(--color-primary-light)] cursor-pointer"
                  aria-label="Correspondent filter"
                >
                  <option value="">Any correspondent</option>
                  {correspondentOptions.map((c) => (
                    <option key={c.id} value={c.name}>{c.name}</option>
                  ))}
                </select>
              ) : (
                <input
                  type="text"
                  value={correspondent}
                  onChange={(e) => setCorrespondent(e.target.value)}
                  placeholder="e.g. Bank of America"
                  className="w-full h-9 px-[var(--space-3)] rounded-[var(--radius-md)] border border-[var(--color-neutral-200)] bg-white text-[var(--text-small-size)] text-[var(--color-neutral-700)] placeholder:text-[var(--color-neutral-400)] outline-none focus:border-[var(--color-primary-light)]"
                  aria-label="Correspondent filter"
                />
              )}
            </div>
          )}

          {/* Tags (documents) */}
          {(typeFilter === "file" || typeFilter === "all") && (
            <div>
              <label className="block text-[var(--text-caption-size)] text-[var(--color-neutral-500)] mb-[var(--space-1)] font-medium">
                Tags
              </label>
              <input
                type="text"
                value={tagsInput}
                onChange={(e) => setTagsInput(e.target.value)}
                placeholder="e.g. invoice, tax (comma-separated)"
                className="w-full h-9 px-[var(--space-3)] rounded-[var(--radius-md)] border border-[var(--color-neutral-200)] bg-white text-[var(--text-small-size)] text-[var(--color-neutral-700)] placeholder:text-[var(--color-neutral-400)] outline-none focus:border-[var(--color-primary-light)]"
                aria-label="Tags filter"
              />
            </div>
          )}
        </div>
      )}

      {/* Result count */}
      {query && !isLoading && !error && allCards.length > 0 && (
        <p className="text-[var(--text-caption-size)] leading-[var(--text-caption-height)] text-[var(--color-neutral-500)] mb-[var(--space-4)]">
          {totalCount && totalCount > allCards.length
            ? `Showing 1–${allCards.length} of ${totalCount} results`
            : `Showing ${allCards.length} result${allCards.length !== 1 ? "s" : ""}`}
        </p>
      )}

      {/* States */}
      {!query && (
        <EmptyState
          title={getEmptyStateTitle()}
          description={getEmptyStateDescription()}
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
          title={
            typeFilter === "file"
              ? "No documents match your search."
              : `No results for "${query}"`
          }
          description={
            typeFilter === "file"
              ? "Try different keywords or clear filters."
              : "Try different keywords or broaden your filters."
          }
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
