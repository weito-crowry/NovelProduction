import { expect, test } from "@playwright/test";
import { createProject, createStructureFixture, createWorldFact } from "./helpers";

test("keeps dashboard Work controls usable at the narrow viewport", async ({ page, request }) => {
  const project = await createProject(request, "e2e-mobile-dashboard");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/projects/${project.project_id}/dashboard`);
  await expect(page.getByRole("button", { name: "Open navigation" })).toBeVisible();
  await expect(page.locator("#project-navigation")).toBeHidden();
  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(page.getByRole("button", { name: "Hide navigation" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Open navigation" })).toBeFocused();

  await page.getByLabel("Genre").fill("mobile mystery");
  await expect(page.getByText("Unsaved changes")).toBeVisible();
  await expect(page.getByRole("button", { name: "Save changes" })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});

test("uses full-width entity and structure detail panes on narrow routes", async ({ page, request }) => {
  const structure = await createStructureFixture(request, "e2e-mobile-structure");
  const fact = await createWorldFact(request, structure.projectId, "Narrow statement", "Narrow fact");
  await page.setViewportSize({ width: 390, height: 844 });

  await page.goto(`/projects/${structure.projectId}/structure/scenes/${structure.scene.id}`);
  await expect(page.locator(".structure-tree-pane")).toBeHidden();
  await expect(page.locator(".structure-detail-pane")).toBeVisible();
  await expect(page.getByRole("button", { name: "Save changes" })).toBeVisible();

  await page.goto(`/projects/${structure.projectId}/world/${fact.id}`);
  await expect(page.locator(".entity-list-pane")).toBeHidden();
  await expect(page.locator(".entity-detail-pane")).toBeVisible();
  await expect(page.getByRole("button", { name: "Save changes" })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});
