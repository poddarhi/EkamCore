import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import Card from "../Card";

describe("Card", () => {
  it("renders children", () => {
    render(<Card>Card content</Card>);
    expect(screen.getByText("Card content")).toBeInTheDocument();
  });

  it("is interactive when onClick is provided", () => {
    render(<Card onClick={() => {}}>Click card</Card>);
    expect(screen.getByRole("button")).toBeInTheDocument();
  });

  it("is not interactive without onClick", () => {
    render(<Card>Static card</Card>);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("calls onClick when clicked", async () => {
    const onClick = vi.fn();
    render(<Card onClick={onClick}>Click me</Card>);
    await userEvent.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("responds to keyboard activation", async () => {
    const onClick = vi.fn();
    render(<Card onClick={onClick}>Press me</Card>);
    screen.getByRole("button").focus();
    await userEvent.keyboard("{Enter}");
    expect(onClick).toHaveBeenCalledOnce();
  });
});
