/**
 * Cmd/Ctrl+Z shortcut for People Graph pages (S13-007).
 *
 * Binds a document-level listener that triggers peopleApi.undoLast
 * for the current workspace's most recent non-undone operation. The
 * caller passes ``onToast`` so the hook can surface success/error
 * copy without owning toast state itself.
 *
 * Intentionally independent of the UndoDrawer — the two surfaces
 * serve different speeds. Power users hit Cmd+Z from anywhere; the
 * drawer is for reviewing and reaching into older operations.
 *
 * Safety: the listener skips when the user is typing in an input or
 * a contenteditable so it doesn't fight with the browser's text
 * undo stack. It also skips when Shift is held so a future "redo"
 * can claim that chord later.
 */

import { useEffect, useRef } from "react";
import { mutate as globalMutate } from "swr";

import { peopleApi } from "../api/people";
import { t } from "../i18n";
import { trackPeopleEvent } from "../utils/metrics";

type ToastVariant = "success" | "info" | "warning" | "error";

export interface UseUndoShortcutOptions {
  enabled: boolean;
  onToast?: (toast: { message: string; variant: ToastVariant }) => void;
}

export function useUndoShortcut({
  enabled,
  onToast,
}: UseUndoShortcutOptions) {
  // Ref so the effect can read the latest callback without
  // re-binding the event listener on every render.
  const onToastRef = useRef(onToast);
  onToastRef.current = onToast;

  useEffect(() => {
    if (!enabled) return;
    const handler = async (e: KeyboardEvent) => {
      const isUndo = (e.metaKey || e.ctrlKey) && !e.shiftKey && e.key === "z";
      if (!isUndo) return;
      const target = e.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      )
        return;
      e.preventDefault();
      try {
        const result = await peopleApi.undoLast();
        trackPeopleEvent("undo.triggered", {
          operation_type: result.operation_type,
        });
        await Promise.allSettled([
          globalMutate(
            (key) =>
              typeof key === "string" && key.startsWith("/api/v1/people"),
            undefined,
            { revalidate: true },
          ),
          globalMutate(
            (key) =>
              typeof key === "string" &&
              key.startsWith("/api/v1/review-queue"),
            undefined,
            { revalidate: true },
          ),
        ]);
        onToastRef.current?.({
          message: t("undo.successToast", {
            operation: result.operation_type,
          }),
          variant: "success",
        });
      } catch (err) {
        trackPeopleEvent("undo.failed", {
          reason: (err as { code?: string })?.code ?? "unknown",
        });
        onToastRef.current?.({
          message: t("undo.errorToast", {
            reason: (err as Error)?.message ?? t("error.generic"),
          }),
          variant: "error",
        });
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [enabled]);
}
