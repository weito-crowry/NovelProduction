import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../../api/client";
import { fetchCharacters } from "../characters/characterApi";
import {
  fetchDraftDocument,
  fetchDraftAuthoringHtml,
  fetchDraftHistory,
  fetchDraftWeb,
  fetchAllCharacters,
  fetchFreshLatestDocument,
  fetchNarouExport,
  restoreDraft,
  saveDraftHtml,
} from "./manuscriptApi";

vi.mock("../../api/client", () => ({ apiRequest: vi.fn() }));
vi.mock("../characters/characterApi", () => ({ fetchCharacters: vi.fn() }));

const requestMock = vi.mocked(apiRequest);
const charactersMock = vi.mocked(fetchCharacters);

const character = {
  id: 1,
  work_id: 7,
  character_key: "hero",
  display_name: "主人公",
  entity_type: "person",
  description: "",
  birth_date: null,
  death_date: null,
  physical_description: "",
  occupation: "",
  core_beliefs: "",
  goals: "",
  fears: "",
  personality: "",
  speech_style: "",
  ai_attitude: "",
  genetic_modification_attitude: "",
  private_notes: "",
  profile_json: "{}",
  canon_status: "draft",
  version: 1,
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
};

describe("Phase E manuscript API adapter", () => {
  beforeEach(() => {
    requestMock.mockReset();
    requestMock.mockResolvedValue(null);
    charactersMock.mockReset();
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

  it("requests the selected emotions authoring projection at an explicit revision", async () => {
    await fetchDraftAuthoringHtml("A", 2, 5);

    expect(requestMock).toHaveBeenCalledWith(
      "/api/v1/projects/A/episodes/2/draft?revision=5&format=html&annotation_projection=selected&annotation_keys=emotions",
      { projectId: "A" },
    );
  });

  it("sends an HTML-only normal save payload", async () => {
    await saveDraftHtml("A", 2, {
      html: "<p>本文</p>",
      expected_parent_draft_id: 8,
      source_agent: "webui",
      change_summary: "Edit manuscript",
    });

    expect(requestMock).toHaveBeenCalledWith(
      "/api/v1/projects/A/episodes/2/drafts",
      {
        method: "POST",
        body: {
          html: "<p>本文</p>",
          expected_parent_draft_id: 8,
          source_agent: "webui",
          change_summary: "Edit manuscript",
        },
        projectId: "A",
      },
    );
  });

  it("loads all work characters in bounded pages", async () => {
    const firstPage = Array.from({ length: 100 }, (_, index) => ({
      ...character,
      id: index + 1,
      character_key: `character-${index + 1}`,
    }));
    const lastPage = [{ ...character, id: 101, character_key: "last" }];
    charactersMock.mockResolvedValueOnce(firstPage).mockResolvedValueOnce(lastPage);

    await expect(fetchAllCharacters("A")).resolves.toHaveLength(101);
    expect(charactersMock.mock.calls).toEqual([
      ["A", 100, 0],
      ["A", 100, 100],
    ]);
  });

  it("stops when a character page repeats", async () => {
    const page = Array.from({ length: 100 }, (_, index) => ({
      ...character,
      id: index + 1,
      character_key: `character-${index + 1}`,
    }));
    charactersMock.mockResolvedValueOnce(page).mockResolvedValueOnce(page);

    await expect(fetchAllCharacters("A")).resolves.toHaveLength(100);
    expect(charactersMock).toHaveBeenCalledTimes(2);
  });
});
