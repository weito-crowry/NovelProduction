import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { appRoutes } from "../../app/routes";
import type { OutlineView } from "../../api/types";

const chapterOne = { id: 1, work_id: 7, position: 1, title: "First", summary: "", purpose: "", canon_status: "draft", production_status: "planned", version: 2, created_at: "", updated_at: "" };
const chapterTwo = { id: 4, work_id: 7, position: 2, title: "Second", summary: "", purpose: "", canon_status: "draft", production_status: "planned", version: 3, created_at: "", updated_at: "" };
const episodeOne = { id: 2, work_id: 7, chapter_id: 1, position: 1, title: "Episode one", summary: "", purpose: "", foreshadowing_notes_json: "{}", canon_status: "draft", production_status: "planned", version: 4, created_at: "", updated_at: "" };
const episodeTwo = { id: 5, work_id: 7, chapter_id: 4, position: 1, title: "Episode two", summary: "", purpose: "", foreshadowing_notes_json: "{}", canon_status: "draft", production_status: "planned", version: 5, created_at: "", updated_at: "" };

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

function renderTree(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const router = createMemoryRouter(appRoutes, { initialEntries: ["/projects/A/structure"] });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={queryClient}><RouterProvider router={router} /></QueryClientProvider>);
}

describe("structure reorder", () => {
  afterEach(() => vi.restoreAllMocks());

  it("uses keyboard drag to send a one-based chapter target and current version, then refetches canonical order", async () => {
    let swapped = false;
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
    renderTree(fetchMock);
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
});
