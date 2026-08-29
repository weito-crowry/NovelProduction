import { expect, test } from "@playwright/test";
import { createChapter, createEpisode, createProject } from "./helpers";

test("appends plain manuscript revisions and preserves earlier history", async ({ page, request }) => {
  const project = await createProject(request, "e2e-manuscript");
  const chapter = await createChapter(request, project.project_id, "Manuscript chapter");
  const episode = await createEpisode(request, project.project_id, chapter.id, "Manuscript episode");
  await page.goto(`/projects/${project.project_id}/manuscript/${episode.id}`);
  await expect(page.getByText("No draft revisions yet.")).toBeVisible();

  const body = page.getByLabel("Manuscript body");
  await body.fill("Revision one body");
  await expect(page.getByText("Unsaved changes")).toBeVisible();
  await page.getByRole("button", { name: "Save new revision" }).click();
  await expect(page.getByText("Saved revision 1")).toBeVisible();
  await expect(page.getByText("Revision 1", { exact: true })).toBeVisible();

  await body.fill("Revision two body");
  await page.getByRole("button", { name: "Save new revision" }).click();
  await expect(page.getByText("Saved revision 2")).toBeVisible();
  await expect(page.getByText("Revision 1", { exact: true })).toBeVisible();
  await expect(page.getByText("Revision 2", { exact: true })).toBeVisible();

  const revisionOne = await request.get(
    `/api/v1/projects/${project.project_id}/episodes/${episode.id}/draft?revision=1`,
  );
  const revisionTwo = await request.get(
    `/api/v1/projects/${project.project_id}/episodes/${episode.id}/draft?revision=2`,
  );
  expect((await revisionOne.json()).data.body).toBe("Revision one body");
  expect((await revisionTwo.json()).data.body).toBe("Revision two body");
  expect((await revisionTwo.json()).data.parent_draft_id).toBe((await revisionOne.json()).data.id);
  expect((await revisionTwo.json()).data.source_agent).toBe("webui");
});
