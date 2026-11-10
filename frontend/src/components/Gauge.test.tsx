import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Gauge } from "./Gauge";

describe("Gauge", () => {
  it("shows the rounded value", () => {
    render(<Gauge label="CPU" percent={41.6} detail="8 cores" />);
    expect(screen.getByText("42%")).toBeTruthy();
    expect(screen.getByText("8 cores")).toBeTruthy();
  });
  it("clamps out-of-range input", () => {
    render(<Gauge label="CPU" percent={250} />);
    expect(screen.getByText("100%")).toBeTruthy();
  });
  it("shows a dash, not zero, when there is no data", () => {
    render(<Gauge label="CPU" percent={null} />);
    expect(screen.getByText("—")).toBeTruthy();
    expect(screen.queryByText("0%")).toBeNull();
  });
});
