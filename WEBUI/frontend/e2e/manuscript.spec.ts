import { expect, test } from "@playwright/test";
import { createE4ManuscriptFixture } from "./helpers";

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
