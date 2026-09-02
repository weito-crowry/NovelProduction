import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { appRoutes } from "../../app/routes";

function envelope(data: unknown) {
  return JSON.stringify({ project_id: "demo", data });
}

function renderRoute(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(appRoutes, { initialEntries: [path] });
  render(<QueryClientProvider client={queryClient}><RouterProvider router={router} /></QueryClientProvider>);
  return router;
}

describe("style analysis WebUI flows", () => {
  it("offers local-only source import and shows duplicate-safe import feedback", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/reference-works") && (!init || init.method === undefined)) {
        return new Response(envelope([]), { status: 200 });
      }
      if (url.endsWith("/imports/file")) {
        return new Response(envelope({ reused_existing: true, reference_work_id: 7, source_id: 8 }), { status: 200 });
      }
      return new Response(envelope([]), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderRoute("/projects/demo/style-analysis/sources");

    expect(await screen.findByRole("heading", { name: "Sources" })).toBeInTheDocument();
    expect(screen.queryByLabelText(/URL/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Refresh/i })).not.toBeInTheDocument();
    const file = new File(["短い本文"], "sample.txt", { type: "text/plain" });
    const input = screen.getByLabelText("Local file");
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.submit(input.closest("form") as HTMLFormElement);
    expect(await screen.findByText(/既存Sourceを再利用しました/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/imports/file"), expect.objectContaining({ method: "POST" }));
  });

  it("polls an analysis job and renders its terminal result", async () => {
    let jobReads = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/reference-works")) return new Response(envelope([{ reference_work_id: 7, source_id: 8, source_type: "text", title: "Sample", author_name: null, episode_count: 1, created_at: "now" }]), { status: 200 });
      if (url.endsWith("/reference-works/7") && (!init || init.method === undefined)) return new Response(envelope({ reference_work_id: 7, source_id: 8, source_type: "text", title: "Sample", author_name: null, episode_count: 1, created_at: "now" }), { status: 200 });
      if (url.endsWith("/reference-works/7/episodes")) return new Response(envelope([{ reference_episode_id: 9, reference_work_id: 7, title: "Episode", order_index: 1, style_document_id: 10, current_text_revision_id: 2, current_structure_revision_id: 3, current_structure_kind: "paragraph", analysis_status: { basic: { state: "not_analyzed" }, semantic: { state: "not_analyzed" } } }]), { status: 200 });
      if (url.endsWith("/reference-works/7/analyze")) return new Response(envelope({ job_id: 11, job_type: "analyze_reference_work", status: "queued", progress: { current: 0, total: 1 }, result: {}, warnings: [], error_code: null, error_message: null }), { status: 202 });
      if (url.endsWith("/jobs/11")) {
        jobReads += 1;
        const status = jobReads > 1 ? "succeeded" : "running";
        return new Response(envelope({ job_id: 11, job_type: "analyze_reference_work", status, progress: { current: status === "succeeded" ? 1 : 0, total: 1 }, result: { analysis_run_id: 12 }, warnings: [], error_code: null, error_message: null }), { status: 200 });
      }
      return new Response(envelope([]), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderRoute("/projects/demo/style-analysis/reference-works/7");
    expect(await screen.findByRole("heading", { name: "Sample" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Deterministic analyze" }));
    expect(await screen.findByText("Analysis job #11")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("succeeded")).toBeInTheDocument(), { timeout: 3000 });
    expect(screen.getByText(/analysis_run_id/)).toBeInTheDocument();
    expect(jobReads).toBeGreaterThan(1);
    fireEvent.click(screen.getByRole("link", { name: "Document" }));
    expect(await screen.findByRole("heading", { name: /Document Analysis #10/ })).toBeInTheDocument();
  });

  it("captures a project draft and exposes the captured document to lint", async () => {
    let captureBody: unknown = null;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/views/outline")) {
        return new Response(JSON.stringify({ project_id: "demo", data: { chapters: [{ chapter: { id: 1 }, episodes: [{ episode: { id: 2, title: "Draft episode" }, scenes: [] }] }] } }), { status: 200 });
      }
      if (url.includes("/episodes/2/drafts?limit=1")) {
        return new Response(envelope([{ id: 15, episode_id: 2, revision: 3, parent_draft_id: 14, source_agent: "webui", change_summary: "Latest draft", created_at: "now" }]), { status: 200 });
      }
      if (url.endsWith("/project-episodes/2/capture") && init?.method === "POST") {
        captureBody = JSON.parse(String(init.body));
        return new Response(envelope({ document_id: 21, kind: "project_episode_draft", current_text_revision_id: 8, current_structure_revision_id: 9, current_structure_kind: "manual", captured_text_revision_id: 8, draft_id: 15, analysis_status: { basic: { state: "not_analyzed" }, semantic: { state: "not_analyzed" } } }), { status: 200 });
      }
      if (url.endsWith("/profiles")) return new Response(envelope([]), { status: 200 });
      if (url.endsWith("/documents/21/revisions")) return new Response(envelope([{ id: 7, document_id: 21, revision_no: 1 }, { id: 8, document_id: 21, revision_no: 2 }]), { status: 200 });
      if (url.endsWith("/documents/21/structures")) return new Response(envelope([{ id: 6, document_id: 21, text_revision_id: 7, revision_no: 1, source_kind: "automatic" }, { id: 9, document_id: 21, text_revision_id: 8, revision_no: 2, source_kind: "manual" }]), { status: 200 });
      if (url.includes("/lint-runs?document_id=21")) return new Response(envelope([{ id: 99, document_id: 21, text_revision_id: 7, structure_revision_id: 6, profile_id: 3, profile_version_id: 4, scene_id: null, status: "succeeded", warnings: [], enabled_rule_count: 1, applicable_rule_count: 1, missing_rule_count: 0, coverage_ratio: 1, stale: false, created_at: "now", finished_at: "now" }]), { status: 200 });
      if (url.endsWith("/lint-runs")) return new Response(envelope([]), { status: 200 });
      return new Response(envelope([]), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderRoute("/projects/demo/style-analysis/lint");

    expect(await screen.findByRole("heading", { name: "Lint" })).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Capture latest Project Draft" }));
    expect(await screen.findByText(/Project DraftをCaptureしました/)).toBeInTheDocument();
    expect(captureBody).toEqual({ draft_id: 15 });
    expect(screen.getByLabelText("Document")).toHaveValue("21");
    expect(screen.getByRole("link", { name: /Document #21/ })).toHaveAttribute("href", "/projects/demo/style-analysis/documents/21");
    expect(await screen.findByLabelText("Text revision")).toHaveValue("8");
    expect(screen.getByLabelText("Text revision")).toHaveTextContent("7");
    expect(screen.getByLabelText("Structure revision")).toHaveTextContent("9");
    await user.selectOptions(screen.getByLabelText("Text revision"), "7");
    expect(screen.getByLabelText("Structure revision")).toHaveTextContent("6");
  });

  it("submits selected text and structure revisions and can request a rebuild", async () => {
    let analyzeBody: unknown = null;
    let overrideBody: unknown = null;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/reference-works")) return new Response(envelope([{ reference_work_id: 7, source_id: 8, source_type: "text", title: "Sample", author_name: null, episode_count: 1, created_at: "now" }]), { status: 200 });
      if (url.endsWith("/reference-works/7/episodes")) return new Response(envelope([{ reference_episode_id: 9, reference_work_id: 7, title: "Episode", order_index: 1, style_document_id: 10, current_text_revision_id: 2, current_structure_revision_id: 3, current_structure_kind: "paragraph", analysis_status: { basic: { state: "not_analyzed" }, semantic: { state: "not_analyzed" } } }]), { status: 200 });
      if (url.endsWith("/documents/10/revisions")) return new Response(envelope([{ id: 5, document_id: 10, revision_no: 1 }]), { status: 200 });
      if (url.endsWith("/documents/10/structures")) return new Response(envelope([{ id: 6, document_id: 10, text_revision_id: 5, revision_no: 1, source_kind: "automatic" }]), { status: 200 });
      if (url.endsWith("/documents/10/runs")) return new Response(envelope([{ id: 20, analyzer_id: "basic", analyzer_version: 1, text_revision_id: 5, structure_revision_id: 6, status: "succeeded", started_at: "now", finished_at: "now" }]), { status: 200 });
      if (url.includes("/documents/10/semantics?structure_revision_id=6")) return new Response(envelope({ structure_revision_id: 6, analysis_status: {}, effective: {}, outputs: [{ id: 41, annotation_type: "speaker", subject_type: "block", subject_id: 42, value: { speaker_entity_id: 8 }, confidence: 0.9, analysis_run_id: 50, start_cp: 0, end_cp: 3, created_at: "now" }] }), { status: 200 });
      if (url.endsWith("/overrides") && init?.method === "POST") {
        overrideBody = JSON.parse(String(init.body));
        return new Response(envelope({ id: 60 }), { status: 201 });
      }
      if (url.endsWith("/documents/10/analyze") && init?.method === "POST") {
        analyzeBody = JSON.parse(String(init.body));
        return new Response(envelope({ job_id: 30, job_type: "analyze_document", status: "queued", progress: { current: 0, total: 1 }, result: {}, warnings: [], error_code: null, error_message: null }), { status: 202 });
      }
      if (url.endsWith("/jobs/30")) return new Response(envelope({ job_id: 30, job_type: "analyze_document", status: "succeeded", progress: { current: 1, total: 1 }, result: {}, warnings: [], error_code: null, error_message: null }), { status: 200 });
      return new Response(envelope([]), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderRoute("/projects/demo/style-analysis/documents/10");

    expect(await screen.findByRole("heading", { name: "Document Analysis #10" })).toBeInTheDocument();
    await user.selectOptions(await screen.findByLabelText("Text revision"), "5");
    await user.selectOptions(screen.getByLabelText("Structure revision"), "6");
    await user.click(screen.getByLabelText("Rebuild structure"));
    await user.click(screen.getByRole("button", { name: "Analyze selected revisions" }));
    await waitFor(() => expect(analyzeBody).toEqual({ text_revision_id: 5, preset: "deterministic", rebuild_structure: true }));
    expect(screen.getByRole("tab", { name: "Text" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Structure" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Semantics" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Metrics" })).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Semantics" }));
    await user.click(await screen.findByRole("button", { name: "Override speaker" }));
    await waitFor(() => expect(overrideBody).toEqual({ document_id: 10, subject_type: "block", subject_id: 42, field_path: "block.speaker_entity_id", operation: "set", value: 8, base_analysis_run_id: 50, structure_revision_id: 6, note: "SA-H WebUI" }));
  });

  it("submits manual split against the selected current structure", async () => {
    let structureId = 6;
    let splitBody: unknown = null;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/reference-works")) return new Response(envelope([]), { status: 200 });
      if (url.endsWith("/documents")) return new Response(envelope([{ document_id: 10, kind: "project_episode_draft", current_text_revision_id: 5, current_structure_revision_id: structureId, current_structure_kind: structureId === 6 ? "automatic" : "manual", analysis_status: { basic: { state: "succeeded" }, semantic: { state: "not_analyzed" } } }]), { status: 200 });
      if (url.endsWith("/documents/10/revisions")) return new Response(envelope([{ id: 5, document_id: 10, revision_no: 1 }]), { status: 200 });
      if (url.endsWith("/documents/10/structures")) return new Response(envelope([{ id: structureId, document_id: 10, text_revision_id: 5, revision_no: structureId === 6 ? 1 : 2, source_kind: structureId === 6 ? "automatic" : "manual" }]), { status: 200 });
      if (url.includes("/documents/10/structure?structure_revision_id=")) {
        const id = structureId;
        return new Response(envelope({ id, document_id: 10, text_revision_id: 5, revision_no: id === 6 ? 1 : 2, segmenter_id: id === 6 ? "automatic" : "manual", segmenter_version: 1, source_kind: id === 6 ? "automatic" : "manual", parent_structure_revision_id: id === 6 ? null : 6, fingerprint: `fp-${id}`, created_at: "now", scene_count: id === 6 ? 1 : 2, block_count: 2, scenes: id === 6 ? [{ id: 1 }] : [{ id: 11 }, { id: 12 }], blocks: [{ id: 2, scene_id: id === 6 ? 1 : 11 }, { id: 3, scene_id: id === 6 ? 1 : 12 }], sentences: [] }), { status: 200 });
      }
      if (url.endsWith("/documents/10/scenes/1/split") && init?.method === "POST") {
        splitBody = JSON.parse(String(init.body));
        structureId = 7;
        return new Response(envelope({ id: 7, document_id: 10, text_revision_id: 5, revision_no: 2, segmenter_id: "manual", segmenter_version: 1, source_kind: "manual", parent_structure_revision_id: 6, fingerprint: "fp-7", created_at: "now", scene_count: 2, block_count: 2, scenes: [{ id: 11 }, { id: 12 }], blocks: [{ id: 2, scene_id: 11 }, { id: 3, scene_id: 12 }], sentences: [] }), { status: 200 });
      }
      return new Response(envelope([]), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderRoute("/projects/demo/style-analysis/documents/10");

    await user.click(await screen.findByRole("tab", { name: "Structure" }));
    await user.type(screen.getByLabelText("Split scene ID"), "1");
    await user.type(screen.getByLabelText("Split after block ID"), "2");
    await user.click(screen.getByRole("button", { name: "Split scene" }));

    await waitFor(() => expect(splitBody).toEqual({ after_block_id: 2, expected_structure_revision_id: 6 }));
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/documents/10/scenes/1/split"), expect.objectContaining({ method: "POST" }));
  });

  it("submits the selected review priority", async () => {
    let reviewBody: unknown = null;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/review-items?status=open")) return new Response(envelope([]), { status: 200 });
      if (url.endsWith("/review-items") && init?.method === "POST") {
        reviewBody = JSON.parse(String(init.body));
        return new Response(envelope({ id: 1, subject_type: "scene", subject_id: 2, analysis_run_id: null, priority: "high", status: "open", reason_code: "MANUAL", evidence: {}, resolution_note: null, version: 1 }), { status: 201 });
      }
      return new Response(envelope([]), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderRoute("/projects/demo/style-analysis/review");
    await user.type(await screen.findByLabelText("Subject ID"), "2");
    await user.selectOptions(screen.getByLabelText("Priority"), "high");
    await user.click(screen.getByRole("button", { name: "Create ReviewItem" }));
    await waitFor(() => expect(reviewBody).toEqual({ subject_type: "scene", subject_id: 2, priority: "high" }));
  });

  it("submits aggregate target, filter, and metric selections", async () => {
    let aggregateBody: unknown = null;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/corpora")) return new Response(envelope([{ id: 1, name: "Reference corpus", description: "", created_at: "now", updated_at: "now" }]), { status: 200 });
      if (url.endsWith("/corpora/1")) return new Response(envelope({ id: 1, name: "Reference corpus" }), { status: 200 });
      if (url.endsWith("/corpora/1/aggregates")) return new Response(envelope([]), { status: 200 });
      if (url.endsWith("/corpora/1/aggregates/recompute") && init?.method === "POST") {
        aggregateBody = JSON.parse(String(init.body));
        return new Response(envelope({ job_id: 40, job_type: "recompute_aggregates", status: "queued", progress: { current: 0, total: 1 }, result: {}, warnings: [], error_code: null, error_message: null }), { status: 202 });
      }
      if (url.endsWith("/jobs/40")) return new Response(envelope({ job_id: 40, job_type: "recompute_aggregates", status: "succeeded", progress: { current: 1, total: 1 }, result: {}, warnings: [], error_code: null, error_message: null }), { status: 200 });
      return new Response(envelope([]), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderRoute("/projects/demo/style-analysis/corpora");
    await user.click(await screen.findByRole("button", { name: /Reference corpus/ }));
    await user.selectOptions(await screen.findByLabelText("Aggregate target"), "scene");
    await user.clear(screen.getByLabelText("Aggregate filter JSON"));
    fireEvent.change(screen.getByLabelText("Aggregate filter JSON"), { target: { value: '{"scene":{"function":["daily"]}}' } });
    await user.click(screen.getByLabelText("Metric sentence.len.p90"));
    await user.click(screen.getByRole("button", { name: "Recompute aggregates" }));
    await waitFor(() => expect(aggregateBody).toEqual({ measurement_target_type: "scene", filter: { scene: { function: ["daily"] } }, metric_names: ["sentence.len.p50", "paragraph.len.p50", "paragraph.len.p90"] }));
  });

  it("submits a fully specified manual profile rule", async () => {
    let profileBody: unknown = null;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/profiles") && (!init || !init.method)) return new Response(envelope([]), { status: 200 });
      if (url.endsWith("/corpora")) return new Response(envelope([]), { status: 200 });
      if (url.endsWith("/profiles/manual") && init?.method === "POST") {
        profileBody = JSON.parse(String(init.body));
        return new Response(envelope({ profile: {}, versions: [] }), { status: 201 });
      }
      return new Response(envelope([]), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderRoute("/projects/demo/style-analysis/profiles");
    await user.type(await screen.findByLabelText("Name", { selector: "#style-profile-name" }), "Scene profile");
    await user.selectOptions(screen.getByLabelText("Target scope"), "scene");
    await user.clear(screen.getByLabelText("Scope selector JSON"));
    fireEvent.change(screen.getByLabelText("Scope selector JSON"), { target: { value: '{"function":["exposition"]}' } });
    await user.clear(screen.getByLabelText("Minimum"));
    await user.type(screen.getByLabelText("Minimum"), "4.5");
    await user.clear(screen.getByLabelText("Maximum"));
    await user.type(screen.getByLabelText("Maximum"), "8.5");
    await user.click(screen.getByRole("button", { name: "Save draft profile" }));
    await waitFor(() => expect(profileBody).toEqual({ name: "Scene profile", description: "", rules: [{ target_scope: "scene", scope_selector: { function: ["exposition"] }, metric_name: "sentence.len.p50", metric_version: 1, preferred_value: 0, min_value: 4.5, max_value: 8.5, weight: 1, enabled: true, severity_policy: "standard" }] }));
  });

  it("submits semantic entity, term, alias, character-link, and override corrections", async () => {
    const requests: Array<{ url: string; body: unknown }> = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/reference-works")) return new Response(envelope([]), { status: 200 });
      if (url.endsWith("/documents")) return new Response(envelope([{ document_id: 10, kind: "project_episode_draft", current_text_revision_id: 5, current_structure_revision_id: 6, current_structure_kind: "automatic", analysis_status: { basic: { state: "succeeded" }, semantic: { state: "succeeded" } } }]), { status: 200 });
      if (url.endsWith("/documents/10/revisions")) return new Response(envelope([{ id: 5, document_id: 10, revision_no: 1 }]), { status: 200 });
      if (url.endsWith("/documents/10/structures")) return new Response(envelope([{ id: 6, document_id: 10, text_revision_id: 5, revision_no: 1, source_kind: "automatic" }]), { status: 200 });
      if (url.includes("/documents/10/semantics?structure_revision_id=6")) return new Response(envelope({ structure_revision_id: 6, analysis_status: {}, effective: {}, outputs: [], inference_targets: [{ id: 77, annotation_type: "entity_alias", subject_type: "entity_alias", subject_id: 77, value: { alias: "A" }, confidence: null, analysis_run_id: 50, start_cp: null, end_cp: null, created_at: "now" }] }), { status: 200 });
      if (["/entities", "/terms", "/overrides", "/inference-reviews"].some((suffix) => url.endsWith(suffix)) || url.includes("/aliases") || url.includes("/character-links/")) {
        requests.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null });
        return new Response(envelope({ id: 101 }), { status: 201 });
      }
      return new Response(envelope([]), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderRoute("/projects/demo/style-analysis/documents/10");

    await user.click(await screen.findByRole("tab", { name: "Semantics" }));
    expect(await screen.findByRole("heading", { name: "Manual Entity" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Canonical name"), "Alice");
    await user.click(screen.getByRole("button", { name: "Create Entity" }));
    await user.type(screen.getByLabelText("Entity ID"), "101");
    await user.type(screen.getByLabelText("Entity alias"), "A");
    await user.click(screen.getByRole("button", { name: "Create Entity Alias" }));
    await user.type(screen.getByLabelText("Canonical label"), "Skyline");
    await user.click(screen.getByRole("button", { name: "Create Term" }));
    await user.type(screen.getByLabelText("Term ID"), "202");
    await user.type(screen.getByLabelText("Term alias"), "SL");
    await user.click(screen.getByRole("button", { name: "Create Term Alias" }));
    await user.type(screen.getByLabelText("Project character ID"), "303");
    await user.type(screen.getByLabelText("Linked Entity ID"), "101");
    await user.click(screen.getByRole("button", { name: "Link Character" }));
    await user.click(await screen.findByRole("button", { name: "Unlink Character" }));
    await user.type(screen.getByLabelText("Override subject ID"), "404");
    await user.clear(screen.getByLabelText("Override value JSON"));
    await user.type(screen.getByLabelText("Override value JSON"), "5");
    await user.click(screen.getByRole("button", { name: "Save Semantic Override" }));
    await user.selectOptions(screen.getByLabelText("Operation"), "clear");
    await user.click(screen.getByRole("button", { name: "Save Semantic Override" }));
    await user.click(screen.getByRole("button", { name: "Confirm" }));

    await waitFor(() => expect(requests).toEqual([
      { url: expect.stringContaining("/entities"), body: { document_id: 10, entity_type: "person", canonical_name: "Alice" } },
      { url: expect.stringContaining("/entities/101/aliases"), body: { alias: "A", alias_kind: "name" } },
      { url: expect.stringContaining("/terms"), body: { document_id: 10, canonical_label: "Skyline", term_type: "world_term" } },
      { url: expect.stringContaining("/terms/202/aliases"), body: { alias: "SL" } },
      { url: expect.stringContaining("/character-links/303"), body: { style_entity_id: 101 } },
      { url: expect.stringContaining("/character-links/303"), body: null },
      { url: expect.stringContaining("/overrides"), body: { subject_type: "block", subject_id: 404, field_path: "block.speaker_entity_id", operation: "set", value: 5, document_id: 10, structure_revision_id: 6, note: "SA-H WebUI" } },
      { url: expect.stringContaining("/overrides"), body: { subject_type: "block", subject_id: 404, field_path: "block.speaker_entity_id", operation: "clear", value: null, document_id: 10, structure_revision_id: 6, note: "SA-H WebUI" } },
      { url: expect.stringContaining("/inference-reviews"), body: { analysis_run_id: 50, subject_type: "entity_alias", subject_id: 77, field_path: "entity_alias.acceptance", review_status: "confirmed", note: "SA-H WebUI" } },
    ]));
  });
});
