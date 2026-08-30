import { expect, test } from "@playwright/test";
import { createCharacter, createE4ManuscriptFixture, createStructureFixture, saveStructuredDraft } from "./helpers";

test("reads structured revisions, inspects metadata, restores, and downloads Narou export", async ({ page, request }) => {
  const fixture = await createE4ManuscriptFixture(request, "e2e-manuscript");
  await page.goto(`/projects/${fixture.projectId}/manuscript/${fixture.episode.id}`);

  await expect(page.getByRole("heading", { name: "Manuscript reader" })).toBeVisible();
  await expect(page.getByText("Latest revision 2")).toBeVisible();
  await expect(page.getByText("これは構造化された本文です。"))
    .toBeVisible();
  await expect(page.locator("textarea")).toHaveCount(0);
  await expect(page.locator("ruby")).toContainText("東京");
  await expect(page.locator("rt")).toHaveText("とうきょう");
  await expect(page.locator('em[data-emphasis="dot"]')).toHaveText("急げ");
  await expect(page.getByRole("heading", { name: "第二章", level: 2 })).toBeVisible();
  await expect(page.locator("blockquote")).toContainText("引用された言葉");
  await expect(page.locator("hr")).toHaveCount(1);
  await expect(page.getByText("Production note", { exact: true })).toHaveCount(0);

  await page.getByLabel("Show production notes").check();
  await expect(page.getByText("Production note", { exact: true })).toBeVisible();
  await page.getByLabel("Block selector").selectOption(fixture.dialogueId);
  const inspector = page.getByRole("heading", { name: "Block Inspector" }).locator("..");
  await expect(inspector.getByText("scene_id", { exact: true }).locator("..")).toContainText(String(fixture.scene.id));
  await expect(inspector.getByText("speaker_character_id", { exact: true }).locator("..")).toContainText(String(fixture.character.id));
  await expect(page.getByText("焦り")).toBeVisible();
  await expect(page.getByText("tense")).toBeVisible();
  await expect(page.getByText("analysis-bundle")).toHaveCount(0);
  await page.getByRole("button", { name: "Show Raw annotations JSON" }).click();
  await expect(page.getByText(/analysis-bundle/)).toBeVisible();
  await page.getByRole("button", { name: "Show Raw Document" }).click();
  await expect(page.locator("pre.raw-document")).toContainText('"note"');

  await expect(page.getByRole("button", { name: "View revision 1" })).toBeVisible();
  await page.getByRole("button", { name: "View revision 1" }).click();
  await expect(page.getByText("Historical revision 1")).toBeVisible();
  await expect(page.getByText("これは構造化された本文です。", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "View latest" }).click();
  await expect(page.getByText("Latest revision 2")).toBeVisible();

  await page.getByRole("button", { name: "View revision 1" }).click();
  await expect(page.getByRole("button", { name: "Restore revision 1" })).toBeVisible();
  await page.getByRole("button", { name: "Restore revision 1" }).click();
  await expect(page.getByRole("dialog")).toContainText("Restore revision 1 as a new revision?");
  await page.getByRole("button", { name: "Confirm restore" }).click();
  await expect(page.getByText("Restore succeeded as revision 3")).toBeVisible();
  await expect(page.getByText("Latest revision 3")).toBeVisible();
  await expect(page.getByText("これは構造化された本文です。", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "View revision 3" })).toBeVisible();

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download Narou export" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe(`episode-${fixture.episode.id}-r3.txt`);
});

