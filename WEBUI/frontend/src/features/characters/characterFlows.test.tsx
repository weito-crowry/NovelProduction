import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { appRoutes } from "../../app/routes";
import type {
  CharacterRecord,
  EffectiveKnowledgeRecord,
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

function renderRoute(initialEntry: string) {
  const router = createMemoryRouter(appRoutes, {
    initialEntries: [initialEntry],
  });
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
      (fetchMock.mock.calls as unknown as Array<[RequestInfo | URL, RequestInit | undefined]>).some(
        ([, init]) =>
          init?.method === "PUT" && String(init?.body).includes("knowledge"),
      ),
    ).toBe(false);
  });
});
