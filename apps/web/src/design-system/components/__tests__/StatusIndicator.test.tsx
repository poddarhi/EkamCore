import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import StatusIndicator from "../StatusIndicator";

describe("StatusIndicator", () => {
  it("renders with default label", () => {
    render(<StatusIndicator status="healthy" />);
    expect(screen.getByRole("status")).toHaveTextContent("Healthy");
  });

  it("renders with custom label", () => {
    render(<StatusIndicator status="error" label="API Down" />);
    expect(screen.getByRole("status")).toHaveTextContent("API Down");
  });

  it("renders all statuses without error", () => {
    const statuses = ["healthy", "degraded", "error", "unknown"] as const;
    for (const status of statuses) {
      const { unmount } = render(<StatusIndicator status={status} />);
      expect(screen.getByRole("status")).toBeInTheDocument();
      unmount();
    }
  });
});
