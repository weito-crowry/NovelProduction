import { expect, test } from "@playwright/test";
import { createChapter, createEpisode, createProjectInUi, saveStructuredDraft } from "./helpers";

function envelope(projectId: string, data: unknown) {
  return JSON.stringify({ project_id: projectId, data });
}

test("runs the style analysis UI flow with mocked style-analysis responses", async ({ page, request }) => {
  const projectId = await createProjectInUi(page, "e2e-style");
  const chapter = await createChapter(request, projectId, "capture chapter");
  const episode = await createEpisode(request, projectId, chapter.id, "capture episode");
  const draft = await saveStructuredDraft(request, projectId, episode.id, {
    html: '<p data-np-type="narration">Captured style-analysis fixture.</p>',
    source_agent: "style-analysis-e2e",
    change_summary: "Project draft capture fixture",
  });
  const captureResponse = await request.post(`/api/v1/projects/${projectId}/style-analysis/project-episodes/${episode.id}/capture`, { data: { draft_id: draft.id } });
  expect(captureResponse.status()).toBe(200);
  const capturePayload = (await captureResponse.json()) as { data: { document_id: number } };
  expect(capturePayload.data.document_id).toBeGreaterThan(0);
  let imported = false;
  let profileCreated = false;
  let corpusProfilePayload: unknown = null;
  let findingReviewed = false;
  let profilePostCount = 0;
  const jobReads = new Map<number, number>();

  await page.route(/\/api\/v1\/projects\/[^/]+\/style-analysis(?:\/.*)?$/, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const respond = (data: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: envelope(projectId, data) });

    if (path.endsWith("/imports/file") && method === "POST") {
      imported = true;
      return respond({ reused_existing: false, reference_work_id: 7, source_id: 8 }, 201);
    }
    if (path.endsWith("/reference-works") && method === "GET") {
      return respond(imported ? [{ reference_work_id: 7, source_id: 8, source_type: "text", title: "Mock reference", author_name: "Fixture Author", episode_count: 1, created_at: "now" }] : []);
    }
    if (path.endsWith("/reference-works/7") && method === "GET") {
      return respond({ reference_work_id: 7, source_id: 8, source_type: "text", title: "Mock reference", author_name: "Fixture Author", episode_count: 1, created_at: "now" });
    }
    if (path.endsWith("/reference-works/7/episodes") && method === "GET") {
      return respond([{ reference_episode_id: 9, reference_work_id: 7, title: "Mock episode", order_index: 1, style_document_id: 10, current_text_revision_id: 2, current_structure_revision_id: 3, current_structure_kind: "paragraph", analysis_status: { basic: { state: "analyzed", reasons: [] }, semantic: { state: "not_analyzed", reasons: [] } } }]);
    }
    if (path.endsWith("/reference-works/7/analyze") && method === "POST") {
      return respond({ job_id: 51, job_type: "analyze_reference_work", status: "queued", progress: { current: 0, total: 1 }, result: {}, warnings: [], error_code: null, error_message: null }, 202);
    }
    if (path.endsWith("/documents/10/analyze") && method === "POST") {
      return respond({ job_id: 53, job_type: "analyze_document", status: "queued", progress: { current: 0, total: 1 }, result: {}, warnings: [], error_code: null, error_message: null }, 202);
    }
    const jobMatch = path.match(/\/jobs\/(\d+)$/);
    if (jobMatch && method === "GET") {
      const jobId = Number(jobMatch[1]);
      const reads = (jobReads.get(jobId) ?? 0) + 1;
      jobReads.set(jobId, reads);
      const status = reads > 1 ? "succeeded" : "running";
      return respond({ job_id: jobId, job_type: "style_analysis", status, progress: { current: status === "succeeded" ? 1 : 0, total: 1 }, result: jobId === 52 ? { lint_run_id: 61, coverage_ratio: 0.5 } : { analysis_run_id: 12 }, warnings: [], error_code: null, error_message: null });
    }
    if (path.endsWith("/documents/10/runs") && method === "GET") return respond([{ id: 12, analyzer_id: "deterministic", analyzer_version: 1, text_revision_id: 2, structure_revision_id: 3, status: "succeeded", started_at: "now", finished_at: "now" }]);
    if (path.endsWith("/documents/10/semantics") && method === "GET") return respond({ analysis_status: { basic: { state: "analyzed" }, semantic: { state: "not_analyzed" } }, analysis_run_ids: [12], effective: [], outputs: [] });
    if (path.endsWith("/corpora") && method === "GET") return respond([{ id: 20, name: "Mock corpus", description: "fixture", created_at: "now", updated_at: "now" }]);
    if (path.endsWith("/corpora") && method === "POST") return respond({ id: 20, name: "Mock corpus", description: "fixture", created_at: "now", updated_at: "now" }, 201);
    if (path.endsWith("/corpora/20/works") && method === "POST") return respond({ corpus_id: 20, reference_work_id: 7 }, 201);
    if (path.endsWith("/corpora/20/aggregates/recompute") && method === "POST") return respond({ job_id: 54, job_type: "recompute_aggregates", status: "queued", progress: { current: 0, total: 1 }, result: {}, warnings: [], error_code: null, error_message: null }, 202);
    if (path.endsWith("/corpora/20/aggregates") && method === "GET") return respond([
      { id: 30, container_type: "corpus", container_id: 20, measurement_target_type: "document", filter_json: "{}", metric_name: "sentence.len.p50", metric_version: 1, statistic: "median", value_real: 10, source_measurement_count: 1, sample_count: 1, stale: false, warning_json: "[]" },
      { id: 31, container_type: "corpus", container_id: 20, measurement_target_type: "document", filter_json: "{}", metric_name: "sentence.len.p50", metric_version: 1, statistic: "p25", value_real: 5, source_measurement_count: 1, sample_count: 1, stale: false, warning_json: "[]" },
      { id: 32, container_type: "corpus", container_id: 20, measurement_target_type: "document", filter_json: "{}", metric_name: "sentence.len.p50", metric_version: 1, statistic: "p75", value_real: 15, source_measurement_count: 1, sample_count: 1, stale: false, warning_json: "[]" },
    ]);
    if (path.endsWith("/profiles/40") && method === "GET") return respond({ profile: { id: 40, name: "Mock profile", description: "fixture", source_corpus_id: null, status: "draft", active_version_id: null, created_at: "now", updated_at: "now" }, versions: [{ version: { id: 41, profile_id: 40, version_no: 1, parent_version_id: null, created_at: "now" }, rules: [] }] });
    if (path.endsWith("/profiles") && method === "GET") return respond(profileCreated ? [{ id: 40, name: "Mock profile", description: "fixture", source_corpus_id: null, status: "draft", active_version_id: null, created_at: "now", updated_at: "now" }] : []);
    if (path.endsWith("/profiles/manual") && method === "POST") { profilePostCount += 1; profileCreated = true; return respond({ profile: { id: 40, name: "Mock profile", description: "fixture", source_corpus_id: null, status: "draft", active_version_id: null, created_at: "now", updated_at: "now" }, versions: [] }, 201); }
    if (path.endsWith("/profiles/from-corpus") && method === "POST") { corpusProfilePayload = request.postDataJSON(); return respond({ profile: { id: 40, name: "Corpus profile", description: "fixture", source_corpus_id: 20, status: "draft", active_version_id: null, created_at: "now", updated_at: "now" }, versions: [] }, 201); }
    if (path.endsWith("/documents/10/lint") && method === "POST") return respond({ job_id: 52, job_type: "run_lint", status: "queued", progress: { current: 0, total: 1 }, result: {}, warnings: [], error_code: null, error_message: null }, 202);
    if (path.endsWith("/lint-runs") && method === "GET") return respond([]);
    if (path.endsWith("/lint-runs/61/findings") && method === "GET") return respond([{ id: 70, lint_run_id: 61, rule_id: 71, target_type: "document", target_id: 10, metric_name: "sentence.len.p50", observed_value: 25, expected_min: 5, expected_max: 15, preferred_value: 10, deviation: 10, severity: "warning", sort_score: 10, explanation_code: "above_max", evidence: { source: "mock" }, review_status: findingReviewed ? "acknowledged" : null, review_note: findingReviewed ? "確認済み" : null }]);
    if (path.endsWith("/findings/70/review") && method === "POST") { findingReviewed = true; return respond({ id: 70, review_status: "acknowledged" }); }
    return respond([]);
  });

  await page.goto(`/projects/${projectId}/style-analysis/sources`);
  await expect(page.getByRole("heading", { name: "Sources" })).toBeVisible();
  await expect(page.getByText(/Network URLやRefresh操作はありません/)).toBeVisible();
  await page.getByLabel("Local file").setInputFiles({ name: "fixture.txt", mimeType: "text/plain", buffer: Buffer.from("短い本文") });
  await page.getByRole("button", { name: "Import" }).click();
  await expect(page.getByText(/新しいSourceを登録しました/)).toBeVisible();
  await page.getByRole("link", { name: /Mock reference/ }).click();
  await page.getByRole("button", { name: "Deterministic analyze" }).click();
  await expect(page.getByText("Analysis job #51")).toBeVisible();
  await expect(page.getByText("succeeded")).toBeVisible();
  await page.getByRole("link", { name: "Document" }).click();
  await expect(page.getByRole("heading", { name: "Document Analysis #10" })).toBeVisible();
  await page.getByLabel("Analyze preset").selectOption("full");
  await page.getByRole("button", { name: "Analyze selected revisions" }).click();
  await expect(page.getByText("Analysis job #53")).toBeVisible();
  await page.getByRole("link", { name: "Corpora / Aggregate" }).click();
  await page.getByLabel("Name").first().fill("Mock corpus from browser");
  await page.getByRole("button", { name: "Save corpus" }).click();
  await page.getByRole("button", { name: /Mock corpus/ }).click();
  await page.getByLabel("Add reference work").selectOption("7");
  await page.getByRole("button", { name: "Add work" }).click();
  await page.getByRole("button", { name: "Recompute aggregates" }).click();
  await expect(page.getByText("Analysis job #54")).toBeVisible();
  await expect(page.getByText("succeeded")).toBeVisible();
  await page.getByRole("link", { name: "Profiles" }).click();
  await expect(page.getByRole("heading", { name: "Profiles" })).toBeVisible();
  await page.getByLabel("Name").first().fill("Mock profile");
  await page.getByRole("button", { name: "Save draft profile" }).click();
  await expect.poll(() => profilePostCount).toBe(1);
  await expect(page.getByText("Mock profile")).toBeVisible();
  await page.getByLabel("Name").nth(1).fill("Corpus profile");
  await page.getByLabel("Corpus").selectOption("20");
  await expect(page.getByLabel("Aggregate group")).toHaveValue(/sentence\.len\.p50/);
  await expect(page.getByLabel("preferred,min,max aggregate IDs")).toHaveValue("30,31,32");
  await page.getByRole("button", { name: "Build from exact aggregates" }).click();
  await expect.poll(() => corpusProfilePayload).toMatchObject({ corpus_id: 20, rules: [{ preferred_aggregate_id: 30, min_aggregate_id: 31, max_aggregate_id: 32 }] });
  await page.getByRole("link", { name: "Lint" }).click();
  await page.getByLabel("Document").selectOption("10");
  await page.getByLabel("Profile", { exact: true }).selectOption("40");
  await expect(page.getByLabel("Profile version")).toHaveValue("1");
  await page.getByRole("button", { name: "Run lint" }).click();
  await expect(page.getByText("Coverage")).toBeVisible();
  await expect(page.getByText("above_max")).toBeVisible();
  await page.getByRole("button", { name: "Acknowledge" }).click();
  await expect(page.getByText("acknowledged")).toBeVisible();
});
