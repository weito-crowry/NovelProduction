import { formatStoredJson, parseJsonEditor } from "../../api/jsonFields";
import type {
  ChapterRecord,
  ChapterUpdate,
  EpisodeRecord,
  EpisodeUpdate,
  SceneRecord,
  SceneUpdate,
} from "../../api/types";

export interface ChapterFormValues {
  title: string;
  summary: string;
  purpose: string;
  production_status: string;
  canon_status: string;
  reason: string;
}

export interface EpisodeFormValues {
  title: string;
  summary: string;
  purpose: string;
  foreshadowing_notes_json: string;
  production_status: string;
  canon_status: string;
  reason: string;
}

export interface SceneFormValues {
  title: string;
  summary: string;
  purpose: string;
  production_status: string;
  canon_status: string;
  reason: string;
}

export function chapterToForm(record: ChapterRecord): ChapterFormValues {
  return {
    title: record.title,
    summary: record.summary,
    purpose: record.purpose,
    production_status: record.production_status,
    canon_status: record.canon_status,
    reason: "",
  };
}

export function episodeToForm(record: EpisodeRecord): EpisodeFormValues {
  return {
    title: record.title,
    summary: record.summary,
    purpose: record.purpose,
    foreshadowing_notes_json: formatStoredJson(record.foreshadowing_notes_json),
    production_status: record.production_status,
    canon_status: record.canon_status,
    reason: "",
  };
}

export function sceneToForm(record: SceneRecord): SceneFormValues {
  return {
    title: record.title,
    summary: record.summary,
    purpose: record.purpose,
    production_status: record.production_status,
    canon_status: record.canon_status,
    reason: "",
  };
}

export function buildChapterUpdate(
  values: ChapterFormValues,
  baseline: ChapterRecord,
): ChapterUpdate | null {
  const update: ChapterUpdate = { expected_version: baseline.version };
  addChanged(update, "title", values.title, baseline.title);
  addChanged(update, "summary", values.summary, baseline.summary);
  addChanged(update, "purpose", values.purpose, baseline.purpose);
  addChanged(
    update,
    "production_status",
    values.production_status,
    baseline.production_status,
  );
  addChanged(update, "canon_status", values.canon_status, baseline.canon_status);
  return withReasonOrNull(update, values.reason);
}

export function buildEpisodeUpdate(
  values: EpisodeFormValues,
  baseline: EpisodeRecord,
): EpisodeUpdate | null {
  const update: EpisodeUpdate = { expected_version: baseline.version };
  addChanged(update, "title", values.title, baseline.title);
  addChanged(update, "summary", values.summary, baseline.summary);
  addChanged(update, "purpose", values.purpose, baseline.purpose);
  const baselineJson = formatStoredJson(baseline.foreshadowing_notes_json);
  if (values.foreshadowing_notes_json !== baselineJson) {
    update.foreshadowing_notes = parseJsonEditor(values.foreshadowing_notes_json);
  }
  addChanged(
    update,
    "production_status",
    values.production_status,
    baseline.production_status,
  );
  addChanged(update, "canon_status", values.canon_status, baseline.canon_status);
  return withReasonOrNull(update, values.reason);
}

export function buildSceneUpdate(
  values: SceneFormValues,
  baseline: SceneRecord,
): SceneUpdate | null {
  const update: SceneUpdate = { expected_version: baseline.version };
  addChanged(update, "title", values.title, baseline.title);
  addChanged(update, "summary", values.summary, baseline.summary);
  addChanged(update, "purpose", values.purpose, baseline.purpose);
  addChanged(
    update,
    "production_status",
    values.production_status,
    baseline.production_status,
  );
  addChanged(update, "canon_status", values.canon_status, baseline.canon_status);
  return withReasonOrNull(update, values.reason);
}

function addChanged(
  update: { expected_version: number },
  field: string,
  value: string,
  baseline: string,
): void {
  if (value !== baseline) {
    (update as unknown as Record<string, unknown>)[field] = value;
  }
}

function withReasonOrNull<T extends { expected_version: number }>(
  update: T,
  reason: string,
): T | null {
  if (Object.keys(update).length === 1) return null;
  if (reason.trim()) {
    (update as T & { reason?: string }).reason = reason.trim();
  }
  return update;
}

export function sameChapterSemanticForm(
  values: ChapterFormValues,
  baseline: ChapterRecord,
): boolean {
  return buildChapterUpdate({ ...values, reason: "" }, baseline) === null;
}

export function sameEpisodeSemanticForm(
  values: EpisodeFormValues,
  baseline: EpisodeRecord,
): boolean {
  return buildEpisodeSemanticComparison(values, baseline);
}

export function sameSceneSemanticForm(
  values: SceneFormValues,
  baseline: SceneRecord,
): boolean {
  return buildSceneUpdate({ ...values, reason: "" }, baseline) === null;
}

function buildEpisodeSemanticComparison(
  values: EpisodeFormValues,
  baseline: EpisodeRecord,
): boolean {
  return (
    values.title === baseline.title &&
    values.summary === baseline.summary &&
    values.purpose === baseline.purpose &&
    values.foreshadowing_notes_json ===
      formatStoredJson(baseline.foreshadowing_notes_json) &&
    values.production_status === baseline.production_status &&
    values.canon_status === baseline.canon_status
  );
}
