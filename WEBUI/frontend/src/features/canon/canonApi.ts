import { apiRequest } from "../../api/client";
import type { CanonDecisionRecord, CanonStatusSet } from "../../api/types";

const apiBase = "/api/v1";

function canonPath(projectId: string, suffix = ""): string {
  return `${apiBase}/projects/${encodeURIComponent(projectId)}/canon${suffix}`;
}

export function fetchCanonDecisions(
  projectId: string,
  limit = 50,
  offset = 0,
): Promise<CanonDecisionRecord[]> {
  return apiRequest<CanonDecisionRecord[]>(
    `${canonPath(projectId, "/decisions")}?limit=${limit}&offset=${offset}`,
    { projectId },
  );
}

export function searchCanonDecisions(
  projectId: string,
  query: string,
  limit = 50,
): Promise<CanonDecisionRecord[]> {
  if (!query.trim()) return Promise.resolve([]);
  return apiRequest<CanonDecisionRecord[]>(
    `${canonPath(projectId, "/decisions/search")}?query=${encodeURIComponent(query)}&limit=${limit}`,
    { projectId },
  );
}

export function fetchCanonDecision(
  projectId: string,
  decisionId: number,
): Promise<CanonDecisionRecord> {
  return apiRequest<CanonDecisionRecord>(
    canonPath(projectId, `/decisions/${decisionId}`),
    { projectId },
  );
}

export function setCanonStatus(
  projectId: string,
  input: CanonStatusSet,
): Promise<CanonDecisionRecord> {
  return apiRequest<CanonDecisionRecord>(canonPath(projectId, "/status"), {
    method: "POST",
    body: input,
    projectId,
  });
}
