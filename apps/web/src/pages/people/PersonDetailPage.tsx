/**
 * /people/:personId — trusted person detail page (S13-003).
 *
 * Surfaces:
 *   - Header card (avatar, inline-rename name, counts, kebab menu)
 *   - Four tabs (Photos / Files / Events / Reminders) keyed by URL hash
 *   - Faces management grid with per-face remove ("this isn't them")
 *   - Delete + remove-face confirmation modals
 *
 * Files and Reminders return empty lists today — the underlying
 * linkage tables haven't landed. The tabs render so the UI is stable.
 *
 * Gating layers (must all pass before the real UI renders):
 *   1. face_clustering_enabled feature flag
 *   2. active face consent for the workspace
 *   3. successful person fetch
 *
 * Uses the design-system primitives (TabBar, Modal, Breadcrumb,
 * EmptyState, ErrorBanner, Skeleton, Button) plus PersonAvatar from
 * S13-002.
 */

import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  Check,
  MoreVertical,
  Pencil,
  Trash2,
  X,
} from "lucide-react";

import PersonAvatar from "../../components/people/PersonAvatar";
import Toast, { type ToastVariant } from "../../components/Toast";
import Breadcrumb from "../../design-system/components/Breadcrumb";
import Button from "../../design-system/components/Button";
import EmptyState from "../../design-system/components/EmptyState";
import ErrorBanner from "../../design-system/components/ErrorBanner";
import FeatureComingSoon from "../../design-system/components/FeatureComingSoon";
import Modal from "../../design-system/components/Modal";
import Skeleton from "../../design-system/components/Skeleton";
import TabBar from "../../design-system/components/TabBar";
import { useFlag } from "../../contexts/FlagContext";
import {
  useFaceConsent,
  usePerson,
  usePersonEvents,
  usePersonFaces,
  usePersonFiles,
  usePersonPhotos,
  usePersonReminders,
} from "../../hooks/usePeople";
import { peopleApi } from "../../api/people";
import { t } from "../../i18n";
import type {
  PersonEventItem,
  PersonFileItem,
  PersonPhotoItem,
  PersonReminderItem,
  TrustedPerson,
} from "../../types/people";
import { trackPeopleEvent } from "../../utils/metrics";

type TabKey = "photos" | "files" | "events" | "reminders";
const VALID_TABS: TabKey[] = ["photos", "files", "events", "reminders"];

interface ToastState {
  message: string;
  variant: ToastVariant;
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString();
}

function isNotFound(err: unknown): boolean {
  if (!err || typeof err !== "object") return false;
  const status = (err as { status?: number }).status;
  return status === 404;
}

