import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { appRoutes } from "../../app/routes";

function response(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const outline = {
  chapters: [
    {
      chapter: {
        id: 1,
        work_id: 7,
        position: 1,
        title: "Chapter One",
        summary: "Summary",
        purpose: "Purpose",
        canon_status: "draft",
        production_status: "planned",
        version: 1,
        created_at: "2026-01-01",
        updated_at: "2026-01-01",
      },
      episodes: [
        {
          episode: {
            id: 2,
            work_id: 7,
            chapter_id: 1,
            position: 1,
            title: "Episode One",
            summary: "Summary",
            purpose: "Purpose",
            foreshadowing_notes_json: "{}",
            canon_status: "draft",
            production_status: "planned",
            version: 1,
            created_at: "2026-01-01",
            updated_at: "2026-01-01",
          },
          scenes: [
            {
              id: 3,
              work_id: 7,
              episode_id: 2,
              position: 1,
              title: "Scene One",
              summary: "Summary",
              purpose: "Purpose",
              canon_status: "draft",
              production_status: "planned",
              version: 1,
              created_at: "2026-01-01",
              updated_at: "2026-01-01",
            },
          ],
        },
      ],
    },
  ],
};

function renderRoute(initialEntry: string) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [initialEntry] });
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

describe("D2 structure routing and tree", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders chapter, episode, and scene nesting from the outline view", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input) === "/api/v1/projects/A/views/outline") {
        return response({ project_id: "A", data: outline });
      }
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderRoute("/projects/A/structure");

    expect(await screen.findByText("Chapter One")).toBeInTheDocument();
    expect(screen.getByText("Episode One")).toBeInTheDocument();
    expect(screen.getByText("Scene One")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/projects/A/views/outline",
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
  });

  it("does not request an API resource for an invalid entity route id", async () => {
    const fetchMock = vi.fn(async () =>
      response({ error: { code: "UNEXPECTED", message: "Unexpected request" } }, 500),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderRoute("/projects/A/structure/chapters/not-a-number");

    expect(await screen.findByRole("heading", { name: /not found/i })).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).not.toHaveBeenCalled());
  });
});
