import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { appRoutes } from "../../app/routes";
import { projectQueryKeys } from "../../api/queryKeys";
import type { EpisodeView, OutlineView } from "../../api/types";
import { sameParent } from "./structureTreeUtils";

const chapterOne = { id: 1, work_id: 7, position: 1, title: "First", summary: "", purpose: "", canon_status: "draft", production_status: "planned", version: 2, created_at: "", updated_at: "" };
const chapterTwo = { id: 4, work_id: 7, position: 2, title: "Second", summary: "", purpose: "", canon_status: "draft", production_status: "planned", version: 3, created_at: "", updated_at: "" };
const episodeOne = { id: 2, work_id: 7, chapter_id: 1, position: 1, title: "Episode one", summary: "", purpose: "", foreshadowing_notes_json: "{}", canon_status: "draft", production_status: "planned", version: 4, created_at: "", updated_at: "" };
const episodeTwo = { id: 5, work_id: 7, chapter_id: 4, position: 1, title: "Episode two", summary: "", purpose: "", foreshadowing_notes_json: "{}", canon_status: "draft", production_status: "planned", version: 5, created_at: "", updated_at: "" };
const episodeThree = { id: 6, work_id: 7, chapter_id: 1, position: 2, title: "Episode three", summary: "", purpose: "", foreshadowing_notes_json: "[]", canon_status: "draft", production_status: "planned", version: 5, created_at: "", updated_at: "" };
const sceneOne = { id: 3, work_id: 7, episode_id: 2, position: 1, title: "Scene one", summary: "", purpose: "", canon_status: "draft", production_status: "planned", version: 6, created_at: "", updated_at: "" };
const sceneTwo = { id: 7, work_id: 7, episode_id: 2, position: 2, title: "Scene two", summary: "", purpose: "", canon_status: "draft", production_status: "planned", version: 7, created_at: "", updated_at: "" };

function outline(swapped = false): OutlineView {
  const chapters = swapped ? [
    { chapter: { ...chapterTwo, position: 1, version: 4 }, episodes: [{ episode: episodeTwo, scenes: [] }] },
    { chapter: { ...chapterOne, position: 2, version: 3 }, episodes: [{ episode: episodeOne, scenes: [] }] },
  ] : [
    { chapter: chapterOne, episodes: [{ episode: episodeOne, scenes: [] }] },
    { chapter: chapterTwo, episodes: [{ episode: episodeTwo, scenes: [] }] },
  ];
  return { chapters };
}

function episodeSiblingOutline(swapped = false): OutlineView {
  const first = { ...episodeOne, position: swapped ? 2 : 1, version: swapped ? 5 : 4 };
  const second = { ...episodeThree, position: swapped ? 1 : 2, version: swapped ? 6 : 5 };
  return { chapters: [{ chapter: chapterOne, episodes: [{ episode: first, scenes: [] }, { episode: second, scenes: [] }] }, { chapter: chapterTwo, episodes: [] }] };
}

function sceneSiblingOutline(swapped = false): OutlineView {
  const first = { ...sceneOne, position: swapped ? 2 : 1, version: swapped ? 7 : 6 };
  const second = { ...sceneTwo, position: swapped ? 1 : 2, version: swapped ? 8 : 7 };
  return { chapters: [{ chapter: chapterOne, episodes: [{ episode: episodeOne, scenes: [first, second] }] }] };
}

function episodeView(record = episodeOne, scenes: typeof sceneOne[] = []): EpisodeView {
  return {
    episode: record,
    scenes,
    episode_references: [],
    outline: { episode: record, scenes, participants: [], references: { world_facts: [], timeline_events: [], information: [] }, protected_information_guards: [] },
    context: { episode: record, scenes, participants: [], world_facts: [], timeline_events: [], reader_context: { known_before_episode: [], reveal_this_episode: [] }, protected_information_guards: [], recent_context: { previous_episode_summaries: [], previous_draft_tail: "" }, foreshadowing_notes: [], context_meta: {} },
    latest_draft: null,
    recent_draft_history: [],
  };
}

