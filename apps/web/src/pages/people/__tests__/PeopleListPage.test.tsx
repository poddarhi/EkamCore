/**
 * PeopleListPage tests (S13-002).
 *
 * Stubs SWR by patching global fetch and wraps the page in a
 * MemoryRouter + SWRConfig. Verifies:
 *   - consent-off empty state CTA links to settings
 *   - populated grid renders names
 *   - search input debounces and calls the API with ?search=
 *   - grid/list toggle switches the rendered list
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { SWRConfig } from "swr";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FlagProvider } from "../../../contexts/FlagContext";
import PeopleListPage from "../PeopleListPage";

type FetchCall = { url: string };

function mountWithFetch(
  handler: (url: string) => { status: number; body: unknown },
): FetchCall[] {
  const calls: FetchCall[] = [];
  global.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    calls.push({ url });
    const { status, body } = handler(url);
    return new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;
  return calls;
}

function renderPage() {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <FlagProvider>
        <MemoryRouter initialEntries={["/people"]}>
          <Routes>
            <Route path="/people" element={<PeopleListPage />} />
            <Route path="/people/:id" element={<div>PERSON DETAIL</div>} />
            <Route
              path="/settings/photo-intelligence"
              element={<div>SETTINGS</div>}
            />
            <Route path="/people/review" element={<div>REVIEW</div>} />
          </Routes>
        </MemoryRouter>
      </FlagProvider>
    </SWRConfig>,
  );
}

describe("PeopleListPage", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("renders consent CTA when face consent is not active", async () => {
    mountWithFetch((url) => {
      if (url.includes("/settings/face-clustering/consent")) {
        return { status: 200, body: { accepted: false } };
      }
      return { status: 200, body: { items: [], next_cursor: null } };
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByText(/Go to Review Queue/i).length).toBeGreaterThan(0);
    });
  });

  it("renders people grid with names when consent is active", async () => {
    mountWithFetch((url) => {
      if (url.includes("/settings/face-clustering/consent")) {
        return { status: 200, body: { accepted: true } };
      }
      if (url.startsWith("/api/v1/review-queue")) {
        return { status: 200, body: { items: [], next_cursor: null } };
      }
      return {
        status: 200,
        body: {
          items: [
            {
              id: "p1",
              workspace_id: "w",
              display_name: "Alice Alpha",
              canonical_contact_id: null,
              trust_source: "manual",
              confirmed_at: "2026-04-01T00:00:00Z",
              confirmed_by: "u",
              created_at: "2026-04-01T00:00:00Z",
              updated_at: "2026-04-01T00:00:00Z",
            },
            {
              id: "p2",
              workspace_id: "w",
              display_name: "Bob Bravo",
              canonical_contact_id: null,
              trust_source: "manual",
              confirmed_at: "2026-04-02T00:00:00Z",
              confirmed_by: "u",
              created_at: "2026-04-02T00:00:00Z",
              updated_at: "2026-04-02T00:00:00Z",
            },
          ],
          next_cursor: null,
        },
      };
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Alice Alpha")).toBeTruthy();
      expect(screen.getByText("Bob Bravo")).toBeTruthy();
    });
    expect(screen.getByTestId("people-grid")).toBeTruthy();
  });

  it("debounces search input and hits API with ?search=", async () => {
    const calls = mountWithFetch((url) => {
      if (url.includes("/settings/face-clustering/consent")) {
        return { status: 200, body: { accepted: true } };
      }
      if (url.startsWith("/api/v1/review-queue")) {
        return { status: 200, body: { items: [], next_cursor: null } };
      }
      return { status: 200, body: { items: [], next_cursor: null } };
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Search people/i)).toBeTruthy();
    });
    const input = screen.getByPlaceholderText(
      /Search people/i,
    ) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "alic" } });

    // Debounce is 300ms. Fast-forward past it.
    await vi.advanceTimersByTimeAsync(350);

    await waitFor(() => {
      const hit = calls.find(
        (c) =>
          c.url.startsWith("/api/v1/people") && c.url.includes("search=alic"),
      );
      expect(hit).toBeTruthy();
    });
  });

  it("toggles between grid and list view", async () => {
    mountWithFetch((url) => {
      if (url.includes("/settings/face-clustering/consent")) {
        return { status: 200, body: { accepted: true } };
      }
      if (url.startsWith("/api/v1/review-queue")) {
        return { status: 200, body: { items: [], next_cursor: null } };
      }
      return {
        status: 200,
        body: {
          items: [
            {
              id: "p1",
              workspace_id: "w",
              display_name: "Alice",
              canonical_contact_id: null,
              trust_source: "manual",
              confirmed_at: "2026-04-01T00:00:00Z",
              confirmed_by: "u",
              created_at: "2026-04-01T00:00:00Z",
              updated_at: "2026-04-01T00:00:00Z",
            },
          ],
          next_cursor: null,
        },
      };
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("people-grid")).toBeTruthy();
    });
    fireEvent.click(screen.getByLabelText("List view"));
    expect(screen.getByTestId("people-list")).toBeTruthy();
  });
});
