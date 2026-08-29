import { expect, test } from "@playwright/test";
import { createProjectInUi } from "./helpers";

test("shows VERSION_CONFLICT local/latest data without an automatic retry", async ({ page, request }) => {
  const projectId = await createProjectInUi(page, "e2e-conflict");
  let browserWrites = 0;
  page.on("request", (outgoing) => {
    if (outgoing.method() === "PATCH" && outgoing.url().endsWith("/work")) {
      browserWrites += 1;
    }
  });

  const title = page.getByLabel("Working title");
  await title.fill("Local unsaved title");
  const external = await request.patch(`/api/v1/projects/${projectId}/work`, {
    data: { working_title: "External database title", expected_version: 1 },
  });
  expect(external.status()).toBe(200);

  await page.getByRole("button", { name: "Save changes" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("Local unsaved title");
  await expect(dialog).toContainText("External database title");
  await page.getByRole("button", { name: "Keep local edits" }).click();
  await expect(title).toHaveValue("Local unsaved title");
  await expect(page.getByText("Unsaved changes")).toBeVisible();
  await expect.poll(() => browserWrites).toBe(1);
});
