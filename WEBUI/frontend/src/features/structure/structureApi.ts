import { apiRequest } from "../../api/client";
import type {
  ChapterCreate,
  ChapterRecord,
  ChapterUpdate,
  EpisodeCreate,
  EpisodeRecord,
  EpisodeReferenceAdd,
  EpisodeReferenceRecord,
  EpisodeUpdate,
  EpisodeView,
  OutlineView,
  ReorderInput,
  SceneCreate,
  SceneRecord,
  SceneUpdate,
} from "../../api/types";

const apiBase = "/api/v1";

function structurePath(projectId: string, suffix = ""): string {
  return `${apiBase}/projects/${encodeURIComponent(projectId)}${suffix}`;
}

export function fetchOutline(projectId: string): Promise<OutlineView> {
  return apiRequest<OutlineView>(
    structurePath(projectId, "/views/outline"),
    { projectId },
  );
}

export function createChapter(
  projectId: string,
  input: ChapterCreate,
): Promise<ChapterRecord> {
  return apiRequest<ChapterRecord>(structurePath(projectId, "/chapters"), {
    method: "POST",
    body: input,
    projectId,
  });
}

export function updateChapter(
  projectId: string,
  chapterId: number,
  input: ChapterUpdate,
): Promise<ChapterRecord> {
  return apiRequest<ChapterRecord>(
    structurePath(projectId, `/chapters/${chapterId}`),
    { method: "PATCH", body: input, projectId },
  );
}

export function reorderChapter(
  projectId: string,
  chapterId: number,
  input: ReorderInput,
): Promise<ChapterRecord[]> {
  return apiRequest<ChapterRecord[]>(
    structurePath(projectId, `/chapters/${chapterId}/reorder`),
    { method: "POST", body: input, projectId },
  );
}

export function createEpisode(
  projectId: string,
  chapterId: number,
  input: EpisodeCreate,
): Promise<EpisodeRecord> {
  return apiRequest<EpisodeRecord>(
    structurePath(projectId, `/chapters/${chapterId}/episodes`),
    { method: "POST", body: input, projectId },
  );
}

export function fetchEpisode(
  projectId: string,
  episodeId: number,
): Promise<EpisodeRecord> {
  return apiRequest<EpisodeRecord>(
    structurePath(projectId, `/episodes/${episodeId}`),
    { projectId },
  );
}

export function updateEpisode(
  projectId: string,
  episodeId: number,
  input: EpisodeUpdate,
): Promise<EpisodeRecord> {
  return apiRequest<EpisodeRecord>(
    structurePath(projectId, `/episodes/${episodeId}`),
    { method: "PATCH", body: input, projectId },
  );
}

export function reorderEpisode(
  projectId: string,
  episodeId: number,
  input: ReorderInput,
): Promise<EpisodeRecord[]> {
  return apiRequest<EpisodeRecord[]>(
    structurePath(projectId, `/episodes/${episodeId}/reorder`),
    { method: "POST", body: input, projectId },
  );
}

export function createScene(
  projectId: string,
  episodeId: number,
  input: SceneCreate,
): Promise<SceneRecord> {
  return apiRequest<SceneRecord>(
    structurePath(projectId, `/episodes/${episodeId}/scenes`),
    { method: "POST", body: input, projectId },
  );
}

export function fetchScene(
  projectId: string,
  sceneId: number,
): Promise<SceneRecord> {
  return apiRequest<SceneRecord>(
    structurePath(projectId, `/scenes/${sceneId}`),
    { projectId },
  );
}

export function updateScene(
  projectId: string,
  sceneId: number,
  input: SceneUpdate,
): Promise<SceneRecord> {
  return apiRequest<SceneRecord>(
    structurePath(projectId, `/scenes/${sceneId}`),
    { method: "PATCH", body: input, projectId },
  );
}

export function reorderScene(
  projectId: string,
  sceneId: number,
  input: ReorderInput,
): Promise<SceneRecord[]> {
  return apiRequest<SceneRecord[]>(
    structurePath(projectId, `/scenes/${sceneId}/reorder`),
    { method: "POST", body: input, projectId },
  );
}

export function fetchEpisodeView(
  projectId: string,
  episodeId: number,
): Promise<EpisodeView> {
  return apiRequest<EpisodeView>(
    structurePath(projectId, `/views/episodes/${episodeId}`),
    { projectId },
  );
}

export function fetchEpisodeReferences(
  projectId: string,
  episodeId: number,
): Promise<EpisodeReferenceRecord[]> {
  return apiRequest<EpisodeReferenceRecord[]>(
    structurePath(projectId, `/episodes/${episodeId}/references`),
    { projectId },
  );
}

export function addEpisodeReference(
  projectId: string,
  episodeId: number,
  input: EpisodeReferenceAdd,
): Promise<EpisodeReferenceRecord> {
  return apiRequest<EpisodeReferenceRecord>(
    structurePath(projectId, `/episodes/${episodeId}/references`),
    { method: "POST", body: input, projectId },
  );
}

export function removeEpisodeReference(
  projectId: string,
  episodeId: number,
  referenceType: string,
  targetId: number,
): Promise<unknown> {
  return apiRequest(
    structurePath(
      projectId,
      `/episodes/${episodeId}/references/${encodeURIComponent(referenceType)}/${targetId}`,
    ),
    { method: "DELETE", projectId },
  );
}
