import { apiRequest } from "../../api/client";
import { fetchCharacters } from "../characters/characterApi";
import type {
  CharacterRecord,
  DraftDocumentRead,
  DraftHtmlRead,
  DraftHtmlSaveInput,
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

export function fetchDraftAuthoringHtml(
  projectId: string,
  episodeId: number,
  revision: number,
): Promise<DraftHtmlRead | null> {
  return apiRequest<DraftHtmlRead | null>(
    queryPath(draftPath(projectId, episodeId), {
      revision,
      format: "html",
      annotation_projection: "selected",
      annotation_keys: "emotions",
    }),
    { projectId },
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

export function saveDraftHtml(
  projectId: string,
  episodeId: number,
  input: DraftHtmlSaveInput,
): Promise<DraftSaveResult> {
  return apiRequest<DraftSaveResult>(
    manuscriptPath(projectId, `/episodes/${episodeId}/drafts`),
    { method: "POST", body: input, projectId },
  );
}

export async function fetchAllCharacters(projectId: string): Promise<CharacterRecord[]> {
  const characters: CharacterRecord[] = [];
  const seenIds = new Set<number>();
  let offset = 0;
  while (true) {
    const page = await fetchCharacters(projectId, 100, offset);
    const pageIds = new Set<number>();
    for (const character of page) {
      if (seenIds.has(character.id) || pageIds.has(character.id)) {
        throw new Error("Character pagination returned duplicate IDs.");
      }
      pageIds.add(character.id);
    }
    for (const id of pageIds) seenIds.add(id);
    characters.push(...page);
    if (page.length < 100) return characters;
    const nextOffset = offset + page.length;
    if (nextOffset <= offset) return characters;
    offset = nextOffset;
  }
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
