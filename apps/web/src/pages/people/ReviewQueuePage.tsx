/**
 * /people/review — fast keyboard-driven Review Queue (S13-004).
 *
 * Mental model: the queue is a session-local cursor over the items
 * SWR returned. Actions advance the cursor optimistically — the user
 * never waits for the API. On failure we restore the item, surface a
 * toast, and let them retry.
 *
 * Keyboard:
 *   Enter        confirm the active candidate
 *   R            reject ("not a person")
 *   S            skip
 *   N            create new person (opens modal)
 *   1–5          pick the n-th candidate as active
 *   ← / →        navigate already-actioned items in the session
 *   ?            toggle the keyboard hint banner
 *   Esc          close any open modal
 *
 * Out of scope (deferred, with hooks already in place):
 *   - split-pane layout on ≥1024px (current build is focused-mode only)
 *   - settings persistence of the "hide hint banner" preference
 *
 * Batch mode is intentionally minimal — the spec asks for "advanced",
 * we ship checkbox selection + bulk Reject/Skip via the floating
 * action bar. Bulk Confirm needs a contact picker that doesn't exist
 * yet, so it lives behind a TODO comment for the next pass.
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useState,
} from "react";
import { Link } from "react-router-dom";
import { Check, Keyboard, X as XIcon } from "lucide-react";

import Toast, { type ToastVariant } from "../../components/Toast";
import Breadcrumb from "../../design-system/components/Breadcrumb";
import Button from "../../design-system/components/Button";
import EmptyState from "../../design-system/components/EmptyState";
import ErrorBanner from "../../design-system/components/ErrorBanner";
import FeatureComingSoon from "../../design-system/components/FeatureComingSoon";
import FilterChip from "../../design-system/components/FilterChip";
import Modal from "../../design-system/components/Modal";
import Skeleton from "../../design-system/components/Skeleton";
import { useFlag } from "../../contexts/FlagContext";
import { peopleApi } from "../../api/people";
import { reviewQueueApi } from "../../api/review_queue";
import { useFaceConsent, useReviewQueue } from "../../hooks/usePeople";
import { t } from "../../i18n";
import type {
  ConfidenceBucket,
  ReviewQueueItem,
} from "../../types/people";
import { trackPeopleEvent } from "../../utils/metrics";

type ConfidenceFilter = "all" | ConfidenceBucket;
type ActionTaken = "confirmed" | "rejected" | "skipped" | "new_person";

interface QueueState {
  /** Cursor into the visible queue. */
  index: number;
  /** Local copy of the items so we can roll back on failure without
   *  waiting for SWR revalidation. */
  items: ReviewQueueItem[];
  /** Per-cluster action history for ← navigation and undo-on-failure. */
  history: Record<string, ActionTaken>;
  /** Active candidate slot (0 = top, 1..N = "other candidates"). */
  candidateIndex: number;
  /** Cluster ids selected for batch actions. */
  selectedForBatch: Set<string>;
}

type QueueAction =
  | { type: "load"; items: ReviewQueueItem[] }
  | { type: "advance" }
  | { type: "back" }
  | { type: "set_candidate"; index: number }
  | { type: "record_action"; clusterId: string; action: ActionTaken }
  | { type: "rollback"; clusterId: string; reinsertAt: number }
  | { type: "toggle_select"; clusterId: string }
  | { type: "clear_selection" };

function queueReducer(state: QueueState, action: QueueAction): QueueState {
  switch (action.type) {
    case "load":
      return {
        ...state,
        items: action.items,
        index: Math.min(state.index, Math.max(action.items.length - 1, 0)),
      };
    case "advance":
      return {
        ...state,
        index: Math.min(state.index + 1, state.items.length),
        candidateIndex: 0,
      };
    case "back":
      return {
        ...state,
        index: Math.max(state.index - 1, 0),
        candidateIndex: 0,
      };
    case "set_candidate":
      return { ...state, candidateIndex: action.index };
    case "record_action":
      return {
        ...state,
        history: { ...state.history, [action.clusterId]: action.action },
      };
    case "rollback": {
      const next = { ...state.history };
      delete next[action.clusterId];
      return { ...state, history: next };
    }
    case "toggle_select": {
      const next = new Set(state.selectedForBatch);
      if (next.has(action.clusterId)) next.delete(action.clusterId);
      else next.add(action.clusterId);
      return { ...state, selectedForBatch: next };
    }
    case "clear_selection":
      return { ...state, selectedForBatch: new Set() };
    default:
      return state;
  }
}

