import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { appRoutes } from "../../app/routes";
import type { EpisodeView, OutlineView } from "../../api/types";

const episode = {
  id: 2, work_id: 7, chapter_id: 1, position: 1, title: "Episode", summary: "Summary", purpose: "Purpose",
  foreshadowing_notes_json: '[{"clue":true}]', canon_status: "draft", production_status: "planned", version: 5,
  created_at: "2026-01-01", updated_at: "2026-01-01",
};
const scene = {
  id: 3, work_id: 7, episode_id: 2, position: 1, title: "Scene", summary: "Summary", purpose: "Purpose",
  canon_status: "draft", production_status: "planned", version: 6, created_at: "2026-01-01", updated_at: "2026-01-01",
};
const chapter = {
  id: 1, work_id: 7, position: 1, title: "Chapter", summary: "Summary", purpose: "Purpose",
  canon_status: "draft", production_status: "planned", version: 4, created_at: "2026-01-01", updated_at: "2026-01-01",
};

function outline(): OutlineView {
  return { chapters: [{ chapter, episodes: [{ episode, scenes: [scene] }] }] };
}

function view(references: EpisodeView["episode_references"] = []): EpisodeView {
  return {
    episode,
    scenes: [scene],
    episode_references: references,
    outline: { episode, scenes: [scene], participants: [], references: { world_facts: [], timeline_events: [], information: [] }, protected_information_guards: [] },
    context: {
      episode, scenes: [scene],
      participants: [{
        profile: { id: 9, character_key: "hero", display_name: "Hero", entity_type: "character", description: "A hero", birth_date: null, physical_description: "Tired", occupation: "Pilot", core_beliefs: "Truth", goals: "Return", fears: "Loss", personality: "Calm", speech_style: "Plain", ai_attitude: "Trusting", genetic_modification_attitude: "Neutral", canon_status: "canon" },
        effective_state: { state_id: 12, source_episode_id: 2, physical_state: "Injured", emotional_state: "Afraid", beliefs: { clue: true }, location_world_fact_id: 44 },
        effective_relationships: [{ relationship_id: 13, related_character_id: 10, relationship_type: "ally", description: "Trusts them", canon_status: "canon" }],
        known_information: [{ information_item_id: 21, knowledge_state: "known", source_episode_id: 1, statement: "The gate is open", truth_status: "true", canon_status: "canon" }],
      }],
      world_facts: [], timeline_events: [], reader_context: { known_before_episode: [], reveal_this_episode: [] }, protected_information_guards: [], recent_context: { previous_episode_summaries: [], previous_draft_tail: "tail" }, foreshadowing_notes: [{ clue: true }], context_meta: { source: "test" },
    },
    latest_draft: { id: 10, work_id: 7, episode_id: 2, revision: 1, parent_draft_id: null, body: "Read-only draft", source_agent: "agent", change_summary: "Initial", content_hash: "sha256:abc", created_at: "2026-01-02" },
    recent_draft_history: [{ id: 10, episode_id: 2, revision: 1, parent_draft_id: null, source_agent: "agent", change_summary: "Recent change summary", content_hash: "sha256:abc", body_chars: 16, created_at: "2026-01-02" }],
  };
}

function renderEpisode() {
  const router = createMemoryRouter(appRoutes, { initialEntries: ["/projects/A/structure/episodes/2"] });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={queryClient}><RouterProvider router={router} /></QueryClientProvider>);
  return router;
}

