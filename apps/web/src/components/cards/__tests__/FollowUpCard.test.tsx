/**
 * FollowUpCard tests (S14-009).
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import FollowUpCard from "../FollowUpCard";

interface Call { url: string; method: string; body?: string }

function mountWithFetch(
  handler: (a: Call) => { status: number; body: unknown },
): Call[] {
  const calls: Call[] = [];
  global.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = (init?.method ?? "GET").toUpperCase();
    const body = typeof init?.body === "string" ? init.body : undefined;
    calls.push({ url, method, body });
    const { status, body: b } = handler({ url, method, body });
    return new Response(b === undefined ? null : JSON.stringify(b), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;
  return calls;
}

function LocationSentinel() {
  const loc = useLocation();
  return <div data-testid="sentinel">{loc.pathname}</div>;
}

function renderCard(onAck?: () => void) {
  return render(
    <MemoryRouter initialEntries={["/today"]}>
      <Routes>
        <Route
          path="/today"
          element={
            <>
              <FollowUpCard
                cardId="c1"
                payload={{
                  person_id: "p1",
                  person_display_name: "Alice",
                  days_since_last_interaction: 12,
                  last_interaction_context: "Q4 meeting",
                }}
                onAcknowledged={onAck}
              />
              <LocationSentinel />
            </>
          }
        />
        <Route path="/people/:pid" element={<LocationSentinel />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("FollowUpCard", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders title and body", () => {
    mountWithFetch(() => ({ status: 200, body: {} }));
    renderCard();
    expect(screen.getByText(/Follow up with Alice/i)).toBeTruthy();
    expect(screen.getByText(/12 days ago/)).toBeTruthy();
  });

  it("click Done calls acknowledge API", async () => {
    const calls = mountWithFetch(({ url, method }) => {
      if (method === "POST" && url.includes("/acknowledge"))
        return { status: 200, body: {} };
      return { status: 200, body: {} };
    });
    const onAck = vi.fn();
    renderCard(onAck);

    fireEvent.click(screen.getByText(/^Done$/));

    await waitFor(() => {
      const hit = calls.find(
        (c) => c.method === "POST" && c.url.includes("/c1/acknowledge"),
      );
      expect(hit).toBeTruthy();
      expect(hit?.body).toContain('"done"');
    });
    await waitFor(() => expect(onAck).toHaveBeenCalled());
  });

  it("click person navigates to /people/:id", async () => {
    mountWithFetch(() => ({ status: 200, body: {} }));
    renderCard();
    fireEvent.click(screen.getByText("View person"));
    await waitFor(() => {
      expect(screen.getByTestId("sentinel").textContent).toBe("/people/p1");
    });
  });

  it("snooze picker opens on Remind me later", () => {
    mountWithFetch(() => ({ status: 200, body: {} }));
    renderCard();
    fireEvent.click(screen.getByText(/Remind me later/i));
    expect(screen.getByText("Tomorrow")).toBeTruthy();
    expect(screen.getByText("Next week")).toBeTruthy();
  });
});
