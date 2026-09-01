import { apiRequest } from "../../api/client";

const apiBase = "/api/v1";

export type StyleImportType = "text" | "html_file" | "epub";
export type AnalysisPreset = "deterministic" | "full";
export type ReviewStatus = "acknowledged" | "ignored";

export interface ReferenceWork {
  reference_work_id: number;
  source_id: number;
  source_type: string;
  title: string;
  author_name: string | null;
  episode_count: number;
  created_at: string;
}

export interface ReferenceEpisode {
  reference_episode_id: number;
  reference_work_id: number;
  title: string;
  order_index: number;
  style_document_id: number | null;
  current_text_revision_id: number | null;
  current_structure_revision_id: number | null;
  current_structure_kind: string | null;
  analysis_status: AnalysisStatus;
}

export interface AnalysisStatus {
  basic?: { state: string; reasons?: string[] };
  semantic?: { state: string; reasons?: string[] };
}

export interface StyleJob {
  job_id: number;
  job_type: string;
  status: string;
  progress: { current: number | null; total: number | null };
  result: Record<string, unknown>;
  warnings: unknown[];
  error_code: string | null;
  error_message: string | null;
}

export interface Corpus {
  id: number;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
}

export interface Aggregate {
  id: number;
  container_type?: "corpus" | "reference_work";
  container_id?: number;
  measurement_target_type?: "document" | "scene";
  filter_json?: string;
  metric_name: string;
  metric_version: number;
  statistic: string;
  aggregate_policy_version?: number;
  value_real: number;
  source_measurement_count: number;
  sample_count: number;
  work_count?: number;
  skipped_target_count?: number;
  stale: boolean;
  warning_json: string;
  created_at?: string;
}

