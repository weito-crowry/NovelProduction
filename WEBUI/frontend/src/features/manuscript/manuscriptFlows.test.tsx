import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { appRoutes } from "../../app/routes";
import type { DraftDocumentRead, DraftExport, DraftHistoryItem, DraftWebRead, NovelDocument } from "../../api/types";

function response(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
}

const episode = { id: 2, work_id: 7, chapter_id: 1, position: 1, title: "Episode", summary: "", purpose: "", foreshadowing_notes_json: "[]", canon_status: "draft", production_status: "planned", version: 1, created_at: "", updated_at: "" };
const outline = { chapters: [{ chapter: { id: 1, work_id: 7, position: 1, title: "Chapter", summary: "", purpose: "", canon_status: "draft", production_status: "planned", version: 1, created_at: "", updated_at: "" }, episodes: [{ episode, scenes: [] }] }] };
const blockId = "blk_0123456789abcdef0123456789abcdef";

function documentRead(revision: number, id = revision, blocks: NovelDocument["blocks"] = [{
  id: blockId,
  type: "dialogue",
  html: "<p>canonical</p>",
  attrs: { scene_id: 3, speaker_character_id: 9 },
  annotations: { emotions: ["焦り"], mood: "tense", "analysis-bundle": { nested: [1, true] } },
}]): DraftDocumentRead {
  return { id, work_id: 7, episode_id: 2, revision, parent_draft_id: revision > 1 ? id - 1 : null, format: "document", content: { schema_version: 1, type: "novel_document", blocks }, source_agent: "agent", change_summary: `revision ${revision}`, created_at: `2026-01-0${revision}` };
}

function webRead(document: DraftDocumentRead, content = `<p id="${blockId}">WEB revision ${document.revision}</p>`): DraftWebRead {
  return { ...document, format: "web", content };
}

function historyItem(revision: number): DraftHistoryItem {
  return { id: revision, episode_id: 2, revision, parent_draft_id: revision > 1 ? revision - 1 : null, source_agent: "agent", change_summary: `revision ${revision}`, created_at: `2026-01-0${revision}` };
}

function renderRoute(initialEntry = "/projects/A/manuscript/2") {
  const router = createMemoryRouter(appRoutes, { initialEntries: [initialEntry] });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={queryClient}><RouterProvider router={router} /></QueryClientProvider>);
  return { router, queryClient };
}

function routeFor(
  latest: DraftDocumentRead | null,
  history: DraftHistoryItem[] = latest ? [historyItem(latest.revision)] : [],
  webByRevision: Record<number, DraftWebRead> = latest ? { [latest.revision]: webRead(latest) } : {},
  exportWarnings: DraftExport["warnings"] = [],
) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://test");
    if (url.pathname.endsWith("/views/outline")) return response({ project_id: "A", data: outline });
    if (url.pathname.endsWith("/episodes/2/draft")) {
      if (url.searchParams.get("format") === "document") {
        const revision = url.searchParams.get("revision");
        return response({ project_id: "A", data: revision ? (Number(revision) === latest?.revision ? latest : documentRead(Number(revision))) : latest });
      }
      if (url.searchParams.get("format") === "web") {
        const revision = Number(url.searchParams.get("revision"));
        return response({ project_id: "A", data: webByRevision[revision] ?? webRead(documentRead(revision)) });
      }
    }
    if (url.pathname.endsWith("/drafts") && init?.method !== "POST") return response({ project_id: "A", data: history });
    if (url.pathname.endsWith("/draft/export")) return response({ project_id: "A", data: { format: "narou", media_type: "text/plain", content: "export", suggested_filename: "episode-2-r1.txt", warnings: exportWarnings } });
    return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
  });
}

