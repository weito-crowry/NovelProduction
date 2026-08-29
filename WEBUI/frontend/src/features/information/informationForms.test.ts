import { describe, expect, it } from "vitest";
import {
  buildInformationCreate,
  buildInformationUpdate,
  emptyInformationForm,
  hasInformationChanges,
  toInformationForm,
} from "./informationForms";

const baseline = {
  id: 4,
  work_id: 7,
  statement: "A secret",
  truth_status: "true",
  authoring_guard: "keep private",
  notes_json: '{"source":"draft"}',
  canon_status: "draft",
  importance: 2,
  version: 3,
  created_at: "",
  updated_at: "",
};

describe("information forms", () => {
  it("sends only changed semantic fields and the loaded version", () => {
    const values = { ...toInformationForm(baseline), statement: "Updated" };
    expect(buildInformationUpdate(values, baseline)).toEqual({
      expected_version: 3,
      statement: "Updated",
    });
  });

  it("does not create a PATCH for a reason-only edit", () => {
    const values = { ...toInformationForm(baseline), reason: "explanation" };
    expect(hasInformationChanges(values, baseline)).toBe(false);
    expect(buildInformationUpdate(values, baseline)).toBeNull();
  });

  it("parses notes JSON and rejects invalid JSON before a request", () => {
    expect(
      buildInformationCreate({
        ...emptyInformationForm(),
        statement: "New",
        notes_json: '{"ok":true}',
      }),
    ).toMatchObject({ statement: "New", notes_json: { ok: true } });
    expect(() =>
      buildInformationCreate({
        ...emptyInformationForm(),
        statement: "New",
        notes_json: "{",
      }),
    ).toThrow("valid JSON");
  });
});
