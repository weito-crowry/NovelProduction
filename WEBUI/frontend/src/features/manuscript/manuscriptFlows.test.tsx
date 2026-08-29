import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { appRoutes } from "../../app/routes";

function response(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
}

const episode = { id: 2, work_id: 7, chapter_id: 1, position: 1, title: "Episode", summary: "", purpose: "", foreshadowing_notes_json: "[]", canon_status: "draft", production_status: "planned", version: 1, created_at: "", updated_at: "" };
const outline = { chapters: [{ chapter: { id: 1, work_id: 7, position: 1, title: "Chapter", summary: "", purpose: "", canon_status: "draft", production_status: "planned", version: 1, created_at: "", updated_at: "" }, episodes: [{ episode, scenes: [] }] }] };
const draft = { id: 7, work_id: 7, episode_id: 2, revision: 1, parent_draft_id: null, body: "First draft", source_agent: "other", change_summary: "initial", content_hash: "hash", created_at: "2026-01-01" };

function renderRoute(initialEntry: string) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [initialEntry] });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={queryClient}><RouterProvider router={router} /></QueryClientProvider>);
  return { router, queryClient };
}

describe("D4 manuscript flows", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads latest/history, previews a revision, and appends a new webui revision", async () => {
    const saved = { ...draft, id: 8, revision: 2, parent_draft_id: 7, body: "Second draft", source_agent: "webui" };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/views/outline")) return response({ project_id: "A", data: outline });
      if (url.endsWith("/episodes/2/draft") && !url.includes("revision")) return response({ project_id: "A", data: draft });
      if (url.includes("/episodes/2/draft?revision=1")) return response({ project_id: "A", data: draft });
      if (url.endsWith("/episodes/2/drafts?limit=20")) return response({ project_id: "A", data: [{ ...draft, body_chars: 11 }] });
      if (url.endsWith("/episodes/2/drafts") && init?.method === "POST") {
        expect(JSON.parse(String(init.body))).toEqual({ body: "Second draft", expected_parent_draft_id: 7, source_agent: "webui", change_summary: "" });
        return response({ project_id: "A", data: saved }, 201);
      }
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    const { queryClient } = renderRoute("/projects/A/manuscript/2");
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries").mockResolvedValue(undefined);
    expect(await screen.findByDisplayValue("First draft")).toBeInTheDocument();
    expect(screen.getByText(/Revision 1/)).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Preview revision 1/ }));
    expect(await screen.findByText("Read-only revision preview")).toBeInTheDocument();
    const body = screen.getByLabelText("Manuscript body");
    await user.clear(body);
    await user.type(body, "Second draft");
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save new revision" }));
    expect(await screen.findByText("Saved revision 2")).toBeInTheDocument();
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["project", "A", "draft-history", 2, 20] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["project", "A", "episode-view"] });
  });

  it("keeps local text without retrying, adopts fallback latest, and uses it on the next explicit save", async () => {
    const remote = { ...draft, id: 8, revision: 2, parent_draft_id: 7, body: "Remote draft", source_agent: "other" };
    const fallbackLatest = { ...draft, id: 9, revision: 3, parent_draft_id: 8, body: "Fallback latest", source_agent: "other" };
    const final = { ...draft, id: 10, revision: 4, parent_draft_id: 9, body: "Final draft", source_agent: "webui" };
    let latestReads = 0;
    const postBodies: unknown[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/views/outline")) return response({ project_id: "A", data: outline });
      if (url.endsWith("/episodes/2/draft") && !init?.method) {
        latestReads += 1;
        return response({ project_id: "A", data: latestReads === 1 ? draft : fallbackLatest });
      }
      if (url.endsWith("/episodes/2/drafts?limit=20")) return response({ project_id: "A", data: [] });
      if (url.endsWith("/episodes/2/drafts") && init?.method === "POST") {
        postBodies.push(JSON.parse(String(init.body)));
        if (postBodies.length === 1) return response({ error: { code: "VERSION_CONFLICT", message: "stale", details: { current_resource: remote } } }, 409);
        if (postBodies.length === 2) return response({ error: { code: "VERSION_CONFLICT", message: "stale", details: {} } }, 409);
        return response({ project_id: "A", data: final }, 201);
      }
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    const { queryClient } = renderRoute("/projects/A/manuscript/2");
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries").mockResolvedValue(undefined);
    const user = userEvent.setup();
    const body = await screen.findByDisplayValue("First draft");
    await user.clear(body);
    await user.type(body, "Local draft");
    await user.click(screen.getByRole("button", { name: "Save new revision" }));
    await screen.findByRole("dialog");
    expect(postBodies).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Keep local and use latest as parent" }));
    expect(screen.getByLabelText("Manuscript body")).toHaveValue("Local draft");
    expect(postBodies).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Save new revision" }));
    await screen.findByRole("dialog");
    expect(postBodies[1]).toEqual({ body: "Local draft", expected_parent_draft_id: 8, source_agent: "webui", change_summary: "" });
    expect(latestReads).toBe(2);
    expect(postBodies).toHaveLength(2);

    await user.click(screen.getByRole("button", { name: "Load latest and discard local edits" }));
    await waitFor(() => expect(screen.getByLabelText("Manuscript body")).toHaveValue("Fallback latest"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(postBodies).toHaveLength(2);

    await user.clear(screen.getByLabelText("Manuscript body"));
    await user.type(screen.getByLabelText("Manuscript body"), "Final draft");
    await user.click(screen.getByRole("button", { name: "Save new revision" }));
    await screen.findByText("Saved revision 4");
    expect(postBodies[2]).toEqual({ body: "Final draft", expected_parent_draft_id: 9, source_agent: "webui", change_summary: "" });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["project", "A", "episode-view"] });
  });
});
