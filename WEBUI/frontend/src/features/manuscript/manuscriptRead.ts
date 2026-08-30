import type {
  DraftDocumentRead,
  DraftWebRead,
  JsonValue,
  NovelDocument,
} from "../../api/types";

const formalBlockId = /^blk_[0-9a-f]{32}$/;
const projectableAnnotationKey = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export type RestoreRefreshStatus =
  | "confirmed"
  | "refresh-failed"
  | "stale"
  | "inconsistent";

export function assertDocumentIdentity(
  value: DraftDocumentRead | null,
  episodeId: number,
  expectedRevision?: number,
): DraftDocumentRead {
  if (
    value === null ||
    value.format !== "document" ||
    !positiveInteger(value.id) ||
    value.episode_id !== episodeId ||
    !positiveInteger(value.revision) ||
    (expectedRevision !== undefined && value.revision !== expectedRevision) ||
    !isNovelDocument(value.content)
  ) {
    throw new Error("The manuscript document has an invalid snapshot identity.");
  }
  return value;
}

export function assertWebIdentity(
  value: DraftWebRead | null,
  document: DraftDocumentRead,
): DraftWebRead {
  if (
    value === null ||
    value.format !== "web" ||
    value.id !== document.id ||
    value.work_id !== document.work_id ||
    value.episode_id !== document.episode_id ||
    value.revision !== document.revision
  ) {
    throw new Error("Unable to load a consistent manuscript view.");
  }
  return value;
}

export function projectableUnknownAnnotations(
  annotations: Record<string, JsonValue>,
): Array<{ key: string; value: string }> {
  return Object.entries(annotations)
    .filter(
      ([key, value]) =>
        key !== "emotions" && projectableAnnotationKey.test(key) && typeof value === "string",
    )
    .map(([key, value]) => ({ key, value: value as string }));
}

export function isFormalBlockId(value: string): boolean {
  return formalBlockId.test(value);
}

export function restoreRefreshStatus(
  actualLatest: { revision: number; id: number } | null,
  committed: { revision: number; id: number },
): RestoreRefreshStatus {
  if (actualLatest === null) return "refresh-failed";
  if (actualLatest.revision < committed.revision) return "stale";
  if (actualLatest.revision === committed.revision && actualLatest.id !== committed.id) {
    return "inconsistent";
  }
  return "confirmed";
}

function isNovelDocument(value: unknown): value is NovelDocument {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const candidate = value as { schema_version?: unknown; type?: unknown; blocks?: unknown };
  return candidate.schema_version === 1 && candidate.type === "novel_document" && Array.isArray(candidate.blocks);
}

function positiveInteger(value: number): boolean {
  return Number.isInteger(value) && value > 0;
}
