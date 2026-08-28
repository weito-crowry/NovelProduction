import { describe, expect, it } from "vitest";
import { formatStoredJson, parseJsonEditor } from "./jsonFields";

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
});
