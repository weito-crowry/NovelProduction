import { apiRequest } from "../../api/client";
import type {
  TimelineEventCreate,
  TimelineEventRecord,
  TimelineEventUpdate,
  TimelineMove,
  TimelineRelationCreate,
  TimelineRelationRecord,
} from "../../api/types";

const apiBase = "/api/v1";

function timelinePath(projectId: string, suffix = ""): string {
  return `${apiBase}/projects/${encodeURIComponent(projectId)}${suffix}`;
}

export function fetchTimelineEvents(projectId: string, limit = 50, offset = 0): Promise<TimelineEventRecord[]> {
  return apiRequest<TimelineEventRecord[]>(
    `${timelinePath(projectId, "/timeline/events")}?limit=${limit}&offset=${offset}`,
    { projectId },
  );
}

export function searchTimelineEvents(projectId: string, query: string, limit = 50): Promise<TimelineEventRecord[]> {
  if (!query.trim()) return Promise.resolve([]);
  return apiRequest<TimelineEventRecord[]>(
    `${timelinePath(projectId, "/timeline/events/search")}?query=${encodeURIComponent(query)}&limit=${limit}`,
    { projectId },
  );
}

export function fetchTimelineRange(
  projectId: string,
  start: string,
  end: string,
  limit = 50,
): Promise<TimelineEventRecord[]> {
  return apiRequest<TimelineEventRecord[]>(
    `${timelinePath(projectId, "/timeline/range")}?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&limit=${limit}`,
    { projectId },
  );
}

export function fetchTimelineEvent(projectId: string, eventId: number): Promise<TimelineEventRecord> {
  return apiRequest<TimelineEventRecord>(timelinePath(projectId, `/timeline/events/${eventId}`), { projectId });
}

export function createTimelineEvent(projectId: string, input: TimelineEventCreate): Promise<TimelineEventRecord> {
  return apiRequest<TimelineEventRecord>(timelinePath(projectId, "/timeline/events"), {
    method: "POST",
    body: input,
    projectId,
  });
}

export function updateTimelineEvent(
  projectId: string,
  eventId: number,
  input: TimelineEventUpdate,
): Promise<TimelineEventRecord> {
  return apiRequest<TimelineEventRecord>(timelinePath(projectId, `/timeline/events/${eventId}`), {
    method: "PATCH",
    body: input,
    projectId,
  });
}

export function moveTimelineEvent(
  projectId: string,
  eventId: number,
  input: TimelineMove,
): Promise<TimelineEventRecord> {
  return apiRequest<TimelineEventRecord>(timelinePath(projectId, `/timeline/events/${eventId}/move`), {
    method: "POST",
    body: input,
    projectId,
  });
}

export function fetchTimelineRelations(
  projectId: string,
  eventId: number | null,
  limit = 50,
  offset = 0,
): Promise<TimelineRelationRecord[]> {
  const filter = eventId === null ? "" : `&event_id=${eventId}`;
  return apiRequest<TimelineRelationRecord[]>(
    `${timelinePath(projectId, "/timeline/relations")}?limit=${limit}&offset=${offset}${filter}`,
    { projectId },
  );
}

export function createTimelineRelation(
  projectId: string,
  input: TimelineRelationCreate,
): Promise<TimelineRelationRecord> {
  return apiRequest<TimelineRelationRecord>(timelinePath(projectId, "/timeline/relations"), {
    method: "POST",
    body: input,
    projectId,
  });
}
