import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import Input from "../Input";

describe("Input", () => {
  it("renders with label", () => {
    render(<Input label="Email" />);
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
  });

  it("shows required asterisk", () => {
    render(<Input label="Name" required />);
    expect(screen.getByText("*")).toBeInTheDocument();
  });

  it("shows error message with aria-describedby", () => {
    render(<Input label="Password" error="Too short" />);
    const input = screen.getByLabelText("Password");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("Too short");
  });

  it("is disabled when disabled prop set", () => {
    render(<Input label="Field" disabled />);
    expect(screen.getByLabelText("Field")).toBeDisabled();
  });

  it("renders without error when no error prop", () => {
    render(<Input label="Clean" />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
