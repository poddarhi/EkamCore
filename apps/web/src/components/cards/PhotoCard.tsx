import { useState } from "react";
import { Image, X } from "lucide-react";
import { Card } from "../../design-system/components";
import type { PhotoPayload } from "../../api/client";

interface PhotoCardProps {
  id: string;
  payload: PhotoPayload;
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
}

export default function PhotoCard({ id, payload }: PhotoCardProps) {
  const [modalOpen, setModalOpen] = useState(false);

  const thumbnailUrl = payload.thumbnail_url ?? null;

  function handleCardClick() {
    setModalOpen(true);
  }

  function handleModalClose(e: React.MouseEvent) {
    e.stopPropagation();
    setModalOpen(false);
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") setModalOpen(false);
  }

  return (
    <>
      <Card onClick={handleCardClick}>
        <div className="flex items-start gap-[var(--space-3)]">
          {/* Thumbnail */}
          <div
            className="relative shrink-0 w-[120px] h-[120px] rounded-[var(--radius-md)] overflow-hidden bg-[var(--color-neutral-100)] flex items-center justify-center"
            aria-hidden="true"
          >
            {thumbnailUrl ? (
              <img
                src={thumbnailUrl}
                alt=""
                className="w-full h-full object-cover"
                loading="lazy"
              />
            ) : (
              <Image size={32} className="text-[var(--color-neutral-300)]" />
            )}
          </div>

          {/* Metadata */}
          <div className="min-w-0 flex-1">
            {payload.taken_at && (
              <p className="font-semibold text-[var(--text-body-size)] leading-[var(--text-body-height)] text-[var(--color-neutral-900)]">
                {formatDate(payload.taken_at)}
              </p>
            )}

            <div className="mt-[var(--space-2)] space-y-[var(--space-1)]">
              {payload.location_name && (
                <p className="text-[var(--text-small-size)] leading-[var(--text-small-height)] text-[var(--color-neutral-600)] truncate">
                  {payload.location_name}
                </p>
              )}
              {payload.camera && (
                <p className="text-[var(--text-caption-size)] leading-[var(--text-caption-height)] text-[var(--color-neutral-400)]">
                  {payload.camera}
                </p>
              )}
              {payload.width && payload.height && (
                <p className="text-[var(--text-caption-size)] leading-[var(--text-caption-height)] text-[var(--color-neutral-400)]">
                  {payload.width} × {payload.height}
                </p>
              )}
            </div>
          </div>
        </div>
      </Card>

      {/* Modal */}
      {modalOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Photo preview"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
          onClick={handleModalClose}
          onKeyDown={handleKeyDown}
          tabIndex={-1}
        >
          <div
            className="relative max-w-[90vw] max-h-[90vh] rounded-[var(--radius-lg)] overflow-hidden bg-[var(--color-neutral-900)]"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={handleModalClose}
              className="absolute top-[var(--space-3)] right-[var(--space-3)] z-10 p-1.5 rounded-[var(--radius-sm)] bg-black/50 text-white hover:bg-black/70 cursor-pointer transition-colors"
              aria-label="Close preview"
            >
              <X size={18} aria-hidden="true" />
            </button>

            {thumbnailUrl ? (
              <img
                src={`/api/v1/photos/${id}/thumbnail`}
                alt={payload.location_name ?? "Photo"}
                className="block max-w-[90vw] max-h-[90vh] object-contain"
                onError={(e) => {
                  // Fall back to thumbnail_url if full-res not available yet
                  (e.currentTarget as HTMLImageElement).src = thumbnailUrl;
                }}
              />
            ) : (
              <div className="w-64 h-64 flex items-center justify-center">
                <Image size={48} className="text-[var(--color-neutral-600)]" />
              </div>
            )}

            {/* Caption */}
            {(payload.taken_at || payload.location_name) && (
              <div className="px-[var(--space-4)] py-[var(--space-3)] bg-black/60 text-white">
                {payload.taken_at && (
                  <p className="text-[var(--text-small-size)]">{formatDate(payload.taken_at)}</p>
                )}
                {payload.location_name && (
                  <p className="text-[var(--text-caption-size)] text-white/70 mt-0.5">
                    {payload.location_name}
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