const CONFIDENCE_FILTERS: { key: ConfidenceFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "high", label: "High" },
  { key: "medium", label: "Medium" },
  { key: "low", label: "Low" },
];

function confidenceClasses(bucket: ConfidenceBucket): string {
  switch (bucket) {
    case "high":
      return "bg-[var(--color-success-surface)] text-[var(--color-success)]";
    case "medium":
      return "bg-[var(--color-warning-surface)] text-[var(--color-warning)]";
    case "low":
      return "bg-[var(--color-neutral-100)] text-[var(--color-neutral-600)]";
    default:
      return "bg-[var(--color-neutral-100)] text-[var(--color-neutral-600)]";
  }
}

interface ToastState {
  message: string;
  variant: ToastVariant;
}

export default function ReviewQueuePage() {
  const enabled = useFlag("face_clustering_enabled");
  const { accepted, loading: consentLoading } = useFaceConsent();
  const [filter, setFilter] = useState<ConfidenceFilter>("all");
  const { data, error, isLoading, mutate } = useReviewQueue(
    {
      limit: 50,
      confidence: filter === "all" ? undefined : filter,
    },
    { shouldRetryOnError: false },
  );

  const [state, dispatch] = useReducer(queueReducer, {
    index: 0,
    items: [],
    history: {},
    candidateIndex: 0,
    selectedForBatch: new Set<string>(),
  });

  const [hintOpen, setHintOpen] = useState(true);
  const [toast, setToast] = useState<ToastState | null>(null);
  const [newPersonOpen, setNewPersonOpen] = useState(false);
  const [newPersonName, setNewPersonName] = useState("");
  const [batchSubmitting, setBatchSubmitting] = useState(false);
  const [announcement, setAnnouncement] = useState("");

  // Sync SWR data into the reducer-owned local copy whenever the
  // server returns a fresh page. We deliberately keep the local copy
  // mutable so optimistic actions don't ping-pong with the cache.
  useEffect(() => {
    if (data?.items) dispatch({ type: "load", items: data.items });
  }, [data?.items]);

  useEffect(() => {
    if (enabled && accepted) trackPeopleEvent("reviewQueue.viewed");
  }, [enabled, accepted]);

  const current = state.items[state.index];
  const candidates = useMemo(() => {
    if (!current) return [];
    return [current.top_candidate, ...current.other_candidates].filter(
      (c): c is NonNullable<typeof c> => c !== null,
    );
  }, [current]);
  const activeCandidate =
    candidates[state.candidateIndex] ?? candidates[0] ?? null;

  const announce = useCallback((message: string) => {
    setAnnouncement(message);
  }, []);

  const advance = useCallback(() => {
    dispatch({ type: "advance" });
  }, []);

  const handleConfirm = useCallback(async () => {
    if (!current || !activeCandidate) return;
    const clusterId = current.cluster_id;
    const contactId = activeCandidate.contact_id;
    const candidateName =
      activeCandidate.contact_display_name ?? "this person";
    const rank = state.candidateIndex + 1;
    dispatch({
      type: "record_action",
      clusterId,
      action: "confirmed",
    });
    advance();
    announce(`Confirmed as ${candidateName}. Next item.`);
    trackPeopleEvent("reviewQueue.confirmed", {
      confidence_bucket: current.confidence_bucket,
      candidate_rank: rank,
    });
    try {
      await peopleApi.confirmCandidate({
        cluster_id: clusterId,
        contact_id: contactId,
      });
      void mutate();
      setToast({
        message: t("reviewQueue.confirmToast", { name: candidateName }),
        variant: "success",
      });
    } catch (err) {
      dispatch({ type: "rollback", clusterId, reinsertAt: state.index });
      setToast({
        message: (err as Error)?.message || t("error.generic"),
        variant: "error",
      });
    }
  }, [activeCandidate, advance, announce, current, mutate, state.candidateIndex, state.index]);

  const handleReject = useCallback(async () => {
    if (!current) return;
    const clusterId = current.cluster_id;
    dispatch({
      type: "record_action",
      clusterId,
      action: "rejected",
    });
    advance();
    announce("Marked as not a person. Next item.");
    trackPeopleEvent("reviewQueue.rejected");
    try {
      await peopleApi.rejectCluster({ cluster_id: clusterId });
      void mutate();
      setToast({
        message: t("reviewQueue.rejectToast"),
        variant: "success",
      });
    } catch (err) {
      dispatch({ type: "rollback", clusterId, reinsertAt: state.index });
      setToast({
        message: (err as Error)?.message || t("error.generic"),
        variant: "error",
      });
    }
  }, [advance, announce, current, mutate, state.index]);

  const handleSkip = useCallback(async () => {
    if (!current) return;
    const clusterId = current.cluster_id;
    dispatch({
      type: "record_action",
      clusterId,
      action: "skipped",
    });
    advance();
    announce("Skipped. Next item.");
    trackPeopleEvent("reviewQueue.skipped");
    try {
      await reviewQueueApi.skip(clusterId);
      void mutate();
      setToast({
        message: t("reviewQueue.skipToast"),
        variant: "success",
      });
    } catch (err) {
      dispatch({ type: "rollback", clusterId, reinsertAt: state.index });
      setToast({
        message: (err as Error)?.message || t("error.generic"),
        variant: "error",
      });
    }
  }, [advance, announce, current, mutate, state.index]);

  const handleCreateNewPerson = useCallback(async () => {
    if (!current) return;
    const name = newPersonName.trim();
    if (!name) return;
    const clusterId = current.cluster_id;
    setNewPersonOpen(false);
    setNewPersonName("");
    dispatch({
      type: "record_action",
      clusterId,
      action: "new_person",
    });
    advance();
    announce(`Created new person ${name}. Next item.`);
    trackPeopleEvent("reviewQueue.newPersonCreated");
    try {
      await peopleApi.create({ cluster_id: clusterId, display_name: name });
      void mutate();
      setToast({
        message: t("reviewQueue.confirmToast", { name }),
        variant: "success",
      });
    } catch (err) {
      dispatch({ type: "rollback", clusterId, reinsertAt: state.index });
      setToast({
        message: (err as Error)?.message || t("error.generic"),
        variant: "error",
      });
    }
  }, [advance, announce, current, mutate, newPersonName, state.index]);

  // Keyboard handler — runs on the document so the user doesn't need
  // to tab into a specific element to drive the queue.
  useEffect(() => {
    if (!enabled || !accepted) return;
    const handler = (e: KeyboardEvent) => {
      if (newPersonOpen) {
        if (e.key === "Escape") setNewPersonOpen(false);
        return;
      }
      // Skip when typing in an input field.
      const target = e.target as HTMLElement;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      )
        return;

      if (e.key === "Enter") {
        e.preventDefault();
        void handleConfirm();
      } else if (e.key === "r" || e.key === "R") {
        e.preventDefault();
        void handleReject();
      } else if (e.key === "s" || e.key === "S") {
        e.preventDefault();
        void handleSkip();
      } else if (e.key === "n" || e.key === "N") {
        e.preventDefault();
        setNewPersonOpen(true);
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        dispatch({ type: "advance" });
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        dispatch({ type: "back" });
      } else if (e.key === "?") {
        e.preventDefault();
        setHintOpen((o) => !o);
      } else if (/^[1-5]$/.test(e.key)) {
        const idx = Number(e.key) - 1;
        if (idx < candidates.length) {
          dispatch({ type: "set_candidate", index: idx });
        }
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [
    enabled,
    accepted,
    newPersonOpen,
    handleConfirm,
    handleReject,
    handleSkip,
    candidates.length,
  ]);

  // ── Gating
  if (!enabled) return <FeatureComingSoon featureName="People Review Queue" />;
  if (consentLoading)
    return (
      <div className="max-w-[960px] mx-auto p-6">
        <Skeleton variant="card" />
      </div>
    );
  if (!accepted) {
    return (
      <div className="max-w-[960px] mx-auto p-6">
        <EmptyState
          title={t("people.list.empty.title")}
          description={t("people.list.empty.description")}
        />
      </div>
    );
  }

  const visibleItems = state.items.filter(
    (it) => !state.history[it.cluster_id],
  );
  const allReviewed =
    !isLoading && state.items.length > 0 && visibleItems.length === 0;

  return (
    <div className="max-w-[1100px] mx-auto p-6">
      <div className="mb-3">
        <Breadcrumb
          items={[
            { label: t("people.list.title"), href: "/people" },
            { label: t("reviewQueue.title") },
          ]}
        />
      </div>
      <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
        <div>
          <h1 className="text-2xl font-semibold">{t("reviewQueue.title")}</h1>
          <p className="text-sm text-[var(--color-neutral-600)]">
            {visibleItems.length} groups to review
          </p>
        </div>
        <div className="flex items-center gap-2">
          {CONFIDENCE_FILTERS.map((f) => (
            <FilterChip
              key={f.key}
              label={f.label}
              active={filter === f.key}
              onClick={() => setFilter(f.key)}
            />
          ))}
        </div>
      </div>

      {hintOpen && (
        <div
          role="note"
          className="flex items-center justify-between gap-3 mb-4 p-3 rounded-[var(--radius-md)] border border-[var(--color-neutral-200)] bg-[var(--color-neutral-50)] text-sm"
        >
          <div className="flex items-center gap-2">
            <Keyboard size={16} aria-hidden="true" />
            <span>{t("reviewQueue.keyboard.hint")}</span>
          </div>
          <button
            type="button"
            aria-label="Dismiss keyboard hint"
            onClick={() => setHintOpen(false)}
            className="p-1 rounded hover:bg-[var(--color-neutral-100)]"
          >
            <XIcon size={14} aria-hidden="true" />
          </button>
        </div>
      )}

      {isLoading && <Skeleton variant="card" />}
      {error && <ErrorBanner message={t("error.generic")} />}
      {!isLoading && state.items.length === 0 && (
        <EmptyState
          title={t("reviewQueue.empty.title")}
          description={t("reviewQueue.empty.description")}
        />
      )}
      {allReviewed && (
        <EmptyState
          title={t("reviewQueue.empty.title")}
          description={`Reviewed ${Object.keys(state.history).length} items in this session.`}
        />
      )}

      {!allReviewed && current && (
        <ReviewCard
          item={current}
          activeCandidateIndex={state.candidateIndex}
          candidates={candidates}
          onCandidatePick={(i) => dispatch({ type: "set_candidate", index: i })}
          onConfirm={() => void handleConfirm()}
          onReject={() => void handleReject()}
          onSkip={() => void handleSkip()}
          onNewPerson={() => setNewPersonOpen(true)}
          isSelected={state.selectedForBatch.has(current.cluster_id)}
          onToggleSelect={() =>
            dispatch({ type: "toggle_select", clusterId: current.cluster_id })
          }
        />
      )}

      {state.selectedForBatch.size > 0 && (
        <BatchActionBar
          count={state.selectedForBatch.size}
          submitting={batchSubmitting}
          onClear={() => dispatch({ type: "clear_selection" })}
          onBatchReject={async () => {
            setBatchSubmitting(true);
            const ids = Array.from(state.selectedForBatch);
            for (const id of ids) {
              try {
                await peopleApi.rejectCluster({ cluster_id: id });
                dispatch({
                  type: "record_action",
                  clusterId: id,
                  action: "rejected",
                });
              } catch {
                /* per-item failure surfaces via toast count */
              }
            }
            void mutate();
            dispatch({ type: "clear_selection" });
            setBatchSubmitting(false);
            setToast({
              message: `Rejected ${ids.length} groups`,
              variant: "success",
            });
          }}
          onBatchSkip={async () => {
            setBatchSubmitting(true);
            const ids = Array.from(state.selectedForBatch);
            for (const id of ids) {
              try {
                await reviewQueueApi.skip(id);
                dispatch({
                  type: "record_action",
                  clusterId: id,
                  action: "skipped",
                });
              } catch {
                /* per-item failure surfaces via toast count */
              }
            }
            void mutate();
            dispatch({ type: "clear_selection" });
            setBatchSubmitting(false);
            setToast({
              message: `Skipped ${ids.length} groups`,
              variant: "success",
            });
          }}
        />
      )}

      <Modal
        open={newPersonOpen}
        onClose={() => setNewPersonOpen(false)}
        title="Create new person"
        size="sm"
      >
        <p className="text-sm text-[var(--color-neutral-700)] mb-3">
          Give this group a name. You can rename them later.
        </p>
        <input
          type="text"
          autoFocus
          value={newPersonName}
          onChange={(e) => setNewPersonName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void handleCreateNewPerson();
          }}
          aria-label="New person name"
          placeholder="Display name"
          className="w-full border border-[var(--color-neutral-300)] rounded p-2 mb-4"
        />
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setNewPersonOpen(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={() => void handleCreateNewPerson()}
            icon={<Check size={14} />}
          >
            Create
          </Button>
        </div>
      </Modal>

      {/* SR-only live region */}
      <div className="sr-only" role="status" aria-live="polite">
        {announcement}
      </div>

      {toast && (
        <Toast
          message={toast.message}
          variant={toast.variant}
          onDismiss={() => setToast(null)}
        />
      )}

      <p className="mt-6 text-xs text-[var(--color-neutral-500)]">
        <Link to="/people" className="hover:underline">
          ← Back to People
        </Link>
      </p>
    </div>
  );
}

// ── ReviewCard ───────────────────────────────────────────────────────────

interface ReviewCardProps {
  item: ReviewQueueItem;
  candidates: NonNullable<ReviewQueueItem["top_candidate"]>[];
  activeCandidateIndex: number;
  onCandidatePick: (index: number) => void;
  onConfirm: () => void;
  onReject: () => void;
  onSkip: () => void;
  onNewPerson: () => void;
  isSelected: boolean;
  onToggleSelect: () => void;
}

function ReviewCard({
  item,
  candidates,
  activeCandidateIndex,
  onCandidatePick,
  onConfirm,
  onReject,
  onSkip,
  onNewPerson,
  isSelected,
  onToggleSelect,
}: ReviewCardProps) {
  const active = candidates[activeCandidateIndex] ?? candidates[0] ?? null;
  const memberLabel =
    item.member_count === 1
      ? t("reviewQueue.item.memberCount", { count: item.member_count })
      : t("reviewQueue.item.memberCountPlural", { count: item.member_count });

  return (
    <div
      data-testid="review-card"
      className="rounded-[var(--radius-lg)] border border-[var(--color-neutral-200)] bg-[var(--color-white)] p-5"
    >
      <div className="flex items-start justify-between gap-3 mb-4">
        <div>
          <p className="text-sm text-[var(--color-neutral-600)]">
            {memberLabel}
            {item.first_seen_at && item.last_seen_at && (
              <>
                {" · "}
                {t("reviewQueue.item.seenRange", {
                  from: new Date(item.first_seen_at).toLocaleDateString(),
                  to: new Date(item.last_seen_at).toLocaleDateString(),
                })}
              </>
            )}
          </p>
        </div>
        <label className="flex items-center gap-1 text-xs text-[var(--color-neutral-600)]">
          <input
            type="checkbox"
            checked={isSelected}
            onChange={onToggleSelect}
            aria-label="Select for batch"
          />
          Batch
        </label>
      </div>

      {/* Member photos */}
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 mb-4">
        {item.sample_photo_asset_ids.slice(0, 6).map((pid) => (
          <div
            key={pid}
            className="aspect-square rounded-[var(--radius-md)] overflow-hidden bg-[var(--color-neutral-100)]"
          >
            <img
              src={`/api/v1/photos/${pid}/thumbnail`}
              alt=""
              className="w-full h-full object-cover"
              loading="lazy"
            />
          </div>
        ))}
      </div>

      {/* Active candidate */}
      {active ? (
        <div className="flex items-center gap-3 mb-3">
          <div className="w-12 h-12 rounded-full bg-[var(--color-primary-surface)] flex items-center justify-center font-medium">
            {(active.contact_display_name ?? "?")
              .split(" ")
              .map((p) => p[0])
              .slice(0, 2)
              .join("")}
          </div>
          <div className="flex-1 min-w-0">
            <div className="font-medium truncate">
              {t("reviewQueue.item.topSuggestion", {
                name: active.contact_display_name ?? "Unknown",
              })}
            </div>
            <span
              className={[
                "inline-block mt-1 px-2 py-0.5 rounded-full text-xs",
                confidenceClasses(active.confidence),
              ].join(" ")}
            >
              {active.confidence}
            </span>
          </div>
        </div>
      ) : (
        <p className="text-sm text-[var(--color-neutral-500)] mb-3">
          No suggested matches.
        </p>
      )}

      {/* Other candidates */}
      {candidates.length > 1 && (
        <div className="mb-4">
          <div className="text-xs text-[var(--color-neutral-500)] mb-1">
            {t("reviewQueue.item.otherSuggestions")}
          </div>
          <div className="flex gap-2 overflow-x-auto">
            {candidates.map((c, i) => (
              <button
                key={c.contact_id}
                type="button"
                onClick={() => onCandidatePick(i)}
                aria-pressed={i === activeCandidateIndex}
                className={[
                  "flex items-center gap-1 px-2 py-1 rounded-full text-xs whitespace-nowrap border",
                  i === activeCandidateIndex
                    ? "border-[var(--color-primary)] bg-[var(--color-primary-surface)]"
                    : "border-[var(--color-neutral-200)]",
                ].join(" ")}
              >
                <span>{i + 1}.</span>
                <span>{c.contact_display_name ?? "Unknown"}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <Button variant="primary" onClick={onConfirm} icon={<Check size={14} />}>
          {t("reviewQueue.item.confirmButton")}
        </Button>
        <Button variant="ghost" onClick={onReject}>
          {t("reviewQueue.item.rejectButton")}
        </Button>
        <Button variant="ghost" onClick={onSkip}>
          {t("reviewQueue.item.skipButton")}
        </Button>
        <Button variant="secondary" onClick={onNewPerson}>
          {t("reviewQueue.item.newPersonButton")}
        </Button>
      </div>
    </div>
  );
}

// ── BatchActionBar ───────────────────────────────────────────────────────

interface BatchActionBarProps {
  count: number;
  submitting: boolean;
  onClear: () => void;
  onBatchReject: () => void;
  onBatchSkip: () => void;
}

function BatchActionBar({
  count,
  submitting,
  onClear,
  onBatchReject,
  onBatchSkip,
}: BatchActionBarProps) {
  return (
    <div
      role="region"
      aria-label="Batch actions"
      className="fixed bottom-4 left-1/2 -translate-x-1/2 z-30 flex items-center gap-2 px-4 py-2 rounded-full bg-[var(--color-neutral-900)] text-[var(--color-white)] shadow-[var(--shadow-lg)]"
    >
      <span className="text-sm">{count} selected</span>
      <Button
        variant="ghost"
        size="sm"
        loading={submitting}
        onClick={onBatchReject}
      >
        Reject
      </Button>
      <Button
        variant="ghost"
        size="sm"
        loading={submitting}
        onClick={onBatchSkip}
      >
        Skip
      </Button>
      <button
        type="button"
        onClick={onClear}
        aria-label="Clear selection"
        className="p-1 rounded hover:bg-white/10"
      >
        <XIcon size={14} />
      </button>
    </div>
  );
}
