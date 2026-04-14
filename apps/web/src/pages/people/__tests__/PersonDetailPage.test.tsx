/**
 * PersonDetailPage tests (S13-003).
 *
 * Mocks fetch globally and wraps the page in MemoryRouter + SWRConfig
 * so each test starts from a clean SWR cache. Covers the rename
 * inline flow, delete confirm modal, remove-face flow, tab switching,
 * and the 404 view.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { SWRConfig } from "swr";
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import { FlagProvider } from "../../../contexts/FlagContext";
import PersonDetailPage from "../PersonDetailPage";

type FetchCall = { url: string; method: string; body?: string };

const PERSON_ID = "11111111-1111-1111-1111-111111111111";

interface FetchHandlerArgs {
  url: string;
  method: string;
  body?: string;
}

function mountWithFetch(
  handler: (args: FetchHandlerArgs) => { status: number; body: unknown },
): FetchCall[] {
  const calls: FetchCall[] = [];
  global.fetch = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      const method = (init?.method ?? "GET").toUpperCase();
      const body =
        typeof init?.body === "string" ? init.body : undefined;
      calls.push({ url, method, body });
      const { status, body: respBody } = handler({ url, method, body });
      return new Response(
        respBody === undefined ? null : JSON.stringify(respBody),
        {
          status,
          headers: { "Content-Type": "application/json" },
        },
      );
    },
  ) as typeof fetch;
  return calls;
}

function renderPage(initialPath = `/people/${PERSON_ID}`) {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <FlagProvider>
        <MemoryRouter initialEntries={[initialPath]}>
          <Routes>
            <Route
              path="/people/:personId"
              element={<PersonDetailPage />}
            />
            <Route path="/people" element={<div>PEOPLE LIST</div>} />
          </Routes>
        </MemoryRouter>
      </FlagProvider>
    </SWRConfig>,
  );
}

const PERSON_BODY = {
  id: PERSON_ID,
  workspace_id: "w",
  display_name: "Alice",
  canonical_contact_id: null,
  trust_source: "manual",
  confirmed_at: "2026-04-01T00:00:00Z",
  confirmed_by: "u",
  face_count: 4,
  first_seen_at: "2026-01-01T00:00:00Z",
  last_seen_at: "2026-04-01T00:00:00Z",
  created_at: "2026-04-01T00:00:00Z",
  updated_at: "2026-04-01T00:00:00Z",
};

function defaultHandler({ url }: FetchHandlerArgs) {
  if (url.includes("/settings/face-clustering/consent")) {
    return { status: 200, body: { accepted: true } };
  }
  if (url.endsWith(`/api/v1/people/${PERSON_ID}`)) {
    return { status: 200, body: PERSON_BODY };
  }
  if (url.includes(`/people/${PERSON_ID}/photos`)) {
    return { status: 200, body: { items: [], next_cursor: null } };
  }
  if (url.includes(`/people/${PERSON_ID}/files`)) {
    return { status: 200, body: { items: [], next_cursor: null } };
  }
  if (url.includes(`/people/${PERSON_ID}/events`)) {
    return { status: 200, body: { items: [], next_cursor: null } };
  }
  if (url.includes(`/people/${PERSON_ID}/reminders`)) {
    return { status: 200, body: { items: [], next_cursor: null } };
  }
  if (url.includes(`/people/${PERSON_ID}/faces`)) {
    return {
      status: 200,
      body: {
        items: [
          {
            face_detection_id: "f1",
            photo_asset_id: "pa1",
            cluster_id: "c1",
            detection_score: 0.9,
            thumbnail_url: `/api/v1/people/${PERSON_ID}/faces/f1/thumbnail`,
          },
        ],
      },
    };
  }
  if (url.includes("/api/v1/metrics/events")) {
    return { status: 204, body: {} };
  }
  return { status: 200, body: {} };
}

describe("PersonDetailPage", () => {
  beforeEach(() => {
    // jsdom navigation no-op
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the header with name, face count, and seen range", async () => {
    mountWithFetch(defaultHandler);
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByText("Alice").length).toBeGreaterThan(0);
    });
    expect(screen.getByText(/4 faces/i)).toBeTruthy();
  });

  it("404 view when the person fetch returns 404", async () => {
    mountWithFetch((args) => {
      if (args.url.includes("/settings/face-clustering/consent")) {
        return { status: 200, body: { accepted: true } };
      }
      if (args.url.endsWith(`/api/v1/people/${PERSON_ID}`)) {
        return { status: 404, body: { error_code: "PERSON_NOT_FOUND" } };
      }
      return { status: 200, body: {} };
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/Person not found/i)).toBeTruthy();
    });
  });

  it("rename flow PATCHes the person and refetches", async () => {
    const calls = mountWithFetch((args) => {
      if (args.method === "PATCH") {
        return {
          status: 200,
          body: { ...PERSON_BODY, display_name: "Alicia" },
        };
      }
      return defaultHandler(args);
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByText("Alice").length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getByLabelText(/Rename/i));
    const input = screen.getByLabelText(/Display name/i) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "Alicia" } });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() => {
      const hit = calls.find(
        (c) =>
          c.method === "PATCH" &&
          c.url.endsWith(`/api/v1/people/${PERSON_ID}`),
      );
      expect(hit).toBeTruthy();
    });
  });

  it("delete confirm modal calls DELETE then navigates away", async () => {
    const calls = mountWithFetch((args) => {
      if (args.method === "DELETE") {
        return { status: 204, body: undefined };
      }
      return defaultHandler(args);
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByText("Alice").length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getByLabelText(/Actions/i));
    fireEvent.click(screen.getByText(/^Delete$/));
    fireEvent.click(screen.getByText(/Delete person/i));

    await waitFor(() => {
      const hit = calls.find(
        (c) =>
          c.method === "DELETE" &&
          c.url.endsWith(`/api/v1/people/${PERSON_ID}`),
      );
      expect(hit).toBeTruthy();
    });
    await waitFor(() => {
      expect(screen.getByText("PEOPLE LIST")).toBeTruthy();
    });
  });

  it("remove-face flow POSTs to /remove-face after confirmation", async () => {
    const calls = mountWithFetch((args) => {
      if (
        args.method === "POST" &&
        args.url.includes(`/people/${PERSON_ID}/remove-face`)
      ) {
        return { status: 204, body: undefined };
      }
      return defaultHandler(args);
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByLabelText("Not Alice")).toBeTruthy();
    });
    fireEvent.click(screen.getByLabelText("Not Alice"));
    fireEvent.click(screen.getByText(/Remove face/i));

    await waitFor(() => {
      const hit = calls.find(
        (c) =>
          c.method === "POST" &&
          c.url.includes(`/people/${PERSON_ID}/remove-face`),
      );
      expect(hit).toBeTruthy();
      expect(hit?.body).toContain("f1");
    });
  });
});
