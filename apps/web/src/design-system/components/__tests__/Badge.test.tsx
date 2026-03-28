import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import Badge from "../Badge";

describe("Badge", () => {
  it("renders with children", () => {
    render(<Badge variant="high">High confidence</Badge>);
    expect(screen.getByText("High confidence")).toBeInTheDocument();
  });

  it("renders all variants without error", () => {
    const variants = ["high", "medium", "low", "info", "success", "warning", "error"] as const;
    for (const variant of variants) {
      const { unmount } = render(<Badge variant={variant}>{variant}</Badge>);
      expect(screen.getByText(variant)).toBeInTheDocument();
      unmount();
    }
  });
});
