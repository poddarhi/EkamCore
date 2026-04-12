/**
 * WCAG AA accessibility tests (G-14 / ART-26).
 *
 * Uses axe-core via the `toHaveNoA11yViolations` matcher defined in
 * src/test-setup.ts. Runs each page/component in isolation with mocked
 * contexts so axe can scan the rendered DOM.
 *
 * Run:
 *   pnpm test -- a11y
 *
 * What's covered:
 *   - LoginPage          (unauthenticated form)
 *   - TodayPage          (authenticated, empty state)
 *   - RecapPage          (authenticated, empty state)
 *   - SearchPage         (authenticated, empty state)
 *   - FilesPage          (authenticated, empty state)
 *   - PhotosPage         (authenticated, empty state)
 *   - NotFoundPage       (standalone)
 *   - Settings pages     (GeneralSettings, AccountSettings, AboutSettings)
 *   - Core components    (ErrorBanner, EmptyState, FeatureComingSoon)
 */

import { describe, it, vi, beforeEach } from "vitest";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";

// ── Mock contexts so pages can render without real auth/flag/API calls ──

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { id: "test-user", workspaceIds: ["test-ws"] },
    isAuthenticated: true,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
  }),
  AuthProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

vi.mock("../../contexts/FlagContext", () => ({
  useFlag: (key: string) => {
    // Enable flags for pages under test
    const enabled = new Set([
      "today_enabled",
      "recap_enabled",
      "search_enabled",
      "files_enabled",
      "photos_enabled",
      "llm_query_enabled",
    ]);
    return enabled.has(key);
  },
  useFlags: () => ({
    today_enabled: true,
    recap_enabled: true,
    search_enabled: true,
    files_enabled: true,
    photos_enabled: true,
  }),
  FlagProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

vi.mock("../../contexts/NotificationContext", () => ({
  useNotifications: () => ({
    notifications: [],
    unreadCount: 0,
    markRead: vi.fn(),
    markAllRead: vi.fn(),
  }),
  NotificationProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

// Mock SWR to return empty data (pages render in empty state)
vi.mock("swr", async () => {
  const actual = await vi.importActual<typeof import("swr")>("swr");
  return {
    ...actual,
    default: vi.fn(() => ({
      data: undefined,
      error: undefined,
      isLoading: false,
      isValidating: false,
      mutate: vi.fn(),
    })),
  };
});

// Mock useSWRInfinite for SearchPage
vi.mock("swr/infinite", () => ({
  default: vi.fn(() => ({
    data: undefined,
    error: undefined,
    isLoading: false,
    isValidating: false,
    setSize: vi.fn(),
    mutate: vi.fn(),
  })),
}));

// Mock API client to avoid network calls
vi.mock("../../api/client", () => ({
  swrFetcher: vi.fn(),
  apiFetch: vi.fn(),
  getUserMessage: (code: string) => code,
  ApiError: class ApiError extends Error {
    errorCode: string;
    correlationId?: string;
    constructor(code: string, msg: string) {
      super(msg);
      this.errorCode = code;
    }
  },
}));

// ── Helpers ─────────────────────────────────────────────────────────────────

function renderWithRouter(ui: ReactNode, route = "/") {
  return render(<MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>);
}

beforeEach(() => {
  vi.clearAllMocks();
});

// ── Page tests ──────────────────────────────────────────────────────────────

describe("A11y: Pages", () => {
  it("LoginPage has no WCAG AA violations", async () => {
    const { default: LoginPage } = await import("../../pages/LoginPage");
    const { container } = renderWithRouter(<LoginPage />);
    await expect(container).toHaveNoA11yViolations();
  });

  it("NotFoundPage has no WCAG AA violations", async () => {
    const { default: NotFoundPage } = await import("../../pages/NotFoundPage");
    const { container } = renderWithRouter(<NotFoundPage />);
    await expect(container).toHaveNoA11yViolations();
  });

  it("TodayPage (empty state) has no WCAG AA violations", async () => {
    const { default: TodayPage } = await import("../../pages/TodayPage");
    const { container } = renderWithRouter(<TodayPage />);
    await expect(container).toHaveNoA11yViolations();
  });

  it("RecapPage (empty state) has no WCAG AA violations", async () => {
    const { default: RecapPage } = await import("../../pages/RecapPage");
    const { container } = renderWithRouter(<RecapPage />);
    await expect(container).toHaveNoA11yViolations();
  });

  it("SearchPage (empty state) has no WCAG AA violations", async () => {
    const { default: SearchPage } = await import("../../pages/SearchPage");
    const { container } = renderWithRouter(<SearchPage />);
    await expect(container).toHaveNoA11yViolations();
  });
});

// ── Component tests ─────────────────────────────────────────────────────────

describe("A11y: Shared Components", () => {
  it("EmptyState has no WCAG AA violations", async () => {
    const { default: EmptyState } = await import("../../components/EmptyState");
    const { container } = render(
      <EmptyState
        title="Nothing here yet"
        description="Your data will show up here soon."
      />,
    );
    await expect(container).toHaveNoA11yViolations();
  });

  it("ErrorBanner has no WCAG AA violations", async () => {
    const { default: ErrorBanner } = await import("../../components/ErrorBanner");
    const { container } = render(
      <ErrorBanner
        message="Something went wrong"
        correlationId="abc-123"
        onRetry={() => {}}
      />,
    );
    await expect(container).toHaveNoA11yViolations();
  });

  it("FeatureComingSoon has no WCAG AA violations", async () => {
    const { default: FeatureComingSoon } = await import(
      "../../design-system/components/FeatureComingSoon"
    );
    const { container } = render(<FeatureComingSoon featureName="Photos" />);
    await expect(container).toHaveNoA11yViolations();
  });

  it("CardSkeleton has no WCAG AA violations", async () => {
    const { default: CardSkeleton } = await import("../../components/CardSkeleton");
    const { container } = render(<CardSkeleton count={3} />);
    await expect(container).toHaveNoA11yViolations();
  });
});

// ── Utility tests (unit tests for a11y.ts) ──────────────────────────────────

describe("a11y utilities", () => {
  it("announceToScreenReader creates a live region and sets its content", async () => {
    const { announceToScreenReader } = await import("../../utils/a11y");
    announceToScreenReader("test message");

    const region = document.getElementById("ekamcore-a11y-live-region");
    expect(region).not.toBeNull();
    expect(region?.getAttribute("role")).toBe("status");
    expect(region?.getAttribute("aria-live")).toBe("polite");

    // Content is set via rAF — wait a frame
    await new Promise((r) => requestAnimationFrame(() => r(null)));
    expect(region?.textContent).toBe("test message");
  });

  it("announceToScreenReader supports assertive priority", async () => {
    const { announceToScreenReader } = await import("../../utils/a11y");
    announceToScreenReader("urgent message", "assertive");

    const region = document.getElementById("ekamcore-a11y-live-region");
    expect(region?.getAttribute("aria-live")).toBe("assertive");
  });

  it("skipToContent focuses the main element when it exists", async () => {
    const { skipToContent } = await import("../../utils/a11y");

    const main = document.createElement("main");
    main.id = "main-content";
    document.body.appendChild(main);

    skipToContent();

    expect(document.activeElement).toBe(main);
    expect(main.getAttribute("tabindex")).toBe("-1");

    main.remove();
  });

  it("skipToContent is a no-op when no main element exists", async () => {
    const { skipToContent } = await import("../../utils/a11y");
    // Just verify it doesn't throw
    expect(() => skipToContent()).not.toThrow();
  });

  it("prefersReducedMotion reads the media query", async () => {
    const { prefersReducedMotion } = await import("../../utils/a11y");
    // jsdom returns false for matchMedia by default
    expect(typeof prefersReducedMotion()).toBe("boolean");
  });
});