export default function PersonDetailPage() {
  const enabled = useFlag("face_clustering_enabled");
  const { accepted, loading: consentLoading } = useFaceConsent();
  const { personId } = useParams<{ personId: string }>();
  const navigate = useNavigate();
  const location = useLocation();

  const personHook = usePerson(personId, { shouldRetryOnError: false });
  const { data: person, error, isLoading, mutate: mutatePerson } = personHook;

  const activeTab: TabKey = useMemo(() => {
    const hash = location.hash.replace(/^#/, "") as TabKey;
    return VALID_TABS.includes(hash) ? hash : "photos";
  }, [location.hash]);

  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState("");
  const [renameError, setRenameError] = useState<string | null>(null);
  const [renameSubmitting, setRenameSubmitting] = useState(false);

  const [menuOpen, setMenuOpen] = useState(false);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [deleteSubmitting, setDeleteSubmitting] = useState(false);

  const [toast, setToast] = useState<ToastState | null>(null);

  useEffect(() => {
    if (enabled && accepted && personId) {
      trackPeopleEvent("people.detail.viewed", { person_id: personId });
    }
  }, [enabled, accepted, personId]);

  // ── Gating
  if (!enabled) return <FeatureComingSoon featureName="People" />;
  if (consentLoading || isLoading) {
    return (
      <div className="max-w-[960px] mx-auto p-6">
        <Skeleton variant="card" />
      </div>
    );
  }
  if (!accepted) {
    return (
      <div className="max-w-[960px] mx-auto p-6">
        <ErrorBanner message={t("error.generic")} />
      </div>
    );
  }
  if (isNotFound(error) || (!person && error)) {
    return (
      <div className="max-w-[960px] mx-auto p-6 text-center">
        <h1 className="text-xl font-semibold mb-2">Person not found</h1>
        <Link
          to="/people"
          className="text-[var(--color-primary)] hover:underline"
        >
          ← Back to People
        </Link>
      </div>
    );
  }
  if (!person) {
    return (
      <div className="max-w-[960px] mx-auto p-6">
        <ErrorBanner message={t("error.generic")} />
      </div>
    );
  }

  // ── Handlers
  const handleSetTab = (key: string) => {
    navigate({ hash: `#${key}` }, { replace: false });
    trackPeopleEvent("people.detail.tab_changed", {
      person_id: person.id,
      tab: key,
    });
  };

  const startRename = () => {
    setRenameValue(person.display_name);
    setRenameError(null);
    setRenaming(true);
  };

  const submitRename = async () => {
    const next = renameValue.trim();
    if (!next || next === person.display_name) {
      setRenaming(false);
      return;
    }
    setRenameSubmitting(true);
    setRenameError(null);
    try {
      await peopleApi.rename(person.id, next);
      await mutatePerson();
      trackPeopleEvent("people.detail.renamed", { person_id: person.id });
      setRenaming(false);
      setToast({
        message: t("person.detail.renameLabel") + " ✓",
        variant: "success",
      });
    } catch (err) {
      setRenameError(
        (err as Error)?.message || t("error.generic"),
      );
    } finally {
      setRenameSubmitting(false);
    }
  };

  const cancelRename = () => {
    setRenaming(false);
    setRenameError(null);
  };

  const handleDelete = async () => {
    setDeleteSubmitting(true);
    try {
      await peopleApi.delete(person.id);
      trackPeopleEvent("people.detail.deleted", { person_id: person.id });
      setDeleteModalOpen(false);
      navigate("/people", { replace: true });
    } catch (err) {
      setToast({
        message: (err as Error)?.message || t("error.generic"),
        variant: "error",
      });
    } finally {
      setDeleteSubmitting(false);
    }
  };

  const seenRange = formatSeenRange(person);
  const mergedFromCount = person.merged_from_ids?.length ?? 0;

  return (
    <div className="max-w-[960px] mx-auto p-6">
      <div className="mb-4">
        <Breadcrumb
          items={[
            { label: t("people.list.title"), href: "/people" },
            { label: person.display_name },
          ]}
        />
      </div>

      {/* Header card */}
      <div className="flex items-start gap-4 p-4 rounded-[var(--radius-lg)] border border-[var(--color-neutral-200)] bg-[var(--color-white)] mb-6">
        <PersonAvatar person={person} size="xl" />
        <div className="flex-1 min-w-0">
          {renaming ? (
            <div>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={renameValue}
                  onChange={(e) => setRenameValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") void submitRename();
                    if (e.key === "Escape") cancelRename();
                  }}
                  autoFocus
                  aria-label={t("person.detail.renameLabel")}
                  className="flex-1 text-2xl font-semibold border-b border-[var(--color-neutral-300)] outline-none focus:border-[var(--color-primary)] bg-transparent"
                />
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => void submitRename()}
                  loading={renameSubmitting}
                  icon={<Check size={14} />}
                >
                  {t("person.detail.saveButton")}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={cancelRename}
                  icon={<X size={14} />}
                >
                  Cancel
                </Button>
              </div>
              {renameError && (
                <div className="mt-2">
                  <ErrorBanner message={renameError} />
                </div>
              )}
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-semibold text-[var(--color-neutral-900)] truncate">
                {person.display_name}
              </h1>
              <button
                type="button"
                onClick={startRename}
                aria-label={t("person.detail.rename")}
                className="p-1 rounded hover:bg-[var(--color-neutral-100)]"
              >
                <Pencil size={14} aria-hidden="true" />
              </button>
            </div>
          )}
          <div className="mt-1 flex items-center gap-3 flex-wrap text-sm text-[var(--color-neutral-600)]">
            {typeof person.face_count === "number" && (
              <span>
                {person.face_count === 1
                  ? t("people.list.faceCount", { count: person.face_count })
                  : t("people.list.faceCountPlural", {
                      count: person.face_count,
                    })}
              </span>
            )}
            {seenRange && <span>{seenRange}</span>}
            {mergedFromCount > 0 && (
              <span className="px-2 py-0.5 rounded-full bg-[var(--color-info-surface)] text-[var(--color-info)] text-xs">
                {mergedFromCount === 1
                  ? t("person.detail.mergedFrom", { count: mergedFromCount })
                  : t("person.detail.mergedFromPlural", {
                      count: mergedFromCount,
                    })}
              </span>
            )}
          </div>
        </div>

        <div className="relative">
          <button
            type="button"
            onClick={() => setMenuOpen((o) => !o)}
            aria-label="Actions"
            className="p-2 rounded hover:bg-[var(--color-neutral-100)]"
          >
            <MoreVertical size={18} aria-hidden="true" />
          </button>
          {menuOpen && (
            <div
              className="absolute right-0 top-10 z-20 w-56 rounded-[var(--radius-md)] border border-[var(--color-neutral-200)] bg-[var(--color-white)] shadow-[var(--shadow-lg)] py-1"
              role="menu"
              onMouseLeave={() => setMenuOpen(false)}
            >
              <MenuItem
                label={t("person.detail.merge")}
                onClick={() => {
                  setMenuOpen(false);
                  setToast({
                    message: "Merge UI lands in S13-005",
                    variant: "info",
                  });
                }}
              />
              <MenuItem
                label={t("person.detail.split")}
                onClick={() => {
                  setMenuOpen(false);
                  setToast({
                    message: "Split UI lands in S13-006",
                    variant: "info",
                  });
                }}
              />
              <MenuItem
                label={t("person.detail.delete")}
                danger
                icon={<Trash2 size={14} />}
                onClick={() => {
                  setMenuOpen(false);
                  setDeleteModalOpen(true);
                }}
              />
            </div>
          )}
        </div>
      </div>

      {/* Tabs */}
      <TabBar
        tabs={[
          { key: "photos", label: t("person.detail.tabs.photos") },
          { key: "files", label: t("person.detail.tabs.files") },
          { key: "events", label: t("person.detail.tabs.events") },
          { key: "reminders", label: t("person.detail.tabs.reminders") },
        ]}
        activeTab={activeTab}
        onChange={handleSetTab}
      />
      <div className="mt-4 mb-8" id={`panel-${activeTab}`} role="tabpanel">
        {activeTab === "photos" && <PhotosTab personId={person.id} />}
        {activeTab === "files" && <FilesTab personId={person.id} />}
        {activeTab === "events" && <EventsTab personId={person.id} />}
        {activeTab === "reminders" && <RemindersTab personId={person.id} />}
      </div>

      {/* Faces section */}
      <FacesSection
        personId={person.id}
        personName={person.display_name}
        onToast={setToast}
        onPersonRefresh={() => void mutatePerson()}
      />

      {/* Delete confirm */}
      <Modal
        open={deleteModalOpen}
        onClose={() => setDeleteModalOpen(false)}
        title={t("person.detail.deleteConfirm.title", {
          name: person.display_name,
        })}
        size="sm"
      >
        <p className="text-sm text-[var(--color-neutral-700)] mb-4">
          {t("person.detail.deleteConfirm.body")}
        </p>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setDeleteModalOpen(false)}>
            Cancel
          </Button>
          <Button
            variant="danger"
            loading={deleteSubmitting}
            onClick={() => void handleDelete()}
          >
            {t("person.detail.deleteConfirm.confirm")}
          </Button>
        </div>
      </Modal>

      {toast && (
        <Toast
          message={toast.message}
          variant={toast.variant}
          onDismiss={() => setToast(null)}
        />
      )}
    </div>
  );
}

