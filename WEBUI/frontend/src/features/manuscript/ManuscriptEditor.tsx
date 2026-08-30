import { EditorContent, useEditor } from "@tiptap/react";
import { NodeSelection } from "@tiptap/pm/state";
import { useEffect, useMemo, useRef, useState, type MouseEvent } from "react";
import type { Editor as TiptapEditor } from "@tiptap/core";
import type {
  CharacterRecord,
  DraftDocumentRead,
  NovelBlock,
  SceneRecord,
} from "../../api/types";
import { Button } from "../../components/ui/Button";
import { useModalFocus } from "../../components/ui/useModalFocus";
import {
  assertNoDuplicateBlockIds,
  canAddRubyToSelection,
  clearableReferenceValue,
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
  updateSelectedBlockAttributes,
  type EditableBlockType,
  type PhaseEBlockAttributes,
} from "./manuscriptEdit";
import { phaseEExtensions } from "./tiptap/phaseEExtensions";

const editableTypes: EditableBlockType[] = [
  "narration",
  "dialogue",
  "thought",
  "description",
  "quote",
  "heading",
  "separator",
  "note",
];

export interface ManuscriptEditorProps {
  initialHtml: string;
  baselineDocument: DraftDocumentRead | null;
  scenes: SceneRecord[];
  characters: CharacterRecord[];
  charactersLoading: boolean;
  charactersError: string | null;
  saving: boolean;
  cancelPending: boolean;
  onDirtyChange: (dirty: boolean) => void;
  onSave: (html: string) => void;
  onCancel: (dirty: boolean) => void;
}

