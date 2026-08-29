import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
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
  return router;
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
    renderRoute("/projects/A/manuscript/2");
    expect(await screen.findByDisplayValue("First draft")).toBeInTheDocument();
    expect(screen.getByText(/Revision 1/)).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Preview revision 1/ }));
    expect(await screen.findByText("Read-only revision preview")).toBeInTheDocument();
    const body = screen.getByLabelText("Manuscript body");
    await user.clear(body);
    await user.type(body, "Second draft");
    await user.click(screen.getByRole("button", { name: "Save new revision" }));
    expect(await screen.findByText("Saved revision 2")).toBeInTheDocument();
  });
});
