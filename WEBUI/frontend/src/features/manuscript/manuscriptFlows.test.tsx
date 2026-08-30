import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { appRoutes } from "../../app/routes";
import { projectQueryKeys } from "../../api/queryKeys";
import type { CharacterRecord, DraftDocumentRead, DraftExport, DraftHistoryItem, DraftHtmlRead, DraftWebRead, NovelDocument } from "../../api/types";

function response(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((nextResolve) => { resolve = nextResolve; });
  return { promise, resolve };
}

const episode = { id: 2, work_id: 7, chapter_id: 1, position: 1, title: "Episode", summary: "", purpose: "", foreshadowing_notes_json: "[]", canon_status: "draft", production_status: "planned", version: 1, created_at: "", updated_at: "" };
const outline = { chapters: [{ chapter: { id: 1, work_id: 7, position: 1, title: "Chapter", summary: "", purpose: "", canon_status: "draft", production_status: "planned", version: 1, created_at: "", updated_at: "" }, episodes: [{ episode, scenes: [] }] }] };
const navigationOutline = { chapters: [{ ...outline.chapters[0], episodes: [{ episode, scenes: [] }, { episode: { ...episode, id: 3, position: 2, title: "Episode 2" }, scenes: [] }] }] };
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

function authoringHtml(document: DraftDocumentRead, content = `<p id="${blockId}" data-np-type="dialogue">canonical</p>`): DraftHtmlRead {
  return { ...document, format: "html", content };
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
  authoringHtmlByRevision: Record<number, DraftHtmlRead> = latest ? { [latest.revision]: authoringHtml(latest) } : {},
  characters: CharacterRecord[] = [],
  outlineView = outline,
) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://test");
    if (url.pathname.endsWith("/views/outline")) return response({ project_id: "A", data: outlineView });
    if (url.pathname.endsWith("/episodes/2/draft")) {
      if (url.searchParams.get("format") === "document") {
        const revision = url.searchParams.get("revision");
        return response({ project_id: "A", data: revision ? (Number(revision) === latest?.revision ? latest : documentRead(Number(revision))) : latest });
      }
      if (url.searchParams.get("format") === "web") {
        const revision = Number(url.searchParams.get("revision"));
        return response({ project_id: "A", data: webByRevision[revision] ?? webRead(documentRead(revision)) });
      }
      if (url.searchParams.get("format") === "html") {
        const revision = Number(url.searchParams.get("revision"));
        return response({ project_id: "A", data: authoringHtmlByRevision[revision] ?? authoringHtml(documentRead(revision)) });
      }
    }
    if (url.pathname.endsWith("/characters")) return response({ project_id: "A", data: characters });
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

  it("opens edit from a fresh Document and matching HTML, then confirms the committed revision", async () => {
    let current = documentRead(1, 10);
    const currentHtml = () => authoringHtml(current, '<p id="blk_0123456789abcdef0123456789abcdef" data-np-type="dialogue">canonical</p>');
    const postBodies: Record<string, unknown>[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://test");
      if (url.pathname.endsWith("/views/outline")) return response({ project_id: "A", data: outline });
      if (url.pathname.endsWith("/episodes/2/draft")) {
        if (url.searchParams.get("format") === "document") return response({ project_id: "A", data: current });
        if (url.searchParams.get("format") === "html") return response({ project_id: "A", data: currentHtml() });
        if (url.searchParams.get("format") === "web") return response({ project_id: "A", data: webRead(current) });
      }
      if (url.pathname.endsWith("/drafts") && init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        postBodies.push(body);
        current = documentRead(3, 21);
        return response({ project_id: "A", data: { id: 21, revision: 3, parent_draft_id: 20, id_map: {} } }, 201);
      }
      if (url.pathname.endsWith("/drafts")) return response({ project_id: "A", data: [historyItem(current.revision)] });
      if (url.pathname.endsWith("/characters")) return response({ project_id: "A", data: [] });
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute();
    const user = userEvent.setup();

    await screen.findByText("Latest revision 1");
    current = documentRead(2, 20);
    await user.click(screen.getByRole("button", { name: "Edit manuscript" }));
    expect(await screen.findByRole("textbox", { name: "Manuscript editor" })).toBeInTheDocument();
    expect(screen.getByText("Revision 2 · Draft #20")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Block type"), "heading");
    await user.click(screen.getByRole("button", { name: "Save manuscript" }));

    expect(await screen.findByText("Latest revision 3")).toBeInTheDocument();
    expect(postBodies).toHaveLength(1);
    expect(postBodies[0]).toEqual(expect.objectContaining({
      expected_parent_draft_id: 20,
      source_agent: "webui",
      change_summary: "Edit manuscript",
    }));
    expect(postBodies[0]).not.toHaveProperty("plain_text");
    expect(postBodies[0]).not.toHaveProperty("metadata_updates");
    expect(String(postBodies[0].html)).toContain("<h1");
  });

  it("shows a VERSION_CONFLICT without retrying and keeps the local editor", async () => {
    const current = documentRead(1, 10);
    const latestHtml = authoringHtml(documentRead(2, 20), '<p id="blk_0123456789abcdef0123456789abcdef" data-np-type="dialogue">server latest</p>');
    let postCount = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://test");
      if (url.pathname.endsWith("/views/outline")) return response({ project_id: "A", data: outline });
      if (url.pathname.endsWith("/episodes/2/draft")) {
        if (url.searchParams.get("format") === "document") return response({ project_id: "A", data: current });
        if (url.searchParams.get("format") === "html") return response({ project_id: "A", data: authoringHtml(current) });
        if (url.searchParams.get("format") === "web") return response({ project_id: "A", data: webRead(current) });
      }
      if (url.pathname.endsWith("/drafts") && init?.method === "POST") {
        postCount += 1;
        return response({ error: { code: "VERSION_CONFLICT", message: "stale", details: { current_resource: latestHtml } } }, 409);
      }
      if (url.pathname.endsWith("/drafts")) return response({ project_id: "A", data: [historyItem(1)] });
      if (url.pathname.endsWith("/characters")) return response({ project_id: "A", data: [] });
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute();
    const user = userEvent.setup();

    await screen.findByText("Latest revision 1");
    await user.click(screen.getByRole("button", { name: "Edit manuscript" }));
    await screen.findByRole("textbox", { name: "Manuscript editor" });
    await user.selectOptions(screen.getByLabelText("Block type"), "heading");
    await user.click(screen.getByRole("button", { name: "Save manuscript" }));

    expect(await screen.findByRole("dialog")).toHaveTextContent("VERSION_CONFLICT");
    expect(screen.getByRole("dialog")).toHaveTextContent("server latest");
    expect(postCount).toBe(1);
    await user.click(screen.getByRole("button", { name: "Keep local edits" }));
    expect(screen.getByRole("textbox", { name: "Manuscript editor" })).toBeInTheDocument();
    expect(postCount).toBe(1);
  });

  it("creates an initial manuscript only after the fresh no-draft check", async () => {
    let current: DraftDocumentRead | null = null;
    const postBodies: Record<string, unknown>[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://test");
      if (url.pathname.endsWith("/views/outline")) return response({ project_id: "A", data: outline });
      if (url.pathname.endsWith("/episodes/2/draft")) {
        if (url.searchParams.get("format") === "document") return response({ project_id: "A", data: current });
        if (url.searchParams.get("format") === "web" && current !== null) return response({ project_id: "A", data: webRead(current) });
      }
      if (url.pathname.endsWith("/drafts") && init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        postBodies.push(body);
        current = documentRead(1, 21);
        return response({ project_id: "A", data: { id: 21, revision: 1, parent_draft_id: null, id_map: {} } }, 201);
      }
      if (url.pathname.endsWith("/drafts")) return response({ project_id: "A", data: [] });
      if (url.pathname.endsWith("/characters")) return response({ project_id: "A", data: [] });
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute();
    const user = userEvent.setup();

    await screen.findByText("No manuscript draft yet.");
    await user.click(screen.getByRole("button", { name: "Create manuscript" }));
    const editor = await screen.findByRole("textbox", { name: "Manuscript editor" });
    await user.type(editor, "新しい本文");
    await user.click(screen.getByRole("button", { name: "Save manuscript" }));

    expect(await screen.findByText("Latest revision 1")).toBeInTheDocument();
    expect(postBodies).toHaveLength(1);
    expect(postBodies[0]).toEqual(expect.objectContaining({ source_agent: "webui", change_summary: "Create manuscript" }));
    expect(postBodies[0]).not.toHaveProperty("expected_parent_draft_id");
    expect(postBodies[0]).not.toHaveProperty("plain_text");
  });

  it.each([
    { label: "same revision and ID", actual: documentRead(6, 61), readerRevision: 6 },
    { label: "newer revision", actual: documentRead(7, 70), readerRevision: 7 },
    { label: "older revision", actual: documentRead(5, 50), readerRevision: null },
    { label: "same revision with a different ID", actual: documentRead(6, 62), readerRevision: null },
  ])("handles $label after a successful manuscript save", async ({ actual, readerRevision }) => {
    const baseline = documentRead(2, 20);
    let saved = false;
    let postCount = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://test");
      if (url.pathname.endsWith("/views/outline")) return response({ project_id: "A", data: outline });
      if (url.pathname.endsWith("/episodes/2/draft")) {
        if (url.searchParams.get("format") === "document") return response({ project_id: "A", data: saved ? actual : baseline });
        if (url.searchParams.get("format") === "html") return response({ project_id: "A", data: authoringHtml(baseline) });
        if (url.searchParams.get("format") === "web") return response({ project_id: "A", data: webRead(saved ? actual : baseline) });
      }
      if (url.pathname.endsWith("/drafts") && init?.method === "POST") {
        saved = true;
        postCount += 1;
        return response({ project_id: "A", data: { id: 61, revision: 6, parent_draft_id: 20, id_map: {} } }, 201);
      }
      if (url.pathname.endsWith("/drafts")) return response({ project_id: "A", data: saved ? [historyItem(actual.revision), historyItem(2)] : [historyItem(2)] });
      if (url.pathname.endsWith("/characters")) return response({ project_id: "A", data: [] });
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute();
    const user = userEvent.setup();

    await screen.findByText("Latest revision 2");
    await user.click(screen.getByRole("button", { name: "Edit manuscript" }));
    await screen.findByRole("textbox", { name: "Manuscript editor" });
    await user.selectOptions(screen.getByLabelText("Block type"), "heading");
    await user.click(screen.getByRole("button", { name: "Save manuscript" }));

    expect(postCount).toBe(1);
    if (readerRevision === null) {
      expect((await screen.findAllByText("Save succeeded as revision 6.")).length).toBeGreaterThan(0);
      expect(screen.getByRole("button", { name: "Reload latest" })).toBeEnabled();
      expect(screen.queryByLabelText("Manuscript reader")).not.toBeInTheDocument();
    } else {
      expect(await screen.findByText(`Latest revision ${readerRevision}`)).toBeInTheDocument();
      expect(screen.getByLabelText("Manuscript reader")).toBeInTheDocument();
      expect(screen.queryByText("Confirming latest manuscript…")).not.toBeInTheDocument();
    }
  });

  it("keeps the committed save lock on confirmation network failure without retrying the POST", async () => {
    const baseline = documentRead(2, 20);
    let saved = false;
    let postCount = 0;
    let confirmationReads = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://test");
      if (url.pathname.endsWith("/views/outline")) return response({ project_id: "A", data: outline });
      if (url.pathname.endsWith("/episodes/2/draft")) {
        if (url.searchParams.get("format") === "document") {
          if (saved && init?.cache === "no-store") {
            confirmationReads += 1;
            throw new Error("confirmation network down");
          }
          return response({ project_id: "A", data: baseline });
        }
        if (url.searchParams.get("format") === "html") return response({ project_id: "A", data: authoringHtml(baseline) });
        if (url.searchParams.get("format") === "web") return response({ project_id: "A", data: webRead(baseline) });
      }
      if (url.pathname.endsWith("/drafts") && init?.method === "POST") {
        saved = true;
        postCount += 1;
        return response({ project_id: "A", data: { id: 61, revision: 6, parent_draft_id: 20, id_map: {} } }, 201);
      }
      if (url.pathname.endsWith("/drafts")) return response({ project_id: "A", data: [historyItem(2)] });
      if (url.pathname.endsWith("/characters")) return response({ project_id: "A", data: [] });
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute();
    const user = userEvent.setup();

    await screen.findByText("Latest revision 2");
    await user.click(screen.getByRole("button", { name: "Edit manuscript" }));
    await screen.findByRole("textbox", { name: "Manuscript editor" });
    await user.selectOptions(screen.getByLabelText("Block type"), "heading");
    await user.click(screen.getByRole("button", { name: "Save manuscript" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Save succeeded as revision 6");
    expect(screen.getByRole("button", { name: "Reload latest" })).toBeEnabled();
    expect(postCount).toBe(1);
    expect(confirmationReads).toBe(1);
  });

  it("clears a previous committed save error when manual latest confirmation restarts", async () => {
    const baseline = documentRead(2, 20);
    const actual = documentRead(6, 61);
    let saved = false;
    let confirmationReads = 0;
    const retryConfirmation = deferred<Response>();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://test");
      if (url.pathname.endsWith("/views/outline")) return response({ project_id: "A", data: outline });
      if (url.pathname.endsWith("/episodes/2/draft")) {
        if (url.searchParams.get("format") === "document") {
          if (saved && init?.cache === "no-store") {
            confirmationReads += 1;
            if (confirmationReads === 1) throw new Error("confirmation network down");
            return retryConfirmation.promise;
          }
          return response({ project_id: "A", data: baseline });
        }
        if (url.searchParams.get("format") === "html") return response({ project_id: "A", data: authoringHtml(baseline) });
        if (url.searchParams.get("format") === "web") return response({ project_id: "A", data: webRead(actual) });
      }
      if (url.pathname.endsWith("/drafts") && init?.method === "POST") {
        saved = true;
        return response({ project_id: "A", data: { id: 61, revision: 6, parent_draft_id: 20, id_map: {} } }, 201);
      }
      if (url.pathname.endsWith("/drafts")) return response({ project_id: "A", data: [historyItem(2)] });
      if (url.pathname.endsWith("/characters")) return response({ project_id: "A", data: [] });
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute();
    const user = userEvent.setup();

    await screen.findByText("Latest revision 2");
    await user.click(screen.getByRole("button", { name: "Edit manuscript" }));
    await screen.findByRole("textbox", { name: "Manuscript editor" });
    await user.selectOptions(screen.getByLabelText("Block type"), "heading");
    await user.click(screen.getByRole("button", { name: "Save manuscript" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Save succeeded as revision 6, but the latest manuscript could not be reloaded.");
    const reload = screen.getByRole("button", { name: "Reload latest" });
    await waitFor(() => expect(reload).toBeEnabled());
    await user.click(reload);
    expect(reload).toBeDisabled();
    expect(screen.getByText("Confirming latest manuscript…")).toHaveAttribute("role", "status");
    expect(screen.queryByText("Save succeeded as revision 6, but the latest manuscript could not be reloaded.")).not.toBeInTheDocument();

    retryConfirmation.resolve(response({ project_id: "A", data: actual }));
    expect(await screen.findByText("Latest revision 6")).toBeInTheDocument();
  });

  it("single-flights automatic save confirmation and disables manual reload while it is pending", async () => {
    const baseline = documentRead(2, 20);
    const actual = documentRead(6, 61);
    const confirmation = deferred<Response>();
    let saved = false;
    let confirmationReads = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://test");
      if (url.pathname.endsWith("/views/outline")) return response({ project_id: "A", data: outline });
      if (url.pathname.endsWith("/episodes/2/draft")) {
        if (url.searchParams.get("format") === "document") {
          if (saved && init?.cache === "no-store") {
            confirmationReads += 1;
            return confirmation.promise;
          }
          return response({ project_id: "A", data: baseline });
        }
        if (url.searchParams.get("format") === "html") return response({ project_id: "A", data: authoringHtml(baseline) });
        if (url.searchParams.get("format") === "web") return response({ project_id: "A", data: webRead(actual) });
      }
      if (url.pathname.endsWith("/drafts") && init?.method === "POST") {
        saved = true;
        return response({ project_id: "A", data: { id: 61, revision: 6, parent_draft_id: 20, id_map: {} } }, 201);
      }
      if (url.pathname.endsWith("/drafts")) return response({ project_id: "A", data: [historyItem(2)] });
      if (url.pathname.endsWith("/characters")) return response({ project_id: "A", data: [] });
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute();
    const user = userEvent.setup();

    await screen.findByText("Latest revision 2");
    await user.click(screen.getByRole("button", { name: "Edit manuscript" }));
    await screen.findByRole("textbox", { name: "Manuscript editor" });
    await user.selectOptions(screen.getByLabelText("Block type"), "heading");
    await user.click(screen.getByRole("button", { name: "Save manuscript" }));

    const reload = await screen.findByRole("button", { name: "Reload latest" });
    expect(reload).toBeDisabled();
    expect(confirmationReads).toBe(1);
    await user.click(reload);
    expect(confirmationReads).toBe(1);

    confirmation.resolve(response({ project_id: "A", data: actual }));
    expect(await screen.findByText("Latest revision 6")).toBeInTheDocument();
    expect(await screen.findByLabelText("Manuscript reader")).toBeInTheDocument();
  });

  it("single-flights clean Cancel, adopts external latest, and refreshes history", async () => {
    const baseline = documentRead(2, 20);
    const external = documentRead(3, 30);
    let current = baseline;
    let holdCancel = false;
    let freshReads = 0;
    const cancelRefresh = deferred<Response>();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://test");
      if (url.pathname.endsWith("/views/outline")) return response({ project_id: "A", data: outline });
      if (url.pathname.endsWith("/episodes/2/draft")) {
        if (url.searchParams.get("format") === "document") {
          if (init?.cache === "no-store") {
            freshReads += 1;
            if (holdCancel) {
              holdCancel = false;
              return cancelRefresh.promise;
            }
          }
          return response({ project_id: "A", data: current });
        }
        if (url.searchParams.get("format") === "html") return response({ project_id: "A", data: authoringHtml(current) });
        if (url.searchParams.get("format") === "web") return response({ project_id: "A", data: webRead(current) });
      }
      if (url.pathname.endsWith("/drafts")) return response({ project_id: "A", data: current === external ? [historyItem(3), historyItem(2)] : [historyItem(2)] });
      if (url.pathname.endsWith("/characters")) return response({ project_id: "A", data: [] });
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute();
    const user = userEvent.setup();

    await screen.findByText("Latest revision 2");
    await user.click(screen.getByRole("button", { name: "Edit manuscript" }));
    await screen.findByRole("textbox", { name: "Manuscript editor" });
    current = external;
    holdCancel = true;
    await user.click(screen.getByRole("button", { name: "Cancel editing" }));

    const cancel = screen.getByRole("button", { name: "Cancel editing" });
    expect(cancel).toBeDisabled();
    expect(freshReads).toBe(3);
    await user.click(cancel);
    expect(freshReads).toBe(3);

    cancelRefresh.resolve(response({ project_id: "A", data: external }));
    expect(await screen.findByText("Latest revision 3")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View revision 3" })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Manuscript editor" })).not.toBeInTheDocument();
  });

  it("blocks Save while dirty Cancel is refreshing the latest manuscript", async () => {
    const baseline = documentRead(2, 20);
    const external = documentRead(3, 30);
    let current = baseline;
    let holdCancel = false;
    let postCount = 0;
    const cancelRefresh = deferred<Response>();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://test");
      if (url.pathname.endsWith("/views/outline")) return response({ project_id: "A", data: outline });
      if (url.pathname.endsWith("/episodes/2/draft")) {
        if (url.searchParams.get("format") === "document") {
          if (init?.cache === "no-store" && holdCancel) {
            holdCancel = false;
            return cancelRefresh.promise;
          }
          return response({ project_id: "A", data: current });
        }
        if (url.searchParams.get("format") === "html") return response({ project_id: "A", data: authoringHtml(current) });
        if (url.searchParams.get("format") === "web") return response({ project_id: "A", data: webRead(current) });
      }
      if (url.pathname.endsWith("/drafts") && init?.method === "POST") {
        postCount += 1;
        return response({ project_id: "A", data: { id: 31, revision: 3, parent_draft_id: 20, id_map: {} } }, 201);
      }
      if (url.pathname.endsWith("/drafts")) return response({ project_id: "A", data: current === external ? [historyItem(3), historyItem(2)] : [historyItem(2)] });
      if (url.pathname.endsWith("/characters")) return response({ project_id: "A", data: [] });
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute();
    const user = userEvent.setup();

    await screen.findByText("Latest revision 2");
    await user.click(screen.getByRole("button", { name: "Edit manuscript" }));
    const editor = await screen.findByRole("textbox", { name: "Manuscript editor" });
    await user.type(editor, " local");
    current = external;
    holdCancel = true;
    await user.click(screen.getByRole("button", { name: "Cancel editing" }));
    await user.click(screen.getByRole("button", { name: "Discard edits" }));

    const save = screen.getByRole("button", { name: "Save manuscript" });
    expect(save).toBeDisabled();
    await user.click(save);
    expect(postCount).toBe(0);

    cancelRefresh.resolve(response({ project_id: "A", data: external }));
    expect(await screen.findByText("Latest revision 3")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Manuscript editor" })).not.toBeInTheDocument();
  });

  it("traps dirty Cancel confirmation and blocks editor actions before and during discard", async () => {
    const baseline = documentRead(2, 20);
    const external = documentRead(3, 30);
    let current = baseline;
    let holdCancel = false;
    let postCount = 0;
    const cancelRefresh = deferred<Response>();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://test");
      if (url.pathname.endsWith("/views/outline")) return response({ project_id: "A", data: outline });
      if (url.pathname.endsWith("/episodes/2/draft")) {
        if (url.searchParams.get("format") === "document") {
          if (init?.cache === "no-store" && holdCancel) {
            holdCancel = false;
            return cancelRefresh.promise;
          }
          return response({ project_id: "A", data: current });
        }
        if (url.searchParams.get("format") === "html") return response({ project_id: "A", data: authoringHtml(current) });
        if (url.searchParams.get("format") === "web") return response({ project_id: "A", data: webRead(current) });
      }
      if (url.pathname.endsWith("/drafts") && init?.method === "POST") {
        postCount += 1;
        return response({ project_id: "A", data: { id: 31, revision: 3, parent_draft_id: 20, id_map: {} } }, 201);
      }
      if (url.pathname.endsWith("/drafts")) return response({ project_id: "A", data: [historyItem(current.revision)] });
      if (url.pathname.endsWith("/characters")) return response({ project_id: "A", data: [] });
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute();
    const user = userEvent.setup();

    await screen.findByText("Latest revision 2");
    await user.click(screen.getByRole("button", { name: "Edit manuscript" }));
    const editor = await screen.findByRole("textbox", { name: "Manuscript editor" });
    await user.type(editor, " local");

    await user.click(screen.getByRole("button", { name: "Cancel editing" }));
    const dialog = screen.getByRole("dialog");
    const keep = screen.getByRole("button", { name: "Keep editing" });
    const discard = screen.getByRole("button", { name: "Discard edits" });
    expect(screen.getByRole("button", { name: "Save manuscript" })).toBeDisabled();
    expect(keep).toHaveFocus();
    await user.tab();
    expect(discard).toHaveFocus();
    await user.tab();
    expect(keep).toHaveFocus();
    await user.tab({ shift: true });
    expect(discard).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(dialog).not.toBeInTheDocument();
    expect(editor).toHaveTextContent("local");

    current = external;
    holdCancel = true;
    await user.click(screen.getByRole("button", { name: "Cancel editing" }));
    await user.click(screen.getByRole("button", { name: "Discard edits" }));
    expect(screen.getByRole("button", { name: "Save manuscript" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel editing" })).toBeDisabled();
    expect(postCount).toBe(0);

    cancelRefresh.resolve(response({ project_id: "A", data: external }));
    expect(await screen.findByText("Latest revision 3")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Manuscript editor" })).not.toBeInTheDocument();
  });

  it("keeps an already observed newer latest after stale save confirmation", async () => {
    const baseline = documentRead(4, 40);
    const saved = documentRead(5, 50);
    const newer = documentRead(7, 70);
    const staleConfirmation = documentRead(6, 60);
    let saveCompleted = false;
    const confirmation = deferred<Response>();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://test");
      if (url.pathname.endsWith("/views/outline")) return response({ project_id: "A", data: outline });
      if (url.pathname.endsWith("/episodes/2/draft")) {
        if (url.searchParams.get("format") === "document") {
          if (saveCompleted && init?.cache === "no-store") return confirmation.promise;
          return response({ project_id: "A", data: baseline });
        }
        if (url.searchParams.get("format") === "html") return response({ project_id: "A", data: authoringHtml(baseline) });
        if (url.searchParams.get("format") === "web") {
          const revision = Number(url.searchParams.get("revision"));
          return response({ project_id: "A", data: webRead(revision === 7 ? newer : staleConfirmation) });
        }
      }
      if (url.pathname.endsWith("/drafts") && init?.method === "POST") {
        saveCompleted = true;
        return response({ project_id: "A", data: { id: saved.id, revision: saved.revision, parent_draft_id: 40, id_map: {} } }, 201);
      }
      if (url.pathname.endsWith("/drafts")) return response({ project_id: "A", data: [historyItem(baseline.revision)] });
      if (url.pathname.endsWith("/characters")) return response({ project_id: "A", data: [] });
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    const { queryClient } = renderRoute();
    const user = userEvent.setup();

    await screen.findByText("Latest revision 4");
    await user.click(screen.getByRole("button", { name: "Edit manuscript" }));
    await screen.findByRole("textbox", { name: "Manuscript editor" });
    await user.selectOptions(screen.getByLabelText("Block type"), "heading");
    await user.click(screen.getByRole("button", { name: "Save manuscript" }));

    queryClient.setQueryData(projectQueryKeys.draftDocument("A", 2, "latest"), newer);
    confirmation.resolve(response({ project_id: "A", data: staleConfirmation }));

    await waitFor(() => expect(screen.getByText("Latest revision 7")).toBeInTheDocument());
    expect(queryClient.getQueryData(projectQueryKeys.draftDocument("A", 2, "latest"))).toEqual(newer);
  });

  it("saves whole-manuscript deletion as empty HTML and an empty canonical document", async () => {
    const baseline = documentRead(1, 10);
    const empty = documentRead(2, 20, []);
    let current = baseline;
    const postBodies: Record<string, unknown>[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://test");
      if (url.pathname.endsWith("/views/outline")) return response({ project_id: "A", data: outline });
      if (url.pathname.endsWith("/episodes/2/draft")) {
        if (url.searchParams.get("format") === "document") return response({ project_id: "A", data: current });
        if (url.searchParams.get("format") === "html") return response({ project_id: "A", data: current.content.blocks.length === 0 ? authoringHtml(empty, "") : authoringHtml(baseline) });
        if (url.searchParams.get("format") === "web") return response({ project_id: "A", data: webRead(current, current.content.blocks.length === 0 ? "" : "<p>canonical</p>") });
      }
      if (url.pathname.endsWith("/drafts") && init?.method === "POST") {
        postBodies.push(JSON.parse(String(init.body)) as Record<string, unknown>);
        current = empty;
        return response({ project_id: "A", data: { id: 20, revision: 2, parent_draft_id: 10, id_map: {} } }, 201);
      }
      if (url.pathname.endsWith("/drafts")) return response({ project_id: "A", data: [historyItem(current.revision)] });
      if (url.pathname.endsWith("/characters")) return response({ project_id: "A", data: [] });
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute();
    const user = userEvent.setup();

    await screen.findByText("Latest revision 1");
    await user.click(screen.getByRole("button", { name: "Edit manuscript" }));
    const editor = await screen.findByRole("textbox", { name: "Manuscript editor" });
    await user.click(editor);
    await user.keyboard("{Control>}a{/Control}");
    await user.keyboard("{Backspace}");
    await user.click(screen.getByRole("button", { name: "Save manuscript" }));

    expect(postBodies).toHaveLength(1);
    expect(postBodies[0]).toEqual(expect.objectContaining({ html: "" }));
    expect(await screen.findByText("Latest revision 2")).toBeInTheDocument();
    expect(screen.getByText("This manuscript revision is empty.")).toBeInTheDocument();
    expect(current.content.blocks).toEqual([]);
  });

  it("guards manuscript route navigation while dirty and never posts on discard", async () => {
    const latest = documentRead(1, 10);
    const route = routeFor(latest, [historyItem(1)], { 1: webRead(latest) }, [], { 1: authoringHtml(latest) }, [], navigationOutline);
    let postCount = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === "POST") postCount += 1;
      return route(input, init);
    });
    vi.stubGlobal("fetch", fetchMock);
    const { router } = renderRoute();
    const user = userEvent.setup();

    await screen.findByText("Latest revision 1");
    await user.click(screen.getByRole("button", { name: "Edit manuscript" }));
    const editor = await screen.findByRole("textbox", { name: "Manuscript editor" });
    await user.type(editor, " local");
    await waitFor(() => expect(screen.getByText("Unsaved changes")).toBeInTheDocument());

    await user.click(screen.getByRole("link", { name: "Back to manuscript" }));
    expect(await screen.findByRole("heading", { name: "Leave without saving?" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Stay" }));
    expect(router.state.location.pathname).toBe("/projects/A/manuscript/2");
    expect(screen.getByRole("textbox", { name: "Manuscript editor" })).toHaveTextContent("local");

    const secondEpisode = screen.getByRole("link", { name: /Episode 2/ });
    await user.click(secondEpisode);
    expect(await screen.findByRole("heading", { name: "Leave without saving?" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Stay" }));
    expect(router.state.location.pathname).toBe("/projects/A/manuscript/2");
    expect(screen.getByRole("textbox", { name: "Manuscript editor" })).toHaveTextContent("local");

    await user.click(secondEpisode);
    await user.click(screen.getByRole("button", { name: "Discard and leave" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/projects/A/manuscript/3"));
    expect(postCount).toBe(0);
  });

  it("reports invalid ordinary save identity with save-specific wording", async () => {
    const latest = documentRead(1, 10);
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://test");
      if (url.pathname.endsWith("/views/outline")) return response({ project_id: "A", data: outline });
      if (url.pathname.endsWith("/episodes/2/draft")) {
        if (url.searchParams.get("format") === "document") return response({ project_id: "A", data: latest });
        if (url.searchParams.get("format") === "html") return response({ project_id: "A", data: authoringHtml(latest) });
        if (url.searchParams.get("format") === "web") return response({ project_id: "A", data: webRead(latest) });
      }
      if (url.pathname.endsWith("/drafts") && init?.method === "POST") return response({ project_id: "A", data: { id: 0, revision: 0, parent_draft_id: 10, id_map: {} } }, 201);
      if (url.pathname.endsWith("/drafts")) return response({ project_id: "A", data: [historyItem(1)] });
      if (url.pathname.endsWith("/characters")) return response({ project_id: "A", data: [] });
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute();
    const user = userEvent.setup();

    await screen.findByText("Latest revision 1");
    await user.click(screen.getByRole("button", { name: "Edit manuscript" }));
    const editor = await screen.findByRole("textbox", { name: "Manuscript editor" });
    await user.type(editor, " local");
    await user.click(screen.getByRole("button", { name: "Save manuscript" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The draft save response has an invalid revision identity.");
    expect(alert).not.toHaveTextContent("restore response");
    expect(screen.getByRole("textbox", { name: "Manuscript editor" })).toBeInTheDocument();
  });

  it("keeps a newer latest cache when a background document refresh completes late", async () => {
    const baseline = documentRead(4, 40);
    const newer = documentRead(7, 70);
    const stale = documentRead(6, 60);
    let holdRefresh = false;
    const backgroundRefresh = deferred<Response>();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://test");
      if (url.pathname.endsWith("/views/outline")) return response({ project_id: "A", data: outline });
      if (url.pathname.endsWith("/episodes/2/draft")) {
        if (url.searchParams.get("format") === "document") {
          if (holdRefresh && init?.cache === "no-store") return backgroundRefresh.promise;
          return response({ project_id: "A", data: baseline });
        }
        if (url.searchParams.get("format") === "web") return response({ project_id: "A", data: webRead(url.searchParams.get("revision") === "7" ? newer : baseline) });
      }
      if (url.pathname.endsWith("/drafts")) return response({ project_id: "A", data: [historyItem(baseline.revision)] });
      if (url.pathname.endsWith("/characters")) return response({ project_id: "A", data: [] });
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    const { queryClient } = renderRoute();

    await screen.findByText("Latest revision 4");
    holdRefresh = true;
    const refresh = queryClient.refetchQueries({ queryKey: projectQueryKeys.draftDocument("A", 2, "latest"), exact: true });
    await waitFor(() => expect(fetchMock.mock.calls.filter(([, init]) => init?.cache === "no-store")).toHaveLength(2));
    queryClient.setQueryData(projectQueryKeys.draftDocument("A", 2, "latest"), newer);
    backgroundRefresh.resolve(response({ project_id: "A", data: stale }));
    await refresh;

    await waitFor(() => expect(screen.getByText("Latest revision 7")).toBeInTheDocument());
    expect(queryClient.getQueryData(projectQueryKeys.draftDocument("A", 2, "latest"))).toEqual(newer);
  });

  it("keeps local conflict edits and shows latest reload failure inside the conflict dialog", async () => {
    const baseline = documentRead(1, 10);
    const latest = documentRead(2, 20);
    let reloadFailure = true;
    let conflictShown = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://test");
      if (url.pathname.endsWith("/views/outline")) return response({ project_id: "A", data: outline });
      if (url.pathname.endsWith("/episodes/2/draft")) {
        if (url.searchParams.get("format") === "document") {
          if (conflictShown && init?.cache === "no-store") {
            if (reloadFailure) throw new Error("latest reload unavailable");
            return response({ project_id: "A", data: latest });
          }
          return response({ project_id: "A", data: baseline });
        }
        if (url.searchParams.get("format") === "html") {
          return response({
            project_id: "A",
            data: conflictShown
              ? authoringHtml(latest, '<p id="blk_0123456789abcdef0123456789abcdef" data-np-type="narration">server latest</p>')
              : authoringHtml(baseline),
          });
        }
        if (url.searchParams.get("format") === "web") return response({ project_id: "A", data: webRead(baseline) });
      }
      if (url.pathname.endsWith("/drafts") && init?.method === "POST") {
        conflictShown = true;
        return response({ error: { code: "VERSION_CONFLICT", message: "stale", details: { current_resource: authoringHtml(latest, '<p id="blk_0123456789abcdef0123456789abcdef" data-np-type="narration">server latest</p>') } } }, 409);
      }
      if (url.pathname.endsWith("/drafts")) return response({ project_id: "A", data: [historyItem(1)] });
      if (url.pathname.endsWith("/characters")) return response({ project_id: "A", data: [] });
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute();
    const user = userEvent.setup();

    await screen.findByText("Latest revision 1");
    await user.click(screen.getByRole("button", { name: "Edit manuscript" }));
    await screen.findByRole("textbox", { name: "Manuscript editor" });
    await user.selectOptions(screen.getByLabelText("Block type"), "heading");
    await user.click(screen.getByRole("button", { name: "Save manuscript" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("VERSION_CONFLICT");

    await user.click(screen.getByRole("button", { name: "Load latest and discard local edits" }));
    expect(await screen.findByRole("dialog")).toHaveTextContent("The API could not be reached.");
    expect(screen.getByRole("textbox", { name: "Manuscript editor" })).toBeInTheDocument();

    reloadFailure = false;
    await user.click(screen.getByRole("button", { name: "Load latest and discard local edits" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByRole("textbox", { name: "Manuscript editor" })).toHaveTextContent("server latest");
  });

  it("single-flights conflict reload and applies the first completed latest baseline", async () => {
    const baseline = documentRead(1, 10);
    const latest = documentRead(3, 30);
    let conflictShown = false;
    let freshReads = 0;
    const latestRefresh = deferred<Response>();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://test");
      if (url.pathname.endsWith("/views/outline")) return response({ project_id: "A", data: outline });
      if (url.pathname.endsWith("/episodes/2/draft")) {
        if (url.searchParams.get("format") === "document") {
          if (conflictShown && init?.cache === "no-store") {
            freshReads += 1;
            return latestRefresh.promise;
          }
          return response({ project_id: "A", data: baseline });
        }
        if (url.searchParams.get("format") === "html") return response({ project_id: "A", data: conflictShown ? authoringHtml(latest, '<p id="blk_0123456789abcdef0123456789abcdef" data-np-type="narration">server latest</p>') : authoringHtml(baseline) });
        if (url.searchParams.get("format") === "web") return response({ project_id: "A", data: webRead(baseline) });
      }
      if (url.pathname.endsWith("/drafts") && init?.method === "POST") {
        conflictShown = true;
        return response({ error: { code: "VERSION_CONFLICT", message: "stale", details: { current_resource: authoringHtml(latest) } } }, 409);
      }
      if (url.pathname.endsWith("/drafts")) return response({ project_id: "A", data: [historyItem(1)] });
      if (url.pathname.endsWith("/characters")) return response({ project_id: "A", data: [] });
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute();
    const user = userEvent.setup();

    await screen.findByText("Latest revision 1");
    await user.click(screen.getByRole("button", { name: "Edit manuscript" }));
    await screen.findByRole("textbox", { name: "Manuscript editor" });
    await user.selectOptions(screen.getByLabelText("Block type"), "heading");
    await user.click(screen.getByRole("button", { name: "Save manuscript" }));

    const load = await screen.findByRole("button", { name: "Load latest and discard local edits" });
    await user.click(load);
    await waitFor(() => expect(load).toBeDisabled());
    const dialog = screen.getByRole("dialog");
    expect(screen.getByRole("button", { name: "Keep local edits" })).toBeDisabled();
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(freshReads).toBe(1);
    await user.click(load);
    expect(freshReads).toBe(1);

    latestRefresh.resolve(response({ project_id: "A", data: latest }));
    await waitFor(() => expect(screen.getByRole("textbox", { name: "Manuscript editor" })).toHaveTextContent("server latest"));
    expect(freshReads).toBe(1);
  });
});