export interface Profile {
  id: number;
  name: string;
  description: string;
  source_corpus_id: number | null;
  status: "draft" | "active" | "archived";
  active_version_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface ProfileVersion {
  id: number;
  profile_id: number;
  version_no: number;
  parent_version_id: number | null;
  created_at: string;
}

export interface StyleRule {
  id: number;
  profile_version_id: number;
  target_scope: "document" | "scene" | "character";
  scope_selector_json: string;
  metric_name: string;
  metric_version: number;
  preferred_value: number | null;
  min_value: number | null;
  max_value: number | null;
  weight: number;
  enabled: boolean;
  severity_policy: string;
  source_kind: string;
}

export interface ProfileDetail {
  profile: Profile;
  versions: Array<{ version: ProfileVersion; rules: StyleRule[] }>;
}

export interface ReviewItem {
  id: number;
  subject_type: string;
  subject_id: number;
  analysis_run_id: number | null;
  priority: string;
  status: string;
  reason_code: string;
  evidence: Record<string, unknown>;
  resolution_note: string | null;
  version: number;
}

export interface LintRun {
  id: number;
  document_id: number;
  text_revision_id: number;
  structure_revision_id: number;
  profile_id: number;
  profile_version_id: number;
  scene_id: number | null;
  status: string;
  warnings: unknown[];
  enabled_rule_count: number;
  applicable_rule_count: number;
  missing_rule_count: number;
  coverage_ratio: number;
  stale: boolean;
  created_at: string;
  finished_at: string | null;
}

export interface LintFinding {
  id: number;
  lint_run_id: number;
  rule_id: number;
  target_type: string;
  target_id: number;
  metric_name: string;
  observed_value: number;
  expected_min: number;
  expected_max: number;
  preferred_value: number | null;
  deviation: number;
  severity: string;
  sort_score: number;
  explanation_code: string;
  evidence: Record<string, unknown>;
  review_status: ReviewStatus | null;
  review_note: string | null;
}

export interface AnalysisRun {
  id: number;
  analyzer_id: string;
  analyzer_version: number;
  text_revision_id: number;
  structure_revision_id: number;
  status: string;
  started_at: string;
  finished_at: string | null;
}

export interface StyleSemanticOutput {
  id: number;
  annotation_type: string;
  subject_type: string;
  subject_id: number;
  value: unknown;
  confidence: number | null;
  analysis_run_id: number;
  start_cp: number | null;
  end_cp: number | null;
  created_at: string;
}

export interface SemanticsView {
  structure_revision_id: number;
  analysis_status: AnalysisStatus;
  analysis_run_ids: number[];
  effective: Record<string, unknown>;
  outputs: StyleSemanticOutput[];
  raw?: StyleSemanticOutput[];
}

function stylePath(projectId: string, suffix = ""): string {
  return `${apiBase}/projects/${encodeURIComponent(projectId)}/style-analysis${suffix}`;
}

export function fetchReferenceWorks(projectId: string): Promise<ReferenceWork[]> {
  return apiRequest<ReferenceWork[]>(stylePath(projectId, "/reference-works"), {
    projectId,
  });
}

export function fetchReferenceWork(
  projectId: string,
  workId: number,
): Promise<ReferenceWork> {
  return apiRequest<ReferenceWork>(
    stylePath(projectId, `/reference-works/${workId}`),
    { projectId },
  );
}

export function fetchReferenceEpisodes(
  projectId: string,
  workId: number,
): Promise<ReferenceEpisode[]> {
  return apiRequest<ReferenceEpisode[]>(
    stylePath(projectId, `/reference-works/${workId}/episodes`),
    { projectId },
  );
}

export function fetchReferenceEpisode(
  projectId: string,
  episodeId: number,
): Promise<ReferenceEpisode> {
  return apiRequest<ReferenceEpisode>(
    stylePath(projectId, `/reference-episodes/${episodeId}`),
    { projectId },
  );
}

export function importStyleFile(
  projectId: string,
  sourceType: StyleImportType,
  file: File,
): Promise<{ reused_existing: boolean; reference_work_id: number; source_id: number }> {
  const body = new FormData();
  body.set("source_type", sourceType);
  body.set("file", file);
  return apiRequest(stylePath(projectId, "/imports/file"), {
    method: "POST",
    body,
    projectId,
  });
}

export function analyzeReferenceWork(
  projectId: string,
  workId: number,
  preset: AnalysisPreset,
  rebuildStructure = false,
): Promise<StyleJob> {
  return apiRequest<StyleJob>(
    stylePath(projectId, `/reference-works/${workId}/analyze`),
    {
      method: "POST",
      body: { preset, rebuild_structure: rebuildStructure },
      projectId,
    },
  );
}

export function deleteReferenceWork(projectId: string, workId: number): Promise<void> {
  return apiRequest<void>(stylePath(projectId, `/reference-works/${workId}`), {
    method: "DELETE",
    projectId,
  });
}

export function analyzeDocument(
  projectId: string,
  documentId: number,
  input: {
    text_revision_id: number;
    structure_revision_id?: number;
    preset: AnalysisPreset;
    rebuild_structure?: boolean;
  },
): Promise<StyleJob> {
  return apiRequest<StyleJob>(
    stylePath(projectId, `/documents/${documentId}/analyze`),
    { method: "POST", body: input, projectId },
  );
}

export function captureProjectEpisode(
  projectId: string,
  episodeId: number,
  draftId: number,
): Promise<Record<string, unknown>> {
  return apiRequest<Record<string, unknown>>(
    stylePath(projectId, `/project-episodes/${episodeId}/capture`),
    { method: "POST", body: { draft_id: draftId }, projectId },
  );
}

export function fetchStyleJob(projectId: string, jobId: number): Promise<StyleJob> {
  return apiRequest<StyleJob>(stylePath(projectId, `/jobs/${jobId}`), { projectId });
}

export function cancelStyleJob(projectId: string, jobId: number): Promise<StyleJob> {
  return apiRequest<StyleJob>(stylePath(projectId, `/jobs/${jobId}/cancel`), {
    method: "POST",
    projectId,
  });
}

export function fetchAnalysisRuns(
  projectId: string,
  documentId: number,
): Promise<AnalysisRun[]> {
  return apiRequest<AnalysisRun[]>(
    stylePath(projectId, `/documents/${documentId}/runs`),
    { projectId },
  );
}

export function fetchSemantics(
  projectId: string,
  documentId: number,
  structureRevisionId: number,
): Promise<SemanticsView> {
  return apiRequest<SemanticsView>(
    stylePath(projectId, `/documents/${documentId}/semantics?structure_revision_id=${structureRevisionId}`),
    { projectId },
  );
}

export function fetchCorpora(projectId: string): Promise<Corpus[]> {
  return apiRequest<Corpus[]>(stylePath(projectId, "/corpora"), { projectId });
}

export function fetchCorpus(
  projectId: string,
  corpusId: number,
): Promise<Record<string, unknown>> {
  return apiRequest<Record<string, unknown>>(
    stylePath(projectId, `/corpora/${corpusId}`),
    { projectId },
  );
}

export function createCorpus(
  projectId: string,
  name: string,
  description: string,
): Promise<Corpus> {
  return apiRequest<Corpus>(stylePath(projectId, "/corpora"), {
    method: "POST",
    body: { name, description },
    projectId,
  });
}

export function addCorpusWork(
  projectId: string,
  corpusId: number,
  referenceWorkId: number,
): Promise<Record<string, unknown>> {
  return apiRequest<Record<string, unknown>>(
    stylePath(projectId, `/corpora/${corpusId}/works`),
    {
      method: "POST",
      body: { reference_work_id: referenceWorkId, include_all_episodes: true },
      projectId,
    },
  );
}

export function compareCorpora(
  projectId: string,
  corpusIds: number[],
): Promise<Record<string, unknown>[]> {
  const query = corpusIds.map((id) => `corpus_id=${id}`).join("&");
  return apiRequest<Record<string, unknown>[]>(
    stylePath(projectId, `/corpora/compare?${query}`),
    { projectId },
  );
}

export function fetchAggregates(
  projectId: string,
  containerType: "corpus" | "reference-work",
  containerId: number,
): Promise<Aggregate[]> {
  const prefix = containerType === "corpus" ? "corpora" : "reference-works";
  return apiRequest<Aggregate[]>(
    stylePath(projectId, `/${prefix}/${containerId}/aggregates`),
    { projectId },
  );
}

export function recomputeAggregates(
  projectId: string,
  containerType: "corpus" | "reference-work",
  containerId: number,
  input: {
    measurement_target_type: "document" | "scene";
    filter: Record<string, unknown>;
    metric_names: string[];
  },
): Promise<StyleJob> {
  const prefix = containerType === "corpus" ? "corpora" : "reference-works";
  return apiRequest<StyleJob>(
    stylePath(projectId, `/${prefix}/${containerId}/aggregates/recompute`),
    { method: "POST", body: input, projectId },
  );
}

export function fetchProfiles(projectId: string): Promise<Profile[]> {
  return apiRequest<Profile[]>(stylePath(projectId, "/profiles"), { projectId });
}

export function fetchProfile(
  projectId: string,
  profileId: number,
): Promise<ProfileDetail> {
  return apiRequest<ProfileDetail>(stylePath(projectId, `/profiles/${profileId}`), {
    projectId,
  });
}

export function createManualProfile(
  projectId: string,
  input: {
    name: string;
    description: string;
    rules: Array<Record<string, unknown>>;
  },
): Promise<ProfileDetail> {
  return apiRequest<ProfileDetail>(stylePath(projectId, "/profiles/manual"), {
    method: "POST",
    body: input,
    projectId,
  });
}

export function createProfileFromCorpus(
  projectId: string,
  input: {
    corpus_id: number;
    name: string;
    description: string;
    rules: Array<{
      preferred_aggregate_id: number;
      min_aggregate_id: number;
      max_aggregate_id: number;
    }>;
  },
): Promise<ProfileDetail> {
  return apiRequest<ProfileDetail>(stylePath(projectId, "/profiles/from-corpus"), {
    method: "POST",
    body: input,
    projectId,
  });
}

export function activateProfile(
  projectId: string,
  profileId: number,
  versionNo: number,
): Promise<Profile> {
  return apiRequest<Profile>(stylePath(projectId, `/profiles/${profileId}/activate`), {
    method: "POST",
    body: { version_no: versionNo },
    projectId,
  });
}

export function archiveProfile(projectId: string, profileId: number): Promise<Profile> {
  return apiRequest<Profile>(stylePath(projectId, `/profiles/${profileId}/archive`), {
    method: "POST",
    projectId,
  });
}

export function fetchReviewItems(
  projectId: string,
  status = "open",
): Promise<ReviewItem[]> {
  return apiRequest<ReviewItem[]>(
    stylePath(projectId, `/review-items?status=${encodeURIComponent(status)}`),
    { projectId },
  );
}

export function resolveReviewItem(
  projectId: string,
  itemId: number,
  expectedVersion: number,
  note: string,
): Promise<ReviewItem> {
  return apiRequest<ReviewItem>(stylePath(projectId, `/review-items/${itemId}/resolve`), {
    method: "POST",
    body: { expected_version: expectedVersion, note: note || null },
    projectId,
  });
}

export function ignoreReviewItem(
  projectId: string,
  itemId: number,
  expectedVersion: number,
  note: string,
): Promise<ReviewItem> {
  return apiRequest<ReviewItem>(stylePath(projectId, `/review-items/${itemId}/ignore`), {
    method: "POST",
    body: { expected_version: expectedVersion, note: note || null },
    projectId,
  });
}

export function createOverride(
  projectId: string,
  input: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  return apiRequest<Record<string, unknown>>(stylePath(projectId, "/overrides"), {
    method: "POST",
    body: input,
    projectId,
  });
}

export function createInferenceReview(
  projectId: string,
  input: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  return apiRequest<Record<string, unknown>>(
    stylePath(projectId, "/inference-reviews"),
    { method: "POST", body: input, projectId },
  );
}

export function createReviewItem(
  projectId: string,
  input: {
    subject_type: string;
    subject_id: number;
    analysis_run_id?: number;
    priority: "normal" | "high";
  },
): Promise<ReviewItem> {
  return apiRequest<ReviewItem>(stylePath(projectId, "/review-items"), {
    method: "POST",
    body: input,
    projectId,
  });
}

export function fetchLintRuns(
  projectId: string,
  documentId?: number,
): Promise<LintRun[]> {
  const query = documentId === undefined ? "" : `?document_id=${documentId}`;
  return apiRequest<LintRun[]>(stylePath(projectId, `/lint-runs${query}`), {
    projectId,
  });
}

export function fetchLintFindings(
  projectId: string,
  lintRunId: number,
): Promise<LintFinding[]> {
  return apiRequest<LintFinding[]>(
    stylePath(projectId, `/lint-runs/${lintRunId}/findings`),
    { projectId },
  );
}

export function runLint(
  projectId: string,
  documentId: number,
  input: {
    text_revision_id: number;
    structure_revision_id: number;
    profile_id: number;
    profile_version_no: number;
    scene_id?: number;
  },
): Promise<StyleJob> {
  return apiRequest<StyleJob>(stylePath(projectId, `/documents/${documentId}/lint`), {
    method: "POST",
    body: input,
    projectId,
  });
}

export function reviewFinding(
  projectId: string,
  findingId: number,
  status: ReviewStatus,
  note: string,
): Promise<LintFinding> {
  return apiRequest<LintFinding>(
    stylePath(projectId, `/findings/${findingId}/review`),
    {
      method: "POST",
      body: { status, note: note || null },
      projectId,
    },
  );
}
