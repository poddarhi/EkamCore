/**
 * SplitPersonModal tests (S13-006).
 *
 * Mocks fetch globally, seeds the faces endpoint with 4 faces, and
 * drives the selection + submit flow. Covers the gating rules, the
 * POST payload, and the success path.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SWRConfig } from "swr";
import { afterEach, describe, expect, it, vi } from "vitest";

import SplitPersonModal from "../SplitPersonModal";
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

const PERSON: TrustedPerson = {
  id: "p1",
  workspace_id: "w",
  display_name: "Alice",
  canonical_contact_id: null,
  trust_source: "manual",
  confirmed_at: null,
  confirmed_by: null,
  face_count: 4,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const FACES = Array.from({ length: 4 }, (_, i) => ({
  face_detection_id: `f${i + 1}`,
  photo_asset_id: `pa${i + 1}`,
  cluster_id: "c1",
  detection_score: 0.9 - i * 0.05,
  thumbnail_url: `/api/v1/people/${PERSON.id}/faces/f${i + 1}/thumbnail`,
}));

function facesHandler({ url, method }: Call) {
  if (url.includes(`/people/${PERSON.id}/faces`) && method === "GET") {
    return { status: 200, body: { items: FACES } };
  }
  return { status: 200, body: {} };
}

function renderModal(opts: {
  preselected?: string[];
  onSplit?: (o: TrustedPerson, n: TrustedPerson) => void;
  onClose?: () => void;
} = {}) {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <SplitPersonModal
        open
        onClose={opts.onClose ?? (() => {})}
        person={PERSON}
        preselectedFaceIds={opts.preselected}
        onSplit={opts.onSplit ?? (() => {})}
      />
    </SWRConfig>,
  );
}

describe("SplitPersonModal", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders all faces from the API", async () => {
    mountWithFetch(facesHandler);
    renderModal();
    const grid = await screen.findByTestId("split-face-grid", undefined, {
      timeout: 3000,
    });
    expect(grid.querySelectorAll('[role="gridcell"]').length).toBe(4);
  });

  it("selecting a face updates the counter", async () => {
    mountWithFetch(facesHandler);
    renderModal();
    await screen.findByTestId("split-face-grid");
    fireEvent.click(
      screen.getByLabelText(/Face 1 of 4, not selected/),
    );
    await waitFor(() => {
      expect(screen.getByTestId("split-selected-count").textContent).toMatch(
        /1 face selected/,
      );
    });
  });

  it("Split button is disabled without name, selection, or when all selected", async () => {
    mountWithFetch(facesHandler);
    renderModal();
    await screen.findByTestId("split-face-grid");
    const btn = screen.getByRole("button", { name: /^Split$/i });
    expect((btn as HTMLButtonElement).disabled).toBe(true);

    // Select all via toolbar then assert still disabled.
    fireEvent.click(screen.getByRole("button", { name: /Select all/i }));
    fireEvent.change(screen.getByLabelText(/New person name/i), {
      target: { value: "Other Alice" },
    });
    expect((btn as HTMLButtonElement).disabled).toBe(true);

    // Clear one face → should become enabled.
    fireEvent.click(screen.getByLabelText(/Face 1 of 4, selected/));
    await waitFor(() => {
      expect((btn as HTMLButtonElement).disabled).toBe(false);
    });
  });

  it("submits the selected face ids and name to /split", async () => {
    const calls = mountWithFetch(({ url, method, body }) => {
      if (method === "POST" && url.includes(`/people/${PERSON.id}/split`))
        return {
          status: 200,
          body: { ...PERSON, id: "p-new", display_name: "Split Out" },
        };
      return facesHandler({ url, method, body });
    });
    const onSplit = vi.fn();
    const onClose = vi.fn();
    renderModal({ onSplit, onClose });
    await screen.findByTestId("split-face-grid");

    fireEvent.click(screen.getByLabelText(/Face 1 of 4, not selected/));
    fireEvent.click(screen.getByLabelText(/Face 2 of 4, not selected/));
    fireEvent.change(screen.getByLabelText(/New person name/i), {
      target: { value: "Split Out" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Split$/i }));

    await waitFor(() => {
      const hit = calls.find(
        (c) =>
          c.method === "POST" &&
          c.url.includes(`/people/${PERSON.id}/split`),
      );
      expect(hit).toBeTruthy();
      expect(hit?.body).toContain("Split Out");
      expect(hit?.body).toContain('"f1"');
      expect(hit?.body).toContain('"f2"');
    });
    await waitFor(() => {
      expect(onSplit).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it("honors preselectedFaceIds on open", async () => {
    mountWithFetch(facesHandler);
    renderModal({ preselected: ["f1", "f3"] });
    await screen.findByTestId("split-face-grid");
    await waitFor(() => {
      expect(screen.getByTestId("split-selected-count").textContent).toMatch(
        /2 faces selected/,
      );
    });
    expect(screen.getByLabelText(/Face 1 of 4, selected/)).toBeTruthy();
    expect(screen.getByLabelText(/Face 3 of 4, selected/)).toBeTruthy();
  });
});
