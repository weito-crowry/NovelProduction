import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { appRoutes } from "../../app/routes";
import { projectQueryKeys } from "../../api/queryKeys";
import type { EpisodeView, OutlineView } from "../../api/types";

function response(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function recordSet(projectId: string) {
  const chapter = {
    id: 1, work_id: 7, position: 1, title: `${projectId} chapter`, summary: "Summary", purpose: "Purpose",
    canon_status: "draft", production_status: "planned", version: 4, created_at: "2026-01-01", updated_at: "2026-01-01",
  };
  const episode = {
    id: 2, work_id: 7, chapter_id: 1, position: 1, title: `${projectId} episode`, summary: "Summary", purpose: "Purpose",
    foreshadowing_notes_json: "{}", canon_status: "draft", production_status: "planned", version: 5, created_at: "2026-01-01", updated_at: "2026-01-01",
  };
  const scene = {
    id: 3, work_id: 7, episode_id: 2, position: 1, title: `${projectId} scene`, summary: "Summary", purpose: "Purpose",
    canon_status: "draft", production_status: "planned", version: 6, created_at: "2026-01-01", updated_at: "2026-01-01",
  };
  const outline: OutlineView = { chapters: [{ chapter, episodes: [{ episode, scenes: [scene] }] }] };
  const view: EpisodeView = {
    episode,
    scenes: [scene],
    episode_references: [],
    outline: {
      episode,
      scenes: [scene],
      participants: [],
      references: { world_facts: [], timeline_events: [], information: [] },
      protected_information_guards: [],
    },
    context: {
      episode,
      scenes: [scene],
      participants: [],
      world_facts: [],
      timeline_events: [],
      reader_context: { known_before_episode: [], reveal_this_episode: [] },
      protected_information_guards: [],
      recent_context: { previous_episode_summaries: [], previous_draft_tail: "" },
      foreshadowing_notes: [],
      context_meta: {},
    },
    latest_draft: null,
    recent_draft_history: [],
  };
  return { chapter, episode, scene, outline, view };
}

function renderRoute(initialEntry: string) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [initialEntry] });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={queryClient}><RouterProvider router={router} /></QueryClientProvider>);
  return router;
}

