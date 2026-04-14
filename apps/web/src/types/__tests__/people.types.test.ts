/**
 * Type compile-check (S13-001).
 *
 * This file exists so the test runner exercises the type module.
 * The assertions are trivial — the real verification is that
 * `tsc --noEmit` passes. Any schema drift surfaces here first.
 */

import { describe, expect, it } from "vitest";

import type {
  CandidateScore,
  ConfidenceBucket,
  PersonOperation,
  ReviewQueueItem,
  TrustedPerson,
} from "../people";

describe("people types", () => {
  it("TrustedPerson literal", () => {
    const row: TrustedPerson = {
      id: "a",
      workspace_id: "b",
      display_name: "Alice",
      canonical_contact_id: null,
      trust_source: "manual",
      confirmed_at: "2026-04-13T00:00:00Z",
      confirmed_by: "u",
      created_at: "2026-04-13T00:00:00Z",
      updated_at: "2026-04-13T00:00:00Z",
    };
    expect(row.display_name).toBe("Alice");
  });

  it("CandidateScore confidence bucket is constrained", () => {
    const buckets: ConfidenceBucket[] = ["high", "medium", "low", "none"];
    expect(buckets).toHaveLength(4);
    const c: CandidateScore = {
      contact_id: "x",
      score: 0.9,
      signals: { co_occurrence: 1.0 },
      confidence: "high",
    };
    expect(c.confidence).toBe("high");
  });

  it("ReviewQueueItem + PersonOperation literals compile", () => {
    const item: ReviewQueueItem = {
      cluster_id: "c",
      member_count: 5,
      sample_face_detection_ids: [],
      sample_photo_asset_ids: [],
      top_candidate: null,
      other_candidates: [],
      confidence_bucket: "none",
      first_seen_at: null,
      last_seen_at: null,
    };
    const op: PersonOperation = {
      id: "o",
      workspace_id: "w",
      user_id: "u",
      operation_type: "rename",
      forward_payload: {},
      created_at: "2026-04-13T00:00:00Z",
      undone_at: null,
      undone_by_user_id: null,
    };
    expect(item.member_count).toBe(5);
    expect(op.operation_type).toBe("rename");
  });
});
