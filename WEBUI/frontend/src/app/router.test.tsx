import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { appRoutes } from "./routes";
import type { DashboardView, ProjectSummary, WorkRecord } from "../api/types";

const projects: ProjectSummary[] = [
  {
    project_id: "A",
    status: "active",
    metadata_state: "ok",
    working_title: "Alpha",
    created_at: null,
    updated_at: null,
    health: "ok",
  },
  {
    project_id: "B",
    status: "active",
    metadata_state: "missing",
    working_title: "Beta",
    created_at: null,
    updated_at: null,
    health: "degraded",
  },
];

function work(projectId: string): WorkRecord {
  return {
    id: 1,
    slug: projectId.toLowerCase(),
    working_title: projectId === "A" ? "Alpha" : "Beta",
    genre: "literary",
    premise: `${projectId} premise`,
    themes_json: '{"theme":"winter"}',
    description: `${projectId} description`,
    production_status: "planning",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    version: 1,
  };
}

function dashboard(projectId: string): DashboardView {
  return {
    work: work(projectId),
    chapter_count: projectId === "A" ? 2 : 7,
    episode_count: 3,
    scene_count: 4,
  };
}

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function installFetchMock() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/v1/projects" && (!init || init.method === undefined)) {
      return jsonResponse({ projects });
    }
    const match = url.match(/\/api\/v1\/projects\/([^/]+)\/(work|views\/dashboard)$/);
    if (match) {
      const projectId = match[1];
      if (match[2] === "work") {
        return jsonResponse({ project_id: projectId, data: work(projectId) });
      }
      return jsonResponse({ project_id: projectId, data: dashboard(projectId) });
    }
    return jsonResponse({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderRouter(initialEntry: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const router = createMemoryRouter(appRoutes, {
    initialEntries: [initialEntry],
  });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

describe("D1 routing and shell", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the project picker at the root route", async () => {
    installFetchMock();
    renderRouter("/");

    expect(
      await screen.findByRole("heading", { name: "Projects" }),
    ).toBeInTheDocument();
  });

  it("renders a project dashboard and keeps projectId in sidebar links", async () => {
    installFetchMock();
    renderRouter("/projects/A/dashboard");

    expect(await screen.findByText("Alpha")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute(
      "href",
      "/projects/A/dashboard",
    );
    expect(screen.getByRole("link", { name: "All projects" })).toHaveAttribute(
      "href",
      "/",
    );
  });

  it("provides a collapsible narrow-layout navigation control", async () => {
    installFetchMock();
    renderRouter("/projects/A/dashboard");

    const user = userEvent.setup();
    const toggle = screen.getByRole("button", { name: "Open navigation" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);
    expect(screen.getByRole("button", { name: "Hide navigation" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close navigation" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  it("does not render project A data after switching to project B", async () => {
    installFetchMock();
    renderRouter("/projects/A/dashboard");
    expect(await screen.findByText("Alpha")).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("link", { name: "All projects" }));
    await user.click(await screen.findByRole("link", { name: /Beta/ }));

    expect(await screen.findByText("Beta")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("Alpha")).not.toBeInTheDocument());
  });
});