describe("episode aggregated detail", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders the D2 details, scenes, references, outline, context, and draft history sections", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      void _init;
      const url = String(input);
      if (url.endsWith("/views/outline")) return new Response(JSON.stringify({ project_id: "A", data: outline() }));
      if (url.endsWith("/views/episodes/2")) return new Response(JSON.stringify({ project_id: "A", data: view() }));
      return new Response(JSON.stringify({ error: { code: "NOT_FOUND", message: "Not found" } }), { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderEpisode();
    expect(await screen.findByRole("heading", { name: "Episode" })).toBeInTheDocument();
    for (const tab of ["Scenes", "References", "Outline", "Context", "Draft history"]) {
      await userEvent.setup().click(screen.getByRole("button", { name: new RegExp(`^${tab}$`) }));
      expect(await screen.findByRole("heading", { name: tab })).toBeInTheDocument();
    }
    await userEvent.setup().click(screen.getByRole("button", { name: /^Draft history$/ }));
    expect(screen.getByText("Read-only draft")).toBeInTheDocument();
    expect(screen.getByText("Recent change summary")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input, init]) => init?.method === "POST" && String(input).includes("/drafts"))).toBe(false);
  });

  it("keeps dirty episode edits mounted across tab switches and navigation guard", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/views/outline")) return new Response(JSON.stringify({ project_id: "A", data: outline() }));
      if (url.endsWith("/views/episodes/2")) return new Response(JSON.stringify({ project_id: "A", data: view() }));
      return new Response(JSON.stringify({ error: { code: "NOT_FOUND", message: "Not found" } }), { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const router = renderEpisode();
    const user = userEvent.setup();
    const title = await screen.findByLabelText("Title");
    await user.clear(title);
    await user.type(title, "Unsaved episode title");
    await user.click(screen.getByRole("button", { name: "Scenes" }));
    await user.click(screen.getByRole("button", { name: "Details" }));
    expect(screen.getByDisplayValue("Unsaved episode title")).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Back to structure" }));
    expect(screen.getByRole("heading", { name: "Leave without saving?" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Stay" }));
    expect(screen.getByDisplayValue("Unsaved episode title")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/projects/A/structure/episodes/2");
  });

  it("renders effective state, relationships, and known information as records", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/views/outline")) return new Response(JSON.stringify({ project_id: "A", data: outline() }));
      if (url.endsWith("/views/episodes/2")) return new Response(JSON.stringify({ project_id: "A", data: view() }));
      return new Response(JSON.stringify({ error: { code: "NOT_FOUND", message: "Not found" } }), { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderEpisode();
    await screen.findByRole("heading", { name: "Episode" });
    await userEvent.setup().click(screen.getByRole("button", { name: "Context" }));
    expect(screen.getByText("Injured")).toBeInTheDocument();
    expect(screen.getByText("Afraid")).toBeInTheDocument();
    expect(screen.getByText("related_character_id")).toBeInTheDocument();
    expect(screen.getByText("Trusts them")).toBeInTheDocument();
    expect(screen.getByText("information_item_id")).toBeInTheDocument();
    expect(screen.getByText("The gate is open")).toBeInTheDocument();
  });

  it("adds a character reference with role and refetches the episode view", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/views/outline")) return new Response(JSON.stringify({ project_id: "A", data: outline() }));
      if (url.endsWith("/views/episodes/2")) return new Response(JSON.stringify({ project_id: "A", data: view() }));
      if (url.endsWith("/episodes/2/references") && init?.method === "POST") return new Response(JSON.stringify({ project_id: "A", data: { id: 11, work_id: 7, episode_id: 2, reference_type: "character", target_id: 9, role: "mentor", created_at: "2026-01-03" } }), { status: 201 });
      return new Response(JSON.stringify({ error: { code: "NOT_FOUND", message: "Not found" } }), { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderEpisode();
    await screen.findByRole("heading", { name: "Episode" });
    await userEvent.setup().click(screen.getByRole("button", { name: /^References$/ }));
    await userEvent.setup().clear(screen.getByLabelText("Target ID"));
    await userEvent.setup().type(screen.getByLabelText("Target ID"), "9");
    await userEvent.setup().clear(screen.getByLabelText("Role"));
    await userEvent.setup().type(screen.getByLabelText("Role"), "mentor");
    await userEvent.setup().click(screen.getByRole("button", { name: "Add reference" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true));
    const call = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ reference_type: "character", target_id: 9, role: "mentor" });
    expect(fetchMock.mock.calls.filter(([input, init]) => String(input).endsWith("/views/episodes/2") && (!init || init.method === undefined)).length).toBeGreaterThanOrEqual(2);
  });

  it("sends no custom role for non-character references and blocks invalid target IDs", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/views/outline")) return new Response(JSON.stringify({ project_id: "A", data: outline() }));
      if (url.endsWith("/views/episodes/2")) return new Response(JSON.stringify({ project_id: "A", data: view() }));
      if (url.endsWith("/episodes/2/references") && init?.method === "POST") return new Response(JSON.stringify({ project_id: "A", data: { id: 11, work_id: 7, episode_id: 2, reference_type: "information", target_id: 9, role: null, created_at: "2026-01-03" } }), { status: 201 });
      return new Response(JSON.stringify({ error: { code: "NOT_FOUND", message: "Not found" } }), { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderEpisode();
    await screen.findByRole("heading", { name: "Episode" });
    await userEvent.setup().click(screen.getByRole("button", { name: /^References$/ }));
    await userEvent.setup().selectOptions(screen.getByLabelText("Reference type"), "information");
    expect(screen.queryByLabelText("Role")).not.toBeInTheDocument();
    await userEvent.setup().type(screen.getByLabelText("Target ID"), "0");
    await userEvent.setup().click(screen.getByRole("button", { name: "Add reference" }));
    expect(screen.getByRole("alert")).toHaveTextContent("positive integer");
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
    await userEvent.setup().clear(screen.getByLabelText("Target ID"));
    await userEvent.setup().type(screen.getByLabelText("Target ID"), "9");
    await userEvent.setup().click(screen.getByRole("button", { name: "Add reference" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true));
    const call = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ reference_type: "information", target_id: 9 });
  });

  it("blocks an invalid foreshadowing JSON update without PATCH", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      void _init;
      const url = String(input);
      if (url.endsWith("/views/outline")) return new Response(JSON.stringify({ project_id: "A", data: outline() }));
      if (url.endsWith("/views/episodes/2")) return new Response(JSON.stringify({ project_id: "A", data: view() }));
      return new Response(JSON.stringify({ error: { code: "NOT_FOUND", message: "Not found" } }), { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderEpisode();
    await screen.findByRole("heading", { name: "Episode" });
    const notes = screen.getByLabelText("Foreshadowing notes JSON");
    await userEvent.setup().clear(notes);
    fireEvent.change(notes, { target: { value: "{broken" } });
    await userEvent.setup().click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter valid JSON.");
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(false);
  });

  it.each(["{}", "null", '"text"'])("blocks non-array foreshadowing update %s without PATCH", async (notes) => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      void _init;
      const url = String(input);
      if (url.endsWith("/views/outline")) return new Response(JSON.stringify({ project_id: "A", data: outline() }));
      if (url.endsWith("/views/episodes/2")) return new Response(JSON.stringify({ project_id: "A", data: view() }));
      return new Response(JSON.stringify({ error: { code: "NOT_FOUND", message: "Not found" } }), { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderEpisode();
    await screen.findByRole("heading", { name: "Episode" });
    const user = userEvent.setup();
    const notesField = screen.getByLabelText("Foreshadowing notes JSON");
    fireEvent.change(notesField, { target: { value: notes } });
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Foreshadowing notes must be a JSON array.");
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(false);
  });

  it("saves an episode explicitly with expected version and preserves local edits on API errors", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/views/outline")) return new Response(JSON.stringify({ project_id: "A", data: outline() }));
      if (url.endsWith("/views/episodes/2")) return new Response(JSON.stringify({ project_id: "A", data: view() }));
      if (url.endsWith("/episodes/2") && init?.method === "PATCH") return new Response(JSON.stringify({ error: { code: "CANON_REASON_REQUIRED", message: "A reason is required.", project_id: "A", details: {} } }), { status: 422 });
      return new Response(JSON.stringify({ error: { code: "NOT_FOUND", message: "Not found" } }), { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderEpisode();
    await screen.findByRole("heading", { name: "Episode" });
    const user = userEvent.setup();
    const title = screen.getByLabelText("Title");
    await user.clear(title);
    await user.type(title, "Local episode title");
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(false);
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("A reason is required.");
    expect(screen.getByDisplayValue("Local episode title")).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH")).toHaveLength(1);
    const call = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ expected_version: 5, title: "Local episode title" });
  });

  it("does not save when only the episode reason changes", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      void _init;
      const url = String(input);
      if (url.endsWith("/views/outline")) return new Response(JSON.stringify({ project_id: "A", data: outline() }));
      if (url.endsWith("/views/episodes/2")) return new Response(JSON.stringify({ project_id: "A", data: view() }));
      return new Response(JSON.stringify({ error: { code: "NOT_FOUND", message: "Not found" } }), { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderEpisode();
    await screen.findByRole("heading", { name: "Episode" });
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Reason"), "audit note");
    expect(screen.queryByText("Unsaved changes")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(false);
  });
});
