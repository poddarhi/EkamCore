/**
 * Tests for PhotoIntelligenceSettings (S11-004).
 *
 * Covers:
 *  - State A: consent inactive → Enable button visible, Disable absent
 *  - State B: consent active → Disable button visible, Enable absent
 *  - Disable confirmation requires explicit click (two-step destructive flow)
 *  - Feature flag gating: photos_enabled=false → FeatureComingSoon
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { SWRConfig } from "swr";

// ── Mocks ──────────────────────────────────────────────────────────────

const apiFetchMock = vi.fn();
const swrFetcherMock = vi.fn();
const useFlagMock = vi.fn();

vi.mock("../../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../../api/client")>(
    "../../../api/client",
  );
  return {
    ...actual,
    apiFetch: (url: string, opts?: RequestInit) => apiFetchMock(url, opts),
    swrFetcher: (url: string) => swrFetcherMock(url),
  };
});

vi.mock("../../../contexts/FlagContext", () => ({
  useFlag: (key: string) => useFlagMock(key),
  FlagProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

// Import the component AFTER mocks are installed
import PhotoIntelligenceSettings from "../PhotoIntelligenceSettings";

/**
 * Wrap the component in a fresh SWRConfig per test so the global
 * cache doesn't leak state between tests. dedupingInterval=0 also
 * prevents SWR from returning a stale value before the fetcher runs.
 */
function renderWithFreshSwr() {
  return render(
    <SWRConfig
      value={{
        provider: () => new Map(),
        dedupingInterval: 0,
        revalidateOnFocus: false,
        revalidateOnReconnect: false,
      }}
    >
      <PhotoIntelligenceSettings />
    </SWRConfig>,
  );
}

// Helpers
function mockConsentState(accepted: boolean) {
  swrFetcherMock.mockImplementation(async () => ({
    accepted,
    version: accepted ? "v1.0-DRAFT-2026-04" : null,
    granted_at: accepted ? "2026-04-12T00:00:00Z" : null,
    revoked_at: null,
    current_text_version: "v1.0-DRAFT-2026-04",
    current_text: "Consent text body.",
  }));
}

beforeEach(() => {
  apiFetchMock.mockReset();
  swrFetcherMock.mockReset();
  useFlagMock.mockReset();
  useFlagMock.mockReturnValue(true); // default: photos_enabled
});

// ── Tests ──────────────────────────────────────────────────────────────

describe("PhotoIntelligenceSettings", () => {
  it("renders FeatureComingSoon when photos_enabled=false", async () => {
    useFlagMock.mockReturnValue(false);
    mockConsentState(false);
    renderWithFreshSwr();
    await waitFor(() => {
      expect(screen.getByText(/is on the way/i)).toBeInTheDocument();
    });
  });

  it("State A: renders Enable button when consent is inactive", async () => {
    mockConsentState(false);
    renderWithFreshSwr();

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Enable Face Clustering/i }),
      ).toBeInTheDocument();
    });

    expect(
      screen.queryByRole("button", { name: /Disable Face Clustering/i }),
    ).toBeNull();
  });

  it("State B: renders Disable button when consent is active", async () => {
    mockConsentState(true);
    renderWithFreshSwr();

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Disable Face Clustering/i }),
      ).toBeInTheDocument();
    });

    expect(
      screen.queryByRole("button", { name: /^Enable Face Clustering$/i }),
    ).toBeNull();
  });

  it("State B: disable button opens a confirmation modal before calling DELETE", async () => {
    mockConsentState(true);
    renderWithFreshSwr();

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Disable Face Clustering/i }),
      ).toBeInTheDocument();
    });

    // Click disable — should NOT yet call DELETE
    await userEvent.click(
      screen.getByRole("button", { name: /Disable Face Clustering/i }),
    );
    expect(apiFetchMock).not.toHaveBeenCalled();

    // Confirmation modal appears
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /Disable face clustering/i }),
      ).toBeInTheDocument();
    });

    // Cancel should NOT call DELETE
    await userEvent.click(screen.getByRole("button", { name: /^Cancel$/i }));
    expect(apiFetchMock).not.toHaveBeenCalled();

    // Re-open and confirm
    await userEvent.click(
      screen.getByRole("button", { name: /Disable Face Clustering/i }),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: /Disable face clustering/i }),
      ).toBeInTheDocument(),
    );

    apiFetchMock.mockResolvedValueOnce({
      detection_count: 5,
      cluster_count: 2,
      qdrant_point_count: 5,
      duration_ms: 100,
    });

    await userEvent.click(
      screen.getByRole("button", { name: /Yes, delete all face data/i }),
    );

    await waitFor(() => {
      expect(apiFetchMock).toHaveBeenCalledWith(
        "/api/v1/settings/face-clustering/consent",
        { method: "DELETE" },
      );
    });
  });
});
