import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { projectQueryKeys } from "../../api/queryKeys";
import { appRoutes } from "../../app/routes";
import type {
  CharacterRecord,
  CharacterStateRecord,
  EffectiveKnowledgeRecord,
  RelationshipRecord,
} from "../../api/types";

function response(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function character(id: number, projectId = "A"): CharacterRecord {
  return {
    id,
    work_id: 1,
    character_key: `key-${id}`,
    display_name: `${projectId} character ${id}`,
    entity_type: "human",
    description: `${projectId} description`,
    birth_date: null,
    death_date: null,
    physical_description: "",
    occupation: "",
    core_beliefs: "",
    goals: "",
    fears: "",
    personality: "",
    speech_style: "",
    ai_attitude: "",
    genetic_modification_attitude: "",
    private_notes: "",
    profile_json: '{"voice":"calm"}',
    canon_status: "draft",
    version: 1,
    created_at: "2026-01-01",
    updated_at: "2026-01-01",
  };
}

function relationship(id = 1, version = 1): RelationshipRecord {
  return {
    id,
    work_id: 1,
    source_character_id: 1,
    target_character_id: 2,
    relationship_type: "ally",
    description: "",
    canon_status: "draft",
    valid_from_episode_id: null,
    valid_to_episode_id: null,
    version,
    created_at: "",
    updated_at: "",
  };
}

function characterState(
  episodeId = 20,
  version = 1,
  physicalState = "calm",
): CharacterStateRecord {
  return {
    id: 50,
    work_id: 1,
    character_id: 1,
    episode_id: episodeId,
    physical_state: physicalState,
    emotional_state: "focused",
    beliefs_json: '{"a":1,"b":2}',
    location_world_fact_id: null,
    state_json: "{}",
    version,
    created_at: "",
    updated_at: "",
  };
}

function outline() {
  return {
    chapters: [
      {
        chapter: {
          id: 10,
          work_id: 1,
          position: 1,
          title: "Chapter",
          summary: "",
          purpose: "",
          canon_status: "draft",
          production_status: "planned",
          version: 1,
          created_at: "",
          updated_at: "",
        },
        episodes: [
          {
            episode: {
              id: 20,
              work_id: 1,
              chapter_id: 10,
              position: 1,
              title: "Episode",
              summary: "",
              purpose: "",
              foreshadowing_notes_json: "[]",
              canon_status: "draft",
              production_status: "planned",
              version: 1,
              created_at: "",
              updated_at: "",
            },
            scenes: [],
          },
        ],
      },
    ],
  };
}

function renderRoute(initialEntry: string, staleTime = 0) {
  const router = createMemoryRouter(appRoutes, {
    initialEntries: [initialEntry],
  });
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

describe("D3 character flows", () => {
  afterEach(() => vi.restoreAllMocks());

  it("browses characters, searches, and keeps project A/B data isolated", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/characters?limit=50&offset=0"))
        return response({
          project_id: url.includes("/B/") ? "B" : "A",
          data: [character(1, url.includes("/B/") ? "B" : "A")],
        });
      if (
        url.includes(
          "/characters/search?query=%E4%B8%BB%E4%BA%BA%E5%85%AC&limit=50",
        )
      )
        return response({ project_id: "A", data: [character(2)] });
      return response(
        { error: { code: "NOT_FOUND", message: "Not found" } },
        404,
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    const router = renderRoute("/projects/A/characters");
    expect(await screen.findByText("A character 1")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.type(
      screen.getByRole("searchbox", { name: "Search characters" }),
      "主人公",
    );
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText("A character 2")).toBeInTheDocument();
    await router.navigate("/projects/B/characters");
    expect(await screen.findByText("B character 1")).toBeInTheDocument();
    expect(screen.queryByText("A character 1")).not.toBeInTheDocument();
  });

  it("validates profile JSON before create and saves a minimal profile update", async () => {
    const original = character(1);
    const created = character(9);
    const updated = { ...original, display_name: "Changed", version: 2 };
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/characters?limit=50&offset=0"))
          return response({ project_id: "A", data: [] });
        if (url.endsWith("/characters") && init?.method === "POST")
          return response({ project_id: "A", data: created }, 201);
        if (url.endsWith("/characters/9"))
          return response({ project_id: "A", data: created });
        if (url.endsWith("/characters/1") && init?.method === "PATCH") {
          expect(JSON.parse(String(init.body))).toEqual({
            expected_version: 1,
            display_name: "Changed",
          });
          return response({ project_id: "A", data: updated });
        }
        if (url.endsWith("/characters/1"))
          return response({ project_id: "A", data: original });
        return response(
          { error: { code: "NOT_FOUND", message: "Not found" } },
          404,
        );
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    const router = renderRoute("/projects/A/characters");
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Characters" });
    await user.click(screen.getByRole("button", { name: "Add character" }));
    await user.type(screen.getByLabelText("Display name"), "New character");
    fireEvent.change(screen.getByLabelText("Profile JSON"), {
      target: { value: "invalid" },
    });
    await user.click(screen.getByRole("button", { name: "Create character" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Enter valid JSON");
    expect(
      fetchMock.mock.calls.some(([, init]) => init?.method === "POST"),
    ).toBe(false);
    fireEvent.change(screen.getByLabelText("Profile JSON"), {
      target: { value: "{}" },
    });
    await user.click(screen.getByRole("button", { name: "Create character" }));
    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/projects/A/characters/9"),
    );

    await router.navigate("/projects/A/characters/1");
    const name = await screen.findByLabelText("Display name");
    await user.clear(name);
    await user.type(name, "Changed");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Saved")).toBeInTheDocument();
  });

  it("reads states and knowledge from the selected episode without a knowledge write", async () => {
    const current = character(1);
    const knowledge: EffectiveKnowledgeRecord = {
      knowledge_state: "knows",
      event_episode_id: 20,
      event_id: 30,
      event_version: 1,
      information_item: {
        id: 40,
        work_id: 1,
        statement: "A secret",
        truth_status: "true",
        authoring_guard: "",
        notes_json: "{}",
        canon_status: "draft",
        importance: 1,
        version: 1,
        created_at: "",
        updated_at: "",
      },
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/characters/1"))
        return response({ project_id: "A", data: current });
      if (url.endsWith("/views/outline"))
        return response({ project_id: "A", data: outline() });
      if (url.includes("/states/20"))
        return response({ project_id: "A", data: null });
      if (url.endsWith("/characters/1/states"))
        return response({ project_id: "A", data: [] });
      if (url.includes("/knowledge?episode_id=20"))
        return response({ project_id: "A", data: [knowledge] });
      if (url.includes("/relationships?character_id=1"))
        return response({ project_id: "A", data: [] });
      return response(
        { error: { code: "NOT_FOUND", message: "Not found" } },
        404,
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute("/projects/A/characters/1");
    await screen.findByDisplayValue("A character 1");
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "States" }));
    expect(
      await screen.findByText("No state for this episode."),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Knowledge" }));
    expect(await screen.findByText("A secret")).toBeInTheDocument();
    expect(
      (
        fetchMock.mock.calls as unknown as Array<
          [RequestInfo | URL, RequestInit | undefined]
        >
      ).some(
        ([, init]) =>
          init?.method === "PUT" && String(init?.body).includes("knowledge"),
      ),
    ).toBe(false);
  });

  it("uses the returned relationship version as baseline and sends reason only with semantic edits", async () => {
    const currentCharacter = character(1);
    let currentRelationship = relationship();
    const patchBodies: unknown[] = [];
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/characters/1"))
          return response({ project_id: "A", data: currentCharacter });
        if (url.endsWith("/views/outline"))
          return response({ project_id: "A", data: outline() });
        if (url.includes("/relationships?character_id=1"))
          return response({ project_id: "A", data: [currentRelationship] });
        if (url.endsWith("/relationships/1") && init?.method === "PATCH") {
          const body = JSON.parse(String(init.body));
          patchBodies.push(body);
          currentRelationship = {
            ...currentRelationship,
            relationship_type: body.relationship_type,
            version: currentRelationship.version + 1,
          };
          return response({ project_id: "A", data: currentRelationship });
        }
        return response(
          { error: { code: "NOT_FOUND", message: "Not found" } },
          404,
        );
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    renderRoute("/projects/A/characters/1");
    const user = userEvent.setup();
    await screen.findByDisplayValue("A character 1");
    await user.click(screen.getByRole("tab", { name: "Relationships" }));
    const type = await screen.findByDisplayValue("ally");
    const reason = screen.getByLabelText("Reason (optional)");
    await user.type(reason, "  because  ");
    expect(
      screen.getByRole("button", { name: "Save relationship" }),
    ).toBeDisabled();
    await user.clear(type);
    await user.type(type, "rival");
    await user.click(screen.getByRole("button", { name: "Save relationship" }));
    await waitFor(() => expect(patchBodies).toHaveLength(1));
    expect(patchBodies[0]).toEqual({
      expected_version: 1,
      relationship_type: "rival",
      reason: "because",
    });
    expect(reason).toHaveValue("");

    const refreshedType = await screen.findByDisplayValue("rival");
    await user.clear(refreshedType);
    await user.type(refreshedType, "enemy");
    await user.click(screen.getByRole("button", { name: "Save relationship" }));
    await waitFor(() => expect(patchBodies).toHaveLength(2));
    expect(patchBodies[1]).toMatchObject({
      expected_version: 2,
      relationship_type: "enemy",
    });
    expect(patchBodies[1]).not.toHaveProperty("reason");
  });

  it("keeps relationship edits and old version after conflict, while guarding external navigation", async () => {
    const currentCharacter = character(1);
    const currentRelationship = relationship();
    const latest = {
      ...currentRelationship,
      relationship_type: "rival",
      version: 2,
    };
    const patchBodies: unknown[] = [];
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/characters/1"))
          return response({ project_id: "A", data: currentCharacter });
        if (url.endsWith("/views/outline"))
          return response({ project_id: "A", data: outline() });
        if (url.includes("/relationships?character_id=1"))
          return response({ project_id: "A", data: [currentRelationship] });
        if (url.endsWith("/relationships/1") && init?.method === "PATCH") {
          patchBodies.push(JSON.parse(String(init.body)));
          if (patchBodies.length === 1)
            return response(
              {
                error: {
                  code: "VERSION_CONFLICT",
                  message: "Conflict",
                  details: { current_resource: latest },
                },
              },
              409,
            );
          return response({ project_id: "A", data: latest });
        }
        return response(
          { error: { code: "NOT_FOUND", message: "Not found" } },
          404,
        );
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    const router = renderRoute("/projects/A/characters/1");
    const user = userEvent.setup();
    await screen.findByDisplayValue("A character 1");
    await user.click(screen.getByRole("tab", { name: "Relationships" }));
    const type = await screen.findByDisplayValue("ally");
    await user.clear(type);
    await user.type(type, "changed locally");
    await user.click(screen.getByRole("button", { name: "Save relationship" }));
    expect(
      await screen.findByText("This relationship changed elsewhere"),
    ).toBeInTheDocument();

    vi.spyOn(window, "confirm").mockReturnValue(false);
    await router.navigate("/projects/A/characters");
    expect(
      await screen.findByText("Leave without saving?"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Stay" }));
    expect(screen.getByDisplayValue("changed locally")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Keep local edits" }));
    const keptType = screen.getByDisplayValue("changed locally");
    await user.clear(keptType);
    await user.type(keptType, "changed again");
    await user.click(screen.getByRole("button", { name: "Save relationship" }));
    await waitFor(() => expect(patchBodies).toHaveLength(2));
    expect(patchBodies[1]).toMatchObject({ expected_version: 1 });
  });

  it("loads a current-resource relationship conflict before the next save", async () => {
    const currentCharacter = character(1);
    const currentRelationship = relationship();
    const latest = {
      ...currentRelationship,
      relationship_type: "rival",
      version: 2,
    };
    const next = { ...latest, relationship_type: "enemy", version: 3 };
    let relationshipReads = 0;
    const patchBodies: unknown[] = [];
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/characters/1"))
          return response({ project_id: "A", data: currentCharacter });
        if (url.endsWith("/views/outline"))
          return response({ project_id: "A", data: outline() });
        if (url.includes("/relationships?character_id=1")) {
          relationshipReads += 1;
          return response({
            project_id: "A",
            data: [relationshipReads === 1 ? currentRelationship : latest],
          });
        }
        if (url.endsWith("/relationships/1") && init?.method === "PATCH") {
          const body = JSON.parse(String(init.body));
          patchBodies.push(body);
          if (patchBodies.length === 1)
            return response(
              {
                error: {
                  code: "VERSION_CONFLICT",
                  message: "Conflict",
                  details: { current_resource: latest },
                },
              },
              409,
            );
          return response({ project_id: "A", data: next });
        }
        return response(
          { error: { code: "NOT_FOUND", message: "Not found" } },
          404,
        );
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    renderRoute("/projects/A/characters/1");
    const user = userEvent.setup();
    await screen.findByDisplayValue("A character 1");
    await user.click(screen.getByRole("tab", { name: "Relationships" }));
    const type = await screen.findByDisplayValue("ally");
    await user.clear(type);
    await user.type(type, "changed locally");
    await user.click(screen.getByRole("button", { name: "Save relationship" }));
    expect(
      await screen.findByText("This relationship changed elsewhere"),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", {
        name: "Load latest and discard local edits",
      }),
    );
    expect(relationshipReads).toBe(2);
    const latestType = await screen.findByDisplayValue("rival");
    await user.clear(latestType);
    await user.type(latestType, "enemy");
    await user.click(screen.getByRole("button", { name: "Save relationship" }));
    await waitFor(() => expect(patchBodies).toHaveLength(2));
    expect(patchBodies[1]).toMatchObject({ expected_version: 2 });
  });

  it("refetches the other relationship endpoint after create", async () => {
    const currentCharacterA = character(1, "A");
    const currentCharacterB = character(2, "A");
    let currentRelationship: RelationshipRecord | null = null;
    const relationshipReads = new Map<number, number>();
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/characters/1"))
          return response({ project_id: "A", data: currentCharacterA });
        if (url.endsWith("/characters/2"))
          return response({ project_id: "A", data: currentCharacterB });
        if (url.endsWith("/views/outline"))
          return response({ project_id: "A", data: outline() });
        const relationshipMatch = url.match(
          /\/relationships\?character_id=(\d+)/,
        );
        if (relationshipMatch) {
          const id = Number(relationshipMatch[1]);
          relationshipReads.set(id, (relationshipReads.get(id) ?? 0) + 1);
          return response({
            project_id: "A",
            data: currentRelationship ? [currentRelationship] : [],
          });
        }
        if (url.endsWith("/relationships") && init?.method === "POST") {
          const body = JSON.parse(String(init.body));
          currentRelationship = {
            ...relationship(10),
            source_character_id: body.source_character_id,
            target_character_id: body.target_character_id,
            relationship_type: body.relationship_type,
          };
          return response({ project_id: "A", data: currentRelationship }, 201);
        }
        return response(
          { error: { code: "NOT_FOUND", message: "Not found" } },
          404,
        );
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    const router = renderRoute("/projects/A/characters/2", 30_000);
    const user = userEvent.setup();
    await screen.findByDisplayValue("A character 2");
    await user.click(screen.getByRole("tab", { name: "Relationships" }));
    expect(
      await screen.findByText("No relationships yet."),
    ).toBeInTheDocument();
    expect(relationshipReads.get(2)).toBe(1);

    await router.navigate("/projects/A/characters/1");
    await screen.findByDisplayValue("A character 1");
    await user.click(screen.getByRole("tab", { name: "Relationships" }));
    await user.type(screen.getByLabelText("Other character ID"), "2");
    await user.type(screen.getByLabelText("Relationship type"), "ally");
    await user.click(
      screen.getByRole("button", { name: "Create relationship" }),
    );
    await waitFor(() =>
      expect(currentRelationship?.relationship_type).toBe("ally"),
    );

    await router.navigate("/projects/A/characters/2");
    await screen.findByDisplayValue("A character 2");
    await user.click(screen.getByRole("tab", { name: "Relationships" }));
    expect(await screen.findByDisplayValue("ally")).toBeInTheDocument();
    expect(relationshipReads.get(2)).toBe(2);
  });

  it("refetches the other relationship endpoint after update", async () => {
    const currentCharacterA = character(1, "A");
    const currentCharacterB = character(2, "A");
    let currentRelationship = relationship();
    const relationshipReads = new Map<number, number>();
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/characters/1"))
          return response({ project_id: "A", data: currentCharacterA });
        if (url.endsWith("/characters/2"))
          return response({ project_id: "A", data: currentCharacterB });
        if (url.endsWith("/views/outline"))
          return response({ project_id: "A", data: outline() });
        const relationshipMatch = url.match(
          /\/relationships\?character_id=(\d+)/,
        );
        if (relationshipMatch) {
          const id = Number(relationshipMatch[1]);
          relationshipReads.set(id, (relationshipReads.get(id) ?? 0) + 1);
          return response({ project_id: "A", data: [currentRelationship] });
        }
        if (url.endsWith("/relationships/1") && init?.method === "PATCH") {
          const body = JSON.parse(String(init.body));
          currentRelationship = {
            ...currentRelationship,
            relationship_type: body.relationship_type,
            version: 2,
          };
          return response({ project_id: "A", data: currentRelationship });
        }
        return response(
          { error: { code: "NOT_FOUND", message: "Not found" } },
          404,
        );
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    const router = renderRoute("/projects/A/characters/2", 30_000);
    const user = userEvent.setup();
    await screen.findByDisplayValue("A character 2");
    await user.click(screen.getByRole("tab", { name: "Relationships" }));
    await screen.findByDisplayValue("ally");
    expect(relationshipReads.get(2)).toBe(1);

    await router.navigate("/projects/A/characters/1");
    await screen.findByDisplayValue("A character 1");
    await user.click(screen.getByRole("tab", { name: "Relationships" }));
    const type = await screen.findByDisplayValue("ally");
    await user.clear(type);
    await user.type(type, "rival");
    await user.click(screen.getByRole("button", { name: "Save relationship" }));
    await waitFor(() =>
      expect(currentRelationship.relationship_type).toBe("rival"),
    );

    await router.navigate("/projects/A/characters/2");
    await screen.findByDisplayValue("A character 2");
    await user.click(screen.getByRole("tab", { name: "Relationships" }));
    expect(await screen.findByDisplayValue("rival")).toBeInTheDocument();
    expect(relationshipReads.get(2)).toBe(2);
  });

  it("does not save an unchanged state and confirms dirty episode switches", async () => {
    const view = outline();
    const firstEpisode = view.chapters[0].episodes[0].episode;
    view.chapters[0].episodes.push({
      ...view.chapters[0].episodes[0],
      episode: { ...firstEpisode, id: 21, title: "Episode 2" },
    });
    const currentCharacter = character(1);
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/characters/1"))
        return response({ project_id: "A", data: currentCharacter });
      if (url.endsWith("/views/outline"))
        return response({ project_id: "A", data: view });
      if (url.includes("/states/20") || url.includes("/states/21"))
        return response({ project_id: "A", data: null });
      if (url.endsWith("/characters/1/states"))
        return response({ project_id: "A", data: [] });
      return response(
        { error: { code: "NOT_FOUND", message: "Not found" } },
        404,
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute("/projects/A/characters/1");
    const user = userEvent.setup();
    await screen.findByDisplayValue("A character 1");
    await user.click(screen.getByRole("tab", { name: "States" }));
    expect(
      await screen.findByText("No state for this episode."),
    ).toBeInTheDocument();
    const save = screen.getByRole("button", { name: "Save state" });
    expect(save).toBeDisabled();
    await user.type(screen.getByLabelText("Physical state"), "injured");
    expect(save).toBeEnabled();
    vi.spyOn(window, "confirm").mockReturnValue(false);
    fireEvent.change(screen.getByLabelText("Episode"), {
      target: { value: "21" },
    });
    expect(screen.getByLabelText("Episode")).toHaveValue("20");
    vi.mocked(window.confirm).mockReturnValue(true);
    fireEvent.change(screen.getByLabelText("Episode"), {
      target: { value: "21" },
    });
    await waitFor(() =>
      expect(screen.getByLabelText("Episode")).toHaveValue("21"),
    );
  });

  it("loads a relationship conflict fallback without retrying the write", async () => {
    const currentCharacter = character(1);
    const currentRelationship = relationship();
    const latest = {
      ...currentRelationship,
      relationship_type: "rival",
      version: 2,
    };
    let relationshipReads = 0;
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/characters/1"))
          return response({ project_id: "A", data: currentCharacter });
        if (url.endsWith("/views/outline"))
          return response({ project_id: "A", data: outline() });
        if (url.includes("/relationships?character_id=1")) {
          relationshipReads += 1;
          return response({
            project_id: "A",
            data: [relationshipReads === 1 ? currentRelationship : latest],
          });
        }
        if (url.endsWith("/relationships/1") && init?.method === "PATCH")
          return response(
            {
              error: {
                code: "VERSION_CONFLICT",
                message: "Conflict",
                details: {},
              },
            },
            409,
          );
        return response(
          { error: { code: "NOT_FOUND", message: "Not found" } },
          404,
        );
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    renderRoute("/projects/A/characters/1");
    const user = userEvent.setup();
    await screen.findByDisplayValue("A character 1");
    await user.click(screen.getByRole("tab", { name: "Relationships" }));
    const type = await screen.findByDisplayValue("ally");
    await user.clear(type);
    await user.type(type, "changed locally");
    await user.click(screen.getByRole("button", { name: "Save relationship" }));
    expect(
      await screen.findByText("This relationship changed elsewhere"),
    ).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toHaveTextContent(
      '"relationship_type": "rival"',
    );
    await user.click(
      screen.getByRole("button", {
        name: "Load latest and discard local edits",
      }),
    );
    expect(await screen.findByDisplayValue("rival")).toBeInTheDocument();
    expect(relationshipReads).toBe(3);
    expect(
      fetchMock.mock.calls.filter(([, request]) => request?.method === "PATCH"),
    ).toHaveLength(1);
  });

  it("keeps the relationship query cache aligned after Canon loads the latest", async () => {
    const currentCharacter = character(1);
    const currentRelationship = relationship();
    const latest = { ...currentRelationship, relationship_type: "rival", canon_status: "canon", version: 2 };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/characters?limit=50&offset=0")) return response({ project_id: "A", data: [currentCharacter] });
      if (url.endsWith("/characters/1")) return response({ project_id: "A", data: currentCharacter });
      if (url.endsWith("/views/outline")) return response({ project_id: "A", data: outline() });
      if (url.includes("/relationships?character_id=1")) return response({ project_id: "A", data: [currentRelationship] });
      if (url.endsWith("/canon/status") && init?.method === "POST") return response({ error: { code: "VERSION_CONFLICT", message: "Changed elsewhere", details: { current_resource: latest } } }, 409);
      return response({ error: { code: "NOT_FOUND", message: "Not found" } }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 10_000 } } });
    queryClient.setQueryData(projectQueryKeys.character("A", 1), currentCharacter);
    queryClient.setQueryData(projectQueryKeys.outline("A"), outline());
    queryClient.setQueryData(projectQueryKeys.relationships("A", 1), [currentRelationship]);
    const router = renderWithQueryClient("/projects/A/characters/1", queryClient);
    const user = userEvent.setup();
    await screen.findByDisplayValue("A character 1");
    await user.click(screen.getByRole("tab", { name: "Relationships" }));
    await screen.findByDisplayValue("ally");
    const canonStatus = document.getElementById("relationship-1-target-status");
    if (!canonStatus) throw new Error("Relationship canon status control not found");
    await user.selectOptions(canonStatus, "canon");
    await user.click(screen.getAllByRole("button", { name: "Change canon status" })[0]);
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: "Load latest and discard local edits" }));
    await waitFor(() => expect(queryClient.getQueryData(projectQueryKeys.relationships("A", 1))).toEqual([latest]));
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);

    await router.navigate("/projects/A/characters");
    await router.navigate("/projects/A/characters/1");
    await user.click(screen.getByRole("tab", { name: "Relationships" }));
    expect(await screen.findByDisplayValue("rival")).toBeInTheDocument();
    expect(screen.getByText("Current status: canon · version 2")).toBeInTheDocument();
  });

  it("keeps state edits across conflict fallback and compares JSON semantically", async () => {
    const currentCharacter = character(1);
    const currentState = characterState();
    const latest = characterState(20, 2, "latest");
    let stateReads = 0;
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/characters/1"))
          return response({ project_id: "A", data: currentCharacter });
        if (url.endsWith("/views/outline"))
          return response({ project_id: "A", data: outline() });
        if (url.includes("/characters/1/states/20") && init?.method === "PUT")
          return response(
            {
              error: {
                code: "VERSION_CONFLICT",
                message: "Conflict",
                details: {},
              },
            },
            409,
          );
        if (url.includes("/characters/1/states/20")) {
          stateReads += 1;
          return response({
            project_id: "A",
            data: stateReads === 1 ? currentState : latest,
          });
        }
        if (url.endsWith("/characters/1/states"))
          return response({ project_id: "A", data: [currentState] });
        return response(
          { error: { code: "NOT_FOUND", message: "Not found" } },
          404,
        );
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    renderRoute("/projects/A/characters/1");
    const user = userEvent.setup();
    await screen.findByDisplayValue("A character 1");
    await user.click(screen.getByRole("tab", { name: "States" }));
    const beliefs = await screen.findByLabelText("Beliefs JSON");
    fireEvent.change(beliefs, {
      target: { value: '{"b":2,"a":1}' },
    });
    const save = screen.getByRole("button", { name: "Save state" });
    expect(save).toBeDisabled();
    const physical = screen.getByLabelText("Physical state");
    await user.clear(physical);
    await user.type(physical, "local");
    expect(save).toBeEnabled();
    await user.click(save);
    expect(
      await screen.findByText("This character state changed elsewhere"),
    ).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toHaveTextContent(
      '"physical_state": "latest"',
    );
    await user.click(
      screen.getByRole("button", {
        name: "Load latest and discard local edits",
      }),
    );
    expect(await screen.findByLabelText("Physical state")).toHaveValue(
      "latest",
    );
    expect(screen.getByRole("button", { name: "Save state" })).toBeDisabled();
    expect(
      fetchMock.mock.calls.filter(([, request]) => request?.method === "PUT"),
    ).toHaveLength(1);
  });
});

function renderWithQueryClient(initialEntry: string, queryClient: QueryClient) {
  const router = createMemoryRouter(appRoutes, {
    initialEntries: [initialEntry],
  });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}
