import { apiRequest } from "../../api/client";
import type {
  CharacterKnowledgeEventRecord,
  CharacterKnowledgeSet,
  InformationCreate,
  InformationItemRecord,
  InformationUpdate,
  ReaderDisclosureRecord,
  ReaderDisclosureSet,
} from "../../api/types";

const apiBase = "/api/v1";

function informationPath(projectId: string, suffix = ""): string {
  return `${apiBase}/projects/${encodeURIComponent(projectId)}${suffix}`;
}

export function fetchInformation(
  projectId: string,
  limit = 50,
  offset = 0,
): Promise<InformationItemRecord[]> {
  return apiRequest<InformationItemRecord[]>(
    `${informationPath(projectId, "/information")}?limit=${limit}&offset=${offset}`,
    { projectId },
  );
}

export function searchInformation(
  projectId: string,
  query: string,
  limit = 50,
): Promise<InformationItemRecord[]> {
  if (!query.trim()) return Promise.resolve([]);
  return apiRequest<InformationItemRecord[]>(
    `${informationPath(projectId, "/information/search")}?query=${encodeURIComponent(query)}&limit=${limit}`,
    { projectId },
  );
}

export function fetchInformationItem(
  projectId: string,
  informationItemId: number,
): Promise<InformationItemRecord> {
  return apiRequest<InformationItemRecord>(
    informationPath(projectId, `/information/${informationItemId}`),
    { projectId },
  );
}

export function createInformation(
  projectId: string,
  input: InformationCreate,
): Promise<InformationItemRecord> {
  return apiRequest<InformationItemRecord>(informationPath(projectId, "/information"), {
    method: "POST",
    body: input,
    projectId,
  });
}

export function updateInformation(
  projectId: string,
  informationItemId: number,
  input: InformationUpdate,
): Promise<InformationItemRecord> {
  return apiRequest<InformationItemRecord>(
    informationPath(projectId, `/information/${informationItemId}`),
    { method: "PATCH", body: input, projectId },
  );
}

export function fetchReaderDisclosure(
  projectId: string,
  informationItemId: number,
): Promise<ReaderDisclosureRecord | null> {
  return apiRequest<ReaderDisclosureRecord | null>(
    informationPath(
      projectId,
      `/information/${informationItemId}/reader-disclosure`,
    ),
    { projectId },
  );
}

export function setReaderDisclosure(
  projectId: string,
  informationItemId: number,
  input: ReaderDisclosureSet,
): Promise<ReaderDisclosureRecord> {
  return apiRequest<ReaderDisclosureRecord>(
    informationPath(
      projectId,
      `/information/${informationItemId}/reader-disclosure`,
    ),
    { method: "PUT", body: input, projectId },
  );
}

export function fetchEffectiveKnowledge(
  projectId: string,
  characterId: number,
  episodeId: number,
): Promise<import("../../api/types").EffectiveKnowledgeRecord[]> {
  return apiRequest<import("../../api/types").EffectiveKnowledgeRecord[]>(
    `${informationPath(projectId, `/characters/${characterId}/knowledge`)}?episode_id=${episodeId}`,
    { projectId },
  );
}

export function fetchExactKnowledge(
  projectId: string,
  characterId: number,
  informationItemId: number,
  episodeId: number,
): Promise<CharacterKnowledgeEventRecord | null> {
  return apiRequest<CharacterKnowledgeEventRecord | null>(
    `${informationPath(projectId, `/characters/${characterId}/knowledge/${informationItemId}`)}?episode_id=${episodeId}`,
    { projectId },
  );
}

export function saveExactKnowledge(
  projectId: string,
  characterId: number,
  informationItemId: number,
  input: CharacterKnowledgeSet,
): Promise<CharacterKnowledgeEventRecord> {
  return apiRequest<CharacterKnowledgeEventRecord>(
    informationPath(
      projectId,
      `/characters/${characterId}/knowledge/${informationItemId}`,
    ),
    { method: "PUT", body: input, projectId },
  );
}
