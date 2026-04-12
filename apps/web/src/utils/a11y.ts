/**
 * Accessibility utilities (G-14 / ART-26).
 *
 * Provides runtime helpers for WCAG AA compliance:
 *   - announceToScreenReader: push a message to a global aria-live region
 *   - trapFocus: constrain Tab focus inside a container (for modals, drawers)
 *   - skipToContent: handler for "Skip to main content" links
 */

import { useEffect, type RefObject } from "react";

// ── Screen reader announcements ─────────────────────────────────────────────

const LIVE_REGION_ID = "ekamcore-a11y-live-region";

/**
 * Announce a message to assistive technologies via a polite aria-live region.
 *
 * Creates a singleton visually-hidden live region on first call.
 * Use for transient, non-urgent announcements (e.g. "Settings saved").
 *
 * For urgent errors, use `announceToScreenReader(msg, "assertive")`.
 */
export function announceToScreenReader(
  message: string,
  priority: "polite" | "assertive" = "polite",
): void {
  if (typeof document === "undefined") return;

  let region = document.getElementById(LIVE_REGION_ID);
  if (!region) {
    region = document.createElement("div");
    region.id = LIVE_REGION_ID;
    region.setAttribute("role", "status");
    region.setAttribute("aria-live", priority);
    region.setAttribute("aria-atomic", "true");
    // Visually hide but keep available to screen readers
    region.style.position = "absolute";
    region.style.left = "-10000px";
    region.style.top = "auto";
    region.style.width = "1px";
    region.style.height = "1px";
    region.style.overflow = "hidden";
    document.body.appendChild(region);
  } else {
    // Update aria-live if priority changed
    region.setAttribute("aria-live", priority);
  }

  // Clear then set: screen readers only announce on content change
  region.textContent = "";
  // Use rAF to ensure the clear is processed before the new content
  requestAnimationFrame(() => {
    if (region) region.textContent = message;
  });
}

// ── Focus trap ─────────────────────────────────────────────────────────────

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
  '[contenteditable="true"]',
].join(",");

/**
 * Constrain Tab/Shift+Tab focus navigation inside a container.
 *
 * Use via the `useFocusTrap` hook for automatic cleanup.
 * Call `trapFocus(ref)` imperatively if you need manual control.
 *
 * @returns A cleanup function to remove the trap.
 */
export function trapFocus(
  containerRef: RefObject<HTMLElement | null>,
): () => void {
  const container = containerRef.current;
  if (!container) return () => {};

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key !== "Tab") return;

    const focusable = Array.from(
      container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
    ).filter((el) => el.offsetParent !== null); // visible only

    if (focusable.length === 0) {
      e.preventDefault();
      return;
    }

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const active = document.activeElement as HTMLElement | null;

    if (e.shiftKey && active === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && active === last) {
      e.preventDefault();
      first.focus();
    }
  };

  container.addEventListener("keydown", handleKeyDown);
  return () => container.removeEventListener("keydown", handleKeyDown);
}

/**
 * React hook wrapper for {@link trapFocus}.
 *
 * Focuses the first focusable element inside the container on mount,
 * traps Tab navigation, and restores focus to the previously active
 * element on unmount.
 *
 * @example
 * function Modal({ onClose }) {
 *   const ref = useRef<HTMLDivElement>(null);
 *   useFocusTrap(ref, true);
 *   return <div ref={ref} role="dialog">...</div>;
 * }
 */
export function useFocusTrap(
  containerRef: RefObject<HTMLElement | null>,
  enabled: boolean = true,
): void {
  useEffect(() => {
    if (!enabled || !containerRef.current) return;

    const previousActive = document.activeElement as HTMLElement | null;
    const cleanup = trapFocus(containerRef);

    // Focus the first focusable element inside the container
    const firstFocusable = containerRef.current.querySelector<HTMLElement>(
      FOCUSABLE_SELECTOR,
    );
    if (firstFocusable) {
      firstFocusable.focus();
    } else {
      containerRef.current.focus();
    }

    return () => {
      cleanup();
      // Restore focus to where it was before the trap engaged
      if (previousActive && typeof previousActive.focus === "function") {
        previousActive.focus();
      }
    };
  }, [enabled, containerRef]);
}

// ── Skip to content ─────────────────────────────────────────────────────────

/**
 * Move keyboard focus to the main content area.
 *
 * Looks for `<main>` first, then falls back to `#main-content`.
 * Sets `tabindex="-1"` temporarily so the element is focusable.
 *
 * Bind this to a "Skip to main content" link that appears on Tab focus.
 */
export function skipToContent(): void {
  if (typeof document === "undefined") return;

  const target =
    document.querySelector("main") ||
    document.getElementById("main-content");

  if (!target) return;

  // Make focusable without adding to tab order
  const prevTabIndex = target.getAttribute("tabindex");
  target.setAttribute("tabindex", "-1");
  (target as HTMLElement).focus();

  // Restore original tabindex (or remove if it wasn't set)
  target.addEventListener(
    "blur",
    () => {
      if (prevTabIndex === null) {
        target.removeAttribute("tabindex");
      } else {
        target.setAttribute("tabindex", prevTabIndex);
      }
    },
    { once: true },
  );
}

// ── Prefers-reduced-motion ──────────────────────────────────────────────────

/**
 * Check if the user has requested reduced motion.
 *
 * Use to gate animations at the JS level (CSS @media queries handle
 * the rest automatically via the tokens.css rules).
 */
export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
