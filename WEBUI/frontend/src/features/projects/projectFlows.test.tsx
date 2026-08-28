import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { appRoutes } from "../../app/routes";
import type { DashboardView, ProjectSummary, WorkRecord } from "../../api/types";

const activeProject: ProjectSummary = {
  project_id: "A",
  status: "active",
  metadata_state: "ok",
  working_title: "Alpha",
  created_at: null,
  updated_at: null,
  health: "ok",
};
const archivedProject: ProjectSummary = {
  ...activeProject,
  project_id: "ARCHIVE",
  status: "archived",
  working_title: "Archived novel",
};

function work(projectId: string): WorkRecord {
  return {
    id: 1,
    slug: projectId.toLowerCase(),
    working_title: projectId === "CREATED" ? "Created novel" : "Alpha",
    genre: "literary",
    premise: "A premise",
    themes_json: "{}",
    description: "A description",
    production_status: "planning",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    version: 1,
  };
}

function response(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function installProjectFetchMock() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/v1/projects" && init?.method === "POST") {
      return response(
        { ...activeProject, project_id: "CREATED", working_title: "Created novel" },
        201,
      );
    }
    if (url === "/api/v1/projects" || url === "/api/v1/projects?include_archived=true") {
      const includeArchived = url.includes("include_archived=true");
      return response({
        projects: includeArchived ? [activeProject, archivedProject] : [activeProject],
      });
    }
    if (url === "/api/v1/projects/ARCHIVE" && init?.method === "PATCH") {
      const payload = JSON.parse(String(init.body)) as { status: string };
      return response({ ...archivedProject, status: payload.status });
    }
    if (url === "/api/v1/projects/A" && init?.method === "PATCH") {
      return response({ ...activeProject, status: "archived" });
    }
    const match = url.match(/\/api\/v1\/projects\/([^/]+)\/views\/dashboard$/);
    if (match) {
      const projectId = match[1];
      const dashboard: DashboardView = {
        work: work(projectId),
        chapter_count: 1,
        episode_count: 2,
        scene_count: 3,
      };
      return response({ project_id: projectId, data: dashboard });
    }
    return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderRouter(initialEntry: string) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [initialEntry] });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

describe("project management flows", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads archived projects only after the include archived toggle", async () => {
    const fetchMock = installProjectFetchMock();
    renderRouter("/");

    expect(await screen.findByText("Alpha")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("checkbox", { name: "Include archived" }));

    expect(await screen.findByText("Archived novel")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/projects?include_archived=true",
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
  });

  it("creates a project and navigates to its dashboard", async () => {
    const fetchMock = installProjectFetchMock();
    renderRouter("/");
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Working title"), "Created novel");
    await user.click(screen.getByRole("button", { name: "Create project" }));

    expect(await screen.findByRole("heading", { name: "Created novel" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/projects",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("archives the selected project and returns to the picker", async () => {
    installProjectFetchMock();
    renderRouter("/projects/A/dashboard");

    expect(await screen.findByRole("heading", { name: "Alpha" })).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Archive project" }));

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Projects" })).toBeInTheDocument(),
    );
  });

  it("unarchives an archived project from the picker", async () => {
    const fetchMock = installProjectFetchMock();
    renderRouter("/");
    const user = userEvent.setup();
    await user.click(screen.getByRole("checkbox", { name: "Include archived" }));
    await screen.findByText("Archived novel");

    await user.click(screen.getByRole("button", { name: "Unarchive" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/projects/ARCHIVE",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({ status: "active" }),
        }),
      ),
    );
  });
});
