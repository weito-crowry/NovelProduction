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
    expect(screen.getByLabelText("Structure revision")).toHaveTextContent("6");
  });

  it("submits selected text and structure revisions and can request a rebuild", async () => {
    let analyzeBody: unknown = null;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/reference-works")) return new Response(envelope([{ reference_work_id: 7, source_id: 8, source_type: "text", title: "Sample", author_name: null, episode_count: 1, created_at: "now" }]), { status: 200 });
      if (url.endsWith("/reference-works/7/episodes")) return new Response(envelope([{ reference_episode_id: 9, reference_work_id: 7, title: "Episode", order_index: 1, style_document_id: 10, current_text_revision_id: 2, current_structure_revision_id: 3, current_structure_kind: "paragraph", analysis_status: { basic: { state: "not_analyzed" }, semantic: { state: "not_analyzed" } } }]), { status: 200 });
      if (url.endsWith("/documents/10/runs")) return new Response(envelope([{ id: 20, analyzer_id: "basic", analyzer_version: 1, text_revision_id: 5, structure_revision_id: 6, status: "succeeded", started_at: "now", finished_at: "now" }]), { status: 200 });
      if (url.includes("/documents/10/semantics?structure_revision_id=3")) return new Response(envelope({ structure_revision_id: 3, analysis_status: {}, effective: {}, outputs: [] }), { status: 200 });
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
    fireEvent.change(screen.getByLabelText("Aggregate filter JSON"), { target: { value: '{"function":["exposition"]}' } });
    await user.click(screen.getByLabelText("Metric sentence.len.p90"));
    await user.click(screen.getByRole("button", { name: "Recompute aggregates" }));
    await waitFor(() => expect(aggregateBody).toEqual({ measurement_target_type: "scene", filter: { function: ["exposition"] }, metric_names: ["sentence.len.p50", "paragraph.len.p50", "paragraph.len.p90"] }));
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
});
