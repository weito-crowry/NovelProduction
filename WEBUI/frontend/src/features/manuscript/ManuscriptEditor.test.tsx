import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentProps } from "react";
import { describe, expect, it, vi } from "vitest";
import type { DraftDocumentRead, SceneRecord } from "../../api/types";
import { ManuscriptEditor } from "./ManuscriptEditor";

const scene: SceneRecord = {
  id: 3,
  work_id: 7,
  episode_id: 2,
  position: 1,
  title: "駅",
  summary: "",
  purpose: "",
  canon_status: "draft",
  production_status: "drafting",
  version: 1,
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
};

const baseline: DraftDocumentRead = {
  id: 20,
  work_id: 7,
  episode_id: 2,
  revision: 4,
  parent_draft_id: 19,
  format: "document",
  content: {
    schema_version: 1,
    type: "novel_document",
    blocks: [
      {
        id: "blk_known",
        type: "dialogue",
        html: "<p>本文</p>",
        attrs: { scene_id: 3, speaker_character_id: 12 },
        annotations: { emotions: ["焦り"], mood: "tense" },
      },
    ],
  },
  source_agent: "webui",
  change_summary: "baseline",
  created_at: "2026-01-01",
};

function renderEditor(overrides: Partial<ComponentProps<typeof ManuscriptEditor>> = {}) {
  const onDirtyChange = vi.fn();
  const onSave = vi.fn();
  const onCancel = vi.fn();
  const rendered = render(
    <ManuscriptEditor
      initialHtml={'<p id="blk_known" data-np-type="dialogue" data-np-scene-id="3" data-np-speaker-id="12" data-ann-emotions=\'["焦り"]\'>本文</p>'}
      baselineDocument={baseline}
      scenes={[scene]}
      characters={[]}
      charactersLoading={false}
      charactersError={null}
      saving={false}
      cancelPending={false}
      onDirtyChange={onDirtyChange}
      onSave={onSave}
      onCancel={onCancel}
      {...overrides}
    />,
  );
  return { ...rendered, onDirtyChange, onSave, onCancel };
}

