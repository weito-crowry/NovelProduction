import { parseJsonEditor, formatStoredJson } from "../../api/jsonFields";
import type {
  InformationCreate,
  InformationItemRecord,
  InformationUpdate,
} from "../../api/types";

export interface InformationFormValues {
  statement: string;
  truth_status: string;
  authoring_guard: string;
  notes_json: string;
  canon_status: string;
  importance: string;
  reason: string;
}

export function emptyInformationForm(): InformationFormValues {
  return {
    statement: "",
    truth_status: "uncertain",
    authoring_guard: "",
    notes_json: "{}",
    canon_status: "draft",
    importance: "0",
    reason: "",
  };
}

export function toInformationForm(
  record: InformationItemRecord,
): InformationFormValues {
  return {
    statement: record.statement,
    truth_status: record.truth_status,
    authoring_guard: record.authoring_guard,
    notes_json: formatStoredJson(record.notes_json),
    canon_status: record.canon_status,
    importance: String(record.importance),
    reason: "",
  };
}

export function hasInformationChanges(
  values: InformationFormValues,
  baseline: InformationItemRecord,
): boolean {
  return (
    values.statement !== baseline.statement ||
    values.truth_status !== baseline.truth_status ||
    values.authoring_guard !== baseline.authoring_guard ||
    jsonChanged(values.notes_json, baseline.notes_json) ||
    values.canon_status !== baseline.canon_status ||
    Number(values.importance) !== baseline.importance
  );
}

export function buildInformationCreate(
  values: InformationFormValues,
): InformationCreate {
  if (!values.statement.trim()) throw new Error("Statement must not be empty.");
  const importance = parseImportance(values.importance);
  return {
    statement: values.statement,
    truth_status: values.truth_status,
    authoring_guard: values.authoring_guard,
    notes_json: parseJsonEditor(values.notes_json),
    canon_status: values.canon_status as InformationCreate["canon_status"],
    importance,
  };
}

export function buildInformationUpdate(
  values: InformationFormValues,
  baseline: InformationItemRecord,
): InformationUpdate | null {
  if (!hasInformationChanges(values, baseline)) return null;
  if (!values.statement.trim()) throw new Error("Statement must not be empty.");
  const update: InformationUpdate = { expected_version: baseline.version };
  if (values.statement !== baseline.statement) update.statement = values.statement;
  if (values.truth_status !== baseline.truth_status)
    update.truth_status = values.truth_status;
  if (values.authoring_guard !== baseline.authoring_guard)
    update.authoring_guard = values.authoring_guard;
  if (jsonChanged(values.notes_json, baseline.notes_json))
    update.notes_json = parseJsonEditor(values.notes_json);
  if (values.canon_status !== baseline.canon_status)
    update.canon_status = values.canon_status as InformationUpdate["canon_status"];
  if (Number(values.importance) !== baseline.importance)
    update.importance = parseImportance(values.importance);
  if (values.reason.trim()) update.reason = values.reason.trim();
  return update;
}

function parseImportance(value: string): number {
  const number = Number(value);
  if (!Number.isInteger(number) || number < 0)
    throw new Error("Importance must be a non-negative integer.");
  return number;
}

function jsonChanged(left: string, right: string): boolean {
  try {
    return JSON.stringify(parseJsonEditor(left)) !== JSON.stringify(JSON.parse(right));
  } catch {
    return true;
  }
}