export function ManuscriptEditor({
  initialHtml,
  baselineDocument,
  scenes,
  characters,
  charactersLoading,
  charactersError,
  saving,
  cancelPending,
  onDirtyChange,
  onSave,
  onCancel,
}: ManuscriptEditorProps) {
  const [baselineHtml, setBaselineHtml] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [documentVersion, setDocumentVersion] = useState(0);
  const [, setSelectionVersion] = useState(0);
  const [transformError, setTransformError] = useState<string | null>(null);
  const [rubyOpen, setRubyOpen] = useState(false);
  const [rubyBase, setRubyBase] = useState("");
  const [rubyReading, setRubyReading] = useState("");
  const [rubyRange, setRubyRange] = useState<{ from: number; to: number; node: boolean } | null>(null);
  const [editorError, setEditorError] = useState<string | null>(null);
  const editorRef = useRef<TiptapEditor | null>(null);

  const editor = useEditor({
    extensions: phaseEExtensions,
    content: initialHtml,
    immediatelyRender: false,
    editorProps: {
      attributes: {
        "aria-label": "Manuscript editor",
        "aria-multiline": "true",
        role: "textbox",
      },
      handleKeyDown: (_view, event) => {
        const activeEditor = editorRef.current;
        if (!activeEditor) return false;
        const action = customEditorKeyAction(event);
        if (action === "split" && splitSelectedBlock(activeEditor)) return true;
        if (action === "join" && joinSelectedBlockBackward(activeEditor)) return true;
        return false;
      },
      handleClickOn: (view, _pos, node, nodePos) => {
        if (node.type.name !== "phaseERuby") return false;
        view.dispatch(view.state.tr.setSelection(NodeSelection.create(view.state.doc, nodePos)));
        return true;
      },
    },
    onUpdate: () => setDocumentVersion((version) => version + 1),
    onSelectionUpdate: () => setSelectionVersion((version) => version + 1),
  });

  useEffect(() => {
    if (!editor) return;
    editorRef.current = editor;
    setBaselineHtml(serializeEditorAuthoringHtml(editor));
    setReady(true);
  }, [editor]);

  const serializedHtml = editor ? serializeEditorAuthoringHtml(editor) : "";
  const dirty = ready && baselineHtml !== null && serializedHtml !== baselineHtml;
  const duplicateIds = editor !== null && hasDuplicateIds(editor);
  const selectedBlock = editor ? getSelectedTopLevelBlock(editor) : null;
  const selectedType = semanticBlockType(selectedBlock) ?? "narration";
  const selectedBaseline = findBaselineBlock(baselineDocument, selectedBlock);
  const selectedEmotions = parseEmotionsAttribute(
    selectedBlock ? stringAttribute(selectedBlock.attrs["data-ann-emotions"]) : null,
  );
  const selectedRuby = getSelectedRuby(editor);
  const hasTextSelection = editor !== null && !editor.state.selection.empty &&
    editor.state.doc.textBetween(editor.state.selection.from, editor.state.selection.to, "").length > 0;

  useEffect(() => {
    if (baselineHtml !== null) onDirtyChange(dirty);
  }, [baselineHtml, dirty, documentVersion, onDirtyChange]);

  const sceneOptions = useMemo(() => {
    const current = positiveReference(selectedBlock?.attrs["data-np-scene-id"]);
    return { current, scenes };
  }, [selectedBlock, scenes]);
  const characterOptions = useMemo(() => {
    const current = positiveReference(selectedBlock?.attrs["data-np-speaker-id"]);
    return { current, characters };
  }, [characters, selectedBlock]);

  function updateAttributes(changes: Partial<PhaseEBlockAttributes>) {
    if (!editor) return;
    setTransformError(null);
    updateSelectedBlockAttributes(editor, changes);
  }

  function changeType(value: string) {
    if (!editor || !editableTypes.includes(value as EditableBlockType)) return;
    setTransformError(null);
    const changed = transformSelectedBlock(editor, value as EditableBlockType);
    if (!changed && value === "separator") {
      setTransformError("A separator can only replace an empty text-bearing block.");
    }
  }

  function changeScene(value: string) {
    const next = value === "" ? clearableReferenceValue(selectedBaseline, "scene_id") : value;
    updateAttributes({ "data-np-scene-id": next });
  }

  function changeSpeaker(value: string) {
    const next = value === "" ? clearableReferenceValue(selectedBaseline, "speaker_character_id") : value;
    updateAttributes({ "data-np-speaker-id": next });
  }

  function setEmotions(emotions: string[]) {
    if (!editor || !selectedBlock) return;
    updateSelectedBlockAttributes(
      editor,
      updateEmotionsAttributes(
        {
          "data-ann-emotions": stringAttribute(selectedBlock.attrs["data-ann-emotions"]),
          "data-np-remove-annotations": stringAttribute(selectedBlock.attrs["data-np-remove-annotations"]),
        },
        selectedBaseline,
        emotions,
      ),
    );
  }

  function removeEmotions() {
    if (!editor || !selectedBlock) return;
    updateSelectedBlockAttributes(
      editor,
      removeEmotionsAttributes(
        {
          "data-ann-emotions": stringAttribute(selectedBlock.attrs["data-ann-emotions"]),
          "data-np-remove-annotations": stringAttribute(selectedBlock.attrs["data-np-remove-annotations"]),
        },
        selectedBaseline,
      ),
    );
  }

  function openRuby() {
    if (!editor) return;
    const ruby = getSelectedRuby(editor);
    if (ruby) {
      setRubyBase(String(ruby.attrs.base ?? ""));
      setRubyReading(String(ruby.attrs.reading ?? ""));
      setRubyRange({ from: editor.state.selection.from, to: editor.state.selection.to, node: true });
      setRubyOpen(true);
      return;
    }
    if (!canAddRubyToSelection(editor)) return;
    setRubyBase(editor.state.doc.textBetween(editor.state.selection.from, editor.state.selection.to, ""));
    setRubyReading("");
    setRubyRange({ from: editor.state.selection.from, to: editor.state.selection.to, node: false });
    setRubyOpen(true);
  }

  function confirmRuby(reading: string) {
    if (!editor || rubyRange === null || !rubyBase.trim() || !reading.trim()) return;
    const chain = editor.chain().focus();
    if (rubyRange.node) {
      chain.setNodeSelection(rubyRange.from);
    } else {
      chain.setTextSelection(rubyRange);
    }
    chain.deleteSelection().insertContent({ type: "phaseERuby", attrs: { base: rubyBase, reading } }).run();
    setRubyOpen(false);
    setRubyRange(null);
  }

  function removeRuby() {
    if (!editor || !selectedRuby) return;
    editor.chain()
      .focus()
      .deleteSelection()
      .insertContent(String(selectedRuby.attrs.base ?? ""))
      .run();
  }

  function toggleEmphasis() {
    if (!editor || !hasTextSelection) return;
    editor.chain().focus().toggleMark("phaseEEmphasisDot").run();
  }

  function insertSeparator() {
    if (editor) insertSeparatorAfterSelection(editor);
  }

  function insertNote() {
    changeType("note");
  }

  function handleEditorClick(event: MouseEvent<HTMLDivElement>) {
    if (!editor || !(event.target instanceof Element)) return;
    const ruby = event.target.closest("ruby");
    if (!ruby || !editor.view.dom.contains(ruby)) return;
    const position = editor.view.posAtDOM(ruby, 0);
    if (editor.state.doc.nodeAt(position)?.type.name !== "phaseERuby") return;
    editor.view.dispatch(editor.state.tr.setSelection(NodeSelection.create(editor.state.doc, position)));
  }

  function save() {
    if (!editor || !ready || !dirty || saving || duplicateIds) return;
    try {
      assertNoDuplicateBlockIds(editor);
      setEditorError(null);
      onSave(serializedHtml);
    } catch (caught) {
      setEditorError(caught instanceof Error ? caught.message : "The manuscript cannot be saved.");
    }
  }

  return (
    <section className="manuscript-edit" aria-label="Manuscript editing">
      <div className="manuscript-edit-meta">
        <div>
          <p className="eyebrow">Edit manuscript</p>
          <p className="read-only-meta">
            {baselineDocument ? `Revision ${baselineDocument.revision} · Draft #${baselineDocument.id}` : "Initial manuscript"}
          </p>
        </div>
        <span className={dirty ? "dirty-indicator" : "read-only-meta"}>{dirty ? "Unsaved changes" : "No unsaved changes"}</span>
      </div>
      <div className="manuscript-editor-toolbar" aria-label="Formatting toolbar">
        <Button type="button" variant="secondary" onMouseDown={(event) => event.preventDefault()} onClick={openRuby} disabled={!canAddRubyToSelection(editor) && selectedRuby === null}>Ruby</Button>
        <Button type="button" variant="secondary" onMouseDown={(event) => event.preventDefault()} onClick={removeRuby} disabled={selectedRuby === null}>Remove Ruby</Button>
        <Button type="button" variant="secondary" onMouseDown={(event) => event.preventDefault()} onClick={toggleEmphasis} disabled={!hasTextSelection}>Emphasis dots</Button>
        <Button type="button" variant="secondary" onMouseDown={(event) => event.preventDefault()} onClick={() => changeType("heading")} disabled={selectedBlock === null}>Heading</Button>
        <Button type="button" variant="secondary" onMouseDown={(event) => event.preventDefault()} onClick={insertSeparator}>Insert separator</Button>
        <Button type="button" variant="secondary" onMouseDown={(event) => event.preventDefault()} onClick={insertNote} disabled={selectedBlock === null || selectedBlock.type.name === "horizontalRule"}>Note</Button>
      </div>
      <div onClick={handleEditorClick}><EditorContent editor={editor} /></div>
      {editor && selectedBlock && (
        <div className="manuscript-metadata-pane">
          <h2>Selected block</h2>
          <label className="field-group" htmlFor="block-type">Block type</label>
          <select id="block-type" className="field-control" value={selectedType} onChange={(event) => changeType(event.target.value)}>
            {editableTypes.map((type) => <option key={type} value={type}>{type}</option>)}
          </select>
          {selectedType === "heading" && (
            <label className="field-group" htmlFor="heading-level">
              Heading level
              <select id="heading-level" className="field-control" value={String(selectedBlock.attrs.level ?? 1)} onChange={(event) => editor.chain().focus().updateAttributes("heading", { level: Number(event.target.value) }).run()}>
                {[1, 2, 3].map((level) => <option key={level} value={level}>{level}</option>)}
              </select>
            </label>
          )}
          <label className="field-group" htmlFor="scene-selector">
            Scene
            <select id="scene-selector" className="field-control" value={stringAttribute(selectedBlock.attrs["data-np-scene-id"]) ?? ""} onChange={(event) => changeScene(event.target.value)}>
              <option value="">No scene</option>
              {sceneOptions.current !== null && !scenes.some((scene) => scene.id === sceneOptions.current) && <option value={String(sceneOptions.current)}>Current unavailable scene #{sceneOptions.current}</option>}
              {scenes.map((scene) => <option key={scene.id} value={String(scene.id)}>{scene.title} (#{scene.id})</option>)}
            </select>
          </label>
          <label className="field-group" htmlFor="speaker-selector">
            Speaker
            <select id="speaker-selector" className="field-control" value={stringAttribute(selectedBlock.attrs["data-np-speaker-id"]) ?? ""} disabled={charactersLoading || charactersError !== null} onChange={(event) => changeSpeaker(event.target.value)}>
              <option value="">No speaker</option>
              {characterOptions.current !== null && !characters.some((character) => character.id === characterOptions.current) && <option value={String(characterOptions.current)}>Current unavailable character #{characterOptions.current}</option>}
              {characters.map((character) => <option key={character.id} value={String(character.id)}>{character.display_name} (#{character.id})</option>)}
            </select>
          </label>
          {charactersLoading && <p className="helper-text">Loading characters…</p>}
          {charactersError && <p className="helper-text" role="alert">{charactersError}</p>}
          <EmotionsEditor emotions={selectedEmotions} onSet={setEmotions} onRemove={removeEmotions} />
          <p className="helper-text">Unknown annotations are preserved and remain read-only.</p>
          {transformError && <p role="alert">{transformError}</p>}
        </div>
      )}
      {duplicateIds && <p role="alert">Duplicate manuscript block IDs must be resolved before saving.</p>}
      {editorError && <p role="alert">{editorError}</p>}
      {!ready && <p role="status">Preparing manuscript editor…</p>}
      <div className="form-actions">
        <Button type="button" onClick={save} disabled={!ready || !dirty || saving || cancelPending || duplicateIds}>{saving ? "Saving…" : "Save manuscript"}</Button>
        <Button type="button" variant="secondary" onClick={() => onCancel(dirty)} disabled={saving || cancelPending}>Cancel editing</Button>
      </div>
      {rubyOpen && <RubyDialog base={rubyBase} reading={rubyReading} onConfirm={confirmRuby} onCancel={() => setRubyOpen(false)} />}
    </section>
  );
}

function EmotionsEditor({
  emotions,
  onSet,
  onRemove,
}: {
  emotions: string[] | null;
  onSet: (emotions: string[]) => void;
  onRemove: () => void;
}) {
  const values = emotions ?? [];
  return (
    <fieldset className="annotation-editor">
      <legend>Emotions annotation</legend>
      <label><input type="checkbox" checked={emotions !== null} onChange={(event) => event.target.checked ? onSet([]) : onRemove()} /> Emotions annotation</label>
      {emotions !== null && <>
        {values.map((emotion, index) => <div className="inline-field" key={index}><label htmlFor={`emotion-${index}`}>Emotion {index + 1}</label><input id={`emotion-${index}`} className="field-control" value={emotion} onChange={(event) => onSet(values.map((current, currentIndex) => currentIndex === index ? event.target.value : current))} /><Button type="button" variant="ghost" aria-label={`Remove emotion ${index + 1}`} onClick={() => onSet(values.filter((_, currentIndex) => currentIndex !== index))}>Remove</Button></div>)}
        <div className="form-actions"><Button type="button" variant="secondary" onClick={() => onSet([...values, ""])}>Add emotion</Button><Button type="button" variant="danger" onClick={onRemove}>Remove emotions annotation</Button></div>
      </>}
    </fieldset>
  );
}

function RubyDialog({
  base,
  reading,
  onConfirm,
  onCancel,
}: {
  base: string;
  reading: string;
  onConfirm: (reading: string) => void;
  onCancel: () => void;
}) {
  const headingId = "ruby-dialog-title";
  const readingRef = useRef<HTMLInputElement>(null);
  const [value, setValue] = useState(reading);
  const { dialogRef, onKeyDown } = useModalFocus(true, {
    initialFocusRef: readingRef,
    onEscape: onCancel,
  });
  return (
    <div className="dialog-backdrop" role="presentation">
      <section ref={dialogRef} className="dialog" role="dialog" aria-modal="true" aria-labelledby={headingId} onKeyDown={onKeyDown}>
        <h2 id={headingId}>Ruby</h2>
        <label className="field-group" htmlFor="ruby-base">Base text<input id="ruby-base" className="field-control" value={base} readOnly /></label>
        <label className="field-group" htmlFor="ruby-reading">Reading<input ref={readingRef} id="ruby-reading" className="field-control" value={value} onChange={(event) => setValue(event.target.value)} /></label>
        <div className="dialog-actions"><Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button><Button type="button" onClick={() => onConfirm(value)} disabled={!base.trim() || !value.trim()}>Confirm Ruby</Button></div>
      </section>
    </div>
  );
}

function findBaselineBlock(document: DraftDocumentRead | null, block: ReturnType<typeof getSelectedTopLevelBlock>): NovelBlock | null {
  const id = block ? stringAttribute(block.attrs.id) : null;
  return id === null || document === null ? null : document.content.blocks.find((candidate) => candidate.id === id) ?? null;
}

function getSelectedRuby(editor: TiptapEditor | null): { attrs: Record<string, unknown> } | null {
  const selection = editor?.state.selection;
  if (!(selection instanceof NodeSelection)) return null;
  return selection.node.type.name === "phaseERuby" ? selection.node : null;
}

function hasDuplicateIds(editor: Parameters<typeof assertNoDuplicateBlockIds>[0]): boolean {
  try {
    assertNoDuplicateBlockIds(editor);
    return false;
  } catch {
    return true;
  }
}

function stringAttribute(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function positiveReference(value: unknown): number | null {
  return typeof value === "string" && /^[1-9]\d*$/.test(value) ? Number(value) : null;
}
