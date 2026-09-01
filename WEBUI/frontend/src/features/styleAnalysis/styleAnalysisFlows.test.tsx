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
});