// ── Subcomponents ────────────────────────────────────────────────────────

interface MenuItemProps {
  label: string;
  onClick: () => void;
  danger?: boolean;
  icon?: React.ReactNode;
}

function MenuItem({ label, onClick, danger, icon }: MenuItemProps) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      className={[
        "w-full text-left px-3 py-2 text-sm flex items-center gap-2",
        "hover:bg-[var(--color-neutral-100)]",
        danger ? "text-[var(--color-error)]" : "text-[var(--color-neutral-800)]",
      ].join(" ")}
    >
      {icon}
      {label}
    </button>
  );
}

function formatSeenRange(person: TrustedPerson): string | null {
  if (!person.first_seen_at && !person.last_seen_at) return null;
  const from = formatDate(person.first_seen_at);
  const to = formatDate(person.last_seen_at);
  if (from && to && from !== to) return `${from} – ${to}`;
  return from || to || null;
}

// ── Tab panels ───────────────────────────────────────────────────────────

function TabSkeleton() {
  return <Skeleton variant="text" count={3} />;
}

function PhotosTab({ personId }: { personId: string }) {
  const { data, error, isLoading } = usePersonPhotos(personId, undefined, {
    shouldRetryOnError: false,
  });
  if (isLoading) return <TabSkeleton />;
  if (error)
    return <ErrorBanner message={t("error.generic")} />;
  const items = data?.items ?? [];
  if (items.length === 0)
    return (
      <EmptyState
        title={t("person.detail.empty.photos")}
      />
    );
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
      {items.map((p: PersonPhotoItem) => (
        <PhotoTile key={p.id} item={p} />
      ))}
    </div>
  );
}

