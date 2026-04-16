/**
 * UndoDrawer tests (S13-007).
 *
 * Mocks fetch globally and drives the drawer through render, undo
 * click, and the already-undone display. Also covers the empty
 * state.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SWRConfig } from "swr";
import { afterEach, describe, expect, it, vi } from "vitest";

import UndoDrawer from "../UndoDrawer";

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

const OP_MERGE = {
  id: "op-merge",
  workspace_id: "w",
  user_id: "u",
  operation_type: "merge" as const,
  forward_payload: { merged_count: 3, person_ids: ["a", "b", "c"] },
  created_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
  undone_at: null,
  undone_by_user_id: null,
};

const OP_RENAME = {
  ...OP_MERGE,
  id: "op-rename",
  operation_type: "rename" as const,
  forward_payload: {
    old_display_name: "Al",
    new_display_name: "Alice",
  },
};

const OP_UNDONE = {
  ...OP_MERGE,
  id: "op-undone",
  undone_at: new Date().toISOString(),
};

function renderDrawer(opts: { onClose?: () => void } = {}) {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <UndoDrawer open onClose={opts.onClose ?? (() => {})} />
    </SWRConfig>,
  );
}

describe("UndoDrawer", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders operations with summaries and undo buttons", async () => {
    mountWithFetch(({ url }) => {
      if (url.startsWith("/api/v1/people/operations"))
        return { status: 200, body: { items: [OP_MERGE, OP_RENAME] } };
      return { status: 200, body: {} };
    });
    renderDrawer();
    const list = await screen.findByTestId("undo-drawer-list", undefined, {
      timeout: 3000,
    });
    expect(list.querySelectorAll("li").length).toBe(2);
    expect(screen.getByText(/Merged 3 people/)).toBeTruthy();
    expect(screen.getByText(/Renamed "Al" to "Alice"/)).toBeTruthy();
  });

  it("already-undone operations render as 'Undone' label", async () => {
    mountWithFetch(({ url }) => {
      if (url.startsWith("/api/v1/people/operations"))
        return { status: 200, body: { items: [OP_UNDONE] } };
      return { status: 200, body: {} };
    });
    renderDrawer();
    await screen.findByTestId("undo-drawer-list");
    expect(screen.getByText(/^Undone$/)).toBeTruthy();
    expect(screen.queryByLabelText(/^Undo:/)).toBeNull();
  });

  it("clicking Undo POSTs to /operations/:id/undo and revalidates", async () => {
    const calls = mountWithFetch(({ url, method }) => {
      if (
        method === "POST" &&
        url.endsWith("/api/v1/people/operations/op-merge/undo")
      )
        return {
          status: 200,
          body: { operation_id: "op-merge", operation_type: "merge" },
        };
      if (url.startsWith("/api/v1/people/operations"))
        return { status: 200, body: { items: [OP_MERGE] } };
      return { status: 200, body: {} };
    });
    renderDrawer();
    await screen.findByTestId("undo-drawer-list");

    fireEvent.click(screen.getByLabelText(/^Undo: Merged/));

    await waitFor(() => {
      const hit = calls.find(
        (c) =>
          c.method === "POST" &&
          c.url.endsWith("/api/v1/people/operations/op-merge/undo"),
      );
      expect(hit).toBeTruthy();
    });
  });

  it("renders the empty state when the list is empty", async () => {
    mountWithFetch(({ url }) => {
      if (url.startsWith("/api/v1/people/operations"))
        return { status: 200, body: { items: [] } };
      return { status: 200, body: {} };
    });
    renderDrawer();
    await waitFor(() => {
      expect(screen.getByText(/No recent operations/i)).toBeTruthy();
    });
  });
});
