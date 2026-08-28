export type ProjectStatus = "active" | "archived";
export type MetadataState = "ok" | "missing" | "invalid";
export type ProjectHealth = "ok" | "degraded";

export interface ProjectSummary {
  project_id: string;
  status: ProjectStatus;
  metadata_state: MetadataState;
  working_title: string | null;
  created_at: string | null;
  updated_at: string | null;
  health: ProjectHealth;
}

export interface ProjectListResponse {
  projects: ProjectSummary[];
}

export interface WorkRecord {
  id: number;
  slug: string;
  working_title: string;
  genre: string;
  premise: string;
  themes_json: string;
  description: string;
  production_status: string;
  created_at: string;
  updated_at: string;
  version: number;
}

export interface DashboardView {
  work: WorkRecord;
  chapter_count: number;
  episode_count: number;
  scene_count: number;
}

export interface WorkUpdate {
  working_title: string;
  expected_version: number;
  genre?: string;
  premise?: string;
  themes_json?: unknown;
  description?: string;
  production_status?: string;
}