function PhotoTile({ item }: { item: PersonPhotoItem }) {
  return (
    <div className="aspect-square rounded-[var(--radius-md)] overflow-hidden bg-[var(--color-neutral-100)]">
      <img
        src={item.thumbnail_url}
        alt=""
        className="w-full h-full object-cover"
        loading="lazy"
      />
    </div>
  );
}

function FilesTab({ personId }: { personId: string }) {
  const { data, error, isLoading } = usePersonFiles(personId, undefined, {
    shouldRetryOnError: false,
  });
  if (isLoading) return <TabSkeleton />;
  if (error) return <ErrorBanner message={t("error.generic")} />;
  const items = data?.items ?? [];
  if (items.length === 0)
    return <EmptyState title={t("person.detail.empty.files")} />;
  return (
    <ul className="divide-y divide-[var(--color-neutral-200)]">
      {items.map((f: PersonFileItem) => (
        <li key={f.id} className="py-3">
          <div className="font-medium">{f.filename}</div>
          <div className="text-xs text-[var(--color-neutral-500)]">
            {f.mime_type ?? "—"}
          </div>
        </li>
      ))}
    </ul>
  );
}

function EventsTab({ personId }: { personId: string }) {
  const { data, error, isLoading } = usePersonEvents(personId, undefined, {
    shouldRetryOnError: false,
  });
  if (isLoading) return <TabSkeleton />;
  if (error) return <ErrorBanner message={t("error.generic")} />;
  const items = data?.items ?? [];
  if (items.length === 0)
    return <EmptyState title={t("person.detail.empty.events")} />;
  return (
    <ul className="divide-y divide-[var(--color-neutral-200)]">
      {items.map((ev: PersonEventItem) => (
        <li key={ev.id} className="py-3">
          <div className="font-medium">{ev.title}</div>
          <div className="text-xs text-[var(--color-neutral-500)]">
            {formatDate(ev.start_at)}
            {ev.location ? ` · ${ev.location}` : ""}
          </div>
        </li>
      ))}
    </ul>
  );
}

