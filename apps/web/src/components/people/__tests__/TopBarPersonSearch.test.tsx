/**
 * TopBarPersonSearch tests (S13-009).
 *
 * Mocks fetch globally (consent + people list) and drives the
 * typeahead: render, dropdown appearance, arrow key + Enter
 * navigation, and the graceful disabled state when consent is off.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { SWRConfig } from "swr";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import TopBarPersonSearch from "../TopBarPersonSearch";
import { FlagProvider } from "../../../contexts/FlagContext";

interface Call {
  url: string;
}

function mountWithFetch(
  handler: (args: Call) => { status: number; body: unknown },
): Call[] {
  const calls: Call[] = [];
  global.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    calls.push({ url });
    const { status, body } = handler({ url });
    return new Response(body === undefined ? null : JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;
  return calls;
}

function LocationSentinel() {
  const location = useLocation();
  return <div data-testid="sentinel">{location.pathname}</div>;
}

function renderTopBar() {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <FlagProvider>
        <MemoryRouter initialEntries={["/today"]}>
          <Routes>
            <Route
              path="/today"
              element={
                <>
                  <TopBarPersonSearch />
                  <LocationSentinel />
                </>
              }
            />
            <Route path="/people/:personId" element={<LocationSentinel />} />
          </Routes>
        </MemoryRouter>
      </FlagProvider>
    </SWRConfig>,
  );
}

describe("TopBarPersonSearch", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("renders disabled input when face consent is not active", async () => {
    mountWithFetch(({ url }) => {
      if (url.includes("/settings/face-clustering/consent"))
        return { status: 200, body: { accepted: false } };
      return { status: 200, body: { items: [], next_cursor: null } };
    });
    renderTopBar();
    await waitFor(() => {
      const input = document.querySelector(
        'input[placeholder="Search..."]',
      ) as HTMLInputElement | null;
      expect(input).not.toBeNull();
      expect(input?.disabled).toBe(true);
    });
  });

  it("renders typeahead dropdown and Enter navigates to /people/:id", async () => {
    mountWithFetch(({ url }) => {
      if (url.includes("/settings/face-clustering/consent"))
        return { status: 200, body: { accepted: true } };
      if (url.startsWith("/api/v1/people"))
        return {
          status: 200,
          body: {
            items: [
              {
                id: "alice-id",
                workspace_id: "w",
                display_name: "Alice",
                canonical_contact_id: null,
                trust_source: "manual",
                confirmed_at: null,
                confirmed_by: null,
                created_at: "2026-04-01T00:00:00Z",
                updated_at: "2026-04-01T00:00:00Z",
              },
            ],
            next_cursor: null,
          },
        };
      return { status: 200, body: {} };
    });
    renderTopBar();

    const input = await screen.findByTestId("topbar-person-search");
    fireEvent.change(input, { target: { value: "@ali" } });
    await vi.advanceTimersByTimeAsync(300);

    await waitFor(() => {
      expect(screen.getByTestId("topbar-person-search-results")).toBeTruthy();
    });
    expect(screen.getByText("Alice")).toBeTruthy();

    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() => {
      expect(screen.getByTestId("sentinel").textContent).toBe(
        "/people/alice-id",
      );
    });
  });
});
