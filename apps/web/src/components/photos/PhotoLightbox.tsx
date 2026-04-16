/**
 * PhotoLightbox — full-screen photo viewer with face overlay (S13-008).
 *
 * The lightbox is the primary bridge between photos and the People
 * Graph: the user sees the full-resolution image, a button per
 * detected face scaled to the rendered image rect, and a sidebar
 * listing the distinct persons in the photo. Clicking a face (or a
 * sidebar row) navigates to the person's detail page, or to the
 * review queue anchored on the cluster for unknown faces.
 *
 * State:
 *   - ``showFaces`` toggles the overlay layer; bound to the F key.
 *   - ``rendered`` stores the image's natural + rendered bounding
 *     rect so bbox buttons can be absolutely positioned in the
 *     image's visual coordinate space. Recomputed on image load
 *     and on window resize while ``open`` is true.
 *
 * Keyboard (document-level, only while open):
 *   Esc          close
 *   ← / →        prev / next (when callbacks provided)
 *   f / F        toggle face overlay
 *
 * Reduced-motion is respected: no opacity fade when the user
 * prefers reduced motion (or when ``window.matchMedia`` is missing,
 * which is the case in our jsdom test setup).
 */

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  Download,
  Eye,
  EyeOff,
  X as XIcon,
} from "lucide-react";

import PersonAvatar from "../people/PersonAvatar";
import Button from "../../design-system/components/Button";
import ErrorBanner from "../../design-system/components/ErrorBanner";
import Skeleton from "../../design-system/components/Skeleton";
import { usePhotoFaces } from "../../hooks/usePhotoFaces";
import { t } from "../../i18n";
import type { PhotoFaceItem } from "../../types/photos";
import { trackPeopleEvent } from "../../utils/metrics";

export interface PhotoLightboxMetadata {
  takenAt?: string | null;
  locationName?: string | null;
}

export interface PhotoLightboxProps {
  open: boolean;
  photoId: string | null;
  onClose: () => void;
  onNext?: () => void;
  onPrev?: () => void;
  metadata?: PhotoLightboxMetadata;
}

interface RenderedRect {
  naturalW: number;
  naturalH: number;
  renderedW: number;
  renderedH: number;
  offsetX: number;
  offsetY: number;
}

