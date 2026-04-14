/**
 * API client tests for people / review queue modules (S13-001).
 *
 * Mocks `global.fetch` and asserts every exported function calls the
 * expected URL + method + body. Never asserts on request bodies that
 * contain names (only on their structure).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { peopleApi } from "../people";
import { reviewQueueApi } from "../review_queue";

type FetchCall = {
  url: string;
  method: string;
  body: unknown;
  headers: Record<string, string>;
};

function mockFetch(): FetchCall[] {
  const calls: FetchCall[] = [];
  global.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = init?.method ?? "GET";
    let body: unknown = undefined;
    if (typeof init?.body === "string") {
      try {
        body = JSON.parse(init.body);
      } catch {
        body = init.body;
      }
    }
    const headers: Record<string, string> = {};
    const h = init?.headers;
    if (h && typeof (h as Headers).forEach === "function") {
      (h as Headers).forEach((v, k) => {
        headers[k] = v;
      });
    } else if (h && typeof h === "object") {
      Object.assign(headers, h);
    }
    calls.push({ url, method, body, headers });
    return new Response(
      JSON.stringify({ ok: true, items: [], next_cursor: null }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  }) as typeof fetch;
  return calls;
}

describe("peopleApi", () => {
  let calls: FetchCall[];
  beforeEach(() => {
    calls = mockFetch();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("list builds GET /api/v1/people with query params", async () => {
    await peopleApi.list({ limit: 10, cursor: "abc" });
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toContain("/api/v1/people?");
    expect(calls[0].url).toContain("limit=10");
    expect(calls[0].url).toContain("cursor=abc");
    expect(calls[0].method).toBe("GET");
  });

  it("get calls GET /api/v1/people/:id", async () => {
    await peopleApi.get("123");
    expect(calls[0].url).toBe("/api/v1/people/123");
    expect(calls[0].method).toBe("GET");
  });

  it("create POSTs cluster_id and display_name", async () => {
    await peopleApi.create({ cluster_id: "c1", display_name: "A" });
    expect(calls[0].url).toBe("/api/v1/people");
    expect(calls[0].method).toBe("POST");
    expect((calls[0].body as Record<string, unknown>).cluster_id).toBe("c1");
  });

  it("confirmCandidate targets /confirm-candidate", async () => {
    await peopleApi.confirmCandidate({ cluster_id: "c1", contact_id: "k1" });
    expect(calls[0].url).toBe("/api/v1/people/confirm-candidate");
    expect(calls[0].method).toBe("POST");
  });

  it("rejectCluster targets /reject-cluster", async () => {
    await peopleApi.rejectCluster({ cluster_id: "c1" });
    expect(calls[0].url).toBe("/api/v1/people/reject-cluster");
    expect(calls[0].method).toBe("POST");
  });

  it("rename PATCHes /api/v1/people/:id", async () => {
    await peopleApi.rename("p1", "New");
    expect(calls[0].url).toBe("/api/v1/people/p1");
    expect(calls[0].method).toBe("PATCH");
    expect((calls[0].body as Record<string, unknown>).display_name).toBe("New");
  });

  it("delete DELETEs /api/v1/people/:id", async () => {
    await peopleApi.delete("p1");
    expect(calls[0].url).toBe("/api/v1/people/p1");
    expect(calls[0].method).toBe("DELETE");
  });

  it("merge POSTs /api/v1/people/merge", async () => {
    await peopleApi.merge({ person_ids: ["a", "b"], keeper_id: "a" });
    expect(calls[0].url).toBe("/api/v1/people/merge");
    expect(calls[0].method).toBe("POST");
  });

  it("split POSTs /api/v1/people/:id/split", async () => {
    await peopleApi.split("p1", {
      face_detection_ids: ["f1"],
      new_display_name: "New",
    });
    expect(calls[0].url).toBe("/api/v1/people/p1/split");
    expect(calls[0].method).toBe("POST");
  });

  it("undoLast POSTs /operations/undo-last", async () => {
    await peopleApi.undoLast();
    expect(calls[0].url).toBe("/api/v1/people/operations/undo-last");
    expect(calls[0].method).toBe("POST");
  });

  it("undoOperation POSTs /operations/:id/undo", async () => {
    await peopleApi.undoOperation("op1");
    expect(calls[0].url).toBe("/api/v1/people/operations/op1/undo");
    expect(calls[0].method).toBe("POST");
  });

  it("listOperations GETs /operations with limit", async () => {
    await peopleApi.listOperations(25);
    expect(calls[0].url).toContain("/api/v1/people/operations?");
    expect(calls[0].url).toContain("limit=25");
    expect(calls[0].method).toBe("GET");
  });
});

describe("reviewQueueApi", () => {
  let calls: FetchCall[];
  beforeEach(() => {
    calls = mockFetch();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("list builds GET /api/v1/review-queue with confidence filter", async () => {
    await reviewQueueApi.list({ confidence: "high", limit: 5 });
    expect(calls[0].url).toContain("/api/v1/review-queue?");
    expect(calls[0].url).toContain("confidence=high");
    expect(calls[0].url).toContain("limit=5");
  });

  it("get calls /api/v1/review-queue/:id", async () => {
    await reviewQueueApi.get("c1");
    expect(calls[0].url).toBe("/api/v1/review-queue/c1");
    expect(calls[0].method).toBe("GET");
  });

  it("skip POSTs /api/v1/review-queue/:id/skip", async () => {
    await reviewQueueApi.skip("c1");
    expect(calls[0].url).toBe("/api/v1/review-queue/c1/skip");
    expect(calls[0].method).toBe("POST");
  });
});
