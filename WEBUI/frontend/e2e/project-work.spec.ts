import { expect, test } from "@playwright/test";
import { createProjectInUi } from "./helpers";

test("creates a project and only saves Work changes explicitly", async ({ page }) => {
  const projectId = await createProjectInUi(page, "e2e-work");
  let workWrites = 0;
  page.on("request", (request) => {
    if (request.method() === "PATCH" && request.url().endsWith("/work")) {
      workWrites += 1;
    }
  });

  await expect(page.getByRole("heading", { name: "Work editor" })).toBeVisible();
  const genre = page.getByLabel("Genre");
  await genre.fill("mystery");
  await expect(page.getByText("Unsaved changes")).toBeVisible();
  await expect.poll(() => workWrites).toBe(0);

  await page.getByRole("button", { name: "Save changes" }).click();
  await expect.poll(() => workWrites).toBe(1);
  await expect(page.getByText("Saved")).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/dashboard$`));
  await page.reload();
  await expect(page.getByLabel("Genre")).toHaveValue("mystery");
});
