import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../../api/client";
import {
  fetchDraftDocument,
  fetchDraftHistory,
  fetchDraftWeb,
  fetchFreshLatestDocument,
  fetchNarouExport,
  restoreDraft,
} from "./manuscriptApi";

vi.mock("../../api/client", () => ({ apiRequest: vi.fn() }));

const requestMock = vi.mocked(apiRequest);

describe("Phase E manuscript API adapter", () => {
  beforeEach(() => {
    requestMock.mockReset();
    requestMock.mockResolvedValue(null);
  });

  it("builds document requests with only the optional historical revision", async () => {
    await fetchDraftDocument("A", 2);
    await fetchDraftDocument("A", 2, 4);

    expect(requestMock.mock.calls[0]).toEqual([
      "/api/v1/projects/A/episodes/2/draft?format=document",
      { projectId: "A" },
    ]);
    expect(requestMock.mock.calls[1]).toEqual([
      "/api/v1/projects/A/episodes/2/draft?format=document&revision=4",
      { projectId: "A" },
    ]);
  });

  it("uses a no-store request for the freshness source", async () => {
    await fetchFreshLatestDocument("A", 2);

    expect(requestMock).toHaveBeenCalledWith(
      "/api/v1/projects/A/episodes/2/draft?format=document",
      { projectId: "A", cache: "no-store" },
    );
  });

  it("pins web and export reads to explicit revisions", async () => {
    await fetchDraftWeb("A", 2, 5, false);
    await fetchDraftWeb("A", 2, 5, true);
    await fetchNarouExport("A", 2, 5);

    expect(requestMock.mock.calls.map(([path]) => path)).toEqual([
      "/api/v1/projects/A/episodes/2/draft?revision=5&format=web&include_notes=false",
      "/api/v1/projects/A/episodes/2/draft?revision=5&format=web&include_notes=true",
      "/api/v1/projects/A/episodes/2/draft/export?revision=5&format=narou",
    ]);
  });

  it("keeps history metadata and restore payload separate from DraftRead", async () => {
    await fetchDraftHistory("A", 2, 30);
    await restoreDraft("A", 2, {
      restore_revision: 3,
      expected_parent_draft_id: 8,
      source_agent: "webui",
      change_summary: "Restore revision 3",
    });

    expect(requestMock.mock.calls[0]).toEqual([
      "/api/v1/projects/A/episodes/2/drafts?limit=30",
      { projectId: "A" },
    ]);
    expect(requestMock.mock.calls[1]).toEqual([
      "/api/v1/projects/A/episodes/2/drafts",
      {
        method: "POST",
        body: {
          restore_revision: 3,
          expected_parent_draft_id: 8,
          source_agent: "webui",
          change_summary: "Restore revision 3",
        },
        projectId: "A",
      },
    ]);
  });
});