function RemindersTab({ personId }: { personId: string }) {
  const { data, error, isLoading } = usePersonReminders(personId, undefined, {
    shouldRetryOnError: false,
  });
  if (isLoading) return <TabSkeleton />;
  if (error) return <ErrorBanner message={t("error.generic")} />;
  const items = data?.items ?? [];
  if (items.length === 0)
    return <EmptyState title={t("person.detail.empty.reminders")} />;
  return (
    <ul className="divide-y divide-[var(--color-neutral-200)]">
      {items.map((r: PersonReminderItem) => (
        <li key={r.id} className="py-3">
          {r.title}
        </li>
      ))}
    </ul>
  );
}

// ── Faces management section ─────────────────────────────────────────────

interface FacesSectionProps {
  personId: string;
  personName: string;
  onToast: (t: ToastState) => void;
  onPersonRefresh: () => void;
}

function FacesSection({
  personId,
  personName,
  onToast,
  onPersonRefresh,
}: FacesSectionProps) {
  const { data, error, isLoading, mutate } = usePersonFaces(personId, {
    shouldRetryOnError: false,
  });
  const [pendingFace, setPendingFace] = useState<string | null>(null);
  const [removing, setRemoving] = useState(false);

  const items = data?.items ?? [];

  const submitRemove = async () => {
    if (!pendingFace) return;
    setRemoving(true);
    try {
      await peopleApi.removeFace(personId, pendingFace);
      trackPeopleEvent("people.detail.face_removed", {
        person_id: personId,
      });
      await mutate();
      onPersonRefresh();
      setPendingFace(null);
      onToast({
        message: t("person.detail.removeFace.confirm") + " ✓",
        variant: "success",
      });
    } catch (err) {
      onToast({
        message: (err as Error)?.message || t("error.generic"),
        variant: "error",
      });
    } finally {
      setRemoving(false);
    }
  };

  return (
    <section className="mt-6">
      <h2 className="text-lg font-semibold mb-3">Faces</h2>
      {isLoading ? (
        <TabSkeleton />
      ) : error ? (
        <ErrorBanner message={t("error.generic")} />
      ) : items.length === 0 ? (
        <p className="text-sm text-[var(--color-neutral-500)]">
          No faces linked.
        </p>
      ) : (
        <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-3">
          {items.map((f) => (
            <div
              key={f.face_detection_id}
              className="relative aspect-square rounded-[var(--radius-md)] overflow-hidden bg-[var(--color-neutral-100)] group"
            >
              <img
                src={f.thumbnail_url}
                alt=""
                className="w-full h-full object-cover"
                loading="lazy"
              />
              <button
                type="button"
                aria-label={`Not ${personName}`}
                onClick={() => setPendingFace(f.face_detection_id)}
                className="absolute top-1 right-1 p-1 rounded-full bg-[var(--color-white)] shadow opacity-0 group-hover:opacity-100 focus:opacity-100"
              >
                <X size={14} aria-hidden="true" />
              </button>
            </div>
          ))}
        </div>
      )}

      <Modal
        open={pendingFace !== null}
        onClose={() => (removing ? null : setPendingFace(null))}
        title={t("person.detail.removeFace.title")}
        size="sm"
      >
        <p className="text-sm text-[var(--color-neutral-700)] mb-4">
          {t("person.detail.removeFace.body", { name: personName })}
        </p>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setPendingFace(null)}>
            Cancel
          </Button>
          <Button
            variant="danger"
            loading={removing}
            onClick={() => void submitRemove()}
          >
            {t("person.detail.removeFace.confirm")}
          </Button>
        </div>
      </Modal>
    </section>
  );
}
