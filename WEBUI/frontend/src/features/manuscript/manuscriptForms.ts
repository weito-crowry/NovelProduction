import type { DraftSave } from "../../api/types";

export interface DraftFormValues {
  body: string;
  change_summary: string;
}

export function emptyDraftForm(): DraftFormValues {
  return { body: "", change_summary: "" };
}

export function hasDraftChanges(
  values: DraftFormValues,
  baselineBody: string,
  baselineSummary: string,
): boolean {
  return (
    values.body !== baselineBody || values.change_summary !== baselineSummary
  );
}

export function buildDraftSave(
  values: DraftFormValues,
  parent: { id: number } | null,
): DraftSave {
  if (!values.body.trim()) throw new Error("Body must not be empty.");
  return {
    body: values.body,
    expected_parent_draft_id: parent?.id ?? null,
    source_agent: "webui",
    change_summary: values.change_summary,
  };
}
