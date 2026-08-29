import { apiRequest } from "../../api/client";
import type { DraftMetadata, DraftRecord, DraftSave } from "../../api/types";

const apiBase = "/api/v1";

function manuscriptPath(projectId: string, suffix = ""): string {
  return `${apiBase}/projects/${encodeURIComponent(projectId)}${suffix}`;
}

export function fetchLatestDraft(
  projectId: string,
  episodeId: number,
): Promise<DraftRecord | null> {
  return apiRequest<DraftRecord | null>(
    manuscriptPath(projectId, `/episodes/${episodeId}/draft`),
    { projectId },
  );
}

export function fetchDraftHistory(
  projectId: string,
  episodeId: number,
  limit = 20,
): Promise<DraftMetadata[]> {
  return apiRequest<DraftMetadata[]>(
    `${manuscriptPath(projectId, `/episodes/${episodeId}/drafts`)}?limit=${limit}`,
    { projectId },
  );
}

export function fetchDraftRevision(
  projectId: string,
  episodeId: number,
  revision: number,
): Promise<DraftRecord | null> {
  return apiRequest<DraftRecord | null>(
    `${manuscriptPath(projectId, `/episodes/${episodeId}/draft`)}?revision=${revision}`,
    { projectId },
  );
}

export function saveDraft(
  projectId: string,
  episodeId: number,
  input: DraftSave,
): Promise<DraftRecord> {
  return apiRequest<DraftRecord>(
    manuscriptPath(projectId, `/episodes/${episodeId}/drafts`),
    { method: "POST", body: input, projectId },
  );
}
