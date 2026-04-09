/**
 * Recap screen type definitions.
 *
 * RecapResponse is a type alias for ResponseEnvelope — the backend /recap
 * endpoint returns the same envelope shape as /today.
 * RecapSection is a mobile-only construct for grouping cards into SectionList
 * sections by date (weekly mode has one section per day; daily mode has one).
 */

export { RecapPeriod } from './api';
import type { Card, ResponseEnvelope } from './cards';

// ── Response ──

/**
 * Alias for ResponseEnvelope. The /recap endpoint returns the standard
 * envelope; this alias makes intent explicit at the call site.
 */
export type RecapResponse = ResponseEnvelope;

// ── Section (mobile-only grouping for SectionList) ──

export interface RecapSection {
  /** ISO date string (YYYY-MM-DD) for the day this section represents. */
  date: string;
  /** Human-readable header e.g. "Monday, Apr 7" or "Today". */
  title: string;
  /** Cards belonging to this day, sorted by priority_score descending. */
  cards: Card[];
}