function renderTree(fetchMock: ReturnType<typeof vi.fn>, initialEntry = "/projects/A/structure", queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  vi.stubGlobal("fetch", fetchMock);
  const router = createMemoryRouter(appRoutes, { initialEntries: [initialEntry] });
  render(<QueryClientProvider client={queryClient}><RouterProvider router={router} /></QueryClientProvider>);
  return queryClient;
}

describe("structure reorder", () => {
  afterEach(() => vi.restoreAllMocks());

  it("uses keyboard drag to send a one-based chapter target and current version, then refetches canonical order", async () => {
    let swapped = false;
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 10_000 } } });
    queryClient.setQueryData(projectQueryKeys.episodeView("A", 88), episodeView());
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/views/outline")) return new Response(JSON.stringify({ project_id: "A", data: outline(swapped) }));
      if (url.endsWith("/chapters/1/reorder") && init?.method === "POST") {
        swapped = true;
        return new Response(JSON.stringify({ project_id: "A", data: [] }));
      }
      return new Response(JSON.stringify({ error: { code: "NOT_FOUND", message: "Not found" } }), { status: 404 });
    });
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
      const top = (this.textContent ?? "").includes("Second") ? 100 : 0;
      return { x: 0, y: top, top, left: 0, right: 300, bottom: top + 50, width: 300, height: 50, toJSON: () => ({}) } as DOMRect;
    });
    renderTree(fetchMock, "/projects/A/structure", queryClient);
    const handle = await screen.findByRole("button", { name: "Reorder chapter First" });
    fireEvent.keyDown(handle, { key: " ", code: "Space", keyCode: 32 });
    await new Promise((resolve) => setTimeout(resolve, 0));
    fireEvent.keyDown(handle, { key: "ArrowDown", code: "ArrowDown", keyCode: 40 });
    fireEvent.keyDown(handle, { key: " ", code: "Space", keyCode: 32 });
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true));
    const call = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(String(call?.[0])).toBe("/api/v1/projects/A/chapters/1/reorder");
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ target_position: 2, expected_version: 2 });
    await waitFor(() => {
      const tree = within(screen.getByLabelText("Structure tree"));
      expect(tree.getAllByRole("link")[0]).toHaveTextContent("Second");
    });
    expect(fetchMock.mock.calls.filter(([input]) => String(input).endsWith("/views/outline")).length).toBeGreaterThanOrEqual(2);
    await waitFor(() => expect(queryClient.getQueryState(projectQueryKeys.episodeView("A", 88))?.isInvalidated).toBe(true));
  });

  it("does not send a request when a keyboard drag is dropped at the same position", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      void _init;
      if (String(input).endsWith("/views/outline")) return new Response(JSON.stringify({ project_id: "A", data: outline() }));
      return new Response(JSON.stringify({ error: { code: "UNEXPECTED", message: "Unexpected" } }), { status: 500 });
    });
    renderTree(fetchMock);
    const handle = await screen.findByRole("button", { name: "Reorder chapter First" });
    fireEvent.keyDown(handle, { key: " ", code: "Space", keyCode: 32 });
    fireEvent.keyDown(handle, { key: " ", code: "Space", keyCode: 32 });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  });

  it("reorders episodes within one chapter with a one-based target and refetches", async () => {
    let swapped = false;
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 10_000 } } });
    queryClient.setQueryData(projectQueryKeys.episodeView("A", 88), episodeView());
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/views/outline")) return new Response(JSON.stringify({ project_id: "A", data: episodeSiblingOutline(swapped) }));
      if (url.endsWith("/episodes/2/reorder") && init?.method === "POST") {
        swapped = true;
        return new Response(JSON.stringify({ project_id: "A", data: [] }));
      }
      return new Response(JSON.stringify({ error: { code: "NOT_FOUND", message: "Not found" } }), { status: 404 });
    });
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
      const top = (this.textContent ?? "").includes("Episode three") ? 100 : 0;
      return { x: 0, y: top, top, left: 0, right: 300, bottom: top + 50, width: 300, height: 50, toJSON: () => ({}) } as DOMRect;
    });
    renderTree(fetchMock, "/projects/A/structure", queryClient);
    const handle = await screen.findByRole("button", { name: "Reorder episode Episode one" });
    fireEvent.keyDown(handle, { key: " ", code: "Space", keyCode: 32 });
    await new Promise((resolve) => setTimeout(resolve, 0));
    fireEvent.keyDown(handle, { key: "ArrowDown", code: "ArrowDown", keyCode: 40 });
    fireEvent.keyDown(handle, { key: " ", code: "Space", keyCode: 32 });
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true));
    const call = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(String(call?.[0])).toBe("/api/v1/projects/A/episodes/2/reorder");
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ target_position: 2, expected_version: 4 });
    await waitFor(() => expect(fetchMock.mock.calls.filter(([input]) => String(input).endsWith("/views/outline")).length).toBeGreaterThanOrEqual(2));
    await waitFor(() => expect(queryClient.getQueryState(projectQueryKeys.episodeView("A", 88))?.isInvalidated).toBe(true));
  });

  it("reorders scenes within one episode and refreshes the scene family", async () => {
    let swapped = false;
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 10_000 } } });
    queryClient.setQueryData(projectQueryKeys.scene("A", 99), sceneOne);
    queryClient.setQueryData(projectQueryKeys.episodeView("A", 2), episodeView());
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/views/outline")) return new Response(JSON.stringify({ project_id: "A", data: sceneSiblingOutline(swapped) }));
      if (url.endsWith("/scenes/3") && !init?.method) return new Response(JSON.stringify({ project_id: "A", data: swapped ? { ...sceneOne, position: 2, version: 7 } : sceneOne }));
      if (url.endsWith("/scenes/3/reorder") && init?.method === "POST") {
        swapped = true;
        return new Response(JSON.stringify({ project_id: "A", data: [] }));
      }
      return new Response(JSON.stringify({ error: { code: "NOT_FOUND", message: "Not found" } }), { status: 404 });
    });
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
      const top = (this.textContent ?? "").includes("Scene two") ? 100 : 0;
      return { x: 0, y: top, top, left: 0, right: 300, bottom: top + 50, width: 300, height: 50, toJSON: () => ({}) } as DOMRect;
    });
    renderTree(fetchMock, "/projects/A/structure/scenes/3", queryClient);
    const handle = await screen.findByRole("button", { name: "Reorder scene Scene one" });
    fireEvent.keyDown(handle, { key: " ", code: "Space", keyCode: 32 });
    await new Promise((resolve) => setTimeout(resolve, 0));
    fireEvent.keyDown(handle, { key: "ArrowDown", code: "ArrowDown", keyCode: 40 });
    fireEvent.keyDown(handle, { key: " ", code: "Space", keyCode: 32 });
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true));
    const call = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(String(call?.[0])).toBe("/api/v1/projects/A/scenes/3/reorder");
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ target_position: 2, expected_version: 6 });
    await waitFor(() => expect(queryClient.getQueryState(projectQueryKeys.scene("A", 99))?.isInvalidated).toBe(true));
    await waitFor(() => expect(queryClient.getQueryState(projectQueryKeys.episodeView("A", 2))?.isInvalidated).toBe(true));
  });

  it("does not allow an episode reorder across chapters", () => {
    expect(sameParent(outline(), { kind: "episode", id: 2 }, { kind: "episode", id: 5 })).toBe(false);
  });

  it("synchronizes a clean chapter editor to the post-reorder version before saving", async () => {
    let swapped = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/views/outline")) return new Response(JSON.stringify({ project_id: "A", data: outline(swapped) }));
      if (url.endsWith("/chapters/1/reorder") && init?.method === "POST") {
        swapped = true;
        return new Response(JSON.stringify({ project_id: "A", data: [] }));
      }
      if (url.endsWith("/chapters/1") && init?.method === "PATCH") return new Response(JSON.stringify({ project_id: "A", data: { ...chapterOne, title: "Saved after reorder", version: 4 } }));
      return new Response(JSON.stringify({ error: { code: "NOT_FOUND", message: "Not found" } }), { status: 404 });
    });
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
      const top = (this.textContent ?? "").includes("Second") ? 100 : 0;
      return { x: 0, y: top, top, left: 0, right: 300, bottom: top + 50, width: 300, height: 50, toJSON: () => ({}) } as DOMRect;
    });
    renderTree(fetchMock, "/projects/A/structure/chapters/1");
    await screen.findByDisplayValue("First");
    const handle = screen.getByRole("button", { name: "Reorder chapter First" });
    fireEvent.keyDown(handle, { key: " ", code: "Space", keyCode: 32 });
    await new Promise((resolve) => setTimeout(resolve, 0));
    fireEvent.keyDown(handle, { key: "ArrowDown", code: "ArrowDown", keyCode: 40 });
    fireEvent.keyDown(handle, { key: " ", code: "Space", keyCode: 32 });
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true));
    await waitFor(() => expect(screen.getByText("Version 3")).toBeInTheDocument());
    const user = userEvent.setup();
    await user.clear(screen.getByLabelText("Title"));
    await user.type(screen.getByLabelText("Title"), "Saved after reorder");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(true));
    const call = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({ expected_version: 3, title: "Saved after reorder" });
  });

  it("synchronizes a clean episode editor after episode reorder before saving", async () => {
    let swapped = false;
    const updatedEpisode = { ...episodeOne, title: "Saved episode", version: 5 };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/views/outline")) return new Response(JSON.stringify({ project_id: "A", data: episodeSiblingOutline(swapped) }));
      if (url.endsWith("/views/episodes/2")) return new Response(JSON.stringify({ project_id: "A", data: episodeView(swapped ? { ...episodeOne, position: 2, version: 5 } : episodeOne) }));
      if (url.endsWith("/episodes/2/reorder") && init?.method === "POST") {
        swapped = true;
        return new Response(JSON.stringify({ project_id: "A", data: [] }));
      }
      if (url.endsWith("/episodes/2") && init?.method === "PATCH") return new Response(JSON.stringify({ project_id: "A", data: updatedEpisode }));
      return new Response(JSON.stringify({ error: { code: "NOT_FOUND", message: "Not found" } }), { status: 404 });
    });
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
      const top = (this.textContent ?? "").includes("Episode three") ? 100 : 0;
      return { x: 0, y: top, top, left: 0, right: 300, bottom: top + 50, width: 300, height: 50, toJSON: () => ({}) } as DOMRect;
    });
    renderTree(fetchMock, "/projects/A/structure/episodes/2");
    await screen.findByDisplayValue("Episode one");
    const handle = screen.getByRole("button", { name: "Reorder episode Episode one" });
    fireEvent.keyDown(handle, { key: " ", code: "Space", keyCode: 32 });
    await new Promise((resolve) => setTimeout(resolve, 0));
    fireEvent.keyDown(handle, { key: "ArrowDown", code: "ArrowDown", keyCode: 40 });
    fireEvent.keyDown(handle, { key: " ", code: "Space", keyCode: 32 });
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true));
    await waitFor(() => expect(screen.getAllByText("Version 5")).toHaveLength(2));
    const user = userEvent.setup();
    await user.clear(screen.getByLabelText("Title"));
    await user.type(screen.getByLabelText("Title"), "Saved episode");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(true));
    const call = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({ expected_version: 5, title: "Saved episode" });
  });

  it("synchronizes a clean scene editor after scene reorder before saving", async () => {
    let swapped = false;
    const updatedScene = { ...sceneOne, title: "Saved scene", version: 7 };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/views/outline")) return new Response(JSON.stringify({ project_id: "A", data: sceneSiblingOutline(swapped) }));
      if (url.endsWith("/scenes/3") && !init?.method) return new Response(JSON.stringify({ project_id: "A", data: swapped ? { ...sceneOne, position: 2, version: 7 } : sceneOne }));
      if (url.endsWith("/scenes/3/reorder") && init?.method === "POST") {
        swapped = true;
        return new Response(JSON.stringify({ project_id: "A", data: [] }));
      }
      if (url.endsWith("/scenes/3") && init?.method === "PATCH") return new Response(JSON.stringify({ project_id: "A", data: updatedScene }));
      return new Response(JSON.stringify({ error: { code: "NOT_FOUND", message: "Not found" } }), { status: 404 });
    });
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
      const top = (this.textContent ?? "").includes("Scene two") ? 100 : 0;
      return { x: 0, y: top, top, left: 0, right: 300, bottom: top + 50, width: 300, height: 50, toJSON: () => ({}) } as DOMRect;
    });
    renderTree(fetchMock, "/projects/A/structure/scenes/3");
    await screen.findByDisplayValue("Scene one");
    const handle = screen.getByRole("button", { name: "Reorder scene Scene one" });
    fireEvent.keyDown(handle, { key: " ", code: "Space", keyCode: 32 });
    await new Promise((resolve) => setTimeout(resolve, 0));
    fireEvent.keyDown(handle, { key: "ArrowDown", code: "ArrowDown", keyCode: 40 });
    fireEvent.keyDown(handle, { key: " ", code: "Space", keyCode: 32 });
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true));
    await waitFor(() => expect(screen.getByText("Version 7")).toBeInTheDocument());
    const user = userEvent.setup();
    await user.clear(screen.getByLabelText("Title"));
    await user.type(screen.getByLabelText("Title"), "Saved scene");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(true));
    const call = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({ expected_version: 7, title: "Saved scene" });
  });

  it("preserves a dirty chapter editor and keeps its old version after reorder", async () => {
    let swapped = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/views/outline")) return new Response(JSON.stringify({ project_id: "A", data: outline(swapped) }));
      if (url.endsWith("/chapters/1/reorder") && init?.method === "POST") {
        swapped = true;
        return new Response(JSON.stringify({ project_id: "A", data: [] }));
      }
      if (url.endsWith("/chapters/1") && init?.method === "PATCH") return new Response(JSON.stringify({ error: { code: "VERSION_CONFLICT", message: "Changed", project_id: "A", details: { current_resource: { ...chapterOne, title: "Server title", version: 3 } } } }), { status: 409 });
      return new Response(JSON.stringify({ error: { code: "NOT_FOUND", message: "Not found" } }), { status: 404 });
    });
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
      const top = (this.textContent ?? "").includes("Second") ? 100 : 0;
      return { x: 0, y: top, top, left: 0, right: 300, bottom: top + 50, width: 300, height: 50, toJSON: () => ({}) } as DOMRect;
    });
    renderTree(fetchMock, "/projects/A/structure/chapters/1");
    const user = userEvent.setup();
    const title = await screen.findByLabelText("Title");
    await user.clear(title);
    await user.type(title, "Local title");
    const handle = screen.getByRole("button", { name: "Reorder chapter First" });
    fireEvent.keyDown(handle, { key: " ", code: "Space", keyCode: 32 });
    await new Promise((resolve) => setTimeout(resolve, 0));
    fireEvent.keyDown(handle, { key: "ArrowDown", code: "ArrowDown", keyCode: 40 });
    fireEvent.keyDown(handle, { key: " ", code: "Space", keyCode: 32 });
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true));
    expect(screen.getByDisplayValue("Local title")).toBeInTheDocument();
    expect(screen.getByText("Version 2")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "This chapter changed elsewhere" })).toBeInTheDocument());
    expect(JSON.parse(String(fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH")?.[1]?.body))).toMatchObject({ expected_version: 2, title: "Local title" });
  });
});
