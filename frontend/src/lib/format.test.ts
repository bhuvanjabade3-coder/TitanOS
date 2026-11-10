import { describe, expect, it } from "vitest";
import { formatBytes, formatUptime, rate } from "./format";

describe("formatBytes", () => {
  it("scales units", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(1023)).toBe("1023 B");
    expect(formatBytes(1024)).toBe("1.0 KB");
    expect(formatBytes(8 * 1024 ** 3)).toBe("8.0 GB");
  });
  it("refuses to invent a value for bad input", () => {
    expect(formatBytes(NaN)).toBe("—");
    expect(formatBytes(-1)).toBe("—");
  });
});

describe("rate", () => {
  it("derives bytes per second", () => expect(rate(1000, 3000, 2)).toBe(1000));
  it("returns null without a baseline or after a counter reset", () => {
    expect(rate(undefined, 10, 1)).toBeNull();
    expect(rate(100, 10, 1)).toBeNull();
    expect(rate(1, 2, 0)).toBeNull();
  });
});

describe("formatUptime", () => {
  it("formats", () => {
    expect(formatUptime(0, 59)).toBe("0m");
    expect(formatUptime(0, 3 * 3600 + 120)).toBe("3h 2m");
    expect(formatUptime(0, 2 * 86400 + 3600)).toBe("2d 1h");
  });
});
