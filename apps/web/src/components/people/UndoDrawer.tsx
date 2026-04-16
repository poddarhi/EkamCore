/**
 * UndoDrawer — one-click undo for recent People Graph operations (S13-007).
 *
 * Right-side slide-out panel listing the last 50 person_operations
 * rows. Each row shows an icon, a one-line summary generated from
 * ``forward_payload``, a relative time, and an Undo button. Already
 * undone rows render as a disabled "Undone" label so the history
 * stays stable.
 *
 * The undo flow is optimistic: the clicked row flips to "Undoing…"
 * immediately and then revalidates both the operations list and the
 * people list on success. Failures restore the button state and
 * surface a toast via the ``onToast`` callback.
 *
 * Keyboard: Esc closes. The parent page is responsible for the
 * Cmd/Ctrl+Z global shortcut — that binding calls peopleApi.undoLast
 * directly and is intentionally drawer-independent so power users
 * can undo without opening anything.
 *
 * Layout is a simple right-side panel rather than a new design
 * system primitive — adding a Drawer component is out of scope for
 * this story.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { mutate as globalMutate } from "swr";
import {
  ArrowLeftRight,
  Check,
  History,
  Pencil,
  Scissors,
  Trash2,
  X as XIcon,
  XCircle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import Button from "../../design-system/components/Button";
import EmptyState from "../../design-system/components/EmptyState";
import ErrorBanner from "../../design-system/components/ErrorBanner";
import Skeleton from "../../design-system/components/Skeleton";
import { peopleApi } from "../../api/people";
import { usePersonOperations } from "../../hooks/usePeople";
import { t } from "../../i18n";
import type { PersonOperation, PersonOperationType } from "../../types/people";
import { trackPeopleEvent } from "../../utils/metrics";

export interface UndoDrawerProps {
  open: boolean;
  onClose: () => void;
  onToast?: (toast: {
    message: string;
    variant: "success" | "info" | "warning" | "error";
  }) => void;
}

const OP_ICONS: Record<PersonOperationType, LucideIcon> = {
  merge: ArrowLeftRight,
  split: Scissors,
  rename: Pencil,
  delete: Trash2,
  confirm: Check,
  reject: XCircle,
  detach_face: Scissors,
};

function summarize(op: PersonOperation): string {
  const p = op.forward_payload as Record<string, unknown>;
  switch (op.operation_type) {
    case "merge": {
      const count =
        typeof p.merged_count === "number"
          ? p.merged_count
          : Array.isArray(p.person_ids)
            ? (p.person_ids as unknown[]).length
            : 0;
      return `Merged ${count} people`;
    }
    case "split": {
      const moved =
        typeof p.moved_count === "number" ? p.moved_count : undefined;
      return moved
        ? `Split ${moved} faces into a new person`
        : "Split person";
    }
    case "rename": {
      const from = typeof p.old_display_name === "string" ? p.old_display_name : "";
      const to = typeof p.new_display_name === "string" ? p.new_display_name : "";
      return from && to ? `Renamed "${from}" to "${to}"` : "Renamed person";
    }
    case "delete":
      return "Deleted person";
    case "confirm":
      return "Confirmed cluster";
    case "reject":
      return "Rejected cluster";
    case "detach_face":
      return "Removed face from person";
    default:
      return op.operation_type;
  }
}

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const diffMs = then - Date.now();
  const absSec = Math.abs(diffMs / 1000);
  const fmt = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  if (absSec < 60) return fmt.format(Math.round(diffMs / 1000), "second");
  if (absSec < 3600) return fmt.format(Math.round(diffMs / 60000), "minute");
  if (absSec < 86400) return fmt.format(Math.round(diffMs / 3600000), "hour");
  return fmt.format(Math.round(diffMs / 86400000), "day");
}

/** Invalidate every SWR cache key that may have changed after an
 *  undo. We intentionally cast a wide net — undo can touch persons,
 *  clusters, graph edges, and the review queue counts. */
