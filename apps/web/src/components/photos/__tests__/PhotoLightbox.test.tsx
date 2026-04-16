/**
 * PhotoLightbox tests (S13-008).
 *
 * Mocks fetch globally and drives the lightbox through render,
 * keyboard shortcuts, and face→person navigation. A sentinel route
 * catches the navigation target so we can assert it without a real
 * page mount.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation, useParams } from "react-router-dom";
import { SWRConfig } from "swr";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import PhotoLightbox from "../PhotoLightbox";

const PHOTO_ID = "11111111-1111-1111-1111-111111111111";
const PERSON_ID = "22222222-2222-2222-2222-222222222222";
const CLUSTER_ID = "33333333-3333-3333-3333-333333333333";

const KNOWN_FACE = {
  face_detection_id: "f-known",
  bbox: { x: 0.1, y: 0.1, w: 0.2, h: 0.2 },
  detection_score: 0.95,
  cluster_id: "c-known",
  trusted_person_id: PERSON_ID,
  trusted_person_display_name: "Alice",
  trusted_person_avatar_url: `/api/v1/people/${PERSON_ID}/avatar`,
};

const UNKNOWN_FACE = {
  face_detection_id: "f-unknown",
  bbox: { x: 0.5, y: 0.5, w: 0.2, h: 0.2 },
  detection_score: 0.9,
  cluster_id: CLUSTER_ID,
  trusted_person_id: null,
  trusted_person_display_name: null,
  trusted_person_avatar_url: null,
};

interface Call {
  url: string;
  method: string;
}

function mountWithFetch(
  handler: (args: Call) => { status: number; body: unknown },
): Call[] {
  const calls: Call[] = [];
  global.fetch = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      const method = (init?.method ?? "GET").toUpperCase();
      calls.push({ url, method });
      const { status, body } = handler({ url, method });
      return new Response(
        body === undefined ? null : JSON.stringify(body),
        { status, headers: { "Content-Type": "application/json" } },
      );
    },
  ) as typeof fetch;
  return calls;
}

function NavigationSentinel() {
  const location = useLocation();
  return (
    <div data-testid="nav-sentinel">
      {location.pathname}
      {location.search}
    </div>
  );
}

function PersonStub() {
  const { personId } = useParams<{ personId: string }>();
  return <div data-testid="person-stub">PERSON {personId}</div>;
}

function ReviewStub() {
  const location = useLocation();
  return <div data-testid="review-stub">REVIEW{location.search}</div>;
}

function renderLightbox(opts: {
  onClose?: () => void;
  onNext?: () => void;
  onPrev?: () => void;
} = {}) {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <MemoryRouter initialEntries={["/photos"]}>
        <Routes>
          <Route
            path="/photos"
            element={
              <>
                <PhotoLightbox
                  open
                  photoId={PHOTO_ID}
                  onClose={opts.onClose ?? (() => {})}
                  onNext={opts.onNext}
                  onPrev={opts.onPrev}
                />
                <NavigationSentinel />
              </>
            }
          />
          <Route path="/people/:personId" element={<PersonStub />} />
          <Route path="/people/review" element={<ReviewStub />} />
        </Routes>
      </MemoryRouter>
    </SWRConfig>,
  );
}

beforeAll(() => {
  // jsdom lacks matchMedia; the lightbox's prefers-reduced-motion
  // check needs a safe stub.
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation(() => ({
      matches: false,
      addListener: vi.fn(),
      removeListener: vi.fn(),
    })),
  });
  // Stub naturalWidth/Height so the lightbox's measure() computes
  // a non-zero rendered rect.
  Object.defineProperty(HTMLImageElement.prototype, "naturalWidth", {
    configurable: true,
    get: () => 1000,
  });
  Object.defineProperty(HTMLImageElement.prototype, "naturalHeight", {
    configurable: true,
    get: () => 800,
  });
});

describe("PhotoLightbox", () => {
  beforeEach(() => {
    mountWithFetch(({ url }) => {
      if (url.includes(`/photos/${PHOTO_ID}/faces`))
        return { status: 200, body: { items: [KNOWN_FACE, UNKNOWN_FACE] } };
      return { status: 200, body: {} };
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the full-resolution image and both face overlays", async () => {
    renderLightbox();
    await waitFor(() => {
      expect(screen.getByTestId("photo-lightbox")).toBeTruthy();
    });
    const img = screen.getByTestId("photo-lightbox").querySelector("img");
    expect(img?.getAttribute("src")).toBe(`/api/v1/photos/${PHOTO_ID}/full`);

    // Trigger onLoad so the overlay layer renders.
    fireEvent.load(img!);

    await waitFor(() => {
      expect(screen.getByTestId("lightbox-faces-layer")).toBeTruthy();
    });
    expect(screen.getByTestId("lightbox-face-f-known")).toBeTruthy();
    expect(screen.getByTestId("lightbox-face-f-unknown")).toBeTruthy();
  });

  it("F toggles the face overlay layer", async () => {
    renderLightbox();
    const img = await waitFor(() =>
      screen.getByTestId("photo-lightbox").querySelector("img"),
    );
    fireEvent.load(img!);
    await waitFor(() => screen.getByTestId("lightbox-faces-layer"));

    fireEvent.keyDown(document, { key: "f" });
    await waitFor(() => {
      expect(screen.queryByTestId("lightbox-faces-layer")).toBeNull();
    });
    fireEvent.keyDown(document, { key: "F" });
    await waitFor(() => {
      expect(screen.getByTestId("lightbox-faces-layer")).toBeTruthy();
    });
  });

  it("Escape calls onClose, arrow keys fire prev/next", async () => {
    const onClose = vi.fn();
    const onNext = vi.fn();
    const onPrev = vi.fn();
    renderLightbox({ onClose, onNext, onPrev });
    await waitFor(() => screen.getByTestId("photo-lightbox"));

    fireEvent.keyDown(document, { key: "ArrowRight" });
    fireEvent.keyDown(document, { key: "ArrowLeft" });
    fireEvent.keyDown(document, { key: "Escape" });

    expect(onNext).toHaveBeenCalledTimes(1);
    expect(onPrev).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("clicking a known-face bbox navigates to the person", async () => {
    renderLightbox();
    const img = await waitFor(() =>
      screen.getByTestId("photo-lightbox").querySelector("img"),
    );
    fireEvent.load(img!);
    await waitFor(() => screen.getByTestId("lightbox-face-f-known"));

    fireEvent.click(screen.getByTestId("lightbox-face-f-known"));

    await waitFor(() => {
      expect(screen.getByTestId("person-stub").textContent).toBe(
        `PERSON ${PERSON_ID}`,
      );
    });
  });

  it("clicking an unknown-face bbox routes to review queue with highlight_cluster", async () => {
    renderLightbox();
    const img = await waitFor(() =>
      screen.getByTestId("photo-lightbox").querySelector("img"),
    );
    fireEvent.load(img!);
    await waitFor(() => screen.getByTestId("lightbox-face-f-unknown"));

    fireEvent.click(screen.getByTestId("lightbox-face-f-unknown"));

    await waitFor(() => {
      const stub = screen.getByTestId("review-stub");
      expect(stub.textContent).toContain(
        `highlight_cluster=${CLUSTER_ID}`,
      );
    });
  });
});
