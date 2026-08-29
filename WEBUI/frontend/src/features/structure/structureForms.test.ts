import { describe, expect, it } from "vitest";
import type { ChapterRecord, EpisodeRecord } from "../../api/types";
import {
  buildChapterUpdate,
  buildEpisodeUpdate,
  chapterToForm,
  episodeToForm,
} from "./structureForms";

const chapter: ChapterRecord = {
  id: 1,
  work_id: 7,
  position: 1,
  title: "Chapter",
  summary: "Summary",
  purpose: "Purpose",
  canon_status: "draft",
  production_status: "planned",
  version: 4,
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
};

const episode: EpisodeRecord = {
  id: 2,
  work_id: 7,
  chapter_id: 1,
  position: 1,
  title: "Episode",
  summary: "Summary",
  purpose: "Purpose",
  foreshadowing_notes_json: '[{"clue":true}]',
  canon_status: "draft",
  production_status: "planned",
  version: 8,
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
};

describe("narrative editor form payloads", () => {
  it("sends only changed chapter fields with expected version and trimmed reason", () => {
    const values = { ...chapterToForm(chapter), summary: "Changed", reason: "  Why  " };
    expect(buildChapterUpdate(values, chapter)).toEqual({
      expected_version: 4,
      summary: "Changed",
      reason: "Why",
    });
  });

  it("does not create a mutation payload for a reason-only edit", () => {
    expect(buildChapterUpdate({ ...chapterToForm(chapter), reason: "Only metadata" }, chapter)).toBeNull();
  });

  it("pretty prints stored episode JSON and sends parsed JSON only when it changes", () => {
    const values = { ...episodeToForm(episode), foreshadowing_notes_json: '[\n  {\n    "clue": false\n  }\n]', reason: "update clue" };
    expect(buildEpisodeUpdate(values, episode)).toEqual({
      expected_version: 8,
      foreshadowing_notes: [{ clue: false }],
      reason: "update clue",
    });
  });

  it("rejects invalid episode JSON before a request can be built", () => {
    expect(() => buildEpisodeUpdate({ ...episodeToForm(episode), foreshadowing_notes_json: "{broken" }, episode)).toThrow("Enter valid JSON.");
  });

  it.each(["{}", "null", '"text"', "42", "true"])(
    "rejects non-array episode notes before update: %s",
    (foreshadowing_notes_json) => {
      expect(() => buildEpisodeUpdate({ ...episodeToForm(episode), foreshadowing_notes_json }, episode)).toThrow(
        "Foreshadowing notes must be a JSON array.",
      );
    },
  );

  it("accepts empty and populated arrays for an episode update", () => {
    expect(buildEpisodeUpdate({ ...episodeToForm(episode), foreshadowing_notes_json: "[]" }, episode)).toEqual({
      expected_version: 8,
      foreshadowing_notes: [],
    });
    expect(buildEpisodeUpdate({ ...episodeToForm(episode), foreshadowing_notes_json: '[{"clue":true}]' }, episode)).toEqual({
      expected_version: 8,
      foreshadowing_notes: [{ clue: true }],
    });
  });
});
