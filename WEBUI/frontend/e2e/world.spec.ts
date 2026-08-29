import { expect, test } from "@playwright/test";
import { createProjectInUi } from "./helpers";

test("creates, reads, and explicitly saves a World fact", async ({ page }) => {
  const projectId = await createProjectInUi(page, "e2e-world");
  await page.goto(`/projects/${projectId}/world`);
  await page.getByRole("button", { name: "Add world fact" }).click();
  await page.getByLabel("Statement").fill("The north wind never stops.");
  await page.getByLabel("Title").fill("North wind");
  await page.getByRole("button", { name: "Create world fact" }).click();

  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/world/\\d+$`));
  await expect(page.getByRole("heading", { name: "North wind" })).toBeVisible();
  const title = page.getByLabel("Title");
  await title.fill("The north wind");
  await expect(page.getByText("Unsaved changes")).toBeVisible();
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Saved")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Title")).toHaveValue("The north wind");
});
