import { describe, expect, it } from "vitest";
import { isTerminalStyleJob } from "./useStyleJobPolling";

describe("style job terminal status", () => {
  it("treats partial analysis results as terminal", () => {
    expect(isTerminalStyleJob("partial")).toBe(true);
  });

  it("continues polling only for non-terminal jobs", () => {
    expect(isTerminalStyleJob("queued")).toBe(false);
    expect(isTerminalStyleJob("running")).toBe(false);
    expect(isTerminalStyleJob("succeeded")).toBe(true);
    expect(isTerminalStyleJob("failed")).toBe(true);
    expect(isTerminalStyleJob("cancelled")).toBe(true);
  });
});
