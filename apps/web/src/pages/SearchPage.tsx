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
import { t } from "../i18n";

const PER_PAGE = 20;
const DEBOUNCE_MS = 300;

type SearchMode = "hybrid" | "semantic" | "exact";

const TYPE_OPTIONS: { value: SearchType; labelKey: string }[] = [
  { value: "all", labelKey: "search.type.all" },
  { value: "calendar", labelKey: "search.type.calendar" },
  { value: "reminder", labelKey: "search.type.reminder" },
  { value: "contact", labelKey: "search.type.contact" },
  { value: "file", labelKey: "search.type.file" },
  { value: "photo", labelKey: "search.type.photo" },
];

const SEARCH_MODE_OPTIONS: { value: SearchMode; labelKey: string }[] = [
  { value: "hybrid", labelKey: "search.mode.hybrid" },
  { value: "semantic", labelKey: "search.mode.semantic" },
  { value: "exact", labelKey: "search.mode.exact" },
];

const SEARCH_MODE_DESCRIPTION_KEYS: Record<SearchMode, string> = {
  hybrid: "search.mode.description.hybrid",
  semantic: "search.mode.description.semantic",
  exact: "search.mode.description.exact",
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
  }).map((opt) => ({ value: opt.value, label: t(opt.labelKey) }));

  function handleClear() {
    setInputValue("");
    setQuery("");
  }

  function getEmptyStateTitle(): string {
    if (typeFilter === "file") return t("search.empty.documents.title");
    if (typeFilter === "photo") return t("search.empty.photos.title");
    return t("search.empty.default.title");
  }

  function getEmptyStateDescription(): string {
    if (typeFilter === "file") return t("search.empty.documents.description");
    if (typeFilter === "photo") return t("search.empty.photos.description");
    return t("search.empty.default.description");
  }

  if (!searchEnabled) {
    return <EmptyState title={t("search.title")} description={t("search.comingSoon")} />;
  }

  return (
    <div>
      {/* Header */}
      <h2 className="text-[var(--text-display-size)] leading-[var(--text-display-height)] font-[var(--text-display-weight)] text-[var(--color-neutral-900)] mb-[var(--space-6)]">
        {t("search.title")}
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
            placeholder={t("search.placeholder")}
            className="w-full h-12 pl-12 pr-10 rounded-[var(--radius-lg)] border-2 border-[var(--color-neutral-200)] bg-[var(--color-white)] text-[var(--text-body-size)] leading-[var(--text-body-height)] text-[var(--color-neutral-900)] placeholder:text-[var(--color-neutral-400)] outline-none transition-colors duration-[var(--duration-normal)] focus:border-[var(--color-primary-light)]"
            aria-label={t("search.ariaLabel")}
          />
          {inputValue && (
            <button
              onClick={handleClear}
              className="absolute right-[var(--space-3)] top-1/2 -translate-y-1/2 p-1 rounded-[var(--radius-sm)] text-[var(--color-neutral-400)] hover:text-[var(--color-neutral-700)] hover:bg-[var(--color-neutral-100)] transition-colors cursor-pointer"
              aria-label={t("search.clear")}
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
            aria-label={t("search.mode.ariaLabel")}
          >
            {SEARCH_MODE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{t(opt.labelKey)}</option>
            ))}
          </select>
          <div className="relative">
            <button
              onMouseEnter={() => setShowModeTooltip(true)}
              onMouseLeave={() => setShowModeTooltip(false)}
              onFocus={() => setShowModeTooltip(true)}
              onBlur={() => setShowModeTooltip(false)}
              className="p-0.5 text-[var(--color-neutral-400)] hover:text-[var(--color-neutral-600)] cursor-pointer transition-colors"
              aria-label={t("search.mode.info")}
              type="button"
            >
              <Info size={14} aria-hidden="true" />
            </button>
            {showModeTooltip && (
              <div className="absolute left-0 top-6 z-10 w-48 p-[var(--space-2)] rounded-[var(--radius-md)] bg-[var(--color-neutral-900)] text-white text-[var(--text-caption-size)] leading-[var(--text-caption-height)] shadow-lg">
                {t(SEARCH_MODE_DESCRIPTION_KEYS[searchMode])}
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
          {t("search.filters.toggle")}
          {showAdvancedFilters ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
      </div>

      {/* Advanced filters (collapsible) */}
      {showAdvancedFilters && (
        <div className="mb-[var(--space-4)] max-w-[600px] space-y-[var(--space-3)] p-[var(--space-4)] rounded-[var(--radius-lg)] border border-[var(--color-neutral-200)] bg-[var(--color-neutral-50)]">
          {/* Date range */}
          <div>
            <label className="block text-[var(--text-caption-size)] text-[var(--color-neutral-500)] mb-[var(--space-1)] font-medium">
              {t("search.filters.dateRange")}
            </label>
            <div className="flex items-center gap-[var(--space-3)]">
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="h-9 px-[var(--space-3)] rounded-[var(--radius-md)] border border-[var(--color-neutral-200)] bg-white text-[var(--text-small-size)] text-[var(--color-neutral-700)] outline-none focus:border-[var(--color-primary-light)]"
                aria-label={t("search.filters.dateFrom")}
              />
              <span className="text-[var(--text-small-size)] text-[var(--color-neutral-400)]">{t("search.filters.dateRangeSeparator")}</span>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="h-9 px-[var(--space-3)] rounded-[var(--radius-md)] border border-[var(--color-neutral-200)] bg-white text-[var(--text-small-size)] text-[var(--color-neutral-700)] outline-none focus:border-[var(--color-primary-light)]"
                aria-label={t("search.filters.dateTo")}
              />
            </div>
          </div>

          {/* Correspondent (documents) */}
          {(typeFilter === "file" || typeFilter === "all") && (
            <div>
              <label className="block text-[var(--text-caption-size)] text-[var(--color-neutral-500)] mb-[var(--space-1)] font-medium">
                {t("search.filters.correspondent")}
              </label>
              {correspondentOptions ? (
                <select
                  value={correspondent}
                  onChange={(e) => setCorrespondent(e.target.value)}
                  className="w-full h-9 px-[var(--space-3)] rounded-[var(--radius-md)] border border-[var(--color-neutral-200)] bg-white text-[var(--text-small-size)] text-[var(--color-neutral-700)] outline-none focus:border-[var(--color-primary-light)] cursor-pointer"
                  aria-label={t("search.filters.correspondentAriaLabel")}
                >
                  <option value="">{t("search.filters.correspondentAny")}</option>
                  {correspondentOptions.map((c) => (
                    <option key={c.id} value={c.name}>{c.name}</option>
                  ))}
                </select>
              ) : (
                <input
                  type="text"
                  value={correspondent}
                  onChange={(e) => setCorrespondent(e.target.value)}
                  placeholder={t("search.filters.correspondentPlaceholder")}
                  className="w-full h-9 px-[var(--space-3)] rounded-[var(--radius-md)] border border-[var(--color-neutral-200)] bg-white text-[var(--text-small-size)] text-[var(--color-neutral-700)] placeholder:text-[var(--color-neutral-400)] outline-none focus:border-[var(--color-primary-light)]"
                  aria-label={t("search.filters.correspondentAriaLabel")}
                />
              )}
            </div>
          )}

          {/* Tags (documents) */}
          {(typeFilter === "file" || typeFilter === "all") && (
            <div>
              <label className="block text-[var(--text-caption-size)] text-[var(--color-neutral-500)] mb-[var(--space-1)] font-medium">
                {t("search.filters.tags")}
              </label>
              <input
                type="text"
                value={tagsInput}
                onChange={(e) => setTagsInput(e.target.value)}
                placeholder={t("search.filters.tagsPlaceholder")}
                className="w-full h-9 px-[var(--space-3)] rounded-[var(--radius-md)] border border-[var(--color-neutral-200)] bg-white text-[var(--text-small-size)] text-[var(--color-neutral-700)] placeholder:text-[var(--color-neutral-400)] outline-none focus:border-[var(--color-primary-light)]"
                aria-label={t("search.filters.tagsAriaLabel")}
              />
            </div>
          )}
        </div>
      )}

      {/* Result count */}
      {query && !isLoading && !error && allCards.length > 0 && (
        <p className="text-[var(--text-caption-size)] leading-[var(--text-caption-height)] text-[var(--color-neutral-500)] mb-[var(--space-4)]">
          {totalCount && totalCount > allCards.length
            ? t("search.results.showingRange", { shown: allCards.length, total: totalCount })
            : allCards.length !== 1
              ? t("search.results.showingCountPlural", { count: allCards.length })
              : t("search.results.showingCount", { count: allCards.length })}
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
          message={(error as { message?: string }).message ?? t("search.error")}
          onRetry={() => mutate()}
        />
      )}

      {query && !isLoading && !error && allCards.length === 0 && (
        <EmptyState
          title={
            typeFilter === "file"
              ? t("search.noResults.documents")
              : t("search.noResults.default", { query })
          }
          description={
            typeFilter === "file"
              ? t("search.noResults.documentsDescription")
              : t("search.noResults.defaultDescription")
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
