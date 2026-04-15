/**
 * MergePersonsModal — pick a keeper and merge N trusted persons into one (S13-005).
 *
 * Two entry points feed this modal:
 *   - PersonDetailPage's kebab "Merge with…" passes [currentPerson.id]
 *     and the user uses the typeahead to add at least one more.
 *   - PeopleListPage's multi-select bar passes every selected id at
 *     once, so the typeahead is optional.
 *
 * The component is responsible for:
 *   - Resolving each id to a full TrustedPerson (uses the optional
 *     ``initialPersons`` cache from the parent if present, otherwise
 *     fetches via peopleApi.get to keep the prop surface narrow).
 *   - Letting the user pick a keeper via radio.
 *   - Letting the user grow the working list via search typeahead.
 *   - Calling peopleApi.merge with optimistic disable, surfacing the
 *     server error inline on failure.
 *
 * On success the parent decides what to do — typically refresh its
 * cache and toast — via the ``onMerged`` callback.
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import Modal from "../../design-system/components/Modal";
import Button from "../../design-system/components/Button";
import ErrorBanner from "../../design-system/components/ErrorBanner";
import Skeleton from "../../design-system/components/Skeleton";
import PersonAvatar from "./PersonAvatar";
import { peopleApi } from "../../api/people";
import { usePeopleList } from "../../hooks/usePeople";
import { t } from "../../i18n";
import type { TrustedPerson } from "../../types/people";
import { trackPeopleEvent } from "../../utils/metrics";

export interface MergePersonsModalProps {
  open: boolean;
  onClose: () => void;
  initialPersonIds: string[];
  /** Optional pre-populated person objects so the modal can render
   *  without an extra round-trip when the parent already has them. */
  initialPersons?: TrustedPerson[];
  onMerged: (keeper: TrustedPerson) => void;
}

function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
}

