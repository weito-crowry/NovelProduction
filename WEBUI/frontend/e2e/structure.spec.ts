import { expect, test } from "@playwright/test";
import { createProjectInUi } from "./helpers";

test("creates and navigates Chapter, Episode, and Scene through the structure tree", async ({ page }) => {
  const projectId = await createProjectInUi(page, "e2e-structure");
  await page.goto(`/projects/${projectId}/structure`);

  await page.getByRole("button", { name: "Add chapter" }).click();
  await expect(page.getByRole("dialog", { name: "Add chapter" })).toBeVisible();
  await page.getByRole("dialog", { name: "Add chapter" }).getByLabel("Title").fill("Chapter one");
  await page.getByRole("dialog", { name: "Add chapter" }).getByRole("button", { name: "Create" }).click();
  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/structure/chapters/\\d+$`));
  await expect(page.getByRole("link", { name: /Chapter one/ })).toBeVisible();

  await page.getByRole("button", { name: "Add episode" }).first().click();
  await expect(page.getByRole("dialog", { name: "Add episode" })).toBeVisible();
  await page.getByRole("dialog", { name: "Add episode" }).getByLabel("Title").fill("Episode one");
  await page.getByRole("dialog", { name: "Add episode" }).getByRole("button", { name: "Create" }).click();
  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/structure/episodes/\\d+$`));
  await expect(page.getByRole("link", { name: /Episode one/ })).toBeVisible();

  await page.getByRole("button", { name: "Add scene" }).first().click();
  await expect(page.getByRole("dialog", { name: "Add scene" })).toBeVisible();
  await page.getByRole("dialog", { name: "Add scene" }).getByLabel("Title").fill("Scene one");
  await page.getByRole("dialog", { name: "Add scene" }).getByRole("button", { name: "Create" }).click();
  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/structure/scenes/\\d+$`));
  await expect(page.getByRole("link", { name: /Scene one/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Scene" })).toBeVisible();
});
