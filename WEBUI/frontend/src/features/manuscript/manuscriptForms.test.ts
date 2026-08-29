import { describe, expect, it } from "vitest";
import {
  buildDraftSave,
  emptyDraftForm,
  hasDraftChanges,
} from "./manuscriptForms";

describe("manuscript forms", () => {
  it("uses null parent for the first append and webui as the source", () => {
    expect(
      buildDraftSave({ ...emptyDraftForm(), body: "First draft" }, null),
    ).toEqual({
      body: "First draft",
      expected_parent_draft_id: null,
      source_agent: "webui",
      change_summary: "",
    });
  });

  it("uses the latest draft as parent for a later append", () => {
    const values = { ...emptyDraftForm(), body: "Second draft" };
    expect(buildDraftSave(values, { id: 8 })).toMatchObject({
      expected_parent_draft_id: 8,
      source_agent: "webui",
    });
    expect(hasDraftChanges(values, "Original", "")).toBe(true);
  });

  it("rejects an empty body before POST", () => {
    expect(() => buildDraftSave(emptyDraftForm(), null)).toThrow(
      "Body must not be empty",
    );
  });
});