export default function MergePersonsModal({
  open,
  onClose,
  initialPersonIds,
  initialPersons = [],
  onMerged,
}: MergePersonsModalProps) {
  const [persons, setPersons] = useState<TrustedPerson[]>(initialPersons);
  const [keeperId, setKeeperId] = useState<string | null>(null);
  const [resolving, setResolving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [searchInput, setSearchInput] = useState("");
  const search = useDebounced(searchInput, 250);

  const seedRef = useRef<string>("");

  // Resolve any ids that the parent didn't pre-populate.
  useEffect(() => {
    if (!open) return;
    const cacheKey = initialPersonIds.join(",");
    if (cacheKey === seedRef.current) return;
    seedRef.current = cacheKey;

    setError(null);
    setKeeperId(null);
    setSearchInput("");

    const known = new Map(initialPersons.map((p) => [p.id, p]));
    const seeded = initialPersonIds
      .map((id) => known.get(id))
      .filter((p): p is TrustedPerson => !!p);
    setPersons(seeded);

    const missing = initialPersonIds.filter((id) => !known.has(id));
    if (missing.length === 0) return;

    setResolving(true);
    Promise.all(missing.map((id) => peopleApi.get(id).catch(() => null)))
      .then((rows) => {
        const fresh = rows.filter((r): r is TrustedPerson => !!r);
        setPersons((prev) => {
          const byId = new Map(prev.map((p) => [p.id, p]));
          for (const r of fresh) byId.set(r.id, r);
          // Preserve original order of initialPersonIds.
          return initialPersonIds
            .map((id) => byId.get(id))
            .filter((p): p is TrustedPerson => !!p);
        });
      })
      .finally(() => setResolving(false));
  }, [open, initialPersonIds, initialPersons]);

  // Reset transient state when the modal closes.
  useEffect(() => {
    if (open) return;
    seedRef.current = "";
    setError(null);
    setSubmitting(false);
    setKeeperId(null);
    setSearchInput("");
  }, [open]);

  const { data: searchData } = usePeopleList(
    { limit: 10, search: search || undefined },
    { shouldRetryOnError: false },
  );

  const candidatesToAdd = useMemo(() => {
    const existing = new Set(persons.map((p) => p.id));
    return (searchData?.items ?? []).filter((p) => !existing.has(p.id));
  }, [persons, searchData]);

  const addPerson = useCallback((person: TrustedPerson) => {
    setPersons((prev) => {
      if (prev.some((p) => p.id === person.id)) return prev;
      return [...prev, person];
    });
    setSearchInput("");
  }, []);

  const removePerson = useCallback(
    (id: string) => {
      setPersons((prev) => prev.filter((p) => p.id !== id));
      if (keeperId === id) setKeeperId(null);
    },
    [keeperId],
  );

  const canMerge = persons.length >= 2 && keeperId !== null && !submitting;

  const submit = useCallback(async () => {
    if (!canMerge || !keeperId) return;
    setSubmitting(true);
    setError(null);
    try {
      const keeper = await peopleApi.merge({
        person_ids: persons.map((p) => p.id),
        keeper_id: keeperId,
      });
      trackPeopleEvent("merge.completed", {
        merged_count: persons.length,
      });
      onMerged(keeper);
      onClose();
    } catch (err) {
      setError((err as Error)?.message || t("error.generic"));
    } finally {
      setSubmitting(false);
    }
  }, [canMerge, keeperId, onClose, onMerged, persons]);

  return (
    <Modal
      open={open}
      onClose={submitting ? () => {} : onClose}
      title={t("merge.title")}
      size="md"
    >
      <p className="text-sm text-[var(--color-neutral-700)] mb-4">
        {t("merge.body")}
      </p>

      {/* Working list */}
      {resolving && persons.length === 0 ? (
        <Skeleton variant="text" count={3} />
      ) : (
        <ul
          className="space-y-2 mb-4"
          role="radiogroup"
          aria-label="Choose the keeper"
          data-testid="merge-person-list"
        >
          {persons.map((p) => {
            const selected = p.id === keeperId;
            return (
              <li key={p.id}>
                <label
                  className={[
                    "flex items-center gap-3 p-3 rounded-[var(--radius-md)] border cursor-pointer",
                    selected
                      ? "border-[var(--color-primary)] bg-[var(--color-primary-surface)]"
                      : "border-[var(--color-neutral-200)] hover:bg-[var(--color-neutral-50)]",
                  ].join(" ")}
                >
                  <input
                    type="radio"
                    name="merge-keeper"
                    checked={selected}
                    onChange={() => setKeeperId(p.id)}
                    aria-label={`Keep ${p.display_name} as the merged person`}
                  />
                  <PersonAvatar person={p} size="lg" />
                  <div className="flex-1 min-w-0">
                    <div className="font-medium truncate">
                      {p.display_name}
                    </div>
                    {typeof p.face_count === "number" && (
                      <div className="text-xs text-[var(--color-neutral-500)]">
                        {p.face_count === 1
                          ? t("people.list.faceCount", {
                              count: p.face_count,
                            })
                          : t("people.list.faceCountPlural", {
                              count: p.face_count,
                            })}
                      </div>
                    )}
                  </div>
                  {persons.length > 1 && (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.preventDefault();
                        removePerson(p.id);
                      }}
                      aria-label={`Remove ${p.display_name}`}
                      className="text-xs text-[var(--color-neutral-500)] hover:text-[var(--color-neutral-700)]"
                    >
                      Remove
                    </button>
                  )}
                </label>
              </li>
            );
          })}
        </ul>
      )}

      {/* Add more typeahead */}
      <div className="mb-4">
        <label className="block text-xs text-[var(--color-neutral-600)] mb-1">
          Add another person
        </label>
        <input
          type="search"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder="Search by name…"
          aria-label="Search persons to add"
          className="w-full border border-[var(--color-neutral-300)] rounded p-2 text-sm"
        />
        {candidatesToAdd.length > 0 && (
          <ul
            className="mt-2 max-h-40 overflow-y-auto border border-[var(--color-neutral-200)] rounded-[var(--radius-md)] divide-y divide-[var(--color-neutral-100)]"
            data-testid="merge-add-results"
          >
            {candidatesToAdd.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  onClick={() => addPerson(p)}
                  className="w-full flex items-center gap-2 px-3 py-2 text-left text-sm hover:bg-[var(--color-neutral-50)]"
                >
                  <PersonAvatar person={p} size="sm" />
                  <span className="truncate">{p.display_name}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {persons.length < 2 && (
        <p className="text-xs text-[var(--color-neutral-500)] mb-3">
          Add at least one more person to merge.
        </p>
      )}

      {error && (
        <div className="mb-3">
          <ErrorBanner message={error} />
        </div>
      )}

      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose} disabled={submitting}>
          {t("merge.cancelButton")}
        </Button>
        <Button
          variant="primary"
          loading={submitting}
          disabled={!canMerge}
          onClick={() => void submit()}
        >
          {t("merge.confirmButton")} {persons.length} → 1
        </Button>
      </div>
    </Modal>
  );
}
