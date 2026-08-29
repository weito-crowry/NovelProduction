import { apiRequest } from "../../api/client";
import type {
  CharacterCreate,
  CharacterRecord,
  CharacterStateRecord,
  CharacterStateSet,
  CharacterUpdate,
  EffectiveKnowledgeRecord,
  RelationshipCreate,
  RelationshipRecord,
  RelationshipUpdate,
} from "../../api/types";

const apiBase = "/api/v1";

function characterPath(projectId: string, suffix = ""): string {
  return `${apiBase}/projects/${encodeURIComponent(projectId)}${suffix}`;
}

export function fetchCharacters(projectId: string, limit = 50, offset = 0): Promise<CharacterRecord[]> {
  return apiRequest<CharacterRecord[]>(
    `${characterPath(projectId, "/characters")}?limit=${limit}&offset=${offset}`,
    { projectId },
  );
}

export function searchCharacters(projectId: string, query: string, limit = 50): Promise<CharacterRecord[]> {
  if (!query.trim()) return Promise.resolve([]);
  return apiRequest<CharacterRecord[]>(
    `${characterPath(projectId, "/characters/search")}?query=${encodeURIComponent(query)}&limit=${limit}`,
    { projectId },
  );
}

export function fetchCharacter(projectId: string, characterId: number): Promise<CharacterRecord> {
  return apiRequest<CharacterRecord>(characterPath(projectId, `/characters/${characterId}`), { projectId });
}

export function createCharacter(projectId: string, input: CharacterCreate): Promise<CharacterRecord> {
  return apiRequest<CharacterRecord>(characterPath(projectId, "/characters"), {
    method: "POST",
    body: input,
    projectId,
  });
}

export function updateCharacter(
  projectId: string,
  characterId: number,
  input: CharacterUpdate,
): Promise<CharacterRecord> {
  return apiRequest<CharacterRecord>(characterPath(projectId, `/characters/${characterId}`), {
    method: "PATCH",
    body: input,
    projectId,
  });
}

export function fetchRelationships(projectId: string, characterId: number): Promise<RelationshipRecord[]> {
  return apiRequest<RelationshipRecord[]>(
    `${characterPath(projectId, "/relationships")}?character_id=${characterId}&limit=100`,
    { projectId },
  );
}

export function createRelationship(projectId: string, input: RelationshipCreate): Promise<RelationshipRecord> {
  return apiRequest<RelationshipRecord>(characterPath(projectId, "/relationships"), {
    method: "POST",
    body: input,
    projectId,
  });
}

export function updateRelationship(
  projectId: string,
  relationshipId: number,
  input: RelationshipUpdate,
): Promise<RelationshipRecord> {
  return apiRequest<RelationshipRecord>(
    characterPath(projectId, `/relationships/${relationshipId}`),
    { method: "PATCH", body: input, projectId },
  );
}

export function fetchCharacterState(
  projectId: string,
  characterId: number,
  episodeId: number,
): Promise<CharacterStateRecord | null> {
  return apiRequest<CharacterStateRecord | null>(
    characterPath(projectId, `/characters/${characterId}/states/${episodeId}`),
    { projectId },
  );
}

export function fetchCharacterStateHistory(
  projectId: string,
  characterId: number,
): Promise<CharacterStateRecord[]> {
  return apiRequest<CharacterStateRecord[]>(
    characterPath(projectId, `/characters/${characterId}/states`),
    { projectId },
  );
}

export function setCharacterState(
  projectId: string,
  characterId: number,
  episodeId: number,
  input: CharacterStateSet,
): Promise<CharacterStateRecord> {
  return apiRequest<CharacterStateRecord>(
    characterPath(projectId, `/characters/${characterId}/states/${episodeId}`),
    { method: "PUT", body: input, projectId },
  );
}

export function fetchCharacterKnowledge(
  projectId: string,
  characterId: number,
  episodeId: number,
): Promise<EffectiveKnowledgeRecord[]> {
  return apiRequest<EffectiveKnowledgeRecord[]>(
    `${characterPath(projectId, `/characters/${characterId}/knowledge`)}?episode_id=${episodeId}`,
    { projectId },
  );
}