async function revalidatePeopleCaches() {
  await Promise.allSettled([
    globalMutate(
      (key) => typeof key === "string" && key.startsWith("/api/v1/people"),
      undefined,
      { revalidate: true },
    ),
    globalMutate(
      (key) =>
        typeof key === "string" && key.startsWith("/api/v1/review-queue"),
      undefined,
      { revalidate: true },
    ),
  ]);
}

export default function UndoDrawer({
  open,
  onClose,
  onToast,
}: UndoDrawerProps) {
  const { data, error, isLoading, mutate } = usePersonOperations(50, {
    shouldRetryOnError: false,
    revalidateOnFocus: false,
  });
  const [pending, setPending] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  const items = useMemo(() => data?.items ?? [], [data]);

  const handleUndo = useCallback(
    async (op: PersonOperation) => {
      if (op.undone_at) return;
      setPending((prev) => new Set(prev).add(op.id));
      trackPeopleEvent("undo.triggered", { operation_type: op.operation_type });
      try {
        await peopleApi.undoOperation(op.id);
        await mutate();
        await revalidatePeopleCaches();
        onToast?.({
          message: t("undo.successToast", { operation: summarize(op) }),
          variant: "success",
        });
      } catch (err) {
        const message = (err as Error)?.message || t("error.generic");
        const code = (err as { code?: string })?.code;
        trackPeopleEvent("undo.failed", { reason: code ?? "unknown" });
        if (code === "OPERATION_ALREADY_UNDONE") {
          // Someone else already undid it — just refresh the list.
          await mutate();
        }
        onToast?.({
          message: t("undo.errorToast", { reason: message }),
          variant: "error",
        });
      } finally {
        setPending((prev) => {
          const next = new Set(prev);
          next.delete(op.id);
          return next;
        });
      }
    },
    [mutate, onToast],
  );

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40">
      <div
        className="absolute inset-0 bg-black/30"
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="undo-drawer-title"
        data-testid="undo-drawer"
        className="absolute right-0 top-0 h-full w-full max-w-[420px] bg-[var(--color-white)] shadow-[var(--shadow-xl)] flex flex-col"
      >
        <header className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-neutral-200)]">
          <h2
            id="undo-drawer-title"
            className="flex items-center gap-2 font-semibold"
          >
            <History size={16} aria-hidden="true" />
            {t("undo.drawer.title")}
          </h2>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            className="p-1 rounded hover:bg-[var(--color-neutral-100)]"
          >
            <XIcon size={16} aria-hidden="true" />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto">
          {isLoading ? (
            <div className="p-4">
              <Skeleton variant="text" count={5} />
            </div>
          ) : error ? (
            <div className="p-4">
              <ErrorBanner message={t("error.generic")} />
            </div>
          ) : items.length === 0 ? (
            <EmptyState title={t("undo.drawer.empty")} />
          ) : (
            <ul
              className="divide-y divide-[var(--color-neutral-200)]"
              data-testid="undo-drawer-list"
            >
              {items.map((op) => {
                const Icon = OP_ICONS[op.operation_type] ?? History;
                const undone = op.undone_at !== null;
                const submitting = pending.has(op.id);
                return (
                  <li
                    key={op.id}
                    className="px-4 py-3 flex items-start gap-3"
                  >
                    <div className="mt-1 text-[var(--color-neutral-500)]">
                      <Icon size={16} aria-hidden="true" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm truncate">{summarize(op)}</div>
                      <div className="text-xs text-[var(--color-neutral-500)]">
                        {relativeTime(op.created_at)}
                      </div>
                    </div>
                    {undone ? (
                      <span className="text-xs text-[var(--color-neutral-400)]">
                        {t("undo.drawer.undoneLabel")}
                      </span>
                    ) : (
                      <Button
                        variant="ghost"
                        size="sm"
                        loading={submitting}
                        onClick={() => void handleUndo(op)}
                        aria-label={`Undo: ${summarize(op)}`}
                      >
                        {t("undo.drawer.undoButton")}
                      </Button>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </aside>
    </div>
  );
}
