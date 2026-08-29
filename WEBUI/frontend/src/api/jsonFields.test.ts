import { describe, expect, it } from "vitest";
import {
  formatStoredJson,
  parseForeshadowingNotesEditor,
  parseJsonEditor,
} from "./jsonFields";

describe("JSON editor helpers", () => {
  it("pretty-prints valid stored JSON", () => {
    expect(formatStoredJson('{"title":"雪","count":2}')).toBe(
      '{\n  "title": "雪",\n  "count": 2\n}',
    );
  });

  it("parses valid edited JSON", () => {
    expect(parseJsonEditor('{\n  "enabled": true\n}')).toEqual({
      enabled: true,
    });
  });

  it("rejects invalid edited JSON before an API request", () => {
    expect(() => parseJsonEditor('{"enabled":')).toThrow(
      "Enter valid JSON.",
    );
  });

  it("accepts only JSON arrays for foreshadowing notes", () => {
    expect(parseForeshadowingNotesEditor('[{"clue":true}]')).toEqual([{ clue: true }]);
    expect(parseForeshadowingNotesEditor("[]")).toEqual([]);
  });

  it.each(["{}", "null", '"text"', "42", "true"])(
    "rejects non-array foreshadowing notes JSON: %s",
    (text) => {
      expect(() => parseForeshadowingNotesEditor(text)).toThrow(
        "Foreshadowing notes must be a JSON array.",
      );
    },
  );
});
