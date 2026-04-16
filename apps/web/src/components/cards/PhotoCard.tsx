import { useState } from "react";
import { Image } from "lucide-react";
import { Card } from "../../design-system/components";
import type { PhotoPayload } from "../../api/client";
import PhotoLightbox from "../photos/PhotoLightbox";

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

      <PhotoLightbox
        open={modalOpen}
        photoId={modalOpen ? id : null}
        onClose={() => setModalOpen(false)}
        metadata={{
          takenAt: payload.taken_at ?? null,
          locationName: payload.location_name ?? null,
        }}
      />
    </>
  );
}
