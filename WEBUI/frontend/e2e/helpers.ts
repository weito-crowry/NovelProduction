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

export async function createCharacter(
  request: APIRequestContext,
  projectId: string,
  displayName: string,
): Promise<{ id: number; display_name: string; version: number }> {
  const response = await request.post(
    `/api/v1/projects/${projectId}/characters`,
    { data: { display_name: displayName } },
  );
  return (await readEnvelope(response, 201)) as {
    id: number;
    display_name: string;
    version: number;
  };
}

export async function saveStructuredDraft(
  request: APIRequestContext,
  projectId: string,
  episodeId: number,
  input: Record<string, unknown>,
): Promise<{ id: number; revision: number; parent_draft_id: number | null; id_map: Record<string, string> }> {
  const response = await request.post(
    `/api/v1/projects/${projectId}/episodes/${episodeId}/drafts`,
    { data: input },
  );
  const result = await readEnvelope(response, 201);
  if (!isSaveResult(result)) throw new Error("Structured draft response did not contain a save result.");
  return result;
}

export async function createE4ManuscriptFixture(
  request: APIRequestContext,
  prefix: string,
) {
  const structure = await createStructureFixture(request, prefix);
  const character = await createCharacter(request, structure.projectId, "E4 Character");
  const revisionOne = await saveStructuredDraft(request, structure.projectId, structure.episode.id, {
    html: [
      '<p id="narration-main" data-np-type="narration">これは構造化された本文です。</p>',
      '<p id="dialogue-main" data-np-type="dialogue"><ruby>東京<rt>とうきょう</rt></ruby>へ急げ。</p>',
      '<p id="emphasis-main" data-np-type="thought"><em data-emphasis="dot">急げ</em></p>',
      '<h2 id="heading-main">第二章</h2>',
      '<blockquote id="quote-main">引用された言葉。</blockquote>',
      '<hr id="separator-main">',
      '<p id="note-fixture-1" data-np-type="note">Production note</p>',
    ].join(""),
    source_agent: "e2e",
    change_summary: "Initial structured fixture",
  });
  const dialogueId = revisionOne.id_map["dialogue-main"];
  if (!dialogueId) throw new Error("Dialogue block ID was not returned by the API.");
  const revisionTwo = await saveStructuredDraft(request, structure.projectId, structure.episode.id, {
    expected_parent_draft_id: revisionOne.id,
    metadata_updates: {
      [dialogueId]: {
        attrs: { scene_id: structure.scene.id, speaker_character_id: character.id },
        annotations: {
          emotions: ["焦り"],
          mood: "tense",
          "analysis-bundle": { nested: ["kept", { value: true }] },
        },
      },
    },
    source_agent: "e2e",
    change_summary: "Add dialogue metadata",
  });
  return { ...structure, character, revisionOne, revisionTwo, dialogueId };
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

function isSaveResult(value: unknown): value is { id: number; revision: number; parent_draft_id: number | null; id_map: Record<string, string> } {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const result = value as { id?: unknown; revision?: unknown; parent_draft_id?: unknown; id_map?: unknown };
  return typeof result.id === "number" && typeof result.revision === "number" && (typeof result.parent_draft_id === "number" || result.parent_draft_id === null) && typeof result.id_map === "object" && result.id_map !== null && !Array.isArray(result.id_map);
}
