import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../../api/client";
import {
  analyzeReferenceWork,
  fetchReferenceEpisodes,
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
});
