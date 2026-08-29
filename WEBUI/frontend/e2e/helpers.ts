import { expect, type APIRequestContext, type Page } from "@playwright/test";

let projectCounter = 0;

export function uniqueProjectId(prefix: string): string {
  projectCounter += 1;
  return `${prefix}-${Date.now().toString(36)}-${projectCounter}`.toLowerCase();
}

export async function createProject(
  request: APIRequestContext,
  prefix: string,
): Promise<{ project_id: string; working_title: string }> {
  const projectId = uniqueProjectId(prefix);
  const response = await request.post("/api/v1/projects", {
    data: { project_id: projectId, working_title: `${prefix} project` },
  });
  return readJson(response, 201);
}

export async function createProjectInUi(
  page: Page,
  prefix: string,
): Promise<string> {
  const projectId = uniqueProjectId(prefix);
  await page.goto("/");
  await page.getByLabel("Working title").fill(`${prefix} project`);
  await page.getByLabel("Project ID (optional)").fill(projectId);
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/dashboard$`));
  return projectId;
}

export async function createChapter(
  request: APIRequestContext,
  projectId: string,
  title: string,
): Promise<{ id: number; title: string; version: number }> {
  const response = await request.post(
    `/api/v1/projects/${projectId}/chapters`,
    { data: { title } },
  );
  return (await readEnvelope(response, 201)) as {
    id: number;
    title: string;
    version: number;
  };
}

export async function createEpisode(
  request: APIRequestContext,
  projectId: string,
  chapterId: number,
  title: string,
): Promise<{ id: number; title: string; version: number }> {
  const response = await request.post(
    `/api/v1/projects/${projectId}/chapters/${chapterId}/episodes`,
    { data: { title, foreshadowing_notes: [] } },
  );
  return (await readEnvelope(response, 201)) as {
    id: number;
    title: string;
    version: number;
  };
}

export async function createScene(
  request: APIRequestContext,
  projectId: string,
  episodeId: number,
  title: string,
): Promise<{ id: number; title: string; version: number }> {
  const response = await request.post(
    `/api/v1/projects/${projectId}/episodes/${episodeId}/scenes`,
    { data: { title } },
  );
  return (await readEnvelope(response, 201)) as {
    id: number;
    title: string;
    version: number;
  };
}

export async function createWorldFact(
  request: APIRequestContext,
  projectId: string,
  statement: string,
  title: string,
): Promise<{ id: number; title: string; statement: string; version: number }> {
  const response = await request.post(
    `/api/v1/projects/${projectId}/world-facts`,
    { data: { statement, title } },
  );
  return (await readEnvelope(response, 201)) as {
    id: number;
    title: string;
    statement: string;
    version: number;
  };
}

export async function createStructureFixture(
  request: APIRequestContext,
  prefix: string,
) {
  const project = await createProject(request, prefix);
  const chapter = await createChapter(request, project.project_id, `${prefix} chapter`);
  const episode = await createEpisode(
    request,
    project.project_id,
    chapter.id,
    `${prefix} episode`,
  );
  const scene = await createScene(
    request,
    project.project_id,
    episode.id,
    `${prefix} scene`,
  );
  return { projectId: project.project_id, chapter, episode, scene };
}

async function readJson<T>(response: Awaited<ReturnType<APIRequestContext["post"]>>, expected: number): Promise<T> {
  if (response.status() !== expected) {
    throw new Error(`Expected HTTP ${expected}, got ${response.status()}: ${await response.text()}`);
  }
  return (await response.json()) as T;
}

async function readEnvelope(
  response: Awaited<ReturnType<APIRequestContext["post"]>>,
  expected: number,
): Promise<unknown> {
  const payload = await readJson<{ data: unknown }>(response, expected);
  return payload.data;
}
