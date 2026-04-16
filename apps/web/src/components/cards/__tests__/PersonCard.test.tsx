/**
 * PersonCard tests (S13-009).
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import PersonCard from "../PersonCard";
import type { PersonPayload } from "../../../api/client";

function LocationSentinel() {
  const location = useLocation();
  return <div data-testid="sentinel">{location.pathname}</div>;
}

function renderCard(payload: PersonPayload) {
  return render(
    <MemoryRouter initialEntries={["/today"]}>
      <Routes>
        <Route
          path="/today"
          element={
            <>
              <PersonCard id="pid-1" payload={payload} surface="today" />
              <LocationSentinel />
            </>
          }
        />
        <Route path="/people/:personId" element={<LocationSentinel />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("PersonCard", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the display name and a 'seen_recently' description", () => {
    renderCard({
      source: "trusted_person",
      person_id: "pid-1",
      display_name: "Alice",
      avatar_url: "/api/v1/people/pid-1/avatar",
      context: "seen_recently",
      supporting_data: { recent_photo_count: 5, recent_days: 14 },
    });
    expect(screen.getByText("Alice")).toBeTruthy();
    expect(screen.getByText(/5 new photos/)).toBeTruthy();
  });

  it("click navigates to /people/:person_id", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(null, { status: 204 }),
    ) as typeof fetch;
    renderCard({
      source: "trusted_person",
      person_id: "pid-42",
      display_name: "Bob",
      avatar_url: null,
      context: "search_match",
    });
    fireEvent.click(screen.getAllByText("Bob")[0]);
    await waitFor(() => {
      expect(screen.getByTestId("sentinel").textContent).toBe(
        "/people/pid-42",
      );
    });
  });
});
