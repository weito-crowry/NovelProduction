import { describe, expect, it } from "vitest";
import type { DraftDocumentRead, DraftWebRead, NovelBlock } from "../../api/types";
import {
  assertDocumentIdentity,
  assertWebIdentity,
  projectableUnknownAnnotations,
  restoreRefreshStatus,
} from "./manuscriptRead";

const block: NovelBlock = {
  id: "blk_0123456789abcdef0123456789abcdef",
  type: "dialogue",
  html: "<p>hello</p>",
  attrs: {},
  annotations: {
    emotions: ["焦り"],
    mood: "tense",
    "analysis-bundle": { nested: [1, true] },
    Count: "not projectable",
    number: 1,
  },
};

const documentRead: DraftDocumentRead = {
  id: 5,
  work_id: 7,
  episode_id: 2,
  revision: 4,
  parent_draft_id: 3,
  format: "document",
  content: { schema_version: 1, type: "novel_document", blocks: [block] },
  source_agent: "agent",
  change_summary: "change",
  created_at: "2026-01-01",
};

const webRead: DraftWebRead = {
  ...documentRead,
  format: "web",
  content: '<p id="blk_0123456789abcdef0123456789abcdef">hello</p>',
};

describe("manuscript read safety", () => {
  it("accepts an empty canonical document and rejects mismatched snapshot identity", () => {
    expect(assertDocumentIdentity({ ...documentRead, content: { schema_version: 1, type: "novel_document", blocks: [] } }, 2)).toBeDefined();
    expect(() => assertDocumentIdentity({ ...documentRead, episode_id: 9 }, 2)).toThrow("identity");
    expect(() => assertDocumentIdentity({ ...documentRead, revision: 0 }, 2)).toThrow("identity");
    expect(() => assertDocumentIdentity({ ...documentRead, revision: 3 }, 2, 4)).toThrow("identity");
  });

  it("requires the WEB projection to match the document anchor", () => {
    expect(assertWebIdentity(webRead, documentRead)).toBe(webRead);
    expect(() => assertWebIdentity({ ...webRead, id: 6 }, documentRead)).toThrow("consistent");
    expect(() => assertWebIdentity(null, documentRead)).toThrow("consistent");
  });

  it("shows only projectable string annotations while preserving raw JSON separately", () => {
    expect(projectableUnknownAnnotations(block.annotations)).toEqual([{ key: "mood", value: "tense" }]);
  });

  it("accepts a concurrent newer append and rejects stale or same-revision mismatched refreshes", () => {
    expect(restoreRefreshStatus({ revision: 6, id: 11 }, { revision: 5, id: 10 })).toBe("confirmed");
    expect(restoreRefreshStatus({ revision: 5, id: 10 }, { revision: 5, id: 10 })).toBe("confirmed");
    expect(restoreRefreshStatus({ revision: 5, id: 99 }, { revision: 5, id: 10 })).toBe("inconsistent");
    expect(restoreRefreshStatus({ revision: 4, id: 9 }, { revision: 5, id: 10 })).toBe("stale");
    expect(restoreRefreshStatus(null, { revision: 5, id: 10 })).toBe("refresh-failed");
  });
});
