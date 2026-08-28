import { parseJsonEditor, formatStoredJson } from "../../api/jsonFields";
import type { WorkRecord, WorkUpdate } from "../../api/types";

export interface WorkFormValues {
  working_title: string;
  genre: string;
  premise: string;
  themes_json: string;
  description: string;
  production_status: string;
}

const optionalFields = [
  "genre",
  "premise",
  "themes_json",
  "description",
  "production_status",
] as const;

export function toForm(work: WorkRecord): WorkFormValues {
  return {
    working_title: work.working_title,
    genre: work.genre,
    premise: work.premise,
    themes_json: formatStoredJson(work.themes_json),
    description: work.description,
    production_status: work.production_status,
  };
}

export function buildWorkUpdate(
  values: WorkFormValues,
  baseline: WorkRecord,
): WorkUpdate {
  const update: WorkUpdate = {
    working_title: values.working_title,
    expected_version: baseline.version,
  };
  const baselineValues = toForm(baseline);
  for (const field of optionalFields) {
    if (values[field] === baselineValues[field]) continue;
    if (field === "themes_json") {
      update.themes_json = parseJsonEditor(values.themes_json);
    } else if (field === "genre") {
      update.genre = values.genre;
    } else if (field === "premise") {
      update.premise = values.premise;
    } else if (field === "description") {
      update.description = values.description;
    } else {
      update.production_status = values.production_status;
    }
  }
  return update;
}
