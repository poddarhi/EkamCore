/**
 * PackSettingsPage tests (S14-010).
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { SWRConfig } from "swr";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FlagProvider } from "../../../contexts/FlagContext";
import PackSettingsPage from "../PackSettingsPage";

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

function renderPage(flagOverrides?: Record<string, boolean>) {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <FlagProvider overrides={flagOverrides}>
        <MemoryRouter initialEntries={["/settings/pack"]}>
          <Routes>
            <Route path="/settings/pack" element={<PackSettingsPage />} />
            <Route path="/settings/photo-intelligence" element={<div>PHOTO</div>} />
          </Routes>
        </MemoryRouter>
      </FlagProvider>
    </SWRConfig>,
  );
}

describe("PackSettingsPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows prerequisite message when face clustering is off", async () => {
    mountWithFetch(() => ({
      status: 200,
      body: { settings: {}, registry: {} },
    }));
    renderPage({ face_clustering_enabled: false, pla_pack_enabled: false });
    await waitFor(() => {
      expect(screen.getByText(/requires face clustering/i)).toBeTruthy();
    });
  });

  it("shows enable CTA when face clustering on but PLA off", async () => {
    mountWithFetch(() => ({
      status: 200,
      body: { settings: {}, registry: {} },
    }));
    renderPage({ face_clustering_enabled: true, pla_pack_enabled: false });
    await waitFor(() => {
      expect(screen.getByText(/Enable PLA/i)).toBeTruthy();
    });
  });

  it("shows full config when PLA is enabled", async () => {
    mountWithFetch(({ url }) => {
      if (url.startsWith("/api/v1/settings"))
        return {
          status: 200,
          body: {
            settings: {
              pla_follow_ups_enabled: true,
              pla_weekly_summary_enabled: true,
              pla_relationship_reminders_enabled: false,
              "pack.pla.follow_up_lookback_days": 7,
              "pack.pla.daily_run_time": "06:00",
            },
            registry: {},
          },
        };
      if (url.includes("/packs/pla/runs"))
        return { status: 200, body: { items: [] } };
      return { status: 200, body: {} };
    });
    renderPage({
      face_clustering_enabled: true,
      pla_pack_enabled: true,
    });
    const title = await screen.findByTestId("pack-settings-title");
    expect(title.textContent).toContain("Personal Life Assistant");
    expect(screen.getByText(/Follow-up suggestions/i)).toBeTruthy();
    expect(screen.getByText(/Disable PLA/i)).toBeTruthy();
  });

  it("enable PLA PATCHes settings", async () => {
    const calls = mountWithFetch(({ url, method }) => {
      if (method === "PATCH")
        return { status: 200, body: { settings: {}, registry: {} } };
      return { status: 200, body: { settings: {}, registry: {} } };
    });
    renderPage({ face_clustering_enabled: true, pla_pack_enabled: false });
    await waitFor(() => screen.getByText(/Enable PLA/i));
    fireEvent.click(screen.getByText(/Enable PLA/i));
    await waitFor(() => {
      const hit = calls.find(
        (c) => c.method === "PATCH" && c.url.includes("/settings"),
      );
      expect(hit).toBeTruthy();
      expect(hit?.body).toContain("pla_pack_enabled");
    });
  });
});
