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

  it("rejects an unscoped malformed 2xx response without exposing its body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("<html>traceback secret</html>", {
          status: 200,
          headers: { "Content-Type": "text/html" },
        }),
      ),
    );

    const error = await apiRequest("/api/v1/projects").catch(
      (caught) => caught,
    );

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 200,
      code: "PROTOCOL_ERROR",
      message: "The API returned an invalid response.",
    });
    expect((error as Error).message).not.toContain("traceback");
    expect((error as Error).message).not.toContain("secret");
  });

  it("rejects a project-scoped malformed 2xx response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("<html>invalid</html>", {
          status: 200,
          headers: { "Content-Type": "text/html" },
        }),
      ),
    );

    await expect(
      apiRequest("/api/v1/projects/A/work", { projectId: "A" }),
    ).rejects.toMatchObject({
      status: 200,
      code: "PROTOCOL_ERROR",
      projectId: "A",
    });
  });

  it("rejects an empty non-204 success response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("", {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(apiRequest("/api/v1/projects")).rejects.toMatchObject({
      status: 200,
      code: "PROTOCOL_ERROR",
      message: "The API returned an invalid response.",
    });
  });

  it("allows body-less HTTP 204 success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 204 })),
    );

    await expect(apiRequest("/api/v1/projects/A")).resolves.toBeUndefined();
  });

  it("passes FormData through without forcing JSON headers", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ project_id: "A", data: { imported: true } }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const body = new FormData();
    body.set("source_type", "text");

    await expect(
      apiRequest<{ imported: boolean }>("/api/v1/projects/A/style-analysis/imports/file", {
        method: "POST",
        body,
        projectId: "A",
      }),
    ).resolves.toEqual({ imported: true });

    const request = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(request.body).toBe(body);
    expect(new Headers(request.headers).has("Content-Type")).toBe(false);
  });
});
