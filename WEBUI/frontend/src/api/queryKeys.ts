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
  worldFacts: (projectId: string, limit = 50, offset = 0) =>
    ["project", projectId, "world-facts", limit, offset] as const,
  worldFactsFamily: (projectId: string) =>
    ["project", projectId, "world-facts"] as const,
  worldFact: (projectId: string, factId: number) =>
    ["project", projectId, "world-fact", factId] as const,
  worldFactSearch: (projectId: string, query: string, limit = 50, offset = 0) =>
    ["project", projectId, "world-fact-search", query, limit, offset] as const,
  worldFactSearchFamily: (projectId: string) =>
    ["project", projectId, "world-fact-search"] as const,
  characters: (projectId: string, limit = 50, offset = 0) =>
    ["project", projectId, "characters", limit, offset] as const,
  charactersFamily: (projectId: string) =>
    ["project", projectId, "characters"] as const,
  character: (projectId: string, characterId: number) =>
    ["project", projectId, "character", characterId] as const,
  characterSearch: (projectId: string, query: string, limit = 50, offset = 0) =>
    ["project", projectId, "character-search", query, limit, offset] as const,
  characterSearchFamily: (projectId: string) =>
    ["project", projectId, "character-search"] as const,
  relationships: (projectId: string, characterId: number) =>
    ["project", projectId, "relationships", characterId] as const,
  characterState: (projectId: string, characterId: number, episodeId: number) =>
    ["project", projectId, "character-state", characterId, episodeId] as const,
  characterStateHistory: (projectId: string, characterId: number) =>
    ["project", projectId, "character-state-history", characterId] as const,
  characterKnowledge: (projectId: string, characterId: number, episodeId: number) =>
    ["project", projectId, "character-knowledge", characterId, episodeId] as const,
  timelineEvents: (projectId: string, limit = 50, offset = 0) =>
    ["project", projectId, "timeline-events", limit, offset] as const,
  timelineEventsFamily: (projectId: string) =>
    ["project", projectId, "timeline-events"] as const,
  timelineEvent: (projectId: string, eventId: number) =>
    ["project", projectId, "timeline-event", eventId] as const,
  timelineEventSearch: (projectId: string, query: string, limit = 50) =>
    ["project", projectId, "timeline-event-search", query, limit] as const,
  timelineEventSearchFamily: (projectId: string) =>
    ["project", projectId, "timeline-event-search"] as const,
  timelineRange: (projectId: string, start: string, end: string, limit = 50) =>
    ["project", projectId, "timeline-range", start, end, limit] as const,
  timelineRangeFamily: (projectId: string) =>
    ["project", projectId, "timeline-range"] as const,
  timelineRelations: (
    projectId: string,
    eventId: number | null,
    limit = 50,
    offset = 0,
  ) => ["project", projectId, "timeline-relations", eventId, limit, offset] as const,
  timelineRelationsFamily: (projectId: string) =>
    ["project", projectId, "timeline-relations"] as const,
};
