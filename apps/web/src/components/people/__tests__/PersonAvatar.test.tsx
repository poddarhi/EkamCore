/**
 * PersonAvatar tests (S13-002).
 *
 * Verify the happy path (image mounted with avatar URL) and the
 * fallback path (onError fires → initials render).
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import PersonAvatar from "../PersonAvatar";

const PERSON = { id: "11111111-1111-1111-1111-111111111111", display_name: "Alice Smith" };

describe("PersonAvatar", () => {
  it("renders an <img> pointing at the avatar endpoint by default", () => {
    render(<PersonAvatar person={PERSON} size="lg" />);
    const img = screen.getByAltText("Alice Smith") as HTMLImageElement;
    expect(img.tagName).toBe("IMG");
    expect(img.getAttribute("src")).toContain(`/api/v1/people/${PERSON.id}/avatar`);
  });

  it("falls back to initials when the image fails to load", () => {
    render(<PersonAvatar person={PERSON} size="md" />);
    const img = screen.getByAltText("Alice Smith");
    fireEvent.error(img);
    // After the onError handler trips, the design-system Avatar
    // renders a <span> with the two-letter initials.
    expect(screen.getByLabelText("Alice Smith").tagName).toBe("SPAN");
    expect(screen.getByLabelText("Alice Smith").textContent).toBe("AS");
  });

  it("renders name alongside avatar when showName=true", () => {
    render(<PersonAvatar person={PERSON} size="sm" showName />);
    expect(screen.getByText("Alice Smith")).toBeTruthy();
  });
});
