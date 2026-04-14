/**
 * Client-side metrics helper (S13-001 / G-15).
 *
 * Fires a fire-and-forget POST to `/api/v1/metrics/events`. Never
 * throws — metrics are advisory and must not block user flows.
 * Payloads must not contain PII (display names, emails, photo
 * contents). Pass IDs only; the backend aggregates counters.
 */

import { apiFetch } from "../api/client";

export type PeopleEventName =
  | "people.list.viewed"
  | "people.detail.viewed"
  | "people.detail.renamed"
  | "people.detail.deleted"
  | "reviewQueue.viewed"
  | "reviewQueue.confirmed"
  | "reviewQueue.rejected"
  | "reviewQueue.skipped"
  | "reviewQueue.newPersonCreated"
  | "merge.completed"
  | "split.completed"
  | "undo.triggered"
  | "undo.failed"
  | "personCard.clickedFromToday"
  | "personCard.clickedFromSearch"
  | "lightbox.openedFromPhoto"
  | "lightbox.personClicked";

export interface TrackEventPayload {
  [key: string]: string | number | boolean | null | undefined;
}

/**
 * Fire a metrics event. Guarantees:
 *  - Never throws (caller doesn't need try/catch)
 *  - Never blocks (background task)
 *  - Never logs the payload (might contain ids that correlate to PII)
 */
export function trackPeopleEvent(
  eventName: PeopleEventName,
  payload: TrackEventPayload = {},
): void {
  // Fire-and-forget. Errors are swallowed so a failed metrics post
  // never disrupts the user's action.
  void apiFetch("/api/v1/metrics/events", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      event: eventName,
      payload,
      timestamp: new Date().toISOString(),
    }),
  }).catch(() => {
    /* intentionally ignored */
  });
}

/** Generic event tracker for non-People surfaces. Same contract. */
export function trackEvent(
  eventName: string,
  payload: TrackEventPayload = {},
): void {
  void apiFetch("/api/v1/metrics/events", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      event: eventName,
      payload,
      timestamp: new Date().toISOString(),
    }),
  }).catch(() => {
    /* intentionally ignored */
  });
}
