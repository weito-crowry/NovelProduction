import type { Editor } from "@tiptap/core";
import type { Node as PMNode } from "@tiptap/pm/model";
import { NodeSelection, TextSelection } from "@tiptap/pm/state";
import { canJoin, canSplit } from "@tiptap/pm/transform";
import type { NovelBlock, NovelBlockType } from "../../api/types";

export type EditableBlockType = NovelBlockType;

export type CustomEditorKeyAction = "split" | "join" | null;

const paragraphTypes = new Set<EditableBlockType>([
  "narration",
  "dialogue",
  "thought",
  "description",
  "note",
]);

const customBlockAttributes = [
  "id",
  "data-np-type",
  "data-np-scene-id",
  "data-np-speaker-id",
  "data-ann-emotions",
  "data-np-remove-annotations",
] as const;

type CustomAttribute = (typeof customBlockAttributes)[number];
export type PhaseEBlockAttributes = Record<CustomAttribute, string | null>;

export function serializeEditorAuthoringHtml(editor: Editor): string {
  if (isDefaultEmptySentinel(editor)) return "";
  return editor.getHTML();
}

export function assertNoDuplicateBlockIds(editor: Editor): void {
  const seen = new Set<string>();
  for (let index = 0; index < editor.state.doc.childCount; index += 1) {
    const id = stringAttribute(editor.state.doc.child(index).attrs.id);
    if (id === null) continue;
    if (seen.has(id)) {
      throw new Error("Duplicate manuscript block IDs must be resolved before saving.");
    }
    seen.add(id);
  }
}

export function customEditorKeyAction(
  event: Pick<KeyboardEvent, "key" | "isComposing" | "keyCode" | "shiftKey" | "ctrlKey" | "metaKey" | "altKey">,
): CustomEditorKeyAction {
  if (event.isComposing || event.keyCode === 229) return null;
  if (event.shiftKey || event.ctrlKey || event.metaKey || event.altKey) return null;
  if (event.key === "Enter") return "split";
  if (event.key === "Backspace") return "join";
  return null;
}

export function canAddRubyToSelection(editor: Editor | null): boolean {
  if (editor === null) return false;
  const { selection, doc } = editor.state;
  if (!(selection instanceof TextSelection) || selection.empty || !selection.$from.sameParent(selection.$to)) return false;
  if (!selection.$from.parent.isTextblock) return false;

  let valid = true;
  let hasSubstantiveText = false;
  doc.nodesBetween(selection.from, selection.to, (node) => {
    if (!valid) return false;
    if (node.isText) {
      hasSubstantiveText ||= (node.text ?? "").trim().length > 0;
      if (node.marks.length > 0) valid = false;
      return;
    }
    if (node.isInline) valid = false;
  });
  return valid && hasSubstantiveText;
}

export function getSelectedTopLevelBlock(editor: Editor): PMNode | null {
  const { selection, doc } = editor.state;
  if (selection instanceof NodeSelection && selection.node.type.name !== "text") {
    if (selection.$from.depth === 0 && isTopLevelBlock(selection.node)) return selection.node;
  }
  if (selection.$from.depth >= 1) return selection.$from.node(1);

  let position = 0;
  for (let index = 0; index < doc.childCount; index += 1) {
    const block = doc.child(index);
    if (selection.from >= position && selection.from <= position + block.nodeSize) {
      return block;
    }
    position += block.nodeSize;
  }
  return null;
}

export function semanticBlockType(block: PMNode | null): EditableBlockType | null {
  if (block === null) return null;
  if (block.type.name === "blockquote") return "quote";
  if (block.type.name === "heading") return "heading";
  if (block.type.name === "horizontalRule") return "separator";
  const type = stringAttribute(block.attrs["data-np-type"]);
  return type !== null && paragraphTypes.has(type as EditableBlockType)
    ? (type as EditableBlockType)
    : "narration";
}

