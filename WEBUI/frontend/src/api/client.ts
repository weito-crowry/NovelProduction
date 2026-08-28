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
  const parsed = parseJson(text);
  if (!response.ok) {
    throw apiErrorFromPayload(
      response.status,
      parsed.ok ? parsed.value : null,
    );
  }
  if (response.status === 204) {
    return undefined as T;
  }
  if (!parsed.ok || parsed.value === null) {
    throw invalidResponseError(response.status, projectId);
  }

  if (projectId !== undefined) {
    if (
      !isRecord(parsed.value) ||
      parsed.value.project_id !== projectId ||
      !("data" in parsed.value)
    ) {
      throw invalidResponseError(response.status, projectId);
    }
    return parsed.value.data as T;
  }
  return parsed.value as T;
}

type ParsedJson = { ok: true; value: unknown } | { ok: false };

function parseJson(text: string): ParsedJson {
  if (!text.trim()) {
    return { ok: false };
  }
  try {
    return { ok: true, value: JSON.parse(text) as unknown };
  } catch {
    return { ok: false };
  }
}

function invalidResponseError(status: number, projectId?: string): ApiError {
  return new ApiError(
    status,
    "PROTOCOL_ERROR",
    "The API returned an invalid response.",
    projectId ?? null,
    {},
  );
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
