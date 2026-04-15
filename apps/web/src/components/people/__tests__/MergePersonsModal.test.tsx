/**
 * MergePersonsModal tests (S13-005).
 *
 * Mocks fetch globally and seeds the modal with two TrustedPerson
 * objects via the optional ``initialPersons`` prop so the test
 * doesn't need to round-trip per-id GETs.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SWRConfig } from "swr";
import { afterEach, describe, expect, it, vi } from "vitest";

import MergePersonsModal from "../MergePersonsModal";
import type { TrustedPerson } from "../../../types/people";

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

const ALICE: TrustedPerson = {
  id: "alice",
  workspace_id: "w",
  display_name: "Alice",
  canonical_contact_id: null,
  trust_source: "manual",
  confirmed_at: null,
  confirmed_by: null,
  face_count: 5,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const BOB: TrustedPerson = {
  ...ALICE,
  id: "bob",
  display_name: "Bob",
  face_count: 3,
};

function renderModal(opts: {
  onMerged?: (k: TrustedPerson) => void;
  onClose?: () => void;
} = {}) {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <MergePersonsModal
        open
        onClose={opts.onClose ?? (() => {})}
        initialPersonIds={[ALICE.id, BOB.id]}
        initialPersons={[ALICE, BOB]}
        onMerged={opts.onMerged ?? (() => {})}
      />
    </SWRConfig>,
  );
}

describe("MergePersonsModal", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders all initial persons", async () => {
    mountWithFetch(() => ({ status: 200, body: { items: [], next_cursor: null } }));
    renderModal();
    await waitFor(() => {
      expect(screen.getByText("Alice")).toBeTruthy();
      expect(screen.getByText("Bob")).toBeTruthy();
    });
  });

  it("merge button is disabled until a keeper is picked", async () => {
    mountWithFetch(() => ({ status: 200, body: { items: [], next_cursor: null } }));
    renderModal();
    const mergeBtn = await waitFor(() =>
      screen.getByRole("button", { name: /Merge 2 → 1/i }),
    );
    expect((mergeBtn as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(
      screen.getByLabelText(/Keep Alice as the merged person/i),
    );
    await waitFor(() => {
      expect((mergeBtn as HTMLButtonElement).disabled).toBe(false);
    });
  });

  it("clicking merge POSTs to /api/v1/people/merge with the keeper id", async () => {
    const calls = mountWithFetch(({ url, method }) => {
      if (method === "POST" && url.endsWith("/api/v1/people/merge"))
        return {
          status: 200,
          body: { ...ALICE, merged_from_ids: [BOB.id] },
        };
      return { status: 200, body: { items: [], next_cursor: null } };
    });
    const onMerged = vi.fn();
    const onClose = vi.fn();
    renderModal({ onMerged, onClose });

    fireEvent.click(
      await screen.findByLabelText(/Keep Alice as the merged person/i),
    );
    fireEvent.click(screen.getByRole("button", { name: /Merge 2 → 1/i }));

    await waitFor(() => {
      const hit = calls.find(
        (c) => c.method === "POST" && c.url.endsWith("/api/v1/people/merge"),
      );
      expect(hit).toBeTruthy();
      expect(hit?.body).toContain('"keeper_id":"alice"');
      expect(hit?.body).toContain('"alice"');
      expect(hit?.body).toContain('"bob"');
    });
    await waitFor(() => {
      expect(onMerged).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it("error response stays open with inline message", async () => {
    mountWithFetch(({ url, method }) => {
      if (method === "POST" && url.endsWith("/api/v1/people/merge"))
        return {
          status: 422,
          body: {
            error_code: "INVALID_MERGE_KEEPER",
            message: "Keeper must be in the list",
          },
        };
      return { status: 200, body: { items: [], next_cursor: null } };
    });
    const onClose = vi.fn();
    renderModal({ onClose });

    fireEvent.click(
      await screen.findByLabelText(/Keep Alice as the merged person/i),
    );
    fireEvent.click(screen.getByRole("button", { name: /Merge 2 → 1/i }));

    // The apiFetch wrapper translates the error_code into a user
    // message via the registry — we assert on role=alert presence
    // rather than a specific string so the test stays robust if the
    // copy is updated.
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeTruthy();
    });
    expect(onClose).not.toHaveBeenCalled();
  });
});
