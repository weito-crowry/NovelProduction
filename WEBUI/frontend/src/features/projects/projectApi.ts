import { apiRequest } from "../../api/client";
import type {
  DashboardView,
  ProjectListResponse,
  ProjectStatus,
  ProjectSummary,
  WorkRecord,
  WorkUpdate,
} from "../../api/types";

const apiBase = "/api/v1";

export function projectPath(projectId: string, suffix = ""): string {
  return `${apiBase}/projects/${encodeURIComponent(projectId)}${suffix}`;
}

export function fetchProjects(includeArchived: boolean): Promise<ProjectSummary[]> {
  const query = includeArchived ? "?include_archived=true" : "";
  return apiRequest<ProjectListResponse>(`${apiBase}/projects${query}`).then(
    (response) => response.projects,
  );
}

export function createProject(input: {
  working_title: string;
  project_id?: string;
}): Promise<ProjectSummary> {
  return apiRequest<ProjectSummary>(`${apiBase}/projects`, {
    method: "POST",
    body: input,
  });
}

export function updateProjectStatus(
  projectId: string,
  status: ProjectStatus,
): Promise<ProjectSummary> {
  return apiRequest<ProjectSummary>(projectPath(projectId), {
    method: "PATCH",
    body: { status },
  });
}

export function fetchWork(projectId: string): Promise<WorkRecord> {
  return apiRequest<WorkRecord>(projectPath(projectId, "/work"), {
    projectId,
  });
}

export function updateWork(
  projectId: string,
  update: WorkUpdate,
): Promise<WorkRecord> {
  return apiRequest<WorkRecord>(projectPath(projectId, "/work"), {
    method: "PATCH",
    body: update,
    projectId,
  });
}

export function fetchDashboard(projectId: string): Promise<DashboardView> {
  return apiRequest<DashboardView>(
    projectPath(projectId, "/views/dashboard"),
    { projectId },
  );
}
