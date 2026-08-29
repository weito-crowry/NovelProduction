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
const outline = {
  chapters: [{ chapter: { title: "Chapter" }, episodes: [1, 2, 3].map((id) => ({ episode: { id, title: `Episode ${id}` }, scenes: [] })) }],
};
const initial = { id: 20, work_id: 7, information_item_id: 1, episode_id: 1, version: 3, created_at: "2026-01-01", updated_at: "2026-01-01" };
const latest = { ...initial, episode_id: 3, version: 4, updated_at: "2026-02-01" };

function renderRoute(queryClient: QueryClient) {
  const router = createMemoryRouter(appRoutes, { initialEntries: ["/projects/A/information/1"] });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

function commonGet(url: string): Response | null {
  if (url.endsWith("/information?limit=50&offset=0")) return response({ project_id: "A", data: [item] });
  if (url.endsWith("/information/1")) return response({ project_id: "A", data: item });
  if (url.endsWith("/views/outline")) return response({ project_id: "A", data: outline });
  return null;
}

describe("D4 reader disclosure review regressions", () => {
  afterEach(() => vi.restoreAllMocks());

  it("saves with CAS, guards dirty selection, and invalidates the episode view family", async () => {
    const saved = { ...initial, episode_id: 2, version: 4 };
    const postBodies: unknown[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const common = commonGet(url);
      if (common) return common;
      if (url.endsWith("/information/1/reader-disclosure")) {
        if (init?.method === "PUT") {
          postBodies.push(JSON.parse(String(init.body)));
          return response({ project_id: "A", data: saved });
        }
        return response({ project_id: "A", data: initial });
      }
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries").mockResolvedValue(undefined);
    renderRoute(queryClient);

    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "Reader Disclosure" }));
    await screen.findByText("Episode 1");
    const episodeSelect = screen.getByLabelText("Disclosure episode");
    await user.selectOptions(episodeSelect, "2");
    vi.spyOn(window, "confirm").mockReturnValue(false);
    await user.selectOptions(episodeSelect, "1");
    expect(episodeSelect).toHaveValue("2");
    await user.click(screen.getByRole("button", { name: "Save disclosure" }));
    await waitFor(() => expect(postBodies).toHaveLength(1));
    expect(postBodies[0]).toEqual({ episode_id: 2, expected_version: 3 });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: projectQueryKeys.episodeViews("A") });
  });

  it("keeps local disclosure on conflict, then loads fallback latest without retrying", async () => {
    const postBodies: unknown[] = [];
    let disclosureReads = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const common = commonGet(url);
      if (common) return common;
      if (url.endsWith("/information/1/reader-disclosure")) {
        if (init?.method === "PUT") {
          postBodies.push(JSON.parse(String(init.body)));
          if (postBodies.length <= 2) return response({ error: { code: "VERSION_CONFLICT", message: "stale", details: postBodies.length === 1 ? { current_resource: latest } : {} } }, 409);
          return response({ project_id: "A", data: latest });
        }
        disclosureReads += 1;
        return response({ project_id: "A", data: disclosureReads === 1 ? initial : latest });
      }
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderRoute(queryClient);

    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "Reader Disclosure" }));
    const episodeSelect = await screen.findByLabelText("Disclosure episode");
    await user.selectOptions(episodeSelect, "2");
    await user.click(screen.getByRole("button", { name: "Save disclosure" }));
    await screen.findByRole("dialog");
    expect(postBodies).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Keep local edits" }));
    expect(episodeSelect).toHaveValue("2");
    expect(postBodies).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Save disclosure" }));
    await screen.findByRole("dialog");
    expect(postBodies[1]).toEqual({ episode_id: 2, expected_version: 3 });
    expect(postBodies).toHaveLength(2);
    await user.click(screen.getByRole("button", { name: "Load latest and discard local edits" }));
    await waitFor(() => expect(episodeSelect).toHaveValue("3"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(postBodies).toHaveLength(2);
    expect(disclosureReads).toBeGreaterThanOrEqual(2);
  });
});
