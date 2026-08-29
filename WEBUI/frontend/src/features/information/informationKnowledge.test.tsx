import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { projectQueryKeys } from "../../api/queryKeys";
import { appRoutes } from "../../app/routes";

function response(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const item = {
  id: 1,
  work_id: 7,
  statement: "A secret",
  truth_status: "true",
  authoring_guard: "",
  notes_json: "{}",
  canon_status: "draft",
  importance: 1,
  version: 1,
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
};
const episode = (id: number) => ({ id, title: `Episode ${id}` });
const outline = {
  chapters: [{ chapter: { title: "Chapter" }, episodes: [{ episode: episode(1), scenes: [] }, { episode: episode(2), scenes: [] }] }],
};
const character = { id: 10, display_name: "Ada" };
const inherited = {
  knowledge_state: "believes",
  event_episode_id: 1,
  event_version: 3,
  information_item: item,
};
const exactAtTwo = {
  id: 90,
  work_id: 7,
  character_id: 10,
  information_item_id: 1,
  episode_id: 2,
  knowledge_state: "believes",
  note: "inherited note",
  version: 3,
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
};

function renderRoute(queryClient: QueryClient, entry = "/projects/A/information/1") {
  const router = createMemoryRouter(appRoutes, { initialEntries: [entry] });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

function commonGet(url: string): Response | null {
  if (url.endsWith("/information/1")) return response({ project_id: "A", data: item });
  if (url.endsWith("/views/outline")) return response({ project_id: "A", data: outline });
  if (url.endsWith("/characters?limit=100&offset=0")) return response({ project_id: "A", data: [character] });
  return null;
}

describe("D4 character knowledge review regressions", () => {
  afterEach(() => vi.restoreAllMocks());

  it("distinguishes inherited effective knowledge from an exact null, then creates and updates with CAS", async () => {
    const saved = { ...exactAtTwo, knowledge_state: "knows", note: "new note", version: 4 };
    const updated = { ...saved, knowledge_state: "confirmed", version: 5 };
    const postBodies: unknown[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const common = commonGet(url);
      if (common) return common;
      if (url.endsWith("/characters/10/knowledge/1?episode_id=1")) return response({ project_id: "A", data: null });
      if (url.endsWith("/characters/10/knowledge?episode_id=1")) return response({ project_id: "A", data: [] });
      if (url.endsWith("/characters/10/knowledge/1?episode_id=2")) return response({ project_id: "A", data: null });
      if (url.endsWith("/characters/10/knowledge?episode_id=2")) return response({ project_id: "A", data: [inherited] });
      if (url.endsWith("/characters/10/knowledge/1") && init?.method === "PUT") {
        postBodies.push(JSON.parse(String(init.body)));
        return response({ project_id: "A", data: postBodies.length === 1 ? saved : updated });
      }
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries").mockResolvedValue(undefined);
    renderRoute(queryClient);

    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "Knowledge" }));
    await screen.findByText("No effective knowledge for this episode.");
    await user.selectOptions(screen.getByLabelText("Episode"), "2");
    expect(await screen.findByText(/Effective state: believes/)).toBeInTheDocument();
    expect(screen.getByText(/No event at the selected episode/)).toBeInTheDocument();

    const knowledgeState = screen.getByLabelText("Knowledge state");
    await user.selectOptions(knowledgeState, "knows");
    expect(knowledgeState).toHaveValue("knows");
    await user.type(screen.getByLabelText("Note"), "new note");
    expect(screen.getByRole("button", { name: "Save knowledge" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Save knowledge" }));
    await waitFor(() => expect(postBodies).toHaveLength(1));
    expect(postBodies[0]).toEqual({ episode_id: 2, knowledge_state: "knows", note: "new note" });

    await user.selectOptions(screen.getByLabelText("Knowledge state"), "confirmed");
    await user.click(screen.getByRole("button", { name: "Save knowledge" }));
    await waitFor(() => expect(postBodies).toHaveLength(2));
    expect(postBodies[1]).toEqual({ episode_id: 2, knowledge_state: "confirmed", note: "new note", expected_version: 4 });
    expect(queryClient.getQueryData(projectQueryKeys.characterKnowledgeExact("A", 10, 1, 2))).toEqual(updated);
    const invalidated = invalidateSpy.mock.calls.flatMap(([filters]) => filters?.queryKey ? [filters.queryKey] : []);
    expect(invalidated).toContainEqual(projectQueryKeys.characterKnowledgeFamily("A", 10));
    expect(invalidated).toContainEqual(projectQueryKeys.episodeViews("A"));
  });

  it("keeps local knowledge on conflict and loads latest without retrying", async () => {
    const latest = { ...exactAtTwo, knowledge_state: "knows", note: "latest", version: 4 };
    const postBodies: unknown[] = [];
    let conflictCount = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const common = commonGet(url);
      if (common) return common;
      if (url.endsWith("/characters/10/knowledge/1?episode_id=1")) return response({ project_id: "A", data: null });
      if (url.endsWith("/characters/10/knowledge?episode_id=1")) return response({ project_id: "A", data: [] });
      if (url.endsWith("/characters/10/knowledge/1?episode_id=2")) return response({ project_id: "A", data: conflictCount > 0 ? latest : exactAtTwo });
      if (url.endsWith("/characters/10/knowledge?episode_id=2")) return response({ project_id: "A", data: [inherited] });
      if (url.endsWith("/characters/10/knowledge/1") && init?.method === "PUT") {
        postBodies.push(JSON.parse(String(init.body)));
        conflictCount += 1;
        return response({ error: { code: "VERSION_CONFLICT", message: "stale", details: { current_resource: latest } } }, 409);
      }
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries").mockResolvedValue(undefined);
    renderRoute(queryClient);

    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "Knowledge" }));
    await screen.findByText("No effective knowledge for this episode.");
    await user.selectOptions(screen.getByLabelText("Episode"), "2");
    await screen.findByText(/Effective state: believes/);
    await user.selectOptions(screen.getByLabelText("Knowledge state"), "confirmed");
    await user.click(screen.getByRole("button", { name: "Save knowledge" }));
    await screen.findByRole("dialog");
    expect(postBodies).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Keep local edits" }));
    expect(screen.getByLabelText("Knowledge state")).toHaveValue("confirmed");
    expect(postBodies).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Save knowledge" }));
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: "Load latest and discard local edits" }));
    await waitFor(() => expect(screen.getByLabelText("Knowledge state")).toHaveValue("knows"));
    expect(screen.getByLabelText("Note")).toHaveValue("latest");
    expect(postBodies).toHaveLength(2);
    expect(queryClient.getQueryData(projectQueryKeys.characterKnowledgeExact("A", 10, 1, 2))).toEqual(latest);
    const invalidated = invalidateSpy.mock.calls.flatMap(([filters]) => filters?.queryKey ? [filters.queryKey] : []);
    expect(invalidated).toContainEqual(projectQueryKeys.characterKnowledgeFamily("A", 10));
    expect(invalidated).toContainEqual(projectQueryKeys.episodeViews("A"));
  });
});
