import { Editor } from "@tiptap/core";
import { describe, expect, it } from "vitest";
import type { NovelBlock } from "../../api/types";
import {
  assertNoDuplicateBlockIds,
  canAddRubyToSelection,
  customEditorKeyAction,
  getSelectedTopLevelBlock,
  insertSeparatorAfterSelection,
  joinSelectedBlockBackward,
  parseEmotionsAttribute,
  removeEmotionsAttributes,
  serializeEditorAuthoringHtml,
  semanticBlockType,
  splitSelectedBlock,
  transformSelectedBlock,
  updateEmotionsAttributes,
} from "./manuscriptEdit";
import { phaseEExtensions } from "./tiptap/phaseEExtensions";

function editor(content: string): Editor {
  return new Editor({ extensions: phaseEExtensions, content });
}

function topLevel(editorInstance: Editor) {
  return Array.from({ length: editorInstance.state.doc.childCount }, (_, index) =>
    editorInstance.state.doc.child(index),
  );
}

describe("Phase E manuscript editor adapter", () => {
  it("serializes only the default empty paragraph sentinel as empty HTML", () => {
    const empty = editor("");
    expect(serializeEditorAuthoringHtml(empty)).toBe("");
    empty.destroy();

    const knownEmpty = editor('<p id="blk_known" data-np-type="narration"></p>');
    expect(serializeEditorAuthoringHtml(knownEmpty)).toContain('id="blk_known"');
    knownEmpty.destroy();

    const metadataEmpty = editor(
      '<p data-np-scene-id="" data-ann-emotions="[]"></p>',
    );
    expect(serializeEditorAuthoringHtml(metadataEmpty)).toContain("data-np-scene-id");
    expect(serializeEditorAuthoringHtml(metadataEmpty)).toContain("data-ann-emotions");
    metadataEmpty.destroy();
  });

  it("round-trips explicit empty metadata attributes instead of dropping them", () => {
    const instance = editor(
      '<p id="blk_known" data-np-type="dialogue" data-np-scene-id="" data-np-speaker-id="" data-ann-emotions="[]" data-np-remove-annotations="[]">本文</p>',
    );

    expect(instance.getHTML()).toContain('data-np-scene-id=""');
    expect(instance.getHTML()).toContain('data-np-speaker-id=""');
    expect(instance.getHTML()).toContain('data-ann-emotions="[]"');
    expect(instance.getHTML()).toContain('data-np-remove-annotations="[]"');
    instance.destroy();
  });

  it("keeps known metadata only on the first block when a dialogue is split", () => {
    const instance = editor(
      '<p id="blk_known" data-np-type="dialogue" data-np-scene-id="3" data-np-speaker-id="12" data-ann-emotions="[&quot;焦り&quot;]">abcdef</p>',
    );
    instance.commands.setTextSelection(4);
    expect(splitSelectedBlock(instance)).toBe(true);

    const [first, second] = topLevel(instance);
    expect(first.attrs).toMatchObject({
      id: "blk_known",
      "data-np-type": "dialogue",
      "data-np-scene-id": "3",
      "data-np-speaker-id": "12",
      "data-ann-emotions": '["焦り"]',
    });
    expect(second.attrs).toMatchObject({
      id: null,
      "data-np-type": null,
      "data-np-scene-id": null,
      "data-np-speaker-id": null,
      "data-ann-emotions": null,
      "data-np-remove-annotations": null,
    });
    instance.destroy();
  });

  it("keeps the first block identity and metadata when blocks are joined", () => {
    const instance = editor(
      '<p id="blk_a" data-np-type="dialogue" data-np-scene-id="3">A</p><p id="blk_b" data-np-type="thought" data-np-speaker-id="12">B</p>',
    );
    instance.commands.setTextSelection(4);
    expect(joinSelectedBlockBackward(instance)).toBe(true);

    const [joined] = topLevel(instance);
    expect(joined.textContent).toBe("AB");
    expect(joined.attrs).toMatchObject({
      id: "blk_a",
      "data-np-type": "dialogue",
      "data-np-scene-id": "3",
      "data-np-speaker-id": null,
    });
    instance.destroy();
  });

  it("does not join different structural node types", () => {
    const instance = editor("<h1>Heading</h1><p>Paragraph</p>");
    instance.commands.setTextSelection(4);
    const before = instance.getHTML();

    expect(joinSelectedBlockBackward(instance)).toBe(false);
    expect(instance.getHTML()).toBe(before);
    instance.destroy();
  });

  it("returns false instead of throwing when split cannot use the selection boundary", () => {
    const instance = editor("<p>本文</p>");
    instance.commands.setNodeSelection(0);
    const before = instance.getHTML();

    expect(splitSelectedBlock(instance)).toBe(false);
    expect(instance.getHTML()).toBe(before);
    instance.destroy();
  });

  it("allows Ruby only for a plain text selection in one textblock", () => {
    const plain = editor("<p>本文</p>");
    plain.commands.setTextSelection({ from: 1, to: 3 });
    expect(canAddRubyToSelection(plain)).toBe(true);
    plain.destroy();

    const marked = editor("<p><strong>本文</strong></p>");
    marked.commands.setTextSelection({ from: 1, to: 3 });
    expect(canAddRubyToSelection(marked)).toBe(false);
    marked.destroy();

    const hardBreak = editor("<p>前<br>後</p>");
    hardBreak.commands.setTextSelection({ from: 1, to: 7 });
    expect(canAddRubyToSelection(hardBreak)).toBe(false);
    hardBreak.destroy();

    const multipleBlocks = editor("<p>前</p><p>後</p>");
    multipleBlocks.commands.setTextSelection({ from: 1, to: 4 });
    expect(canAddRubyToSelection(multipleBlocks)).toBe(false);
    multipleBlocks.destroy();

    const whitespace = editor("<p>   </p>");
    whitespace.commands.setTextSelection({ from: 1, to: 4 });
    expect(canAddRubyToSelection(whitespace)).toBe(false);
    whitespace.destroy();

    const whitespaceOnlySelection = new Editor({
      extensions: phaseEExtensions,
      content: "<p>A   B</p>",
      parseOptions: { preserveWhitespace: "full" },
    });
    whitespaceOnlySelection.commands.setTextSelection({ from: 2, to: 5 });
    expect(whitespaceOnlySelection.state.doc.textBetween(2, 5, "", "")).toBe("   ");
    expect(canAddRubyToSelection(whitespaceOnlySelection)).toBe(false);
    whitespaceOnlySelection.destroy();
  });

  it("allows only plain unmodified keyboard actions for custom split and join", () => {
    const base = { isComposing: false, keyCode: 13, shiftKey: false, ctrlKey: false, metaKey: false, altKey: false };
    expect(customEditorKeyAction({ ...base, key: "Enter" })).toBe("split");
    expect(customEditorKeyAction({ ...base, key: "Enter", shiftKey: true })).toBe(null);
    expect(customEditorKeyAction({ ...base, key: "Enter", ctrlKey: true })).toBe(null);
    expect(customEditorKeyAction({ ...base, key: "Enter", isComposing: true })).toBe(null);
    expect(customEditorKeyAction({ ...base, key: "Enter", keyCode: 229 })).toBe(null);
    expect(customEditorKeyAction({ ...base, key: "Backspace", keyCode: 8 })).toBe("join");
    expect(customEditorKeyAction({ ...base, key: "Backspace", keyCode: 8, altKey: true })).toBe(null);
  });

  it("transforms a selected block without losing known metadata", () => {
    const instance = editor(
      '<p id="blk_known" data-np-type="dialogue" data-np-scene-id="3" data-np-speaker-id="12" data-ann-emotions="[&quot;焦り&quot;]" data-np-remove-annotations="[&quot;emotions&quot;]">本文</p>',
    );
    instance.commands.setTextSelection(2);
    expect(transformSelectedBlock(instance, "heading")).toBe(true);
    expect(instance.getHTML()).toContain('<h1 id="blk_known"');
    expect(instance.getHTML()).not.toContain("data-np-type");
    expect(instance.getHTML()).toContain('data-np-scene-id="3"');
    expect(instance.getHTML()).toContain('data-np-remove-annotations="[&quot;emotions&quot;]"');
    expect(semanticBlockType(getSelectedTopLevelBlock(instance))).toBe("heading");

    expect(transformSelectedBlock(instance, "narration")).toBe(true);
    expect(instance.getHTML()).toContain('<p id="blk_known" data-np-type="narration"');
    instance.destroy();
  });

  it("rejects converting non-empty prose to a separator", () => {
    const instance = editor("<p>本文</p>");
    instance.commands.setTextSelection(2);
    expect(transformSelectedBlock(instance, "separator")).toBe(false);
    expect(instance.getHTML()).toContain("本文");
    instance.destroy();
  });

  it.each([
    ["Ruby-only", '<p><ruby>本文<rt>ほんぶん</rt></ruby></p>', "<ruby>"],
    ["HardBreak-only", "<p><br></p>", "<br"],
    ["marked text", "<p><strong>本文</strong></p>", "<strong>"],
  ])("rejects converting %s content to a separator without deleting it", (_label, html, preserved) => {
    const instance = editor(html);
    instance.commands.setTextSelection(1);
    const before = instance.getHTML();

    expect(transformSelectedBlock(instance, "separator")).toBe(false);
    expect(instance.getHTML()).toBe(before);
    expect(instance.getHTML()).toContain(preserved);
    instance.destroy();
  });

  it("inserts a separator without replacing selected prose", () => {
    const instance = editor('<p id="blk_known" data-np-type="dialogue">本文</p>');
    instance.commands.setTextSelection(2);
    expect(insertSeparatorAfterSelection(instance)).toBe(true);
    expect(topLevel(instance).map((block) => block.textContent).join("")).toBe("本文");
    expect(instance.getHTML()).toContain("<hr");
    expect(instance.getHTML().match(/id="blk_known"/g)).toHaveLength(1);
    instance.destroy();
  });

  it("allows an empty block to become a separator and back to narration", () => {
    const instance = editor('<p id="blk_known" data-np-type="dialogue"></p>');
    instance.commands.setTextSelection(1);
    expect(transformSelectedBlock(instance, "separator")).toBe(true);
    expect(instance.getHTML()).toContain('<hr id="blk_known"');
    expect(topLevel(instance)[0].attrs).toMatchObject({ id: "blk_known" });
    expect(getSelectedTopLevelBlock(instance)?.type.name).toBe("horizontalRule");
    expect(getSelectedTopLevelBlock(instance)?.attrs).toMatchObject({ id: "blk_known" });
    expect(transformSelectedBlock(instance, "narration")).toBe(true);
    expect(topLevel(instance)[0].attrs).toMatchObject({ id: "blk_known", "data-np-type": "narration" });
    expect(instance.getHTML()).toContain('<p id="blk_known" data-np-type="narration"></p>');
    instance.destroy();
  });

  it("rejects duplicate non-empty block IDs without repairing them", () => {
    const instance = editor('<p id="same">A</p><p id="same">B</p>');
    expect(() => assertNoDuplicateBlockIds(instance)).toThrow(
      "Duplicate manuscript block IDs must be resolved before saving.",
    );
    expect(instance.getHTML()).toContain('id="same"');
    instance.destroy();
  });

  it("keeps emotions values valid and applies baseline-aware removal semantics", () => {
    const baseline: NovelBlock = {
      id: "blk_known",
      type: "dialogue",
      html: "<p>本文</p>",
      attrs: {},
      annotations: { emotions: ["焦り"] },
    };
    const removed = removeEmotionsAttributes(
      { "data-ann-emotions": '["焦り"]', "data-np-remove-annotations": null },
      baseline,
    );
    expect(removed).toEqual({
      "data-ann-emotions": null,
      "data-np-remove-annotations": '["emotions"]',
    });
    expect(parseEmotionsAttribute(removed["data-ann-emotions"])).toBeNull();

    const reset = updateEmotionsAttributes(removed, baseline, ["焦り", "", "焦り"]);
    expect(reset).toEqual({
      "data-ann-emotions": '["焦り","","焦り"]',
      "data-np-remove-annotations": null,
    });

    const absentBaseline = { ...baseline, annotations: {} };
    expect(removeEmotionsAttributes(reset, absentBaseline)).toEqual({
      "data-ann-emotions": null,
      "data-np-remove-annotations": null,
    });
  });
});
