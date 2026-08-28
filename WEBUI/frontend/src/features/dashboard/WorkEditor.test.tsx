import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { appRoutes } from "../../app/routes";
import type { DashboardView, WorkRecord } from "../../api/types";

const initialWork: WorkRecord = {
  id: 1,
  slug: "alpha",
  working_title: "Alpha",
  genre: "literary",
  premise: "A premise",
  themes_json: '{"theme":"winter"}',
  description: "A description",
  production_status: "planning",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  version: 3,
};
const latestWork: WorkRecord = {
  ...initialWork,
  working_title: "Latest database title",
  genre: "mystery",
  version: 4,
};

function response(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function dashboard(): DashboardView {
  return {
    work: initialWork,
    chapter_count: 1,
    episode_count: 2,
    scene_count: 3,
  };
}

function installWorkFetchMock(options: {
  conflict?: "current" | "missing";
  updatedWork?: WorkRecord;
} = {}) {
  let workResponse = initialWork;
  let workReads = 0;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/v1/projects/A/views/dashboard") {
      return response({ project_id: "A", data: dashboard() });
    }
    if (url === "/api/v1/projects/A/work" && init?.method === "PATCH") {
      if (options.conflict) {
        const details =
          options.conflict === "current"
            ? { current_resource: latestWork }
            : {};
        return response(
          {
            error: {
              code: "VERSION_CONFLICT",
              message: "The resource changed.",
              project_id: "A",
              details,
            },
          },
          409,
        );
      }
      workResponse = options.updatedWork ?? {
        ...initialWork,
        working_title: "Alpha saved",
        version: 4,
      };
      return response({ project_id: "A", data: workResponse });
    }
    if (url === "/api/v1/projects/A/work") {
      workReads += 1;
      const readResponse =
        options.conflict === "missing" && workReads > 1 ? latestWork : workResponse;
      return response({ project_id: "A", data: readResponse });
    }
    return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderWork() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(appRoutes, {
    initialEntries: ["/projects/A/dashboard"],
  });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

function patchRequest(fetchMock: ReturnType<typeof vi.fn>) {
  const call = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
  expect(call).toBeDefined();
  return JSON.parse(String(call?.[1]?.body)) as Record<string, unknown>;
}

describe("Work editor", () => {
  afterEach(() => vi.restoreAllMocks());

  it("keeps edits local until explicit Save and sends only changed fields", async () => {
    const fetchMock = installWorkFetchMock();
    renderWork();
    const user = userEvent.setup();

    const genre = await screen.findByLabelText("Genre");
    await user.clear(genre);
    await user.type(genre, "mystery");

    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(false);

    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(true),
    );

    expect(patchRequest(fetchMock)).toEqual({
      working_title: "Alpha",
      expected_version: 3,
      genre: "mystery",
    });
    expect(screen.queryByText("Unsaved changes")).not.toBeInTheDocument();
  });

  it("includes required working_title, expected_version, and changed title only", async () => {
    const fetchMock = installWorkFetchMock();
    renderWork();
    const user = userEvent.setup();
    const title = await screen.findByLabelText("Working title");
    await user.clear(title);
    await user.type(title, "Alpha edited");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(true),
    );
    expect(patchRequest(fetchMock)).toEqual({
      working_title: "Alpha edited",
      expected_version: 3,
    });
  });

  it("rejects invalid themes JSON without sending a request", async () => {
    const fetchMock = installWorkFetchMock();
    renderWork();
    const user = userEvent.setup();
    const themes = await screen.findByLabelText("Themes JSON");
    fireEvent.change(themes, { target: { value: '{"broken":' } });
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(screen.getByRole("alert")).toHaveTextContent("Enter valid JSON.");
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(false);
  });

  it("replaces the baseline only after a successful save and invalidates the view", async () => {
    const fetchMock = installWorkFetchMock({
      updatedWork: { ...initialWork, working_title: "Saved title", version: 4 },
    });
    renderWork();
    const user = userEvent.setup();
    const title = await screen.findByLabelText("Working title");
    await user.clear(title);
    await user.type(title, "Saved title");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(screen.getByText("Saved")).toBeInTheDocument());
    expect(screen.queryByText("Unsaved changes")).not.toBeInTheDocument();
    expect(screen.getByDisplayValue("Saved title")).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.filter(([url, init]) =>
        String(url).endsWith("/work") && (!init || init.method === undefined),
      ).length,
    ).toBeGreaterThanOrEqual(2);
  });

  it("preserves local edits on conflict and never automatically retries", async () => {
    const fetchMock = installWorkFetchMock({ conflict: "current" });
    renderWork();
    const user = userEvent.setup();
    const title = await screen.findByLabelText("Working title");
    await user.clear(title);
    await user.type(title, "My local edit");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText("Local unsaved edits")).toBeInTheDocument();
    expect(screen.getByText("Latest database resource")).toBeInTheDocument();
    expect(screen.getByText(/Latest database title/)).toBeInTheDocument();
    expect(screen.getByDisplayValue("My local edit")).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH")).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Keep local edits" }));
    expect(screen.getByDisplayValue("My local edit")).toBeInTheDocument();
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
  });

  it("refetches latest read-only data when conflict details omit current_resource", async () => {
    const fetchMock = installWorkFetchMock({ conflict: "missing" });
    renderWork();
    const user = userEvent.setup();
    const title = await screen.findByLabelText("Working title");
    await user.clear(title);
    await user.type(title, "My local edit");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText(/Latest database title/)).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.filter(([url, init]) =>
        String(url).endsWith("/work") && (!init || init.method === undefined),
      ).length,
    ).toBeGreaterThanOrEqual(2);
  });

  it("can discard local edits and load the latest conflict resource", async () => {
    installWorkFetchMock({ conflict: "current" });
    renderWork();
    const user = userEvent.setup();
    const title = await screen.findByLabelText("Working title");
    await user.clear(title);
    await user.type(title, "My local edit");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText(/Latest database title/);

    await user.click(screen.getByRole("button", { name: "Load latest and discard local edits" }));
    expect(screen.getByDisplayValue("Latest database title")).toBeInTheDocument();
    expect(screen.queryByText("Unsaved changes")).not.toBeInTheDocument();
  });

  it("guards project navigation and browser unload while edits are dirty", async () => {
    installWorkFetchMock();
    renderWork();
    const user = userEvent.setup();
    const title = await screen.findByLabelText("Working title");
    await user.clear(title);
    await user.type(title, "My local edit");

    const unload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(true);

    await user.click(screen.getByRole("link", { name: "All projects" }));
    expect(screen.getByRole("heading", { name: "Leave without saving?" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Stay" }));
    expect(screen.getByDisplayValue("My local edit")).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "All projects" }));
    await user.click(screen.getByRole("button", { name: "Discard and leave" }));
    expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
  });
});
