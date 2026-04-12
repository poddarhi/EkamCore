/**
 * Face clustering consent dialog (S11-004).
 *
 * Legal gate for the face pipeline. Presents the current consent text in
 * a scrollable container and requires the user to scroll to the bottom
 * before the Enable button becomes active (ART-07 §14.2, ART-15 §4 row 1).
 *
 * Behavior:
 *  1. On open: GET /api/v1/settings/face-clustering/consent → current
 *     text + version.
 *  2. Render text inside a scrollable <div role="region" aria-label=...>.
 *  3. Listen for scroll; when scrollTop + clientHeight >= scrollHeight - 20,
 *     set hasScrolledToBottom=true and enable the Enable button.
 *  4. On Enable: POST /consent with {accepted: true, version_acknowledged}.
 *     - 200 → onAccepted()
 *     - 409 CONSENT_VERSION_STALE → re-fetch text, re-render, reset scroll
 *     - other → inline ErrorBanner
 *  5. Focus trap via useFocusTrap from utils/a11y.
 *  6. Escape closes, UNLESS mid-submission (preventClose).
 *
 * Accessibility:
 *  - role=dialog, aria-modal, aria-label from Modal wrapper
 *  - aria-live region announces "ready to submit" when scrolled
 *  - disabled button retains 3:1 contrast (handled by design tokens)
 *  - respects prefers-reduced-motion via the design system
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { ScrollText } from "lucide-react";
import { ApiError, apiFetch } from "../../api/client";
import { Button, Modal } from "../../design-system/components";
import ErrorBanner from "../ErrorBanner";
import { useFocusTrap } from "../../utils/a11y";
import { t } from "../../i18n";

const CONSENT_ENDPOINT = "/api/v1/settings/face-clustering/consent";
const SCROLL_THRESHOLD_PX = 20;

interface ConsentStateResponse {
  accepted: boolean;
  version: string | null;
  granted_at: string | null;
  revoked_at: string | null;
  current_text_version: string;
  current_text: string;
}

interface ConsentGrantResponse {
  accepted: boolean;
  version: string;
  granted_at: string;
  current_text_version: string;
}

interface ConsentDialogProps {
  open: boolean;
  onClose: () => void;
  onAccepted: () => void;
}

type LoadState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "loaded"; text: string; version: string }
  | { status: "error"; message: string };

export default function ConsentDialog({
  open,
  onClose,
  onAccepted,
}: ConsentDialogProps) {
  const [loadState, setLoadState] = useState<LoadState>({ status: "idle" });
  const [hasScrolledToBottom, setHasScrolledToBottom] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const dialogBodyRef = useRef<HTMLDivElement>(null);

  // Focus trap while the dialog is open (and not mid-submit)
  useFocusTrap(dialogBodyRef, open);

  // ── Fetch consent text on open ────────────────────────────────────────
  const fetchConsent = useCallback(async () => {
    setLoadState({ status: "loading" });
    setHasScrolledToBottom(false);
    setSubmitError(null);
    try {
      const data = await apiFetch<ConsentStateResponse>(CONSENT_ENDPOINT);
      setLoadState({
        status: "loaded",
        text: data.current_text,
        version: data.current_text_version,
      });
    } catch (err) {
      setLoadState({
        status: "error",
        message: (err as ApiError).message ?? t("consent.dialog.loadError"),
      });
    }
  }, []);

  useEffect(() => {
    if (open) {
      fetchConsent();
    } else {
      // Reset state when closing so next open is clean
      setLoadState({ status: "idle" });
      setHasScrolledToBottom(false);
      setSubmitError(null);
    }
  }, [open, fetchConsent]);

  // Reset scroll position whenever new text loads
  useEffect(() => {
    if (loadState.status === "loaded" && scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = 0;
    }
  }, [loadState]);

  // ── Scroll-to-bottom detection ────────────────────────────────────────
  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    // clientHeight === 0 means the element hasn't been laid out yet
    // (jsdom or pre-paint). Don't treat an unlaid-out container as
    // "scrolled" — the user hasn't actually seen any text.
    if (el.clientHeight === 0) return;
    const remaining = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (remaining <= SCROLL_THRESHOLD_PX) {
      setHasScrolledToBottom(true);
    }
  }, []);

  // When text loads, check if it already fits in the container (no scroll
  // needed). If so, mark as scrolled immediately — short consent texts
  // mustn't lock users out.
  //
  // Guard: only trust the measurement when clientHeight > 0. In jsdom
  // (and before first paint in a real browser) scrollHeight and
  // clientHeight are both 0; "0 <= 20" would mislead us into enabling
  // the button before the user has seen any text.
  useEffect(() => {
    if (loadState.status !== "loaded") return;
    const el = scrollContainerRef.current;
    if (!el) return;
    if (
      el.clientHeight > 0 &&
      el.scrollHeight <= el.clientHeight + SCROLL_THRESHOLD_PX
    ) {
      setHasScrolledToBottom(true);
    }
  }, [loadState]);

  // ── Submit ─────────────────────────────────────────────────────────────
  const handleAccept = useCallback(async () => {
    if (loadState.status !== "loaded") return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      await apiFetch<ConsentGrantResponse>(CONSENT_ENDPOINT, {
        method: "POST",
        body: JSON.stringify({
          accepted: true,
          version_acknowledged: loadState.version,
        }),
      });
      onAccepted();
    } catch (err) {
      if (err instanceof ApiError && err.errorCode === "CONSENT_VERSION_STALE") {
        // Version changed between open and submit — re-fetch and re-prompt
        setSubmitError(t("consent.dialog.staleVersion"));
        await fetchConsent();
      } else {
        setSubmitError(
          (err as ApiError).message ?? t("consent.dialog.submitError"),
        );
      }
    } finally {
      setSubmitting(false);
    }
  }, [loadState, onAccepted, fetchConsent]);

  // Only prevent close while submitting — otherwise Escape and backdrop
  // click should cancel the flow.
  const preventClose = submitting;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t("consent.dialog.title")}
      size="lg"
      preventClose={preventClose}
    >
      <div ref={dialogBodyRef} className="space-y-[var(--space-4)]">
        {loadState.status === "loading" && (
          <div className="py-[var(--space-8)] text-center text-[var(--color-neutral-500)]">
            <ScrollText
              size={24}
              className="inline-block animate-pulse"
              aria-hidden="true"
            />
          </div>
        )}

        {loadState.status === "error" && (
          <ErrorBanner message={loadState.message} onRetry={fetchConsent} />
        )}

        {loadState.status === "loaded" && (
          <>
            {/* Scrollable consent text */}
            <div
              ref={scrollContainerRef}
              role="region"
              aria-label={t("consent.dialog.textAriaLabel")}
              tabIndex={0}
              onScroll={handleScroll}
              className={[
                "h-[320px] overflow-y-auto",
                "border border-[var(--color-neutral-200)] rounded-[var(--radius-md)]",
                "bg-[var(--color-neutral-50)] p-[var(--space-4)]",
                "text-[var(--text-small-size)] leading-[var(--text-small-height)] text-[var(--color-neutral-900)]",
                "whitespace-pre-wrap font-mono",
                "outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary-light)]",
              ].join(" ")}
            >
              {loadState.text}
            </div>

            {/* Version label */}
            <p className="text-[var(--text-caption-size)] leading-[var(--text-caption-height)] text-[var(--color-neutral-500)]">
              {t("consent.dialog.versionLabel", { version: loadState.version })}
            </p>

            {/* Scroll hint — visible until user reaches the bottom */}
            {!hasScrolledToBottom && (
              <p
                role="status"
                aria-live="polite"
                className="text-[var(--text-caption-size)] leading-[var(--text-caption-height)] text-[var(--color-warning)]"
              >
                {t("consent.dialog.scrollHint")}
              </p>
            )}

            {/* Submit error */}
            {submitError && (
              <ErrorBanner message={submitError} />
            )}

            {/* Actions */}
            <div className="flex items-center justify-end gap-[var(--space-3)] pt-[var(--space-2)]">
              <Button
                variant="secondary"
                onClick={onClose}
                disabled={submitting}
              >
                {t("consent.dialog.cancelButton")}
              </Button>
              <Button
                variant="primary"
                onClick={handleAccept}
                disabled={!hasScrolledToBottom || submitting}
                loading={submitting}
              >
                {t("consent.dialog.acceptButton")}
              </Button>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
