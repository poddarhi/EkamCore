/**
 * SplitPersonModal — split a subset of faces into a new person (S13-006).
 *
 * Flow: user toggles faces in the grid, types a name for the new
 * person, and hits Split. We POST the selected face_detection_ids +
 * new_display_name to /api/v1/people/:id/split which returns the
 * (original, new) trusted_person pair. Parent decides what to do
 * next via the ``onSplit`` callback — typically refresh the detail
 * page and toast.
 *
 * Guardrails enforced client-side:
 *   - at least one face selected
 *   - new display name non-empty
 *   - not every face selected (that would leave the original empty;
 *     the backend will refuse too, but catching it in the client
 *     saves a round-trip and keeps the error UX clean).
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import Button from "../../design-system/components/Button";
import ErrorBanner from "../../design-system/components/ErrorBanner";
import Modal from "../../design-system/components/Modal";
import Skeleton from "../../design-system/components/Skeleton";
import { peopleApi } from "../../api/people";
import { usePersonFaces } from "../../hooks/usePeople";
import { t } from "../../i18n";
import type { PersonFace, TrustedPerson } from "../../types/people";
import { trackPeopleEvent } from "../../utils/metrics";

export interface SplitPersonModalProps {
  open: boolean;
  onClose: () => void;
  person: TrustedPerson;
  /** Optional set of face_detection_ids to pre-select when the modal
   *  opens — used by the PersonDetailPage faces multi-select bar. */
  preselectedFaceIds?: string[];
  onSplit: (original: TrustedPerson, newPerson: TrustedPerson) => void;
}

export default function SplitPersonModal({
  open,
  onClose,
  person,
  preselectedFaceIds,
  onSplit,
}: SplitPersonModalProps) {
  const { data, error: facesError, isLoading, mutate } = usePersonFaces(
    open ? person.id : null,
    { shouldRetryOnError: false },
  );
  const faces: PersonFace[] = useMemo(() => data?.items ?? [], [data]);

  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [newName, setNewName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // When the modal opens (or the preselected list changes), seed the
  // selection and reset the form.
  useEffect(() => {
    if (!open) return;
    setSelected(new Set(preselectedFaceIds ?? []));
    setNewName("");
    setError(null);
  }, [open, preselectedFaceIds]);

  const toggle = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const selectAll = () => setSelected(new Set(faces.map((f) => f.face_detection_id)));
  const clearSelection = () => setSelected(new Set());

  const total = faces.length;
  const selectedCount = selected.size;
  const wouldEmptyOriginal = selectedCount > 0 && selectedCount >= total;
  const nameOk = newName.trim().length > 0;
  const canSubmit =
    selectedCount > 0 && !wouldEmptyOriginal && nameOk && !submitting;

  const submit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const original = person;
      const newPerson = await peopleApi.split(person.id, {
        face_detection_ids: Array.from(selected),
        new_display_name: newName.trim(),
      });
      trackPeopleEvent("split.completed", { face_count: selectedCount });
      onSplit(original, newPerson);
      onClose();
    } catch (err) {
      setError((err as Error)?.message || t("error.generic"));
      void mutate();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={submitting ? () => {} : onClose}
      title={t("split.title")}
      size="lg"
    >
      <p className="text-sm text-[var(--color-neutral-700)] mb-3">
        {t("split.body")}
      </p>

      <div className="flex items-center justify-between mb-2 text-xs">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={selectAll}
            className="text-[var(--color-primary)] hover:underline"
          >
            Select all
          </button>
          <span className="text-[var(--color-neutral-300)]">·</span>
          <button
            type="button"
            onClick={clearSelection}
            className="text-[var(--color-primary)] hover:underline"
          >
            Clear
          </button>
        </div>
        <span
          data-testid="split-selected-count"
          className="text-[var(--color-neutral-600)]"
        >
          {selectedCount === 1
            ? t("split.selectedCount", { count: selectedCount })
            : t("split.selectedCountPlural", { count: selectedCount })}
        </span>
      </div>

      {isLoading ? (
        <Skeleton variant="text" count={3} />
      ) : facesError ? (
        <ErrorBanner message={t("error.generic")} />
      ) : total === 0 ? (
        <p className="text-sm text-[var(--color-neutral-500)] text-center py-6">
          This person has no faces to split.
        </p>
      ) : (
        <div
          role="grid"
          aria-label="Person faces"
          className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 gap-2 max-h-[320px] overflow-y-auto p-1"
          data-testid="split-face-grid"
        >
          {faces.map((f, idx) => {
            const isSelected = selected.has(f.face_detection_id);
            return (
              <button
                key={f.face_detection_id}
                type="button"
                role="gridcell"
                aria-selected={isSelected}
                aria-label={`Face ${idx + 1} of ${total}, ${
                  isSelected ? "selected" : "not selected"
                }`}
                onClick={() => toggle(f.face_detection_id)}
                onKeyDown={(e) => {
                  if (e.key === " " || e.key === "Enter") {
                    e.preventDefault();
                    toggle(f.face_detection_id);
                  }
                }}
                className={[
                  "relative aspect-square rounded-[var(--radius-md)] overflow-hidden bg-[var(--color-neutral-100)]",
                  "outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary-light)]",
                  isSelected
                    ? "ring-2 ring-[var(--color-primary)]"
                    : "ring-1 ring-[var(--color-neutral-200)]",
                ].join(" ")}
              >
                <img
                  src={f.thumbnail_url}
                  alt=""
                  className="w-full h-full object-cover"
                  loading="lazy"
                />
                {isSelected && (
                  <span
                    aria-hidden="true"
                    className="absolute top-1 right-1 w-5 h-5 rounded-full bg-[var(--color-primary)] text-white text-xs flex items-center justify-center"
                  >
                    ✓
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}

      {wouldEmptyOriginal && (
        <p className="mt-2 text-xs text-[var(--color-warning)]">
          Leave at least one face with the original person.
        </p>
      )}

      <div className="mt-4">
        <label
          htmlFor="split-new-name"
          className="block text-xs text-[var(--color-neutral-600)] mb-1"
        >
          {t("split.newNameLabel")}
        </label>
        <input
          id="split-new-name"
          type="text"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="e.g. Alice's coworker"
          className="w-full border border-[var(--color-neutral-300)] rounded p-2 text-sm"
        />
      </div>

      {error && (
        <div className="mt-3">
          <ErrorBanner message={error} />
        </div>
      )}

      <div className="mt-4 flex items-center justify-between">
        <span className="text-xs text-[var(--color-neutral-500)]">
          Splitting from {person.display_name}
        </span>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            {t("split.cancelButton")}
          </Button>
          <Button
            variant="primary"
            loading={submitting}
            disabled={!canSubmit}
            onClick={() => void submit()}
          >
            {t("split.confirmButton")}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
