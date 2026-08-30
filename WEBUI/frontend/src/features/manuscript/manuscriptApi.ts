import { apiRequest } from "../../api/client";
import type {
  DraftDocumentRead,
  DraftExport,
  DraftHistoryItem,
  DraftSaveResult,
  DraftWebRead,
  RestoreDraftInput,
} from "../../api/types";

const apiBase = "/api/v1";

function manuscriptPath(projectId: string, suffix = ""): string {
  return `${apiBase}/projects/${encodeURIComponent(projectId)}${suffix}`;
}

function draftPath(projectId: string, episodeId: number): string {
  return manuscriptPath(projectId, `/episodes/${episodeId}/draft`);
}

function queryPath(path: string, params: Record<string, string | number>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) query.set(key, String(value));
  return `${path}?${query.toString()}`;
}

export function fetchDraftDocument(
  projectId: string,
  episodeId: number,
  revision?: number,
): Promise<DraftDocumentRead | null> {
  return apiRequest<DraftDocumentRead | null>(
    queryPath(draftPath(projectId, episodeId), {
      format: "document",
      ...(revision === undefined ? {} : { revision }),
    }),
    { projectId },
  );
}

export function fetchFreshLatestDocument(
  projectId: string,
  episodeId: number,
): Promise<DraftDocumentRead | null> {
  return apiRequest<DraftDocumentRead | null>(
    queryPath(draftPath(projectId, episodeId), { format: "document" }),
    { projectId, cache: "no-store" },
  );
}

export function fetchDraftWeb(
  projectId: string,
  episodeId: number,
  revision: number,
  includeNotes: boolean,
): Promise<DraftWebRead | null> {
  return apiRequest<DraftWebRead | null>(
    queryPath(draftPath(projectId, episodeId), {
      revision,
      format: "web",
      include_notes: String(includeNotes),
    }),
    { projectId },
  );
}

export function fetchDraftHistory(
  projectId: string,
  episodeId: number,
  limit = 20,
): Promise<DraftHistoryItem[]> {
  return apiRequest<DraftHistoryItem[]>(
    queryPath(manuscriptPath(projectId, `/episodes/${episodeId}/drafts`), { limit }),
    { projectId },
  );
}

export function restoreDraft(
  projectId: string,
  episodeId: number,
  input: RestoreDraftInput,
): Promise<DraftSaveResult> {
  return apiRequest<DraftSaveResult>(
    manuscriptPath(projectId, `/episodes/${episodeId}/drafts`),
    { method: "POST", body: input, projectId },
  );
}

export function fetchNarouExport(
  projectId: string,
  episodeId: number,
  revision: number,
): Promise<DraftExport | null> {
  return apiRequest<DraftExport | null>(
    queryPath(manuscriptPath(projectId, `/episodes/${episodeId}/draft/export`), {
      revision,
      format: "narou",
    }),
    { projectId },
  );
}