export function transformSelectedBlock(editor: Editor, target: EditableBlockType): boolean {
  const block = getSelectedTopLevelBlock(editor);
  if (block === null) return false;
  if (target === "separator" && block.textContent.length > 0) return false;

  const nodeTypeName = target === "quote"
    ? "blockquote"
    : target === "heading"
      ? "heading"
      : target === "separator"
        ? "horizontalRule"
        : "paragraph";
  const nodeType = editor.schema.nodes[nodeTypeName];
  if (!nodeType) return false;

  const attrs = phaseEAttributes(block);
  if (paragraphTypes.has(target)) {
    attrs["data-np-type"] = target;
  } else {
    attrs["data-np-type"] = null;
  }
  const nextAttrs: Record<string, string | number | null> = { ...attrs };
  if (target === "heading") {
    nextAttrs.level = 1;
  }

  const blockIndex = topLevelBlockIndex(editor, block);
  const position = topLevelBlockPosition(editor, block);
  if (blockIndex < 0 || position === null) return false;
  const transaction = editor.state.tr.setNodeMarkup(position, nodeType, nextAttrs);
  if (target === "separator") {
    transaction.setSelection(NodeSelection.create(transaction.doc, position));
  }
  editor.view.dispatch(transaction);
  const transformed = editor.state.doc.child(blockIndex);
  if (transformed === null || transformed.type !== nodeType || !hasExpectedAttributes(transformed, nextAttrs)) {
    editor.view.dispatch(editor.state.tr.setNodeMarkup(position, nodeType, nextAttrs));
  }
  return true;
}

export function splitSelectedBlock(editor: Editor): boolean {
  const { selection } = editor.state;
  if (!selection.empty || selection.$from.depth < 1) return false;
  const block = getSelectedTopLevelBlock(editor);
  if (block === null || !isTextBearingBlock(block)) return false;
  const attrs = Object.fromEntries(
    Object.entries(block.attrs).map(([key, value]) => [
      key,
      customBlockAttributes.includes(key as CustomAttribute) ? null : value,
    ]),
  );
  try {
    const typesAfter = [{ type: block.type, attrs }];
    if (!canSplit(editor.state.doc, selection.from, 1, typesAfter)) return false;
    const transaction = editor.state.tr.split(selection.from, 1, typesAfter);
    editor.view.dispatch(transaction);
    return true;
  } catch {
    return false;
  }
}

export function joinSelectedBlockBackward(editor: Editor): boolean {
  const { selection, doc } = editor.state;
  if (!selection.empty || selection.$from.depth < 1) return false;
  const block = getSelectedTopLevelBlock(editor);
  if (block === null) return false;
  const position = topLevelBlockPosition(editor, block);
  if (position === null || selection.from !== position + 1) return false;
  const blockIndex = topLevelBlockIndex(editor, block);
  if (blockIndex <= 0 || !isTextBearingBlock(doc.child(blockIndex - 1))) return false;
  if (doc.child(blockIndex - 1).type !== block.type) return false;
  try {
    if (!canJoin(editor.state.doc, position)) return false;
    editor.view.dispatch(editor.state.tr.join(position));
    return true;
  } catch {
    return false;
  }
}

export function insertSeparatorAfterSelection(editor: Editor): boolean {
  const block = getSelectedTopLevelBlock(editor);
  if (block === null) return false;
  const position = topLevelBlockPosition(editor, block);
  const separatorType = editor.schema.nodes.horizontalRule;
  if (position === null || separatorType === undefined) return false;

  const separator = separatorType.create();
  editor.view.dispatch(editor.state.tr.insert(position + block.nodeSize, separator));
  return true;
}

export function updateSelectedBlockAttributes(
  editor: Editor,
  changes: Partial<PhaseEBlockAttributes>,
): boolean {
  const block = getSelectedTopLevelBlock(editor);
  if (block === null) return false;
  const position = topLevelBlockPosition(editor, block);
  if (position === null) return false;
  const attrs = { ...block.attrs, ...changes };
  editor.view.dispatch(editor.state.tr.setNodeMarkup(position, undefined, attrs));
  return true;
}

