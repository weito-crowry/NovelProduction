export const projectQueryKeys = {
  project: (projectId: string) => ["project", projectId] as const,
  work: (projectId: string) => ["project", projectId, "work"] as const,
  dashboard: (projectId: string) => ["project", projectId, "dashboard"] as const,
  outline: (projectId: string) => ["project", projectId, "outline"] as const,
  episode: (projectId: string, episodeId: number) =>
    ["project", projectId, "episode", episodeId] as const,
  episodeView: (projectId: string, episodeId: number) =>
    ["project", projectId, "episode-view", episodeId] as const,
  episodeViews: (projectId: string) => ["project", projectId, "episode-view"] as const,
  scene: (projectId: string, sceneId: number) =>
    ["project", projectId, "scene", sceneId] as const,
  scenes: (projectId: string) => ["project", projectId, "scene"] as const,
};
