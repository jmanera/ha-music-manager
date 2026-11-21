import { describe, expect, it } from "vitest";

import { albumKey, formatBytes, formatDuration, formatSpeed } from "./format";

describe("formatBytes", () => {
  it.each([
    [0, "0 B"],
    [512, "512 B"],
    [1536, "1.5 KB"],
    [350 * 1024 ** 2, "350 MB"],
    [1.25 * 1024 ** 3, "1.3 GB"],
    [5 * 1024 ** 5, "5120 TB"],
  ])("%d → %s", (bytes, expected) => {
    expect(formatBytes(bytes)).toBe(expected);
  });

  it("formats speeds", () => {
    expect(formatSpeed(2 * 1024 ** 2)).toBe("2.0 MB/s");
  });
});

describe("formatDuration", () => {
  it.each([
    [0, ""],
    [59, "0:59"],
    [284, "4:44"],
    [3 * 3600 + 5 * 60 + 7, "3:05:07"],
  ])("%d → %s", (seconds, expected) => {
    expect(formatDuration(seconds)).toBe(expected);
  });
});

it("albumKey separates user and folder", () => {
  expect(albumKey({ username: "a", directory: "b\\c" })).not.toBe(
    albumKey({ username: "a\\b", directory: "c" }),
  );
});
