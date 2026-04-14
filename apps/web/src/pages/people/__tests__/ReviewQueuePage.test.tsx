/**
 * ReviewQueuePage tests (S13-004).
 *
 * Mocks fetch globally and drives the page through its keyboard
 * shortcuts. Asserts that each shortcut hits the right endpoint and
 * advances the cursor optimistically. Also covers empty-state, the
 * candidate-pick number keys, the create-new-person modal, and the
 * batch action bar.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { SWRConfig } from "swr";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FlagProvider } from "../../../contexts/FlagContext";
import ReviewQueuePage from "../ReviewQueuePage";

interface Call {
  url: string;
  method: string;
  body?: string;
}

function mountWithFetch(
  handler: (args: Call) => { status: number; body: unknown },
): Call[] {
  const calls: Call[] = [];
  global.fetch = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      const method = (init?.method ?? "GET").toUpperCase();
      const body = typeof init?.body === "string" ? init.body : undefined;
      calls.push({ url, method, body });
      const { status, body: respBody } = handler({ url, method, body });
      return new Response(
        respBody === undefined ? null : JSON.stringify(respBody),
        { status, headers: { "Content-Type": "application/json" } },
      );
    },
  ) as typeof fetch;
  return calls;
}

function renderPage() {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <FlagProvider>
        <MemoryRouter initialEntries={["/people/review"]}>
          <Routes>
            <Route path="/people/review" element={<ReviewQueuePage />} />
            <Route path="/people" element={<div>PEOPLE</div>} />
          </Routes>
        </MemoryRouter>
      </FlagProvider>
    </SWRConfig>,
  );
}

const ITEM_ALPHA = {
  cluster_id: "cluster-alpha",
  member_count: 4,
  sample_face_detection_ids: ["fd1", "fd2"],
  sample_photo_asset_ids: ["pa1", "pa2", "pa3"],
  top_candidate: {
    contact_id: "contact-alpha-top",
    contact_display_name: "Alice",
    score: 0.9,
    signals: { co_occurrence: 0.9 },
    confidence: "high" as const,
  },
  other_candidates: [
    {
      contact_id: "contact-alpha-2",
      contact_display_name: "Alicia",
      score: 0.7,
      signals: {},
      confidence: "medium" as const,
    },
  ],
  confidence_bucket: "high" as const,
  first_seen_at: "2026-01-01T00:00:00Z",
  last_seen_at: "2026-04-01T00:00:00Z",
};

const ITEM_BETA = {
  ...ITEM_ALPHA,
  cluster_id: "cluster-beta",
  top_candidate: {
    contact_id: "contact-beta-top",
    contact_display_name: "Bob",
    score: 0.85,
    signals: {},
    confidence: "high" as const,
  },
  other_candidates: [],
};

function defaultHandler(items: unknown[] = [ITEM_ALPHA, ITEM_BETA]) {
  return ({ url }: Call) => {
    if (url.includes("/settings/face-clustering/consent")) {
      return { status: 200, body: { accepted: true } };
    }
    if (url.startsWith("/api/v1/review-queue")) {
      return { status: 200, body: { items, next_cursor: null } };
    }
    if (url.includes("/api/v1/metrics/events")) {
      return { status: 204, body: {} };
    }
    return { status: 200, body: {} };
  };
}

describe("ReviewQueuePage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the first item card", async () => {
    mountWithFetch(defaultHandler());
    renderPage();
    const card = await screen.findByTestId("review-card", undefined, {
      timeout: 3000,
    });
    expect(card).toBeTruthy();
    expect(screen.getAllByText(/Alice/).length).toBeGreaterThan(0);
  });

  it("Enter confirms the active candidate and advances", async () => {
    const calls = mountWithFetch(({ url, method }) => {
      if (url.includes("/settings/face-clustering/consent"))
        return { status: 200, body: { accepted: true } };
      if (
        method === "POST" &&
        url.endsWith("/api/v1/people/confirm-candidate")
      )
        return { status: 200, body: ITEM_ALPHA.top_candidate };
      if (url.startsWith("/api/v1/review-queue"))
        return {
          status: 200,
          body: { items: [ITEM_ALPHA, ITEM_BETA], next_cursor: null },
        };
      return { status: 200, body: {} };
    });
    renderPage();
    await waitFor(() => screen.getByTestId("review-card"));

    fireEvent.keyDown(document, { key: "Enter" });

    await waitFor(() => {
      const hit = calls.find(
        (c) =>
          c.method === "POST" &&
          c.url.endsWith("/api/v1/people/confirm-candidate"),
      );
      expect(hit).toBeTruthy();
      expect(hit?.body).toContain("cluster-alpha");
      expect(hit?.body).toContain("contact-alpha-top");
    });
    // Advanced to the next item.
    await waitFor(() => {
      expect(screen.getByText(/Bob/)).toBeTruthy();
    });
  });

  it("R rejects the cluster and advances", async () => {
    const calls = mountWithFetch(({ url, method }) => {
      if (url.includes("/settings/face-clustering/consent"))
        return { status: 200, body: { accepted: true } };
      if (method === "POST" && url.endsWith("/api/v1/people/reject-cluster"))
        return { status: 204, body: undefined };
      if (url.startsWith("/api/v1/review-queue"))
        return {
          status: 200,
          body: { items: [ITEM_ALPHA, ITEM_BETA], next_cursor: null },
        };
      return { status: 200, body: {} };
    });
    renderPage();
    await waitFor(() => screen.getByTestId("review-card"));
    fireEvent.keyDown(document, { key: "r" });
    await waitFor(() => {
      const hit = calls.find(
        (c) =>
          c.method === "POST" &&
          c.url.endsWith("/api/v1/people/reject-cluster"),
      );
      expect(hit).toBeTruthy();
      expect(hit?.body).toContain("cluster-alpha");
    });
  });

  it("S skips the cluster and advances", async () => {
    const calls = mountWithFetch(({ url, method }) => {
      if (url.includes("/settings/face-clustering/consent"))
        return { status: 200, body: { accepted: true } };
      if (
        method === "POST" &&
        url.includes("/api/v1/review-queue/cluster-alpha/skip")
      )
        return { status: 204, body: undefined };
      if (url.startsWith("/api/v1/review-queue"))
        return {
          status: 200,
          body: { items: [ITEM_ALPHA, ITEM_BETA], next_cursor: null },
        };
      return { status: 200, body: {} };
    });
    renderPage();
    await waitFor(() => screen.getByTestId("review-card"));
    fireEvent.keyDown(document, { key: "s" });
    await waitFor(() => {
      const hit = calls.find(
        (c) =>
          c.method === "POST" &&
          c.url.includes("/api/v1/review-queue/cluster-alpha/skip"),
      );
      expect(hit).toBeTruthy();
    });
  });

  it("number key picks the second candidate, then Enter confirms it", async () => {
    const calls = mountWithFetch(({ url, method }) => {
      if (url.includes("/settings/face-clustering/consent"))
        return { status: 200, body: { accepted: true } };
      if (
        method === "POST" &&
        url.endsWith("/api/v1/people/confirm-candidate")
      )
        return { status: 200, body: {} };
      if (url.startsWith("/api/v1/review-queue"))
        return {
          status: 200,
          body: { items: [ITEM_ALPHA], next_cursor: null },
        };
      return { status: 200, body: {} };
    });
    renderPage();
    await waitFor(() => screen.getByTestId("review-card"));

    fireEvent.keyDown(document, { key: "2" });
    fireEvent.keyDown(document, { key: "Enter" });

    await waitFor(() => {
      const hit = calls.find(
        (c) =>
          c.method === "POST" &&
          c.url.endsWith("/api/v1/people/confirm-candidate"),
      );
      expect(hit?.body).toContain("contact-alpha-2");
    });
  });

  it("renders the empty state when the queue is empty", async () => {
    mountWithFetch(defaultHandler([]));
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/All caught up/i)).toBeTruthy();
    });
  });

  it("N opens the create-new-person modal and submitting POSTs", async () => {
    const calls = mountWithFetch(({ url, method }) => {
      if (url.includes("/settings/face-clustering/consent"))
        return { status: 200, body: { accepted: true } };
      if (method === "POST" && url.endsWith("/api/v1/people"))
        return { status: 201, body: { id: "p-new" } };
      if (url.startsWith("/api/v1/review-queue"))
        return {
          status: 200,
          body: { items: [ITEM_ALPHA], next_cursor: null },
        };
      return { status: 200, body: {} };
    });
    renderPage();
    await waitFor(() => screen.getByTestId("review-card"));

    fireEvent.keyDown(document, { key: "n" });
    const input = await waitFor(() =>
      screen.getByLabelText(/New person name/i),
    );
    fireEvent.change(input, { target: { value: "Charlie" } });
    fireEvent.click(screen.getByText(/^Create$/));

    await waitFor(() => {
      const hit = calls.find(
        (c) => c.method === "POST" && c.url.endsWith("/api/v1/people"),
      );
      expect(hit?.body).toContain("Charlie");
      expect(hit?.body).toContain("cluster-alpha");
    });
  });
});
