import { describe, expect, it } from "vitest";
import { projectQueryKeys } from "./queryKeys";

describe("project query keys", () => {
  it("includes project identity in every project-scoped key", () => {
    const keys = [
      projectQueryKeys.project("A"),
      projectQueryKeys.work("A"),
      projectQueryKeys.dashboard("A"),
    ];

    for (const key of keys) {
      expect(key[0]).toBe("project");
      expect(key[1]).toBe("A");
    }
  });

  it("keeps A and B project data in distinct cache keys", () => {
    expect(projectQueryKeys.work("A")).not.toEqual(projectQueryKeys.work("B"));
    expect(projectQueryKeys.dashboard("A")).not.toEqual(
      projectQueryKeys.dashboard("B"),
    );
  });
});
