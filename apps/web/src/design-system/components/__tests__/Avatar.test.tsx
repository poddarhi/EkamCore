import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import Avatar from "../Avatar";

describe("Avatar", () => {
  it("renders image when src provided", () => {
    render(<Avatar src="/photo.jpg" name="John" />);
    const img = screen.getByAltText("John");
    expect(img).toBeInTheDocument();
    expect(img).toHaveAttribute("src", "/photo.jpg");
  });

  it("renders initials when name provided without src", () => {
    render(<Avatar name="Jane Doe" />);
    expect(screen.getByText("JD")).toBeInTheDocument();
  });

  it("renders fallback icon when no src or name", () => {
    render(<Avatar />);
    expect(screen.getByLabelText("User avatar")).toBeInTheDocument();
  });

  it("renders all sizes without error", () => {
    const sizes = ["sm", "md", "lg", "xl"] as const;
    for (const size of sizes) {
      const { unmount } = render(<Avatar name="Test User" size={size} />);
      expect(screen.getByText("TU")).toBeInTheDocument();
      unmount();
    }
  });
});
