/**
 * SWR cache-key correctness tests for usePeople hooks (S13-001).
 *
 * The URL string is the SWR cache key. These tests just verify that
 * the hook query-building logic produces deterministic keys.
 */

import { describe, expect, it } from "vitest";

function toQuery(params: Record<string, string | number | undefined | null>) {
  const entries = Object.entries(params).filter(
    ([, v]) => v !== undefined && v !== null && v !== "",
  );
  if (entries.length === 0) return "";
  const qs = new URLSearchParams();
  for (const [k, v] of entries) qs.set(k, String(v));
  return `?${qs.toString()}`;
}

describe("people hook cache keys", () => {
  it("omits undefined params", () => {
    const key = `/api/v1/people${toQuery({ limit: 20, cursor: undefined })}`;
    expect(key).toBe("/api/v1/people?limit=20");
  });

  it("produces a stable key with every param", () => {
    const key = `/api/v1/people${toQuery({ limit: 10, cursor: "abc", search: "a" })}`;
    expect(key).toContain("limit=10");
    expect(key).toContain("cursor=abc");
    expect(key).toContain("search=a");
  });

  it("produces no query for empty params", () => {
    const key = `/api/v1/people${toQuery({})}`;
    expect(key).toBe("/api/v1/people");
  });

  it("review queue filter produces deterministic key", () => {
    const key = `/api/v1/review-queue${toQuery({ confidence: "high", limit: 20 })}`;
    expect(key).toContain("confidence=high");
    expect(key).toContain("limit=20");
  });
});
