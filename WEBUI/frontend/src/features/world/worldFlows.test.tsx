import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { appRoutes } from "../../app/routes";
import type { WorldFactRecord } from "../../api/types";

function response(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function fact(id: number, projectId = "A"): WorldFactRecord {
  return {
    id,
    work_id: 1,
    topic_key: `fact-${id}`,
    category: "setting",
    title: `${projectId} fact ${id}`,
    statement: `${projectId} statement ${id}`,
    details_json: '{"source":"test"}',
    valid_from: null,
    valid_to: null,
    canon_status: "draft",
    importance: 1,
    version: 1,
    created_at: "2026-01-01",
    updated_at: "2026-01-01",
  };
}

function renderRoute(initialEntry: string) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [initialEntry] });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

describe("D3 world flows", () => {
  afterEach(() => vi.restoreAllMocks());

  it("browses, searches, and preserves the project-scoped sidebar links", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/world-facts?limit=50&offset=0")) {
        return response({ project_id: "A", data: [fact(1), fact(2)] });
      }
      if (url.includes("/world-facts/search?query=%E7%81%AB%E5%B1%B1&limit=50")) {
        return response({ project_id: "A", data: [fact(3)] });
      }
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute("/projects/A/world");

    expect(await screen.findByRole("heading", { name: "World" })).toBeInTheDocument();
    expect(await screen.findByText("A fact 1")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Characters" })).toHaveAttribute(
      "href",
      "/projects/A/characters",
    );
    const user = userEvent.setup();
    await user.type(screen.getByRole("searchbox", { name: "Search world facts" }), "火山");
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText("A fact 3")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/projects/A/world-facts/search?query=%E7%81%AB%E5%B1%B1&limit=50",
      expect.anything(),
    );
  });

  it("blocks invalid JSON before creating a world fact and navigates after success", async () => {
    const created = fact(9);
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/world-facts?limit=50&offset=0")) {
        return response({ project_id: "A", data: [] });
      }
      if (url.endsWith("/world-facts") && init?.method === "POST") {
        return response({ project_id: "A", data: created }, 201);
      }
      if (url.endsWith("/world-facts/9")) {
        return response({ project_id: "A", data: created });
      }
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    const router = renderRoute("/projects/A/world");
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "World" });
    await user.click(screen.getByRole("button", { name: "Add world fact" }));
    await user.type(screen.getByLabelText("Statement"), "A new fact");
    const details = screen.getByLabelText("Details JSON");
    await user.clear(details);
    await user.type(details, "not-json");
    await user.click(screen.getByRole("button", { name: "Create world fact" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Enter valid JSON");
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
    fireEvent.change(details, { target: { value: "{\"ok\":true}" } });
    await user.click(screen.getByRole("button", { name: "Create world fact" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/projects/A/world/9"));
  });

  it("saves a world fact with statement, expected version, and changed optional fields only", async () => {
    const original = fact(1);
    const updated = { ...original, statement: "changed", importance: 4, version: 2 };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/world-facts/1") && init?.method === "PATCH") {
        expect(JSON.parse(String(init.body))).toEqual({
          statement: "changed",
          expected_version: 1,
          importance: 4,
        });
        return response({ project_id: "A", data: updated });
      }
      if (url.endsWith("/world-facts/1")) return response({ project_id: "A", data: original });
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute("/projects/A/world/1");
    const user = userEvent.setup();
    const statement = await screen.findByLabelText("Statement");
    await user.clear(statement);
    await user.type(statement, "changed");
    await user.clear(screen.getByLabelText("Importance"));
    await user.type(screen.getByLabelText("Importance"), "4");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Saved")).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH")).toHaveLength(1);
  });

  it("does not request an invalid route ID", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderRoute("/projects/A/world/0");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
