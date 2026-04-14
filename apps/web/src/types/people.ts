/**
 * People Graph / Face Clustering types (S13-001).
 *
 * These mirror the Sprint 12 API contracts exactly. If a field shape
 * changes in `apps/api/api/schemas/{trusted_person,review_queue,
 * people_operations}.py`, update here and bump the test in
 * `src/types/__tests__/people.types.test.ts`.
 */

export type TrustSource =
  | "manual"
  | "candidate_confirmed"
  | "face_confirmed"
  | "imported"
  | "contact_import"
  | "merged";

export interface TrustedPerson {
  id: string;
  workspace_id: string;
  display_name: string;
  canonical_contact_id: string | null;
  trust_source: TrustSource;
  confirmed_at: string | null;
  confirmed_by: string | null;
  merged_from_ids?: string[];
  face_count?: number;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  created_at: string;
  updated_at: string;
  deleted_at?: string | null;
}

export type ConfidenceBucket = "high" | "medium" | "low" | "none";

export interface CandidateScore {
  contact_id: string;
  contact_display_name?: string;
  score: number;
  signals: Record<string, number>;
  confidence: ConfidenceBucket;
}

export interface ReviewQueueItem {
  cluster_id: string;
  member_count: number;
  sample_face_detection_ids: string[];
  sample_photo_asset_ids: string[];
  top_candidate: CandidateScore | null;
  other_candidates: CandidateScore[];
  confidence_bucket: ConfidenceBucket;
  first_seen_at: string | null;
  last_seen_at: string | null;
}

export interface ReviewQueueDetail extends Omit<ReviewQueueItem, "sample_face_detection_ids" | "sample_photo_asset_ids"> {
  face_detection_ids: string[];
  photo_asset_ids: string[];
}

export type PersonOperationType =
  | "merge"
  | "split"
  | "rename"
  | "delete"
  | "confirm"
  | "reject";

export interface PersonOperation {
  id: string;
  workspace_id: string;
  user_id: string;
  operation_type: PersonOperationType;
  forward_payload: Record<string, unknown>;
  created_at: string;
  undone_at: string | null;
  undone_by_user_id: string | null;
}

export interface PersonOperationResult {
  operation_id: string;
  operation_type: PersonOperationType;
}

export interface PaginatedPersons {
  items: TrustedPerson[];
  next_cursor: string | null;
}

export interface PaginatedReviewItems {
  items: ReviewQueueItem[];
  next_cursor: string | null;
}

export interface PaginatedOperations {
  items: PersonOperation[];
}

export interface MergeRequest {
  person_ids: string[];
  keeper_id: string;
}

export interface SplitRequest {
  face_detection_ids: string[];
  new_display_name: string;
}

export interface CreatePersonRequest {
  cluster_id: string;
  display_name: string;
  canonical_contact_id?: string | null;
}

export interface ConfirmCandidateRequest {
  cluster_id: string;
  contact_id: string;
}

export interface RejectClusterRequest {
  cluster_id: string;
  reason?: string | null;
}