describe("D2 structure administration flows", () => {
  afterEach(() => vi.restoreAllMocks());

  it("highlights chapter, episode, and scene route selections", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/views/outline")) return response({ project_id: "A", data: recordSet("A").outline });
      if (url.endsWith("/views/episodes/2")) return response({ project_id: "A", data: recordSet("A").view });
      if (url.endsWith("/scenes/3")) return response({ project_id: "A", data: recordSet("A").scene });
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);

    const chapterRouter = renderRoute("/projects/A/structure/chapters/1");
    expect(await screen.findByDisplayValue("A chapter")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /A chapter/ })).toHaveClass("selected");

    await chapterRouter.navigate("/projects/A/structure/episodes/2");
    expect(await screen.findByRole("heading", { name: "A episode" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /A episode/ })).toHaveClass("selected");

    await chapterRouter.navigate("/projects/A/structure/scenes/3");
    expect(await screen.findByDisplayValue("A scene")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /A scene/ })).toHaveClass("selected");
  });

  it("keeps project A entity data out of project B when both use id 1", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/views/outline")) {
        const projectId = url.includes("/B/") ? "B" : "A";
        return response({ project_id: projectId, data: recordSet(projectId).outline });
      }
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    const router = renderRoute("/projects/A/structure");
    expect(await screen.findByText("A chapter")).toBeInTheDocument();
    await router.navigate("/projects/B/structure");
    expect(await screen.findByText("B chapter")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("A chapter")).not.toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/projects/B/views/outline", expect.anything());
  });

  it("creates a chapter, refetches the outline, and navigates to the new route", async () => {
    const calls: string[] = [];
    const created = { ...recordSet("A").chapter, id: 9, title: "Created chapter" };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      calls.push(`${init?.method ?? "GET"} ${url}`);
      if (url.endsWith("/views/outline")) return response({ project_id: "A", data: recordSet("A").outline });
      if (url.endsWith("/chapters") && init?.method === "POST") return response({ project_id: "A", data: created }, 201);
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    const router = renderRoute("/projects/A/structure");
    await screen.findByText("A chapter");
    await userEvent.setup().click(screen.getByRole("button", { name: "Add chapter" }));
    await userEvent.setup().type(screen.getByLabelText("Title"), "Created chapter");
    await userEvent.setup().click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/projects/A/structure/chapters/9"));
    expect(JSON.parse(String(fetchMock.mock.calls.find(([, init]) => init?.method === "POST")?.[1]?.body))).toEqual({
      title: "Created chapter", summary: "", purpose: "", production_status: "planned", canon_status: "draft",
    });
    expect(calls.filter((call) => call === "GET /api/v1/projects/A/views/outline").length).toBeGreaterThanOrEqual(2);
  });

  it("creates an episode with an explicit empty foreshadowing array", async () => {
    const data = recordSet("A");
    const created = { ...data.episode, id: 9, title: "Created episode", foreshadowing_notes_json: "[]" };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/views/outline")) return response({ project_id: "A", data: data.outline });
      if (url.endsWith("/chapters/1/episodes") && init?.method === "POST") return response({ project_id: "A", data: created }, 201);
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    const router = renderRoute("/projects/A/structure");
    await screen.findByText("A chapter");
    await userEvent.setup().click(screen.getByRole("button", { name: "Add episode" }));
    expect(screen.getByLabelText("Foreshadowing notes JSON")).toHaveValue("[]");
    await userEvent.setup().type(screen.getByLabelText("Title"), "Created episode");
    await userEvent.setup().click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/projects/A/structure/episodes/9"));
    const call = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({
      title: "Created episode", summary: "", purpose: "", foreshadowing_notes: [], production_status: "planned", canon_status: "draft",
    });
  });

  it.each(["{}", "null", '"text"'])("blocks invalid episode create shape %s before POST", async (notes) => {
    const data = recordSet("A");
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void init;
      if (String(input).endsWith("/views/outline")) return response({ project_id: "A", data: data.outline });
      return response({ error: { code: "UNEXPECTED", message: "Unexpected request" } }, 500);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute("/projects/A/structure");
    await screen.findByText("A chapter");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Add episode" }));
    const notesField = screen.getByLabelText("Foreshadowing notes JSON");
    await user.clear(notesField);
    fireEvent.change(notesField, { target: { value: notes } });
    await user.type(screen.getByLabelText("Title"), "Invalid episode");
    await user.click(screen.getByRole("button", { name: "Create" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Foreshadowing notes must be a JSON array.");
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  });

  it("invalidates the project dashboard when creating a chapter", async () => {
    const data = recordSet("A");
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 10_000 } } });
    queryClient.setQueryData(projectQueryKeys.dashboard("A"), { chapter_count: 1, episode_count: 1, scene_count: 1 });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/views/outline")) return response({ project_id: "A", data: data.outline });
      if (url.endsWith("/chapters") && init?.method === "POST") return response({ project_id: "A", data: data.chapter }, 201);
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderWithQueryClient("/projects/A/structure", queryClient);
    await screen.findByText("A chapter");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Add chapter" }));
    await user.type(screen.getByLabelText("Title"), "Created chapter");
    await user.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => expect(queryClient.getQueryState(projectQueryKeys.dashboard("A"))?.isInvalidated).toBe(true));
  });

  it("invalidates the dashboard and episode-view family when creating an episode", async () => {
    const data = recordSet("A");
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 10_000 } } });
    queryClient.setQueryData(projectQueryKeys.dashboard("A"), { episode_count: 1 });
    queryClient.setQueryData(projectQueryKeys.episodeView("A", 88), data.view);
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/views/outline")) return response({ project_id: "A", data: data.outline });
      if (url.endsWith("/chapters/1/episodes") && init?.method === "POST") return response({ project_id: "A", data: { ...data.episode, id: 9 } }, 201);
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderWithQueryClient("/projects/A/structure", queryClient);
    await screen.findByText("A chapter");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Add episode" }));
    await user.type(screen.getByLabelText("Title"), "Created episode");
    await user.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => {
      expect(queryClient.getQueryState(projectQueryKeys.dashboard("A"))?.isInvalidated).toBe(true);
      expect(queryClient.getQueryState(projectQueryKeys.episodeView("A", 88))?.isInvalidated).toBe(true);
    });
  });

  it("invalidates the dashboard and parent episode view when creating a scene", async () => {
    const data = recordSet("A");
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 10_000 } } });
    queryClient.setQueryData(projectQueryKeys.dashboard("A"), { scene_count: 1 });
    queryClient.setQueryData(projectQueryKeys.episodeView("A", 2), data.view);
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/views/outline")) return response({ project_id: "A", data: data.outline });
      if (url.endsWith("/episodes/2/scenes") && init?.method === "POST") return response({ project_id: "A", data: { ...data.scene, id: 9 } }, 201);
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderWithQueryClient("/projects/A/structure", queryClient);
    await screen.findByText("A episode");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Add scene" }));
    await user.type(screen.getByLabelText("Title"), "Created scene");
    await user.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => {
      expect(queryClient.getQueryState(projectQueryKeys.dashboard("A"))?.isInvalidated).toBe(true);
      expect(queryClient.getQueryState(projectQueryKeys.episodeView("A", 2))?.isInvalidated).toBe(true);
    });
  });

  it("saves a chapter with only changed fields and the baseline version", async () => {
    const data = recordSet("A");
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/views/outline")) return response({ project_id: "A", data: data.outline });
      if (url.endsWith("/chapters/1") && init?.method === "PATCH") return response({ project_id: "A", data: { ...data.chapter, summary: "Changed", version: 7 } });
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute("/projects/A/structure/chapters/1");
    const summary = await screen.findByLabelText("Summary");
    await userEvent.setup().clear(summary);
    await userEvent.setup().type(summary, "Changed");
    await userEvent.setup().click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(true));
    const call = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ expected_version: 4, summary: "Changed" });
    expect(await screen.findByText("Saved")).toBeInTheDocument();
  });

  it("invalidates the project episode-view family when updating an episode", async () => {
    const data = recordSet("A");
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 10_000 } } });
    queryClient.setQueryData(projectQueryKeys.episodeView("A", 88), data.view);
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/views/outline")) return response({ project_id: "A", data: data.outline });
      if (url.endsWith("/views/episodes/2")) return response({ project_id: "A", data: data.view });
      if (url.endsWith("/episodes/2") && init?.method === "PATCH") return response({ project_id: "A", data: { ...data.episode, title: "Updated episode", version: 6 } });
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderWithQueryClient("/projects/A/structure/episodes/2", queryClient);
    const user = userEvent.setup();
    const title = await screen.findByLabelText("Title");
    await user.clear(title);
    await user.type(title, "Updated episode");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(queryClient.getQueryState(projectQueryKeys.episodeView("A", 88))?.isInvalidated).toBe(true));
  });

  it("invalidates the scene query and parent episode view when updating a scene", async () => {
    const data = recordSet("A");
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 10_000 } } });
    queryClient.setQueryData(projectQueryKeys.episodeView("A", 2), data.view);
    let sceneReads = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/views/outline")) return response({ project_id: "A", data: data.outline });
      if (url.endsWith("/scenes/3") && !init?.method) {
        sceneReads += 1;
        return response({ project_id: "A", data: data.scene });
      }
      if (url.endsWith("/scenes/3") && init?.method === "PATCH") return response({ project_id: "A", data: { ...data.scene, title: "Updated scene", version: 7 } });
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderWithQueryClient("/projects/A/structure/scenes/3", queryClient);
    const user = userEvent.setup();
    const title = await screen.findByLabelText("Title");
    await user.clear(title);
    await user.type(title, "Updated scene");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(sceneReads).toBe(2));
    await waitFor(() => expect(queryClient.getQueryState(projectQueryKeys.episodeView("A", 2))?.isInvalidated).toBe(true));
  });

  it("keeps local episode edits on a current-resource conflict without retrying", async () => {
    const data = recordSet("A");
    const latest = { ...data.episode, title: "Latest episode", version: 9 };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/views/outline")) return response({ project_id: "A", data: data.outline });
      if (url.endsWith("/views/episodes/2")) return response({ project_id: "A", data: data.view });
      if (url.endsWith("/episodes/2") && init?.method === "PATCH") return response({ error: { code: "VERSION_CONFLICT", message: "Changed elsewhere", project_id: "A", details: { current_resource: latest } } }, 409);
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute("/projects/A/structure/episodes/2");
    const user = userEvent.setup();
    const title = await screen.findByLabelText("Title");
    await user.clear(title);
    await user.type(title, "Local episode");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("heading", { name: "This episode changed elsewhere" })).toBeInTheDocument();
    expect(screen.getByDisplayValue("Local episode")).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH")).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Keep local edits" }));
    expect(screen.getByDisplayValue("Local episode")).toBeInTheDocument();
  });

  it("adopts a latest episode conflict resource into the fresh cache before remount", async () => {
    const data = recordSet("A");
    const latest = { ...data.episode, title: "Latest episode", version: 9 };
    const latestView = { ...data.view, episode: latest, outline: { ...data.view.outline, episode: latest }, context: { ...data.view.context, episode: latest } };
    let viewReads = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/views/outline")) return response({ project_id: "A", data: data.outline });
      if (url.endsWith("/views/episodes/2")) {
        viewReads += 1;
        return response({ project_id: "A", data: viewReads > 1 ? latestView : data.view });
      }
      if (url.endsWith("/episodes/2") && init?.method === "PATCH") return response({ error: { code: "VERSION_CONFLICT", message: "Changed elsewhere", project_id: "A", details: { current_resource: latest } } }, 409);
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 10_000 } } });
    const router = renderWithQueryClient("/projects/A/structure/episodes/2", queryClient);
    const user = userEvent.setup();
    const title = await screen.findByLabelText("Title");
    await user.clear(title);
    await user.type(title, "Local episode");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByRole("heading", { name: "This episode changed elsewhere" });
    await user.click(screen.getByRole("button", { name: "Load latest and discard local edits" }));
    await waitFor(() => expect(screen.getByDisplayValue("Latest episode")).toBeInTheDocument());
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH")).toHaveLength(1);
    await router.navigate("/projects/A/structure");
    await router.navigate("/projects/A/structure/episodes/2");
    expect(await screen.findByDisplayValue("Latest episode")).toBeInTheDocument();
    expect(viewReads).toBe(2);
  });

  it("keeps local scene edits on a current-resource conflict without retrying", async () => {
    const data = recordSet("A");
    const latest = { ...data.scene, title: "Latest scene", version: 9 };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/views/outline")) return response({ project_id: "A", data: data.outline });
      if (url.endsWith("/scenes/3") && !init?.method) return response({ project_id: "A", data: data.scene });
      if (url.endsWith("/scenes/3") && init?.method === "PATCH") return response({ error: { code: "VERSION_CONFLICT", message: "Changed elsewhere", project_id: "A", details: { current_resource: latest } } }, 409);
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute("/projects/A/structure/scenes/3");
    const user = userEvent.setup();
    const title = await screen.findByLabelText("Title");
    await user.clear(title);
    await user.type(title, "Local scene");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("heading", { name: "This scene changed elsewhere" })).toBeInTheDocument();
    expect(screen.getByDisplayValue("Local scene")).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH")).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Keep local edits" }));
    expect(screen.getByDisplayValue("Local scene")).toBeInTheDocument();
  });

  it("does not resurrect the old scene after loading the latest conflict resource", async () => {
    const data = recordSet("A");
    const latest = { ...data.scene, title: "Latest scene", version: 9 };
    let sceneReads = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/views/outline")) return response({ project_id: "A", data: data.outline });
      if (url.endsWith("/scenes/3") && !init?.method) {
        sceneReads += 1;
        return response({ project_id: "A", data: sceneReads > 1 ? latest : data.scene });
      }
      if (url.endsWith("/scenes/3") && init?.method === "PATCH") return response({ error: { code: "VERSION_CONFLICT", message: "Changed elsewhere", project_id: "A", details: { current_resource: latest } } }, 409);
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 10_000 } } });
    const router = renderWithQueryClient("/projects/A/structure/scenes/3", queryClient);
    const user = userEvent.setup();
    const title = await screen.findByLabelText("Title");
    await user.clear(title);
    await user.type(title, "Local scene");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByRole("heading", { name: "This scene changed elsewhere" });
    await user.click(screen.getByRole("button", { name: "Load latest and discard local edits" }));
    await waitFor(() => expect(screen.getByDisplayValue("Latest scene")).toBeInTheDocument());
    await router.navigate("/projects/A/structure");
    await router.navigate("/projects/A/structure/scenes/3");
    expect(await screen.findByDisplayValue("Latest scene")).toBeInTheDocument();
    expect(sceneReads).toBe(2);
  });

  it("shows a chapter conflict without retrying and allows keeping local edits", async () => {
    const data = recordSet("A");
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/views/outline") && init?.method !== "PATCH") return response({ project_id: "A", data: data.outline });
      if (url.endsWith("/chapters/1") && init?.method === "PATCH") return response({ error: { code: "VERSION_CONFLICT", message: "Changed elsewhere", project_id: "A", details: { current_resource: { ...data.chapter, title: "Latest chapter", version: 8 } } } }, 409);
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute("/projects/A/structure/chapters/1");
    const title = await screen.findByLabelText("Title");
    await userEvent.setup().clear(title);
    await userEvent.setup().type(title, "Local chapter");
    await userEvent.setup().click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("heading", { name: "This chapter changed elsewhere" })).toBeInTheDocument();
    expect(screen.getByDisplayValue("Local chapter")).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH")).toHaveLength(1);
    await userEvent.setup().click(screen.getByRole("button", { name: "Keep local edits" }));
    expect(screen.getByDisplayValue("Local chapter")).toBeInTheDocument();
  });

  it("uses a network outline fallback when chapter conflict has no current resource", async () => {
    const data = recordSet("A");
    let outlineReads = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/views/outline")) {
        outlineReads += 1;
        const latest = outlineReads > 1 ? { ...data.outline, chapters: [{ ...data.outline.chapters[0], chapter: { ...data.chapter, title: "Latest chapter", version: 8 } }] } : data.outline;
        return response({ project_id: "A", data: latest });
      }
      if (url.endsWith("/chapters/1") && init?.method === "PATCH") return response({ error: { code: "VERSION_CONFLICT", message: "Changed elsewhere", project_id: "A", details: {} } }, 409);
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute("/projects/A/structure/chapters/1");
    const title = await screen.findByLabelText("Title");
    await userEvent.setup().clear(title);
    await userEvent.setup().type(title, "Local chapter");
    await userEvent.setup().click(screen.getByRole("button", { name: "Save changes" }));
    expect(screen.getAllByText("Latest chapter", { exact: false }).length).toBeGreaterThan(0);
    expect(outlineReads).toBe(2);
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH")).toHaveLength(1);
  });

  it("keeps chapter edits when Stay is chosen in the dirty navigation guard", async () => {
    const data = recordSet("A");
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/views/outline")) return response({ project_id: "A", data: data.outline });
      if (url.endsWith("/views/episodes/2")) return response({ project_id: "A", data: data.view });
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute("/projects/A/structure/chapters/1");
    const user = userEvent.setup();
    const title = await screen.findByLabelText("Title");
    await user.clear(title);
    await user.type(title, "Unsaved chapter");
    await user.click(screen.getByRole("link", { name: /A episode/ }));
    expect(screen.getByRole("heading", { name: "Leave without saving?" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Stay" }));
    expect(screen.getByDisplayValue("Unsaved chapter")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith("/views/episodes/2"))).toBe(false);
  });
});

function renderWithQueryClient(initialEntry: string, queryClient: QueryClient) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [initialEntry] });
  render(<QueryClientProvider client={queryClient}><RouterProvider router={router} /></QueryClientProvider>);
  return router;
}
