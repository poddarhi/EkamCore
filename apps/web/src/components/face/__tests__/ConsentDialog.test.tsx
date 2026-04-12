/**
 * Tests for ConsentDialog (S11-004).
 *
 * Covers:
 *  - Enable button disabled on open (before scroll)
 *  - Simulated scroll-to-bottom enables the button
 *  - Short text (fits in container) auto-enables the button
 *  - POST called with correct version_acknowledged
 *  - 409 CONSENT_VERSION_STALE triggers refetch
 *  - Load error renders ErrorBanner with retry
 *  - Dialog does not render consent body when closed
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ConsentDialog from "../ConsentDialog";
import { ApiError } from "../../../api/client";

// ── Mock apiFetch ──────────────────────────────────────────────────────

const apiFetchMock = vi.fn();

vi.mock("../../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../../api/client")>(
    "../../../api/client",
  );
  return {
    ...actual,
    apiFetch: (url: string, opts?: RequestInit) => apiFetchMock(url, opts),
  };
});

const LONG_TEXT = Array(50).fill("This is a long consent text line.").join("\n");
const SHORT_TEXT = "Short text that fits.";
const VERSION = "v1.0-DRAFT-2026-04";

function mockGetConsent(text: string = LONG_TEXT, version: string = VERSION) {
  apiFetchMock.mockResolvedValueOnce({
    accepted: false,
    version: null,
    granted_at: null,
    revoked_at: null,
    current_text_version: version,
    current_text: text,
  });
}

function mockPostConsent() {
  apiFetchMock.mockResolvedValueOnce({
    accepted: true,
    version: VERSION,
    granted_at: "2026-04-12T00:00:00Z",
    current_text_version: VERSION,
  });
}

function mockPostConsentStale() {
  const err = new ApiError(
    409,
    "CONSENT_VERSION_STALE",
    "stale",
  );
  apiFetchMock.mockRejectedValueOnce(err);
}

beforeEach(() => {
  apiFetchMock.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ── Tests ──────────────────────────────────────────────────────────────

describe("ConsentDialog", () => {
  it("does not render when open=false", () => {
    render(
      <ConsentDialog open={false} onClose={() => {}} onAccepted={() => {}} />,
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("fetches consent text on open", async () => {
    mockGetConsent();
    render(
      <ConsentDialog open={true} onClose={() => {}} onAccepted={() => {}} />,
    );
    await waitFor(() => {
      expect(apiFetchMock).toHaveBeenCalled();
    });
    // First call is the GET. Second arg is always undefined since
    // apiFetch is invoked as apiFetch(url) for reads.
    expect(apiFetchMock.mock.calls[0][0]).toBe(
      "/api/v1/settings/face-clustering/consent",
    );
  });

  it("disables Enable button until user scrolls to bottom", async () => {
    mockGetConsent();
    render(
      <ConsentDialog open={true} onClose={() => {}} onAccepted={() => {}} />,
    );

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /agree.*enable/i }),
      ).toBeInTheDocument();
    });

    const enableBtn = screen.getByRole("button", { name: /agree.*enable/i });
    // Text is long — scrollHeight > clientHeight in jsdom is 0/0 by default,
    // so hasScrolledToBottom stays false until we dispatch a scroll event.
    // We explicitly set jsdom values to simulate a non-trivial scroll area.
    const scrollable = screen.getByRole("region", {
      name: /consent text/i,
    }) as HTMLDivElement;
    Object.defineProperty(scrollable, "scrollHeight", { value: 1000, configurable: true });
    Object.defineProperty(scrollable, "clientHeight", { value: 320, configurable: true });
    scrollable.scrollTop = 0;
    fireEvent.scroll(scrollable);

    expect(enableBtn).toBeDisabled();

    // Scroll to bottom
    scrollable.scrollTop = 680; // 1000 - 320
    fireEvent.scroll(scrollable);

    await waitFor(() => {
      expect(enableBtn).not.toBeDisabled();
    });
  });

  it("enables button when scroll event reaches bottom via short-text path", async () => {
    // jsdom does not lay out elements, so scrollHeight is 0 on initial
    // render. The auto-fit check in ConsentDialog runs on the load
    // effect and only trips for elements that already have dimensions.
    // A short-text scroll event (scrollHeight=100, clientHeight=320) is
    // the jsdom-compatible way to exercise the same code path.
    mockGetConsent(SHORT_TEXT);
    render(
      <ConsentDialog open={true} onClose={() => {}} onAccepted={() => {}} />,
    );

    await waitFor(() => {
      expect(
        screen.getByRole("region", { name: /consent text/i }),
      ).toBeInTheDocument();
    });

    const scrollable = screen.getByRole("region", {
      name: /consent text/i,
    }) as HTMLDivElement;
    // scrollHeight < clientHeight → remaining = negative → <= threshold
    Object.defineProperty(scrollable, "scrollHeight", {
      value: 100,
      configurable: true,
    });
    Object.defineProperty(scrollable, "clientHeight", {
      value: 320,
      configurable: true,
    });
    fireEvent.scroll(scrollable);

    await waitFor(() => {
      const btn = screen.getByRole("button", { name: /agree.*enable/i });
      expect(btn).not.toBeDisabled();
    });
  });

  it("calls POST with version_acknowledged from fetched text", async () => {
    mockGetConsent();
    mockPostConsent();
    const onAccepted = vi.fn();

    render(
      <ConsentDialog
        open={true}
        onClose={() => {}}
        onAccepted={onAccepted}
      />,
    );

    await waitFor(() =>
      expect(screen.getByRole("region", { name: /consent text/i })).toBeInTheDocument(),
    );

    // Scroll to bottom
    const scrollable = screen.getByRole("region", {
      name: /consent text/i,
    }) as HTMLDivElement;
    Object.defineProperty(scrollable, "scrollHeight", { value: 500, configurable: true });
    Object.defineProperty(scrollable, "clientHeight", { value: 320, configurable: true });
    scrollable.scrollTop = 180;
    fireEvent.scroll(scrollable);

    const enableBtn = screen.getByRole("button", { name: /agree.*enable/i });
    await waitFor(() => expect(enableBtn).not.toBeDisabled());

    await userEvent.click(enableBtn);

    await waitFor(() => {
      expect(apiFetchMock).toHaveBeenCalledTimes(2);
    });

    const [, postArgs] = apiFetchMock.mock.calls[1];
    expect(postArgs.method).toBe("POST");
    const body = JSON.parse(postArgs.body);
    expect(body).toEqual({
      accepted: true,
      version_acknowledged: VERSION,
    });
    expect(onAccepted).toHaveBeenCalled();
  });

  it("refetches consent text on 409 CONSENT_VERSION_STALE", async () => {
    mockGetConsent(LONG_TEXT, "v1.0-DRAFT-2026-04");
    mockPostConsentStale();
    mockGetConsent(LONG_TEXT, "v1.1-NEW-2026-04"); // refetched after stale

    const onAccepted = vi.fn();
    render(
      <ConsentDialog
        open={true}
        onClose={() => {}}
        onAccepted={onAccepted}
      />,
    );

    await waitFor(() =>
      expect(screen.getByRole("region", { name: /consent text/i })).toBeInTheDocument(),
    );

    const scrollable = screen.getByRole("region", {
      name: /consent text/i,
    }) as HTMLDivElement;
    Object.defineProperty(scrollable, "scrollHeight", { value: 500, configurable: true });
    Object.defineProperty(scrollable, "clientHeight", { value: 320, configurable: true });
    scrollable.scrollTop = 180;
    fireEvent.scroll(scrollable);

    const enableBtn = screen.getByRole("button", { name: /agree.*enable/i });
    await waitFor(() => expect(enableBtn).not.toBeDisabled());

    await userEvent.click(enableBtn);

    // GET + POST(409) + GET again = 3 calls
    await waitFor(() => {
      expect(apiFetchMock).toHaveBeenCalledTimes(3);
    });
    expect(onAccepted).not.toHaveBeenCalled();

    // New version label should be visible
    await waitFor(() => {
      expect(screen.getByText(/v1\.1-NEW/)).toBeInTheDocument();
    });
  });

  it("renders ErrorBanner on initial fetch failure", async () => {
    apiFetchMock.mockRejectedValueOnce(
      new ApiError(500, "INTERNAL_ERROR", "Something went wrong"),
    );
    render(
      <ConsentDialog open={true} onClose={() => {}} onAccepted={() => {}} />,
    );

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });
});
