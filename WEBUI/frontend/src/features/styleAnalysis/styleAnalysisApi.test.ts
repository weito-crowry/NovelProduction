import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../../api/client";
import {
  analyzeReferenceWork,
  createStyleEntity,
  createStyleEntityAlias,
  createStyleTerm,
  createStyleTermAlias,
  fetchReferenceEpisodes,
  fetchStyleDocument,
  fetchStyleDocuments,
  fetchStyleCharacterLinks,
  fetchStyleMetrics,
  fetchStyleStructure,
  fetchStyleStructures,
  fetchStyleText,
  fetchStyleTextRevisions,
  linkStyleCharacter,
  unlinkStyleCharacter,
  mergeStyleScenes,
  selectStyleStructure,
  splitStyleScene,
  fetchStyleJob,
  importStyleFile,
  reviewFinding,
  runLint,
} from "./styleAnalysisApi";

vi.mock("../../api/client", () => ({ apiRequest: vi.fn() }));

const requestMock = vi.mocked(apiRequest);

describe("style analysis API adapter", () => {
  beforeEach(() => {
    requestMock.mockReset();
    requestMock.mockResolvedValue({});
  });

  it("keeps project scope and uses multipart for local import", async () => {
    const file = new File(["本文"], "chapter.txt", { type: "text/plain" });

    await importStyleFile("novel", "text", file);

    const [path, options] = requestMock.mock.calls[0];
    expect(path).toBe("/api/v1/projects/novel/style-analysis/imports/file");
    expect(options).toMatchObject({
      method: "POST",
      projectId: "novel",
    });
    expect(options?.body).toBeInstanceOf(FormData);
    expect((options?.body as FormData).get("source_type")).toBe("text");
    expect((options?.body as FormData).get("file")).toBe(file);
  });

  it("pins reference episodes and analysis actions to explicit API paths", async () => {
    await fetchReferenceEpisodes("novel", 7);
    await analyzeReferenceWork("novel", 7, "deterministic", true);
    await fetchStyleJob("novel", 11);

    expect(requestMock.mock.calls.map(([path]) => path)).toEqual([
      "/api/v1/projects/novel/style-analysis/reference-works/7/episodes",
      "/api/v1/projects/novel/style-analysis/reference-works/7/analyze",
      "/api/v1/projects/novel/style-analysis/jobs/11",
    ]);
    expect(requestMock.mock.calls[1][1]).toMatchObject({
      method: "POST",
      body: { preset: "deterministic", rebuild_structure: true },
      projectId: "novel",
    });
  });

  it("sends the lint revision/profile contract and finding review separately", async () => {
    await runLint("novel", 21, {
      text_revision_id: 2,
      structure_revision_id: 3,
      profile_id: 4,
      profile_version_no: 5,
      scene_id: 6,
    });
    await reviewFinding("novel", 99, "acknowledged", "確認済み");

    expect(requestMock.mock.calls[0]).toEqual([
      "/api/v1/projects/novel/style-analysis/documents/21/lint",
      {
        method: "POST",
        body: {
          text_revision_id: 2,
          structure_revision_id: 3,
          profile_id: 4,
          profile_version_no: 5,
          scene_id: 6,
        },
        projectId: "novel",
      },
    ]);
    expect(requestMock.mock.calls[1]).toEqual([
      "/api/v1/projects/novel/style-analysis/findings/99/review",
      {
        method: "POST",
        body: { status: "acknowledged", note: "確認済み" },
        projectId: "novel",
      },
    ]);
  });

  it("uses canonical document, revision, structure, and metric endpoints", async () => {
    await fetchStyleDocuments("novel");
    await fetchStyleDocument("novel", 7);
    await fetchStyleTextRevisions("novel", 7);
    await fetchStyleText("novel", 7, 8);
    await fetchStyleStructures("novel", 7);
    await fetchStyleStructure("novel", 7, 9);
    await fetchStyleMetrics("novel", 7, 9);

    expect(requestMock.mock.calls.map(([path]) => path)).toEqual([
      "/api/v1/projects/novel/style-analysis/documents",
      "/api/v1/projects/novel/style-analysis/documents/7",
      "/api/v1/projects/novel/style-analysis/documents/7/revisions",
      "/api/v1/projects/novel/style-analysis/documents/7/text?text_revision_id=8",
      "/api/v1/projects/novel/style-analysis/documents/7/structures",
      "/api/v1/projects/novel/style-analysis/documents/7/structure?structure_revision_id=9",
      "/api/v1/projects/novel/style-analysis/documents/7/metrics?structure_revision_id=9",
    ]);
  });

  it("selects a current structure through the explicit pointer endpoint", async () => {
    await selectStyleStructure("novel", 7, 9);

    expect(requestMock.mock.calls[0]).toEqual([
      "/api/v1/projects/novel/style-analysis/documents/7/structures/9/select-current",
      { method: "POST", projectId: "novel" },
    ]);
  });

  it("uses the expected revision for manual scene split and merge", async () => {
    await splitStyleScene("novel", 7, 8, {
      after_block_id: 9,
      expected_structure_revision_id: 10,
    });
    await mergeStyleScenes("novel", 7, {
      scene_id: 11,
      next_scene_id: 12,
      expected_structure_revision_id: 13,
    });

    expect(requestMock.mock.calls).toEqual([
      [
        "/api/v1/projects/novel/style-analysis/documents/7/scenes/8/split",
        {
          method: "POST",
          body: { after_block_id: 9, expected_structure_revision_id: 10 },
          projectId: "novel",
        },
      ],
      [
        "/api/v1/projects/novel/style-analysis/documents/7/scenes/merge",
        {
          method: "POST",
          body: {
            scene_id: 11,
            next_scene_id: 12,
            expected_structure_revision_id: 13,
          },
          projectId: "novel",
        },
      ],
    ]);
  });

  it("keeps semantic identity and character-link writes on their scoped endpoints", async () => {
    await createStyleEntity("novel", {
      reference_work_id: 7,
      entity_type: "person",
      canonical_name: "人物",
    });
    await createStyleEntityAlias("novel", 8, { alias: "別名", alias_kind: "name" });
    await createStyleTerm("novel", {
      document_id: 9,
      canonical_label: "用語",
      term_type: "other",
    });
    await createStyleTermAlias("novel", 10, "略称");
    await linkStyleCharacter("novel", 9, 11, 8);
    await fetchStyleCharacterLinks("novel", 9);
    await unlinkStyleCharacter("novel", 9, 11);

    expect(requestMock.mock.calls.map(([path]) => path)).toEqual([
      "/api/v1/projects/novel/style-analysis/entities",
      "/api/v1/projects/novel/style-analysis/entities/8/aliases",
      "/api/v1/projects/novel/style-analysis/terms",
      "/api/v1/projects/novel/style-analysis/terms/10/aliases",
      "/api/v1/projects/novel/style-analysis/documents/9/character-links/11",
      "/api/v1/projects/novel/style-analysis/documents/9/character-links",
      "/api/v1/projects/novel/style-analysis/documents/9/character-links/11",
    ]);
    expect(requestMock.mock.calls[6][1]).toMatchObject({ method: "DELETE", projectId: "novel" });
  });
});