test("edits the existing manuscript through Authoring HTML and preserves inherited annotations", async ({ page, request }) => {
  const fixture = await createE4ManuscriptFixture(request, "e5-manuscript");
  const secondCharacter = await createCharacter(request, fixture.projectId, "E5 Second Character");
  await page.goto(`/projects/${fixture.projectId}/manuscript/${fixture.episode.id}`);

  await expect(page.getByText("Latest revision 2")).toBeVisible();
  await page.getByRole("button", { name: "Edit manuscript" }).click();
  const editor = page.getByRole("textbox", { name: "Manuscript editor" });
  await expect(editor).toBeVisible();
  await expect(editor).toContainText("Production note");

  const dialogue = editor.locator(`#${fixture.dialogueId}`);
  await dialogue.locator("ruby").click();
  await page.getByRole("button", { name: "Ruby", exact: true }).click();
  await page.getByLabel("Reading").fill("トウキョウ");
  await page.getByRole("button", { name: "Confirm Ruby" }).click();
  await dialogue.click();
  await page.keyboard.press("End");
  await page.keyboard.type(" 編集済み");
  await page.getByLabel("Speaker").selectOption(String(secondCharacter.id));
  await page.getByRole("textbox", { name: "Emotion 1" }).fill("緊張");

  await page.getByRole("button", { name: "Save manuscript" }).click();
  await expect(page.getByText("Latest revision 3")).toBeVisible();
  await expect(page.getByText("編集済み", { exact: false })).toBeVisible();

  await page.getByLabel("Show production notes").check();
  await page.getByLabel("Block selector").selectOption(fixture.dialogueId);
  const inspector = page.getByRole("heading", { name: "Block Inspector" }).locator("..");
  await expect(inspector.getByText("speaker_character_id", { exact: true }).locator("..")).toContainText(String(secondCharacter.id));
  await expect(inspector).toContainText("緊張");
  await expect(inspector).toContainText("tense");
  await page.getByRole("button", { name: "Show Raw annotations JSON" }).click();
  await expect(inspector).toContainText("analysis-bundle");
  await expect(inspector).toContainText('"kept"');
  await expect(page.getByRole("button", { name: "View revision 3" })).toBeVisible();

  await page.getByRole("button", { name: "View revision 2" }).click();
  await expect(page.getByText("Historical revision 2")).toBeVisible();
  await expect(page.getByText("急げ", { exact: true })).toBeVisible();
});

test("creates an initial manuscript only after the no-draft preflight", async ({ page, request }) => {
  const fixture = await createStructureFixture(request, "e5-initial");
  await page.goto(`/projects/${fixture.projectId}/manuscript/${fixture.episode.id}`);

  await expect(page.getByText("No manuscript draft yet.")).toBeVisible();
  await page.getByRole("button", { name: "Create manuscript" }).click();
  const editor = page.getByRole("textbox", { name: "Manuscript editor" });
  await expect(editor).toBeVisible();
  await editor.fill("初回本文");
  await page.getByRole("button", { name: "Save manuscript" }).click();

  await expect(page.getByText("Latest revision 1")).toBeVisible();
  await expect(page.getByText("初回本文", { exact: true })).toBeVisible();
});

test("shows a manuscript VERSION_CONFLICT and explicitly loads the latest HTML", async ({ page, request }) => {
  const fixture = await createE4ManuscriptFixture(request, "e5-conflict");
  await page.goto(`/projects/${fixture.projectId}/manuscript/${fixture.episode.id}`);
  await page.getByRole("button", { name: "Edit manuscript" }).click();
  const editor = page.getByRole("textbox", { name: "Manuscript editor" });
  const localText = " local only";
  const dialogue = editor.locator(`#${fixture.dialogueId}`);
  await dialogue.click();
  await editor.press("ControlOrMeta+A");
  await editor.type(localText);

  const external = await saveStructuredDraft(request, fixture.projectId, fixture.episode.id, {
    expected_parent_draft_id: fixture.revisionTwo.id,
    html: '<p data-np-type="narration">external latest</p>',
    source_agent: "e2e",
    change_summary: "External append",
  });
  expect(external.revision).toBe(3);

  let pageSavePosts = 0;
  page.on("request", (requestEvent) => {
    if (requestEvent.method() === "POST" && requestEvent.url().includes("/drafts")) pageSavePosts += 1;
  });
  await page.getByRole("button", { name: "Save manuscript" }).click();
  await expect(page.getByRole("dialog")).toContainText("VERSION_CONFLICT");
  await expect(page.getByRole("dialog")).toContainText("local only");
  expect(pageSavePosts).toBe(1);

  await page.getByRole("button", { name: "Load latest and discard local edits" }).click();
  await expect(page.getByRole("textbox", { name: "Manuscript editor" })).toContainText("external latest");
  await expect(page.getByRole("button", { name: "Save manuscript" })).toBeDisabled();
  expect(pageSavePosts).toBe(1);
});
