import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { projectQueryKeys } from "../../api/queryKeys";
import { appRoutes } from "../../app/routes";
import type { InformationItemRecord } from "../../api/types";

function response(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function item(id = 1, statement = "A secret", version = 1): InformationItemRecord {
  return {
    id,
    work_id: 7,
    statement,
    truth_status: "true",
    authoring_guard: "",
    notes_json: '{"source":"test"}',
    canon_status: "draft",
    importance: 1,
    version,
    created_at: "2026-01-01",
    updated_at: "2026-01-01",
  };
}

function renderRoute(initialEntry: string) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [initialEntry] });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={queryClient}><RouterProvider router={router} /></QueryClientProvider>);
  return router;
}

describe("D4 information flows", () => {
  afterEach(() => vi.restoreAllMocks());

  it("browses, loads more, and searches information in the selected project", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/information?limit=50&offset=0"))
        return response({ project_id: "A", data: [item(1), ...Array.from({ length: 49 }, (_, index) => item(index + 51, `Item ${index + 51}`))] });
      if (url.endsWith("/information?limit=50&offset=50"))
        return response({ project_id: "A", data: [item(2, "Second")] });
      if (url.includes("/information/search?query=secret&limit=50"))
        return response({ project_id: "A", data: [item(3, "Search result")] });
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute("/projects/A/information");

    expect(await screen.findByText("A secret")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText("Second")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.type(screen.getByRole("searchbox", { name: "Search information" }), "secret");
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText("Search result")).toBeInTheDocument();
  });

  it("prevents invalid JSON and sends a minimal versioned update", async () => {
    const original = item();
    const updated = item(1, "Updated", 2);
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/information/1") && init?.method === "PATCH") {
        expect(JSON.parse(String(init.body))).toEqual({
          expected_version: 1,
          statement: "Updated",
        });
        return response({ project_id: "A", data: updated });
      }
      if (url.endsWith("/information/1")) return response({ project_id: "A", data: original });
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute("/projects/A/information/1");
    const user = userEvent.setup();
    const statement = await screen.findByLabelText("Statement");
    await user.clear(statement);
    await user.type(statement, "Updated");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Saved")).toBeInTheDocument();
    await waitFor(() => expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH")).toHaveLength(1));
  });

  it("invalidates derived caches after an information update even while their data is fresh", async () => {
    const original = item();
    const updated = item(1, "Updated", 2);
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/information/1") && init?.method === "PATCH") return response({ project_id: "A", data: updated });
      if (url.endsWith("/information/1")) return response({ project_id: "A", data: original });
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 10_000 } } });
    const derivedKeys = [
      projectQueryKeys.informationFamily("A"),
      projectQueryKeys.informationSearchFamily("A"),
      projectQueryKeys.canonDecisionsFamily("A"),
      projectQueryKeys.canonDecisionSearchFamily("A"),
      projectQueryKeys.characterKnowledgeProjectFamily("A"),
      projectQueryKeys.episodeViews("A"),
    ];
    for (const key of derivedKeys) queryClient.setQueryData(key, { cached: true });
    renderRouteWithClient("/projects/A/information/1", queryClient);

    const user = userEvent.setup();
    const statement = await screen.findByLabelText("Statement");
    await user.clear(statement);
    await user.type(statement, "Updated");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText("Saved");

    for (const key of derivedKeys) expect(queryClient.getQueryState(key)?.isInvalidated).toBe(true);
  });

  it("does not request an invalid information route", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderRoute("/projects/A/information/0");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

function renderRouteWithClient(initialEntry: string, queryClient: QueryClient) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [initialEntry] });
  render(<QueryClientProvider client={queryClient}><RouterProvider router={router} /></QueryClientProvider>);
  return router;
}
