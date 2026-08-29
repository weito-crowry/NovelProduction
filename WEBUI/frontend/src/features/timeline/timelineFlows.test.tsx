import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { appRoutes } from "../../app/routes";
import type { TimelineEventRecord } from "../../api/types";

function response(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
}

function event(id: number, title = `Event ${id}`): TimelineEventRecord {
  return { id, work_id: 1, event_key: `event-${id}`, time_start: "2104-01-01", time_end: "2104-01-01", date_precision: "day", date_display: "2104-01-01", title, description: "", category: "general", location_world_fact_id: null, cause_summary: "", consequence_summary: "", canon_status: "draft", importance: 0, version: 1, created_at: "", updated_at: "", participants: [] };
}

function renderRoute(initialEntry: string) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [initialEntry] });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={queryClient}><RouterProvider router={router} /></QueryClientProvider>);
  return router;
}

describe("D3 timeline flows", () => {
  afterEach(() => vi.restoreAllMocks());

  it("separates browse, search, and range modes", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/timeline/events?limit=50&offset=0")) return response({ project_id: "A", data: [event(1)] });
      if (url.includes("/timeline/events/search?query=%E7%81%AB%E5%B1%B1&limit=50")) return response({ project_id: "A", data: [event(2, "Search event")] });
      if (url.includes("/timeline/range?start=2104-01-01&end=2104-12-31&limit=50")) return response({ project_id: "A", data: [event(3, "Range event")] });
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute("/projects/A/timeline");
    expect(await screen.findByText("Event 1")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("radio", { name: "Search" }));
    await user.type(screen.getByRole("searchbox", { name: "Search timeline events" }), "火山");
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText("Search event")).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "Range" }));
    await user.type(screen.getByLabelText("Range start"), "2104-01-01");
    await user.type(screen.getByLabelText("Range end"), "2104-12-31");
    await user.click(screen.getByRole("button", { name: "Load range" }));
    expect(await screen.findByText("Range event")).toBeInTheDocument();
  });

  it("creates an event with event_date and participants, then navigates to detail", async () => {
    const created = event(9, "Created event");
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/timeline/events?limit=50&offset=0")) return response({ project_id: "A", data: [] });
      if (url.endsWith("/timeline/events") && init?.method === "POST") {
        expect(JSON.parse(String(init.body))).toMatchObject({ title: "Created event", event_date: "2126年春頃", participants: [{ character_id: 1, role: "observer" }] });
        return response({ project_id: "A", data: created }, 201);
      }
      if (url.endsWith("/timeline/events/9")) return response({ project_id: "A", data: created });
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    const router = renderRoute("/projects/A/timeline");
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Timeline" });
    await user.click(screen.getByRole("button", { name: "Add timeline event" }));
    await user.type(screen.getByLabelText("Title"), "Created event");
    await user.type(screen.getByLabelText("Event date"), "2126年春頃");
    await user.type(screen.getByLabelText("Participant character ID"), "1");
    await user.type(screen.getByLabelText("Participant role"), "observer");
    await user.click(screen.getByRole("button", { name: "Create timeline event" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/projects/A/timeline/9"));
  });

  it("uses a separate Move action with expected_version and does not put date in normal Save", async () => {
    const original = event(1);
    const moved = { ...original, date_display: "2104-02-01", time_start: "2104-02-01", time_end: "2104-02-01", version: 2 };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/timeline/events/1") && init?.method === "PATCH") {
        expect(JSON.parse(String(init.body))).toEqual({ expected_version: 1, title: "Changed" });
        return response({ project_id: "A", data: { ...original, title: "Changed", version: 2 } });
      }
      if (url.endsWith("/timeline/events/1/move") && init?.method === "POST") {
        expect(JSON.parse(String(init.body))).toEqual({ expected_version: 2, new_date: "2104-02-01", reason: "move" });
        return response({ project_id: "A", data: moved });
      }
      if (url.endsWith("/timeline/events/1")) return response({ project_id: "A", data: original });
      if (url.includes("/timeline/relations?")) return response({ project_id: "A", data: [] });
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute("/projects/A/timeline/1");
    const user = userEvent.setup();
    const title = await screen.findByLabelText("Title");
    await user.clear(title); await user.type(title, "Changed");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Saved")).toBeInTheDocument();
    await user.type(screen.getByLabelText("New date"), "2104-02-01");
    await user.type(screen.getByLabelText("Move reason"), "move");
    await user.click(screen.getByRole("button", { name: "Move event" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true));
  });

  it("does not request an invalid event ID", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderRoute("/projects/A/timeline/-1");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
