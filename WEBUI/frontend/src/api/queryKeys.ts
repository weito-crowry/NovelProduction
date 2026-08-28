export const projectQueryKeys = {
  project: (projectId: string) => ["project", projectId] as const,
  work: (projectId: string) => ["project", projectId, "work"] as const,
  dashboard: (projectId: string) => ["project", projectId, "dashboard"] as const,
};
