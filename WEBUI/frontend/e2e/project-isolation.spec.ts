import { expect, test } from "@playwright/test";
import { createProject, createWorldFact } from "./helpers";

test("keeps overlapping numeric entity IDs isolated between project routes", async ({ page, request }) => {
  const projectA = await createProject(request, "e2e-isolation-a");
  const projectB = await createProject(request, "e2e-isolation-b");
  const factA = await createWorldFact(request, projectA.project_id, "A only statement", "Project A fact");
  const factB = await createWorldFact(request, projectB.project_id, "B only statement", "Project B fact");
  expect(factA.id).toBe(factB.id);

  await page.goto(`/projects/${projectA.project_id}/world/${factA.id}`);
  await expect(page.getByRole("heading", { name: "Project A fact" })).toBeVisible();
  await expect(page.getByLabel("Statement")).toHaveValue("A only statement");

  await page.goto(`/projects/${projectB.project_id}/world/${factB.id}`);
  await expect(page.getByRole("heading", { name: "Project B fact" })).toBeVisible();
  await expect(page.getByLabel("Statement")).toHaveValue("B only statement");
  await expect(page.getByLabel("Statement")).not.toHaveValue("A only statement");

  await page.goto(`/projects/${projectA.project_id}/world/${factA.id}`);
  await expect(page.getByLabel("Statement")).toHaveValue("A only statement");
});
