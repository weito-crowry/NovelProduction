import { apiRequest } from "../../api/client";
import type {
  WorldFactCreate,
  WorldFactRecord,
  WorldFactUpdate,
} from "../../api/types";

const apiBase = "/api/v1";

function worldPath(projectId: string, suffix = ""): string {
  return `${apiBase}/projects/${encodeURIComponent(projectId)}${suffix}`;
}

export function fetchWorldFacts(
  projectId: string,
  limit = 50,
  offset = 0,
): Promise<WorldFactRecord[]> {
  return apiRequest<WorldFactRecord[]>(
    `${worldPath(projectId, "/world-facts")}?limit=${limit}&offset=${offset}`,
    { projectId },
  );
}

export function searchWorldFacts(
  projectId: string,
  query: string,
  limit = 50,
): Promise<WorldFactRecord[]> {
  if (!query.trim()) return Promise.resolve([]);
  return apiRequest<WorldFactRecord[]>(
    `${worldPath(projectId, "/world-facts/search")}?query=${encodeURIComponent(query)}&limit=${limit}`,
    { projectId },
  );
}

export function fetchWorldFact(projectId: string, factId: number): Promise<WorldFactRecord> {
  return apiRequest<WorldFactRecord>(worldPath(projectId, `/world-facts/${factId}`), { projectId });
}

export function createWorldFact(projectId: string, input: WorldFactCreate): Promise<WorldFactRecord> {
  return apiRequest<WorldFactRecord>(worldPath(projectId, "/world-facts"), {
    method: "POST",
    body: input,
    projectId,
  });
}

export function updateWorldFact(
  projectId: string,
  factId: number,
  input: WorldFactUpdate,
): Promise<WorldFactRecord> {
  return apiRequest<WorldFactRecord>(worldPath(projectId, `/world-facts/${factId}`), {
    method: "PATCH",
    body: input,
    projectId,
  });
}
