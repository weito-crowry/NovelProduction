import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { appRoutes } from "../../app/routes";

function response(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
}

const decision = {
  id: 1,
  summary: "Set information_item 4 canon status to canon",
  reason: "approved",
  changes: [{ entity_type: "information_item", entity_id: 4, action: "status_changed", before_payload: { canon_status: "draft" }, after_payload: { canon_status: "canon" } }],
};

function renderRoute(initialEntry: string) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [initialEntry] });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={queryClient}><RouterProvider router={router} /></QueryClientProvider>);
  return router;
}

describe("D4 canon flows", () => {
  afterEach(() => vi.restoreAllMocks());

  it("browses, loads more, searches, and displays decision changes", async () => {
    const second = { ...decision, id: 2, summary: "Second decision" };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/canon/decisions?limit=50&offset=0"))
        return response({ project_id: "A", data: [decision, ...Array.from({ length: 49 }, (_, index) => ({ ...decision, id: index + 3, summary: `Decision ${index + 3}` }))] });
      if (url.endsWith("/canon/decisions?limit=50&offset=50")) return response({ project_id: "A", data: [second] });
      if (url.includes("/canon/decisions/search?query=approved&limit=50")) return response({ project_id: "A", data: [decision] });
      if (url.endsWith("/canon/decisions/1")) return response({ project_id: "A", data: decision });
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute("/projects/A/canon");
    expect(await screen.findByText(decision.summary)).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText("Second decision")).toBeInTheDocument();
    await user.type(screen.getByRole("searchbox", { name: "Search canon decisions" }), "approved");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await user.click(await screen.findByRole("link", { name: /Set information_item 4 canon status/ }));
    expect(await screen.findByText("status_changed")).toBeInTheDocument();
  });

  it("renders the empty state after an empty browse without querying search", async () => {
    const requests: Array<{ url: string; method: string | undefined }> = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      requests.push({ url, method: init?.method });
      if (url.endsWith("/canon/decisions?limit=50&offset=0")) return response({ project_id: "A", data: [] });
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute("/projects/A/canon");

    expect(await screen.findByText("No canon decisions yet.")).toBeInTheDocument();
    expect(screen.queryByRole("status", { name: "Loading canon history…" })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(requests).toEqual([{ url: "/api/v1/projects/A/canon/decisions?limit=50&offset=0", method: undefined }]);
  });
});
