import type { Aggregate, ReferenceEpisode } from "./styleAnalysisApi";

export const AGGREGATE_STATISTICS = [
  "mean",
  "median",
  "p10",
  "p25",
  "p75",
  "p90",
  "stddev",
  "min",
  "max",
] as const;

export type AggregateStatistic = typeof AGGREGATE_STATISTICS[number];

export type AggregateGroup = {
  key: string;
  metricName: string;
  metricVersion: number;
  measurementTargetType: string;
  filterJson: string;
  aggregatePolicyVersion: number;
  stale: boolean;
  warningJson: string[];
  workCount: number;
  skippedTargetCount: number;
  statistics: Partial<Record<AggregateStatistic, Aggregate>>;
};

export type CapturedStyleDocument = {
  documentId: number;
  episodeId: number;
  title: string;
  currentTextRevisionId: number | null;
  currentStructureRevisionId: number | null;
  currentStructureKind: string | null;
};

export type ProjectDraftCandidate = {
  episodeId: number;
  title: string;
  draftId: number;
  revision: number;
};

export type StyleDocumentEntry = {
  documentId: number;
  episodeId: number;
  title: string;
  kind: "reference" | "project_draft";
  currentTextRevisionId: number | null;
  currentStructureRevisionId: number | null;
  currentStructureKind: string | null;
  analysisStatus: ReferenceEpisode["analysis_status"];
};

export type ManualRuleEditorState = {
  targetScope: "document" | "scene" | "character";
  selector: Record<string, unknown>;
  metricName: string;
  metricVersion: number;
  preferredValue: string;
  minValue: string;
  maxValue: string;
  weight: string;
  enabled: boolean;
};

export function buildAggregateGroups(aggregates: Aggregate[]): AggregateGroup[] {
  const groups = new Map<string, AggregateGroup>();
  for (const aggregate of aggregates) {
    if (!AGGREGATE_STATISTICS.includes(aggregate.statistic as AggregateStatistic)) continue;
    const measurementTargetType = aggregate.measurement_target_type ?? "document";
    const filterJson = aggregate.filter_json ?? "{}";
    const aggregatePolicyVersion = aggregate.aggregate_policy_version ?? 0;
    const key = [
      aggregate.metric_name,
      aggregate.metric_version,
      measurementTargetType,
      filterJson,
      aggregatePolicyVersion,
    ].join("|");
    const current = groups.get(key) ?? {
      key,
      metricName: aggregate.metric_name,
      metricVersion: aggregate.metric_version,
      measurementTargetType,
      filterJson,
      aggregatePolicyVersion,
      stale: false,
      warningJson: [],
      workCount: 0,
      skippedTargetCount: 0,
      statistics: {},
    };
    current.stale = current.stale || aggregate.stale;
    current.warningJson.push(...parseWarningJson(aggregate.warning_json));
    current.workCount = Math.max(current.workCount, aggregate.work_count ?? 0);
    current.skippedTargetCount = Math.max(
      current.skippedTargetCount,
      aggregate.skipped_target_count ?? 0,
    );
    current.statistics[aggregate.statistic as AggregateStatistic] = aggregate;
    groups.set(key, current);
  }
  return [...groups.values()]
    .map((group) => ({ ...group, warningJson: [...new Set(group.warningJson)] }))
    .sort((left, right) => left.key.localeCompare(right.key));
}

export function buildManualRule(state: ManualRuleEditorState): Record<string, unknown> {
  return {
    target_scope: state.targetScope,
    scope_selector: state.selector,
    metric_name: state.metricName,
    metric_version: state.metricVersion,
    preferred_value: parseOptionalFinite(state.preferredValue),
    min_value: parseOptionalFinite(state.minValue),
    max_value: parseOptionalFinite(state.maxValue),
    weight: parseOptionalFinite(state.weight) ?? 1,
    enabled: state.enabled,
    severity_policy: "standard",
  };
}

export function mergeStyleDocumentEntries(
  episodes: ReferenceEpisode[],
  captured: CapturedStyleDocument[],
): StyleDocumentEntry[] {
  const entries: StyleDocumentEntry[] = episodes.flatMap((episode) => {
    if (episode.style_document_id === null) return [];
    return [{
      documentId: episode.style_document_id,
      episodeId: episode.reference_episode_id,
      title: episode.title,
      kind: "reference" as const,
      currentTextRevisionId: episode.current_text_revision_id,
      currentStructureRevisionId: episode.current_structure_revision_id,
      currentStructureKind: episode.current_structure_kind,
      analysisStatus: episode.analysis_status,
    }];
  });
  const seen = new Set(entries.map((entry) => entry.documentId));
  for (const document of captured) {
    if (seen.has(document.documentId)) continue;
    seen.add(document.documentId);
    entries.push({
      documentId: document.documentId,
      episodeId: document.episodeId,
      title: document.title,
      kind: "project_draft",
      currentTextRevisionId: document.currentTextRevisionId,
      currentStructureRevisionId: document.currentStructureRevisionId,
      currentStructureKind: document.currentStructureKind,
      analysisStatus: { basic: { state: "not_analyzed" }, semantic: { state: "not_analyzed" } },
    });
  }
  return entries.sort((left, right) => left.documentId - right.documentId);
}

export function readCapturedStyleDocuments(projectId: string): CapturedStyleDocument[] {
  if (typeof sessionStorage === "undefined") return [];
  try {
    const parsed: unknown = JSON.parse(sessionStorage.getItem(storageKey(projectId)) ?? "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isCapturedStyleDocument);
  } catch {
    return [];
  }
}

export function rememberCapturedStyleDocument(
  projectId: string,
  document: CapturedStyleDocument,
): CapturedStyleDocument[] {
  const next = [
    document,
    ...readCapturedStyleDocuments(projectId).filter((item) => item.documentId !== document.documentId),
  ].slice(0, 50);
  if (typeof sessionStorage !== "undefined") {
    sessionStorage.setItem(storageKey(projectId), JSON.stringify(next));
  }
  return next;
}

export function updateRememberedStyleDocument(
  projectId: string,
  documentId: number,
  updates: Partial<Omit<CapturedStyleDocument, "documentId" | "episodeId" | "title">>,
): CapturedStyleDocument[] {
  const current = readCapturedStyleDocuments(projectId);
  const existing = current.find((item) => item.documentId === documentId);
  if (!existing) return current;
  return rememberCapturedStyleDocument(projectId, { ...existing, ...updates });
}

function parseOptionalFinite(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) throw new Error("数値は有限値で入力してください。");
  return parsed;
}

function parseWarningJson(value: string): string[] {
  try {
    const parsed: unknown = JSON.parse(value);
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
}

function storageKey(projectId: string): string {
  return `novelproduction.style-analysis.captured.${projectId}`;
}

function isCapturedStyleDocument(value: unknown): value is CapturedStyleDocument {
  if (!isRecord(value)) return false;
  return (
    typeof value.documentId === "number" && value.documentId > 0 &&
    typeof value.episodeId === "number" && value.episodeId > 0 &&
    typeof value.title === "string" &&
    (typeof value.currentTextRevisionId === "number" || value.currentTextRevisionId === null) &&
    (typeof value.currentStructureRevisionId === "number" || value.currentStructureRevisionId === null) &&
    (typeof value.currentStructureKind === "string" || value.currentStructureKind === null)
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