export function parseEmotionsAttribute(value: string | null | undefined): string[] | null {
  if (value === null || value === undefined) return null;
  try {
    const parsed: unknown = JSON.parse(value);
    return Array.isArray(parsed) && parsed.every((entry) => typeof entry === "string")
      ? parsed
      : null;
  } catch {
    return null;
  }
}

export function updateEmotionsAttributes(
  current: Pick<PhaseEBlockAttributes, "data-ann-emotions" | "data-np-remove-annotations">,
  _baseline: NovelBlock | null,
  emotions: string[],
): Pick<PhaseEBlockAttributes, "data-ann-emotions" | "data-np-remove-annotations"> {
  return {
    "data-ann-emotions": JSON.stringify(emotions),
    "data-np-remove-annotations": encodeRemovalList(
      decodeRemovalList(current["data-np-remove-annotations"]).filter((key) => key !== "emotions"),
    ),
  };
}

export function removeEmotionsAttributes(
  current: Pick<PhaseEBlockAttributes, "data-ann-emotions" | "data-np-remove-annotations">,
  baseline: NovelBlock | null,
): Pick<PhaseEBlockAttributes, "data-ann-emotions" | "data-np-remove-annotations"> {
  const removal = decodeRemovalList(current["data-np-remove-annotations"]).filter(
    (key) => key !== "emotions",
  );
  if (baselineHasAnnotation(baseline, "emotions")) removal.push("emotions");
  return {
    "data-ann-emotions": null,
    "data-np-remove-annotations": encodeRemovalList(removal),
  };
}

export function clearableReferenceValue(
  baseline: NovelBlock | null,
  key: "scene_id" | "speaker_character_id",
): string | null {
  return baseline !== null && baseline.attrs[key] !== undefined ? "" : null;
}

function isDefaultEmptySentinel(editor: Editor): boolean {
  if (editor.state.doc.childCount !== 1) return false;
  const block = editor.state.doc.child(0);
  return (
    block.type.name === "paragraph" &&
    block.content.size === 0 &&
    Object.values(block.attrs).every((value) => value === null || value === undefined)
  );
}

function phaseEAttributes(block: PMNode): PhaseEBlockAttributes {
  return Object.fromEntries(
    customBlockAttributes.map((key) => [key, stringAttribute(block.attrs[key])]),
  ) as PhaseEBlockAttributes;
}

function topLevelBlockPosition(editor: Editor, target: PMNode): number | null {
  let position = 0;
  for (let index = 0; index < editor.state.doc.childCount; index += 1) {
    const block = editor.state.doc.child(index);
    if (block === target) return position;
    position += block.nodeSize;
  }
  return null;
}

function topLevelBlockIndex(editor: Editor, target: PMNode): number {
  for (let index = 0; index < editor.state.doc.childCount; index += 1) {
    if (editor.state.doc.child(index) === target) return index;
  }
  return -1;
}

function isTopLevelBlock(node: PMNode): boolean {
  return node.type.name !== "text";
}

function isTextBearingBlock(node: PMNode): boolean {
  return node.type.name !== "horizontalRule";
}

function hasExpectedAttributes(node: PMNode, expected: Record<string, string | number | null>): boolean {
  return Object.entries(expected).every(([key, value]) => node.attrs[key] === value);
}

function stringAttribute(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function baselineHasAnnotation(baseline: NovelBlock | null, key: string): boolean {
  return baseline !== null && Object.prototype.hasOwnProperty.call(baseline.annotations, key);
}

function decodeRemovalList(value: string | null): string[] {
  if (value === null) return [];
  try {
    const parsed: unknown = JSON.parse(value);
    return Array.isArray(parsed) && parsed.every((entry) => typeof entry === "string")
      ? parsed
      : [];
  } catch {
    return [];
  }
}

function encodeRemovalList(values: string[]): string | null {
  return values.length === 0 ? null : JSON.stringify(Array.from(new Set(values)));
}
