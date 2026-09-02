import { expect, test } from "@playwright/test";
import { createChapter, createEpisode, createProjectInUi, saveStructuredDraft } from "./helpers";

test("runs the style analysis flow against the real API and worker", async ({ page, request }) => {
  const projectId = await createProjectInUi(page, "e2e-style");
  const chapter = await createChapter(request, projectId, "capture chapter");
  const episode = await createEpisode(request, projectId, chapter.id, "capture episode");
  await saveStructuredDraft(request, projectId, episode.id, {
    html: '<p data-np-type="narration">短い文体分析用の本文です。</p>',
    source_agent: "style-analysis-e2e",
    change_summary: "Project draft capture fixture",
  });

  await page.goto(`/projects/${projectId}/style-analysis/sources`);
  await expect(page.getByRole("heading", { name: "Sources" })).toBeVisible();
  await expect(page.getByText(/Network URLやRefresh操作はありません/)).toBeVisible();
  await page.getByLabel("Local file").setInputFiles({
    name: "fixture.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("短い一文です。もう一文です。"),
  });
  await page.getByRole("button", { name: "Import" }).click();
  await expect(page.getByText(/新しいSourceを登録しました/)).toBeVisible();

  const referenceWorkLink = page.getByRole("link", { name: /Reference Work #/ });
  const referenceWorkHref = await referenceWorkLink.getAttribute("href");
  expect(referenceWorkHref).toMatch(/reference-works\/[1-9]\d*$/);
  const referenceWorkId = referenceWorkHref?.split("/").at(-1);
  expect(referenceWorkId).toBeTruthy();
  await referenceWorkLink.click();
  await page.getByRole("button", { name: "Deterministic analyze" }).click();
  await expect(page.getByText(/Analysis job #\d+/)).toBeVisible();
  await expect(page.getByText("succeeded", { exact: true }).last()).toBeVisible({ timeout: 20_000 });

  await page.getByRole("link", { name: "Document" }).click();
  await expect(page.getByRole("heading", { name: /Document Analysis #/ })).toBeVisible();
  await page.getByLabel("Analyze preset").selectOption("full");
  await page.getByRole("button", { name: "Analyze selected revisions" }).click();
  await expect(page.getByText(/Analysis job #\d+/)).toBeVisible();
  await expect(page.getByText("succeeded", { exact: true }).last()).toBeVisible({ timeout: 20_000 });

  const corpusName = "Real backend corpus";
  await page.getByRole("link", { name: "Corpora / Aggregate" }).click();
  await page.getByLabel("Name").first().fill(corpusName);
  await page.getByRole("button", { name: "Save corpus" }).click();
  await expect(page.getByRole("button", { name: corpusName })).toBeVisible();
  await page.getByRole("button", { name: corpusName }).click();
  await page.getByLabel("Add reference work").selectOption(referenceWorkId as string);
  await page.getByRole("button", { name: "Add work" }).click();
  await page.getByRole("button", { name: "Recompute aggregates" }).click();
  await expect(page.getByText(/Analysis job #\d+/)).toBeVisible();
  await expect(page.getByText("succeeded", { exact: true }).last()).toBeVisible({ timeout: 20_000 });

  await page.getByRole("link", { name: "Profiles" }).click();
  await page.getByLabel("Name").first().fill("Real manual profile");
  await page.getByRole("button", { name: "Save draft profile" }).click();
  await expect(page.getByText("Real manual profile")).toBeVisible();
  await page.getByLabel("Name").nth(1).fill("Real corpus profile");
  const corpusValue = await page.getByLabel("Corpus").locator("option").filter({ hasText: corpusName }).getAttribute("value");
  expect(corpusValue).toBeTruthy();
  await page.getByLabel("Corpus").selectOption(corpusValue as string);
  await expect(page.getByLabel("Aggregate group")).toHaveValue(/\.len\./);
  await expect(page.getByLabel("preferred,min,max aggregate IDs")).not.toHaveValue("");
  await page.getByRole("button", { name: "Build from exact aggregates" }).click();
  await expect(page.getByText("Real corpus profile")).toBeVisible();

  await page.getByRole("link", { name: "Lint" }).click();
  await expect(page.getByRole("button", { name: "Capture latest Project Draft" })).toBeVisible();
  await page.getByRole("button", { name: "Capture latest Project Draft" }).click();
  await expect(page.getByText(/Project DraftをCaptureしました/)).toBeVisible();
  const capturedDocumentLink = page.getByRole("link", { name: /Document #/ });
  const capturedDocumentHref = await capturedDocumentLink.getAttribute("href");
  expect(capturedDocumentHref).toBeTruthy();
  const capturedDocumentId = capturedDocumentHref?.split("/").at(-1);
  expect(capturedDocumentId).toMatch(/^[1-9]\d*$/);
  const capturedStorage = await page.evaluate(() => Object.entries(sessionStorage));
  expect(capturedStorage.length).toBeGreaterThan(0);
  await capturedDocumentLink.click();
  await expect(page.getByRole("heading", { name: /Document Analysis #/ })).toBeVisible();
  await page.getByLabel("Analyze preset").selectOption("full");
  await page.getByLabel("Rebuild structure").check();
  await page.getByRole("button", { name: "Analyze selected revisions" }).click();
  await expect(page.getByText(/Analysis job #\d+/)).toBeVisible();
  await expect(page.getByText("succeeded", { exact: true }).last()).toBeVisible({ timeout: 20_000 });
  await page.goto(`/projects/${projectId}/style-analysis/lint`);
  await expect(page.getByRole("heading", { name: "Lint", exact: true })).toBeVisible();
  await page.getByLabel("Document").selectOption(capturedDocumentId as string);
  await expect(page.getByLabel("Structure revision")).not.toHaveValue("");
  const profileSelect = page.getByLabel("Profile", { exact: true });
  const profileValue = await profileSelect.locator("option").filter({ hasText: "Real corpus profile" }).getAttribute("value");
  expect(profileValue).toBeTruthy();
  await profileSelect.selectOption(profileValue as string);
  await expect(page.getByLabel("Profile version")).toHaveValue("1");
  await page.getByRole("button", { name: "Run lint" }).click();
  await expect(page.getByText("Coverage")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/Analysis job #\d+/)).toBeVisible();
});
