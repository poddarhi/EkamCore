/**
 * Card types matching the backend ResponseEnvelope discriminated union.
 *
 * These mirror the Pydantic schemas in api/schemas/envelope.py so the mobile
 * client can type-safely render cards without runtime guessing.
 */

// ── Card payloads ──

export interface EventPayload {
  title: string;
  start_at: string; // ISO 8601
  end_at: string | null;
  is_all_day: boolean;
  location: string | null;
  calendar_name: string | null;
  participants: string[];
}

export interface ReminderPayload {
  title: string;
  due_at: string | null; // ISO 8601
  priority: 'high' | 'medium' | 'low' | 'none' | null;
  list_name: string | null;
  notes: string | null;
  is_overdue: boolean;
}

export interface StatusPayload {
  date: string; // ISO date (YYYY-MM-DD)
  time_of_day: 'morning' | 'afternoon' | 'evening' | 'night';
  weekday: string;
}

// ── Card types (discriminated on `type`) ──

export type CardType =
  | 'event'
  | 'reminder'
  | 'status'
  | 'person'
  | 'file'
  | 'photo'
  | 'suggestion'
  | 'pack';

interface CardBase {
  id: string;
  priority_score: number;
  source_ids: string[];
}

export interface EventCard extends CardBase {
  type: 'event';
  payload: EventPayload;
}

export interface ReminderCard extends CardBase {
  type: 'reminder';
  payload: ReminderPayload;
}

export interface StatusCard extends CardBase {
  type: 'status';
  payload: StatusPayload;
}

export interface GenericCard extends CardBase {
  type: 'person' | 'file' | 'photo' | 'suggestion' | 'pack';
  payload: Record<string, unknown>;
}

export type Card = EventCard | ReminderCard | StatusCard | GenericCard;

// ── Envelope ──

export interface SourceRef {
  type: 'file' | 'contact' | 'event' | 'reminder' | 'photo' | 'person';
  id: string;
  title: string;
  relevance: number;
}

export interface SuggestedAction {
  action_type: string;
  label: string;
  payload: Record<string, unknown>;
}

export interface CacheHint {
  ttl_seconds: number;
}

export interface ResponseMetadata {
  query_path: 'deterministic' | 'semantic' | 'small_model' | 'large_model';
  latency_ms: number;
  is_partial: boolean;
  cache_hint: CacheHint | null;
}

export interface ResponseEnvelope {
  answer_text: string | null;
  confidence_level: 'deterministic' | 'high' | 'medium' | 'low';
  sources: SourceRef[];
  cards: Card[];
  suggested_actions: SuggestedAction[];
  metadata: ResponseMetadata;
}
