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

  it("provides project-scoped structure query keys", () => {
    expect(projectQueryKeys.outline("A")).toEqual(["project", "A", "outline"]);
    expect(projectQueryKeys.episode("A", 1)).toEqual([
      "project",
      "A",
      "episode",
      1,
    ]);
    expect(projectQueryKeys.episodeView("A", 1)).toEqual([
      "project",
      "A",
      "episode-view",
      1,
    ]);
    expect(projectQueryKeys.scene("A", 1)).toEqual([
      "project",
      "A",
      "scene",
      1,
    ]);
  });
});