function prefersReducedMotion(): boolean {
  if (
    typeof window === "undefined" ||
    typeof window.matchMedia !== "function"
  ) {
    return false;
  }
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export default function PhotoLightbox({
  open,
  photoId,
  onClose,
  onNext,
  onPrev,
  metadata,
}: PhotoLightboxProps) {
  const navigate = useNavigate();
  const [showFaces, setShowFaces] = useState(true);
  const imgRef = useRef<HTMLImageElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [rendered, setRendered] = useState<RenderedRect | null>(null);

  const {
    data,
    error: facesError,
    isLoading: facesLoading,
  } = usePhotoFaces(open ? photoId : null, { shouldRetryOnError: false });

  const faces = useMemo<PhotoFaceItem[]>(() => data?.items ?? [], [data]);

  // Distinct persons for the sidebar: dedupe known persons by id,
  // keep each unknown cluster as its own row so users can confirm
  // them independently.
  const sidebarRows = useMemo(() => {
    const seen = new Set<string>();
    const rows: {
      key: string;
      name: string;
      personId: string | null;
      clusterId: string | null;
      avatarUrl: string | null;
    }[] = [];
    for (const f of faces) {
      if (f.trusted_person_id) {
        if (seen.has(f.trusted_person_id)) continue;
        seen.add(f.trusted_person_id);
        rows.push({
          key: f.trusted_person_id,
          name: f.trusted_person_display_name ?? t("lightbox.unknownPerson"),
          personId: f.trusted_person_id,
          clusterId: f.cluster_id,
          avatarUrl: f.trusted_person_avatar_url,
        });
      } else {
        rows.push({
          key: `cluster:${f.cluster_id ?? f.face_detection_id}`,
          name: t("lightbox.unknownPerson"),
          personId: null,
          clusterId: f.cluster_id,
          avatarUrl: null,
        });
      }
    }
    return rows;
  }, [faces]);

  const knownCount = sidebarRows.filter((r) => r.personId !== null).length;
  const unknownCount = sidebarRows.length - knownCount;

  // Track img dimensions for overlay alignment.
  const measure = useCallback(() => {
    const img = imgRef.current;
    const container = containerRef.current;
    if (!img || !container) return;
    const natW = img.naturalWidth;
    const natH = img.naturalHeight;
    if (!natW || !natH) return;
    const rect = img.getBoundingClientRect();
    const containerRect = container.getBoundingClientRect();
    setRendered({
      naturalW: natW,
      naturalH: natH,
      renderedW: rect.width,
      renderedH: rect.height,
      offsetX: rect.left - containerRect.left,
      offsetY: rect.top - containerRect.top,
    });
  }, []);

  useLayoutEffect(() => {
    if (!open) return;
    measure();
  }, [open, photoId, measure]);

  useEffect(() => {
    if (!open) return;
    const handler = () => measure();
    window.addEventListener("resize", handler);
    return () => window.removeEventListener("resize", handler);
  }, [open, measure]);

  // Metrics on open.
  const loggedRef = useRef<string | null>(null);
  useEffect(() => {
    if (!open || !photoId) return;
    if (loggedRef.current === photoId) return;
    loggedRef.current = photoId;
    trackPeopleEvent("lightbox.openedFromPhoto", { photo_id: photoId });
  }, [open, photoId]);

  // Keyboard shortcuts.
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      )
        return;
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      } else if (e.key === "ArrowRight" && onNext) {
        e.preventDefault();
        onNext();
      } else if (e.key === "ArrowLeft" && onPrev) {
        e.preventDefault();
        onPrev();
      } else if (e.key === "f" || e.key === "F") {
        e.preventDefault();
        setShowFaces((v) => !v);
      }
    };
    document.addEventListener("keydown", handler);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handler);
      document.body.style.overflow = "";
    };
  }, [open, onClose, onNext, onPrev]);

  // Body-scroll lock cleanup when photoId changes.
  useEffect(() => {
    if (open) return;
    loggedRef.current = null;
    setRendered(null);
  }, [open, photoId]);

  const goToFace = useCallback(
    (face: PhotoFaceItem) => {
      if (face.trusted_person_id) {
        trackPeopleEvent("lightbox.personClicked", {
          person_id: face.trusted_person_id,
        });
        navigate(`/people/${face.trusted_person_id}`);
      } else if (face.cluster_id) {
        trackPeopleEvent("lightbox.personClicked", { person_id: null });
        navigate(`/people/review?highlight_cluster=${face.cluster_id}`);
      }
      onClose();
    },
    [navigate, onClose],
  );

  if (!open || !photoId) return null;

  const fadeClass = prefersReducedMotion()
    ? ""
    : "transition-opacity duration-200";

  const takenAtLabel = metadata?.takenAt
    ? new Date(metadata.takenAt).toLocaleString()
    : null;
  const announcement =
    sidebarRows.length === 0
      ? t("lightbox.noFaces")
      : t("lightbox.announce", { count: sidebarRows.length });

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Photo viewer"
      data-testid="photo-lightbox"
      className={[
        "fixed inset-0 z-50 bg-black/90 flex flex-col text-white",
        fadeClass,
      ].join(" ")}
    >
      {/* Top bar */}
      <div className="flex items-center justify-between px-4 py-2 gap-3">
        <button
          type="button"
          onClick={onClose}
          aria-label={t("lightbox.closeButton")}
          className="p-2 rounded hover:bg-white/10"
        >
          <XIcon size={20} aria-hidden="true" />
        </button>
        <div className="flex-1 text-center text-sm opacity-80">
          {takenAtLabel && <span>{takenAtLabel}</span>}
          {metadata?.locationName && (
            <span className="ml-2">· {metadata.locationName}</span>
          )}
        </div>
        <button
          type="button"
          onClick={() => setShowFaces((v) => !v)}
          aria-label={t("lightbox.toggleFaces")}
          aria-pressed={showFaces}
          className="p-2 rounded hover:bg-white/10"
          data-testid="lightbox-toggle-faces"
        >
          {showFaces ? (
            <Eye size={18} aria-hidden="true" />
          ) : (
            <EyeOff size={18} aria-hidden="true" />
          )}
        </button>
      </div>

      {/* Image + sidebar */}
      <div className="flex-1 flex overflow-hidden">
        <div
          ref={containerRef}
          className="flex-1 relative flex items-center justify-center min-h-0"
        >
          <img
            ref={imgRef}
            src={`/api/v1/photos/${photoId}/full`}
            alt=""
            onLoad={measure}
            className="max-w-full max-h-full object-contain"
          />

          {showFaces && rendered && faces.length > 0 && (
            <div
              data-testid="lightbox-faces-layer"
              aria-hidden="false"
              className="absolute top-0 left-0 pointer-events-none"
              style={{
                width: rendered.renderedW,
                height: rendered.renderedH,
                transform: `translate(${rendered.offsetX}px, ${rendered.offsetY}px)`,
              }}
            >
              {faces.map((f) => {
                const { x, y, w, h } = f.bbox;
                const known = f.trusted_person_id !== null;
                const label =
                  f.trusted_person_display_name ?? t("lightbox.unknownPerson");
                return (
                  <button
                    key={f.face_detection_id}
                    type="button"
                    onClick={() => goToFace(f)}
                    aria-label={
                      known
                        ? `Face of ${label}. Press Enter to view person.`
                        : `${label}. Press Enter to review.`
                    }
                    data-testid={`lightbox-face-${f.face_detection_id}`}
                    className={[
                      "absolute pointer-events-auto",
                      "outline-none focus-visible:ring-2 focus-visible:ring-white",
                      "rounded-sm",
                    ].join(" ")}
                    style={{
                      left: `${x * 100}%`,
                      top: `${y * 100}%`,
                      width: `${w * 100}%`,
                      height: `${h * 100}%`,
                      border: `2px solid ${
                        known
                          ? "var(--color-primary)"
                          : "var(--color-warning)"
                      }`,
                      background: "transparent",
                    }}
                  >
                    <span
                      className="absolute -top-6 left-0 px-1.5 py-0.5 rounded text-xs whitespace-nowrap"
                      style={{
                        background: known
                          ? "var(--color-primary)"
                          : "var(--color-warning)",
                        color: "white",
                      }}
                    >
                      {label}
                    </span>
                  </button>
                );
              })}
            </div>
          )}

          {facesLoading && (
            <div className="absolute bottom-4 left-4 w-40">
              <Skeleton variant="text" count={1} />
            </div>
          )}
          {facesError && (
            <div className="absolute bottom-4 left-4 right-4">
              <ErrorBanner message={t("error.generic")} />
            </div>
          )}
        </div>

        {/* Sidebar */}
        <aside
          className="hidden md:flex w-64 flex-col border-l border-white/10 bg-black/60"
          aria-label={t("lightbox.facesInPhoto")}
          data-testid="lightbox-sidebar"
        >
          <div className="px-4 py-3 text-sm font-semibold border-b border-white/10">
            {t("lightbox.facesInPhoto")}
          </div>
          <div className="flex-1 overflow-y-auto">
            {sidebarRows.length === 0 ? (
              <p className="px-4 py-6 text-sm text-white/60">
                {t("lightbox.noFaces")}
              </p>
            ) : (
              <ul>
                {sidebarRows.map((row) => (
                  <li
                    key={row.key}
                    className="border-b border-white/5"
                  >
                    <button
                      type="button"
                      onClick={() => {
                        const first = faces.find(
                          (f) =>
                            (row.personId && f.trusted_person_id === row.personId) ||
                            (!row.personId && f.cluster_id === row.clusterId),
                        );
                        if (first) goToFace(first);
                      }}
                      className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-white/5"
                    >
                      {row.personId ? (
                        <PersonAvatar
                          person={{ id: row.personId, display_name: row.name }}
                          size="sm"
                        />
                      ) : (
                        <span
                          aria-hidden="true"
                          className="w-8 h-8 rounded-full bg-[var(--color-warning)]/20 flex items-center justify-center text-xs"
                        >
                          ?
                        </span>
                      )}
                      <span className="flex-1 truncate text-sm">{row.name}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>
      </div>

      {/* Bottom bar */}
      <div className="flex items-center justify-between px-4 py-3 gap-3 border-t border-white/10">
        <div className="flex items-center gap-2">
          {onPrev && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onPrev}
              icon={<ArrowLeft size={14} />}
            >
              {t("lightbox.prevPhoto")}
            </Button>
          )}
          {onNext && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onNext}
              icon={<ArrowRight size={14} />}
            >
              {t("lightbox.nextPhoto")}
            </Button>
          )}
        </div>
        <div className="flex items-center gap-2 text-xs opacity-80">
          <span>
            {knownCount} known · {unknownCount} unknown
          </span>
          <a
            href={`/api/v1/photos/${photoId}/full`}
            download
            className="inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-white/10"
          >
            <Download size={14} aria-hidden="true" /> {t("lightbox.download")}
          </a>
        </div>
      </div>

      {/* SR-only live region */}
      <div className="sr-only" role="status" aria-live="polite">
        {announcement}
      </div>
    </div>
  );
}