describe("ManuscriptEditor", () => {
  it("starts clean and derives block type from the TipTap selection", async () => {
    renderEditor();

    expect(await screen.findByRole("textbox", { name: "Manuscript editor" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save manuscript" })).toBeDisabled();
    expect(screen.getByLabelText("Block type")).toHaveValue("dialogue");
  });

  it("updates the TipTap node on type change and marks the editor dirty", async () => {
    const { onDirtyChange } = renderEditor();
    const user = userEvent.setup();

    await user.selectOptions(screen.getByLabelText("Block type"), "heading");

    expect(await screen.findByRole("heading", { name: "本文", level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save manuscript" })).toBeEnabled();
    expect(onDirtyChange).toHaveBeenLastCalledWith(true);
  });

  it("provides a valid string-list emotions editor without a JSON text area", async () => {
    renderEditor();
    const user = userEvent.setup();

    expect(screen.getByLabelText("Emotions annotation")).toBeChecked();
    expect(screen.getByLabelText("Emotion 1")).toHaveValue("焦り");
    await user.click(screen.getByRole("button", { name: "Add emotion" }));
    expect(screen.getByLabelText("Emotion 2")).toHaveValue("");
    await user.type(screen.getByLabelText("Emotion 2"), "緊張");
    expect(screen.getByLabelText("Emotion 2")).toHaveFocus();
    expect(screen.queryByRole("textbox", { name: "Emotions JSON" })).not.toBeInTheDocument();
  });

  it("keeps plain Enter split semantics while delegating Shift+Enter", async () => {
    renderEditor({ initialHtml: "<p>本文</p>", baselineDocument: null });
    const editor = await screen.findByRole("textbox", { name: "Manuscript editor" });

    fireEvent.keyDown(editor, { key: "Enter", code: "Enter", shiftKey: true });
    expect(editor.querySelectorAll("p")).toHaveLength(1);

    fireEvent.keyDown(editor, { key: "Enter", code: "Enter" });
    expect(editor.querySelectorAll("p")).toHaveLength(2);

  });

  it("disables Add Ruby for selections across blocks, marked text, hard breaks, and whitespace", async () => {
    const cases = [
      { html: "<p>前</p><p>後</p>", expectedParagraphs: 2 },
      { html: "<p><strong>本文</strong></p>", expectedParagraphs: 1 },
      { html: "<p>前<br>後</p>", expectedParagraphs: 1 },
      { html: "<p>   </p>", expectedParagraphs: 1 },
    ];

    for (const testCase of cases) {
      const { unmount } = renderEditor({ initialHtml: testCase.html, baselineDocument: null });
      const user = userEvent.setup();
      const editor = await screen.findByRole("textbox", { name: "Manuscript editor" });
      await user.click(editor);
      await user.keyboard("{Control>}a{/Control}");
      expect(screen.getByRole("button", { name: "Ruby" })).toBeDisabled();
      expect(editor.querySelectorAll("p")).toHaveLength(testCase.expectedParagraphs);
      unmount();
    }
  });

  it("does not allow a whitespace-only Ruby reading", async () => {
    renderEditor({ initialHtml: "<p><ruby>本文<rt>ほんぶん</rt></ruby></p>", baselineDocument: null });
    const user = userEvent.setup();
    const editor = await screen.findByRole("textbox", { name: "Manuscript editor" });
    await user.click(editor.querySelector("ruby") as HTMLElement);
    await user.click(screen.getByRole("button", { name: "Ruby" }));
    expect(screen.getByLabelText("Reading")).toHaveValue("ほんぶん");
    await user.clear(screen.getByLabelText("Reading"));
    await user.type(screen.getByLabelText("Reading"), "   ");

    expect(screen.getByRole("button", { name: "Confirm Ruby" })).toBeDisabled();
    expect(editor.querySelector("ruby")).toHaveTextContent("本文ほんぶん");
  });

  it("preserves the base prose when a selected Ruby is removed", async () => {
    const { onDirtyChange } = renderEditor({
      initialHtml: '<p id="blk_known" data-np-type="dialogue"><ruby>東京<rt>とうきょう</rt></ruby></p>',
      baselineDocument: { ...baseline, content: { ...baseline.content, blocks: [{ ...baseline.content.blocks[0], annotations: {} }] } },
    });
    const user = userEvent.setup();

    const editor = await screen.findByRole("textbox", { name: "Manuscript editor" });
    await user.click(editor.querySelector("ruby") as HTMLElement);
    await user.click(screen.getByRole("button", { name: "Ruby" }));
    const reading = screen.getByLabelText("Reading");
    await user.clear(reading);
    await user.type(reading, "トウキョウ");
    await user.click(screen.getByRole("button", { name: "Confirm Ruby" }));
    expect(editor.querySelector("ruby")).toHaveTextContent("東京トウキョウ");

    await user.click(editor.querySelector("ruby") as HTMLElement);
    await user.click(screen.getByRole("button", { name: "Remove Ruby" }));
    expect(editor.querySelector("ruby")).not.toBeInTheDocument();
    expect(editor).toHaveTextContent("東京");
    expect(onDirtyChange).toHaveBeenCalledWith(true);
  });

  it("does not autosave when the user edits prose", async () => {
    const { onSave } = renderEditor({
      initialHtml: "",
      baselineDocument: null,
    });
    const user = userEvent.setup();
    await user.type(await screen.findByRole("textbox", { name: "Manuscript editor" }), "新しい本文");
    await waitFor(() => expect(onSave).not.toHaveBeenCalled());
  });

  it("keeps unavailable scene and speaker references through prose edits and candidate errors", async () => {
    const { onSave } = renderEditor({
      initialHtml: '<p id="blk_known" data-np-type="dialogue" data-np-scene-id="999" data-np-speaker-id="888">本文</p>',
      scenes: [],
      charactersError: "Unable to load characters.",
    });
    const user = userEvent.setup();

    expect(screen.getByLabelText("Scene")).toHaveValue("999");
    expect(screen.getByRole("option", { name: "Current unavailable scene #999" })).toBeInTheDocument();
    expect(screen.getByLabelText("Speaker")).toHaveValue("888");
    expect(screen.getByRole("option", { name: "Current unavailable character #888" })).toBeInTheDocument();
    expect(screen.getByLabelText("Speaker")).toBeDisabled();

    const editor = screen.getByRole("textbox", { name: "Manuscript editor" });
    await user.click(editor);
    await user.type(editor, "追記");
    expect(editor.querySelector("p")).toHaveAttribute("data-np-scene-id", "999");
    expect(editor.querySelector("p")).toHaveAttribute("data-np-speaker-id", "888");
    await user.click(screen.getByRole("button", { name: "Save manuscript" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledWith(expect.stringContaining('data-np-scene-id="999"')));
  });
});
