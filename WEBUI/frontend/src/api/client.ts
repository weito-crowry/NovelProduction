import { ApiError } from "./errors";

export interface ApiRequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  projectId?: string;
}

export interface ProjectEnvelope<T> {
  project_id: string;
  data: T;
}

export async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  const { body, projectId, headers, ...requestInit } = options;
  const requestHeaders = new Headers(headers);
  if (body !== undefined) {
    requestHeaders.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(path, {
      ...requestInit,
      headers: requestHeaders,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(
      0,
      "NETWORK_ERROR",
      "The API could not be reached.",
      null,
      {},
    );
  }

  const text = await response.text();
  const payload = parseJson(text);
  if (!response.ok) {
    throw apiErrorFromPayload(response.status, payload);
  }
  if (response.status === 204 || payload === null) {
    return undefined as T;
  }

  if (projectId !== undefined) {
    if (
      !isRecord(payload) ||
      payload.project_id !== projectId ||
      !("data" in payload)
    ) {
      throw new ApiError(
        response.status,
        "PROTOCOL_ERROR",
        "The API returned data for an unexpected project.",
        projectId,
        {},
      );
    }
    return payload.data as T;
  }
  return payload as T;
}

function parseJson(text: string): unknown {
  if (!text.trim()) {
    return null;
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

function apiErrorFromPayload(status: number, payload: unknown): ApiError {
  if (!isRecord(payload) || !isRecord(payload.error)) {
    return new ApiError(
      status,
      "API_ERROR",
      "The request could not be completed.",
      null,
      {},
    );
  }
  const error = payload.error;
  const code = typeof error.code === "string" ? error.code : "API_ERROR";
  const message =
    typeof error.message === "string"
      ? error.message
      : "The request could not be completed.";
  const projectId = typeof error.project_id === "string" ? error.project_id : null;
  const details = isRecord(error.details) ? error.details : {};
  return new ApiError(status, code, message, projectId, details);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
