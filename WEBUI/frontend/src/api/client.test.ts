import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./errors";
import { apiRequest } from "./client";

describe("apiRequest", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("parses a project-scoped success envelope and returns its data", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ project_id: "A", data: { version: 3 } }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    await expect(
      apiRequest<{ version: number }>("/api/v1/projects/A/work", {
        projectId: "A",
      }),
    ).resolves.toEqual({ version: 3 });
  });

  it("parses a structured API error without exposing unrelated response text", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: "VERSION_CONFLICT",
              message: "The resource changed.",
              project_id: "A",
              details: { current_resource: { version: 4 } },
            },
          }),
          { status: 409, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    const error = await apiRequest("/api/v1/projects/A/work", {
      method: "PATCH",
      projectId: "A",
    }).catch((caught) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 409,
      code: "VERSION_CONFLICT",
      message: "The resource changed.",
      projectId: "A",
      details: { current_resource: { version: 4 } },
    });
  });

  it("uses a safe fallback for malformed error responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("<html>traceback secret</html>", {
          status: 500,
          headers: { "Content-Type": "text/html" },
        }),
      ),
    );

    const error = await apiRequest("/api/v1/projects/A/work").catch(
      (caught) => caught,
    );

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 500,
      code: "API_ERROR",
      message: "The request could not be completed.",
      projectId: null,
      details: {},
    });
    expect((error as Error).message).not.toContain("traceback");
    expect((error as Error).message).not.toContain("secret");
  });

  it("rejects a project-scoped success response with another project identity", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ project_id: "B", data: { version: 3 } }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    await expect(
      apiRequest("/api/v1/projects/A/work", { projectId: "A" }),
    ).rejects.toMatchObject({
      code: "PROTOCOL_ERROR",
      projectId: "A",
    });
  });
});
