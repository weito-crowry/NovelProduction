import { describe, expect, it } from "vitest";
import { projectQueryKeys } from "./queryKeys";

describe("project query keys", () => {
  it("includes project identity in every project-scoped key", () => {
    const keys = [
      projectQueryKeys.project("A"),
      projectQueryKeys.work("A"),
      projectQueryKeys.dashboard("A"),
      projectQueryKeys.episodeViews("A"),
      projectQueryKeys.scenes("A"),
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
    expect(projectQueryKeys.episodeViews("A")).toEqual([
      "project",
      "A",
      "episode-view",
    ]);
    expect(projectQueryKeys.scenes("A")).toEqual(["project", "A", "scene"]);
  });

  it("provides D3 entity and paginated query keys", () => {
    const keys = [
      projectQueryKeys.worldFacts("A", 50, 0),
      projectQueryKeys.worldFact("A", 1),
      projectQueryKeys.worldFactSearch("A", "火山", 50, 0),
      projectQueryKeys.characters("A", 50, 0),
      projectQueryKeys.character("A", 1),
      projectQueryKeys.characterSearch("A", "主人公", 50, 0),
      projectQueryKeys.relationships("A", 1),
      projectQueryKeys.characterState("A", 1, 2),
      projectQueryKeys.characterStateHistory("A", 1),
      projectQueryKeys.characterKnowledge("A", 1, 2),
      projectQueryKeys.characterKnowledgeExact("A", 1, 3, 2),
      projectQueryKeys.information("A", 50, 0),
      projectQueryKeys.informationItem("A", 1),
      projectQueryKeys.informationSearch("A", "secret", 50),
      projectQueryKeys.readerDisclosure("A", 1),
      projectQueryKeys.canonDecisions("A", 50, 0),
      projectQueryKeys.canonDecision("A", 1),
      projectQueryKeys.canonDecisionSearch("A", "reason", 50),
      projectQueryKeys.draftDocument("A", 2, "latest"),
      projectQueryKeys.draftWeb("A", 2, 3, false),
      projectQueryKeys.draftHistory("A", 2, 20),
      projectQueryKeys.timelineEvents("A", 50, 0),
      projectQueryKeys.timelineEvent("A", 1),
      projectQueryKeys.timelineEventSearch("A", "火山", 50),
      projectQueryKeys.timelineRange("A", "2104-01-01", "2104-12-31", 50),
      projectQueryKeys.timelineRelations("A", 1, 50, 0),
    ];
    for (const key of keys) {
      expect(key[0]).toBe("project");
      expect(key[1]).toBe("A");
    }
    expect(projectQueryKeys.worldFacts("A", 50, 0)).not.toEqual(
      projectQueryKeys.worldFacts("B", 50, 0),
    );
    expect(projectQueryKeys.worldFacts("A", 50, 0)).not.toEqual(
      projectQueryKeys.worldFacts("A", 50, 50),
    );
  });
});
