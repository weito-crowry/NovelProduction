export type ApiDetails = Record<string, unknown>;

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    project_id?: string | null;
    details?: ApiDetails;
  };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly projectId: string | null;
  readonly details: ApiDetails;

  constructor(
    status: number,
    code: string,
    message: string,
    projectId: string | null,
    details: ApiDetails,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.projectId = projectId;
    this.details = details;
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}