describe("Phase E manuscript read flows", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("uses the latest Document as the anchor, pins WEB to it, and exposes read-only inspection", async () => {
    const latest = documentRead(2);
    const revisionOne = documentRead(1, 1, [{ ...latest.content.blocks[0], html: "<p>old</p>" }]);
    const noteBlock = { ...latest.content.blocks[0], id: "blk_fedcba9876543210fedcba9876543210", type: "note" as const, html: "<p>Production note</p>" };
    const latestWithNote = { ...latest, content: { ...latest.content, blocks: [...latest.content.blocks, noteBlock] } };
    const fetchMock = routeFor(latestWithNote, [historyItem(2), historyItem(1)], { 1: webRead(revisionOne, `<p id="${blockId}">WEB revision 1</p>`), 2: webRead(latestWithNote, `<p id="${blockId}">WEB revision 2</p><p id="${noteBlock.id}">Production note</p>`) });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute();

    expect(await screen.findByText("Latest revision 2")).toBeInTheDocument();
    expect(screen.getByText("WEB revision 2")).toBeInTheDocument();
    expect(screen.queryByLabelText("Manuscript body")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show Raw Document" })).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, init]) => init?.cache === "no-store")).toBe(true);

    const user = userEvent.setup();
    await user.click(screen.getByLabelText("Show production notes"));
    expect(await screen.findByText("Production note")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Block selector"), blockId);
    expect(screen.getByText("scene_id")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("tense")).toBeInTheDocument();
    expect(screen.queryByText("analysis-bundle")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show Raw annotations JSON" }));
    expect(screen.getByText(/nested/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show Raw Document" }));
    expect(screen.getByText(/"novel_document"/)).toBeInTheDocument();
  });

  it("clears a selected note when production notes are turned off and does not restore it", async () => {
    const latest = documentRead(2);
    const noteBlock = { ...latest.content.blocks[0], id: "blk_fedcba9876543210fedcba9876543210", type: "note" as const, html: "<p>Production note</p>" };
    const latestWithNote = { ...latest, content: { ...latest.content, blocks: [...latest.content.blocks, noteBlock] } };
    vi.stubGlobal("fetch", routeFor(latestWithNote, [historyItem(2)], { 2: webRead(latestWithNote, `<p id="${noteBlock.id}">Production note</p>`) }));
    renderRoute();
    const user = userEvent.setup();

    await screen.findByText("Latest revision 2");
    await user.click(screen.getByLabelText("Show production notes"));
    await user.selectOptions(screen.getByLabelText("Block selector"), noteBlock.id);
    expect(screen.getByText("Block ID")).toBeInTheDocument();
    expect(screen.getByText(noteBlock.id)).toBeInTheDocument();

    await user.click(screen.getByLabelText("Show production notes"));
    expect(screen.getByLabelText("Block selector")).toHaveValue("");
    expect(screen.getByText("Select a block to inspect its canonical metadata.")).toBeInTheDocument();

    await user.click(screen.getByLabelText("Show production notes"));
    expect(screen.getByLabelText("Block selector")).toHaveValue("");
    expect(screen.getByText("Select a block to inspect its canonical metadata.")).toBeInTheDocument();
  });

  it("downloads Narou export while displaying non-fatal warnings and cleaning up its object URL", async () => {
    const latest = documentRead(1, 1);
    const warning = { code: "NAROU_RUBY_DEGRADED", message: "ruby was degraded for Narou", block_id: blockId };
    const fetchMock = routeFor(latest, [historyItem(1)], { 1: webRead(latest) }, [warning]);
    vi.stubGlobal("fetch", fetchMock);
    const NativeURL = URL;
    const createObjectURL = vi.fn(() => "blob:narou");
    const revokeObjectURL = vi.fn();
    class TestURL extends NativeURL {}
    Object.assign(TestURL, { createObjectURL, revokeObjectURL });
    vi.stubGlobal("URL", TestURL);
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    renderRoute();
    const user = userEvent.setup();

    await screen.findByText("Latest revision 1");
    await user.click(screen.getByRole("button", { name: "Download Narou export" }));

    expect(screen.getByRole("listitem")).toHaveTextContent(warning.message);
    expect(screen.getByText(warning.code)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/draft/export?revision=1&format=narou"))).toBe(true);
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(anchorClick).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:narou");
  });

  it("distinguishes no draft from an existing empty canonical revision", async () => {
    vi.stubGlobal("fetch", routeFor(null));
    renderRoute();
    expect(await screen.findByText("No manuscript draft yet.")).toBeInTheDocument();
    expect(screen.queryByText("Manuscript reader")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Restore/ })).not.toBeInTheDocument();

    cleanup();
    vi.restoreAllMocks();
    const empty = documentRead(1, 1, []);
    vi.stubGlobal("fetch", routeFor(empty, [historyItem(1)], { 1: webRead(empty, "") }));
    renderRoute();
    expect(await screen.findByText("This manuscript revision is empty.")).toBeInTheDocument();
    expect(screen.getByText("Latest revision 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show Raw Document" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download Narou export" })).toBeInTheDocument();
  });

  it("switches historical snapshots through Document then explicit WEB and can view latest", async () => {
    const latest = documentRead(2);
    const revisionOne = documentRead(1, 1, [{ ...latest.content.blocks[0], html: "<p>old</p>" }]);
    const fetchMock = routeFor(latest, [historyItem(2), historyItem(1)], { 1: webRead(revisionOne, `<p id="${blockId}">WEB revision 1</p>`), 2: webRead(latest) });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute();
    const user = userEvent.setup();
    await screen.findByText("Latest revision 2");
    await user.click(screen.getByRole("button", { name: "View revision 1" }));
    expect(await screen.findByText("Historical revision 1")).toBeInTheDocument();
    expect(screen.getByText("WEB revision 1")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "View latest" }));
    expect(await screen.findByText("Latest revision 2")).toBeInTheDocument();
    expect(screen.getByText("WEB revision 2")).toBeInTheDocument();
    const webUrls = fetchMock.mock.calls.map(([input]) => String(input)).filter((url) => url.includes("format=web"));
    expect(webUrls.every((url) => url.includes("revision="))).toBe(true);
  });

  it("restores with the directly-fetched latest parent and confirms a newer post-write latest", async () => {
    const initial = documentRead(3, 30);
    const historical = documentRead(2, 20);
    const freshBeforeRestore = documentRead(4, 40);
    const actualLatest = documentRead(6, 60);
    let freshReads = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://test");
      if (url.pathname.endsWith("/views/outline")) return response({ project_id: "A", data: outline });
      if (url.pathname.endsWith("/episodes/2/draft")) {
        if (url.searchParams.get("format") === "document") {
          if (url.searchParams.get("revision") === "2") return response({ project_id: "A", data: historical });
          if (init?.cache === "no-store") {
            freshReads += 1;
            return response({ project_id: "A", data: freshReads === 1 ? initial : freshReads === 2 ? freshBeforeRestore : actualLatest });
          }
          return response({ project_id: "A", data: initial });
        }
        if (url.searchParams.get("format") === "web") {
          const revision = Number(url.searchParams.get("revision"));
          const document = revision === 6 ? actualLatest : revision === 2 ? historical : initial;
          return response({ project_id: "A", data: webRead(document, `<p id="${blockId}">WEB revision ${revision}</p>`) });
        }
      }
      if (url.pathname.endsWith("/drafts") && init?.method === "POST") {
        expect(JSON.parse(String(init.body))).toEqual({ restore_revision: 2, expected_parent_draft_id: 40, source_agent: "webui", change_summary: "Restore revision 2" });
        return response({ project_id: "A", data: { id: 50, revision: 5, parent_draft_id: 40, id_map: {} } }, 201);
      }
      if (url.pathname.endsWith("/drafts")) return response({ project_id: "A", data: [historyItem(6), historyItem(5), historyItem(4), historyItem(3), historyItem(2)] });
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute();
    const user = userEvent.setup();
    await screen.findByText("Latest revision 3");
    await user.click(screen.getByRole("button", { name: "View revision 2" }));
    await screen.findByText("Historical revision 2");
    await user.click(screen.getByRole("button", { name: "Restore revision 2" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("Restore revision 2 as a new revision?");
    await user.click(screen.getByRole("button", { name: "Confirm restore" }));
    await waitFor(() => expect(screen.getAllByRole("status").some((element) => element.textContent?.includes("Restore succeeded as revision 5"))).toBe(true));
    expect(await screen.findByText("Latest revision 6")).toBeInTheDocument();
    expect(screen.getByText("WEB revision 6")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
  });
});
