/**
 * Photos Page (G-03) — Grid of photo thumbnails grouped by date.
 * Route: /photos | Flag: photos_enabled
 */

import { useState } from "react";
import useSWR from "swr";
import { Image } from "lucide-react";
import { swrFetcher, type SearchResponse, type Card } from "../api/client";
import { useAuth } from "../contexts/AuthContext";
import { useFlag } from "../contexts/FlagContext";
import { Button, FeatureComingSoon, Skeleton } from "../design-system/components";
import ErrorBanner from "../components/ErrorBanner";
import { t } from "../i18n";

function groupByDate(cards: Card[]): Map<string, Card[]> {
  const groups = new Map<string, Card[]>();
  for (const card of cards) {
    const p = card.payload as Record<string, unknown>;
    const taken = String(p.taken_at ?? "");
    const dateKey = taken ? taken.split("T")[0] : t("photos.unknownDate");
    const list = groups.get(dateKey) ?? [];
    list.push(card);
    groups.set(dateKey, list);
  }
  return groups;
}

function formatDateHeader(iso: string): string {
  if (iso === t("photos.unknownDate")) return iso;
  try {
    return new Date(iso).toLocaleDateString(undefined, { weekday: "long", year: "numeric", month: "long", day: "numeric" });
  } catch {
    return iso;
  }
}

export default function PhotosPage() {
  const enabled = useFlag("photos_enabled");
  const { user } = useAuth();
  const wsId = user?.workspaceIds?.[0];
  const [cursor, setCursor] = useState(0);
  const [allCards, setAllCards] = useState<Card[]>([]);

  const { data, error, isLoading, mutate } = useSWR<SearchResponse>(
    enabled && wsId ? `/api/v1/search?type=photo&workspace_id=${wsId}&per_page=40&cursor=${cursor}&q=*` : null,
    swrFetcher,
    {
      onSuccess: (d) => {
        if (cursor === 0) setAllCards(d.data);
        else setAllCards((prev) => [...prev, ...d.data]);
      },
    },
  );

  if (!enabled) return <FeatureComingSoon featureName={t("photos.title")} />;
  if (isLoading && cursor === 0) return <Skeleton variant="card" count={6} />;
  if (error) return <ErrorBanner message={t("photos.error")} onRetry={() => mutate()} />;

  if (allCards.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-[var(--space-16)] text-center">
        <div className="mb-[var(--space-4)] p-[var(--space-4)] rounded-full bg-[var(--color-neutral-100)]">
          <Image size={32} className="text-[var(--color-neutral-400)]" aria-hidden="true" />
        </div>
        <h3 className="font-[var(--text-h3-weight)] text-[var(--text-h3-size)] text-[var(--color-neutral-900)] mb-[var(--space-2)]">
          {t("photos.empty.title")}
        </h3>
        <p className="text-[var(--text-body-size)] text-[var(--color-neutral-500)]">
          {t("photos.empty.description")}
        </p>
      </div>
    );
  }

  const grouped = groupByDate(allCards);
  const hasMore = data?.pagination?.has_more ?? false;

  return (
    <div className="space-y-[var(--space-6)]">
      {Array.from(grouped.entries()).map(([dateKey, photos]) => (
        <section key={dateKey}>
          <h3 className="sticky top-0 z-10 bg-[var(--color-neutral-50)] py-[var(--space-2)] px-[var(--space-1)] font-[var(--text-h3-weight)] text-[var(--text-small-size)] text-[var(--color-neutral-600)] uppercase tracking-wider border-b border-[var(--color-neutral-200)]">
            {formatDateHeader(dateKey)}
          </h3>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(120px,1fr))] gap-1 mt-[var(--space-2)]">
            {photos.map((card) => {
              const p = card.payload as Record<string, unknown>;
              const thumbUrl = String(p.thumbnail_url ?? "");
              const location = String(p.location_name ?? "");

              return (
                <div
                  key={card.id}
                  className="relative aspect-square rounded-[var(--radius-sm)] overflow-hidden bg-[var(--color-neutral-200)] cursor-pointer hover:shadow-[var(--shadow-md)] hover:scale-[1.02] transition-all duration-[var(--duration-normal)]"
                  title={location || undefined}
                >
                  {thumbUrl ? (
                    <img
                      src={thumbUrl}
                      alt={location || t("photos.alt")}
                      className="w-full h-full object-cover"
                      loading="lazy"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center">
                      <Image size={24} className="text-[var(--color-neutral-400)]" aria-hidden="true" />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      ))}

      {hasMore && (
        <div className="text-center pt-[var(--space-4)]">
          <Button variant="secondary" size="sm" onClick={() => setCursor((c) => c + 40)}>
            {t("photos.loadMore")}
          </Button>
        </div>
      )}
    </div>
  );
}
