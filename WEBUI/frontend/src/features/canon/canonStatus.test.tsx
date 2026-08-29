import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { projectQueryKeys } from "../../api/queryKeys";
import { CanonStatusControl } from "./CanonStatusControl";

function response(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderControl(dirty = false, queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  render(
    <QueryClientProvider client={queryClient}>
      <CanonStatusControl
        projectId="A"
        entityType="information_item"
        record={{ id: 4, canon_status: "draft", version: 7 }}
        dirty={dirty}
      />
    </QueryClientProvider>,
  );
  return queryClient;
}

describe("CanonStatusControl", () => {
  afterEach(() => vi.restoreAllMocks());

  it("posts the target status, reason, and loaded expected version", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toBe("/api/v1/projects/A/canon/status");
      expect(init?.method).toBe("POST");
      expect(JSON.parse(String(init?.body))).toEqual({
        entity_type: "information_item",
        entity_id: 4,
        target_status: "canon",
        expected_version: 7,
        reason: "approved",
      });
      return response({
        project_id: "A",
        data: {
          id: 9,
          summary: "Status changed",
          reason: "approved",
          changes: [],
        },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    renderControl();
    const user = userEvent.setup();
    await user.selectOptions(screen.getByRole("combobox", { name: "Target canon status" }), "canon");
    await user.type(screen.getByLabelText("Status reason (optional)"), "approved");
    await user.click(screen.getByRole("button", { name: "Change canon status" }));

    expect(await screen.findByText("Status change recorded")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("disables the status action while the host editor is dirty", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    renderControl(true);

    expect(screen.getByRole("combobox", { name: "Target canon status" })).toBeDisabled();
    expect(screen.getByLabelText("Status reason (optional)")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Change canon status" })).toBeDisabled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("loads a conflict resource into the host baseline before the next action", async () => {
    const staleRecord = { id: 4, canon_status: "draft", version: 7 };
    const latestRecord = { id: 4, canon_status: "canon", version: 8 };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ error: { code: "VERSION_CONFLICT", message: "stale", details: { current_resource: latestRecord } } }, 409))
      .mockResolvedValueOnce(response({ project_id: "A", data: { id: 10, summary: "changed", reason: "revised", changes: [] } }));
    vi.stubGlobal("fetch", fetchMock);

    function HostEditor() {
      const [record, setRecord] = useState(staleRecord);
      return (
        <CanonStatusControl
          projectId="A"
          entityType="information_item"
          record={record}
          onLoadLatest={(latest: typeof latestRecord) => setRecord(latest)}
        />
      );
    }
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><HostEditor /></QueryClientProvider>);
    const user = userEvent.setup();
    await user.selectOptions(screen.getByRole("combobox", { name: "Target canon status" }), "canon");
    await user.type(screen.getByLabelText("Status reason (optional)"), "approved");
    await user.click(screen.getByRole("button", { name: "Change canon status" }));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(await screen.findByRole("dialog")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Load latest and discard local edits" }));

    expect(screen.getByText("Current status: canon · version 8")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Target canon status" })).toHaveValue("");
    expect(screen.getByLabelText("Status reason (optional)")).toHaveValue("");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await user.selectOptions(screen.getByRole("combobox", { name: "Target canon status" }), "deprecated");
    await user.click(screen.getByRole("button", { name: "Change canon status" }));
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toMatchObject({ expected_version: 8, target_status: "deprecated" });
  });

  it("keeps local canon action and host baseline unchanged when requested", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({ error: { code: "VERSION_CONFLICT", message: "stale", details: { current_resource: { id: 4, canon_status: "canon", version: 8 } } } }, 409));
    vi.stubGlobal("fetch", fetchMock);

    renderControl();
    const user = userEvent.setup();
    await user.selectOptions(screen.getByRole("combobox", { name: "Target canon status" }), "canon");
    await user.type(screen.getByLabelText("Status reason (optional)"), "approved");
    await user.click(screen.getByRole("button", { name: "Change canon status" }));
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: "Keep local edits" }));

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Current status: draft · version 7")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Target canon status" })).toHaveValue("canon");
    expect(screen.getByLabelText("Status reason (optional)")).toHaveValue("approved");
  });

  it("uses the readCurrent fallback and keeps local action when it fails", async () => {
    const readCurrent = vi.fn().mockRejectedValue(new Error("read failed"));
    const fetchMock = vi.fn().mockResolvedValue(response({ error: { code: "VERSION_CONFLICT", message: "stale", details: {} } }, 409));
    vi.stubGlobal("fetch", fetchMock);

    render(
      <QueryClientProvider client={new QueryClient()}>
        <CanonStatusControl
          projectId="A"
          entityType="information_item"
          record={{ id: 4, canon_status: "draft", version: 7 }}
          readCurrent={readCurrent}
        />
      </QueryClientProvider>,
    );
    const user = userEvent.setup();
    await user.selectOptions(screen.getByRole("combobox", { name: "Target canon status" }), "canon");
    await user.click(screen.getByRole("button", { name: "Change canon status" }));

    expect(readCurrent).toHaveBeenCalledTimes(1);
    expect((await screen.findAllByText("The latest resource could not be loaded.")).length).toBeGreaterThan(0);
    expect(screen.getByRole("combobox", { name: "Target canon status" })).toHaveValue("canon");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("invalidates common and information-specific canon caches after success", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({ project_id: "A", data: { id: 10, summary: "changed", reason: null, changes: [] } }));
    vi.stubGlobal("fetch", fetchMock);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    renderControl(false, queryClient);
    const user = userEvent.setup();
    await user.selectOptions(screen.getByRole("combobox", { name: "Target canon status" }), "canon");
    await user.click(screen.getByRole("button", { name: "Change canon status" }));
    await screen.findByText("Status change recorded");

    const invalidated = invalidateSpy.mock.calls.flatMap(([filters]) => filters?.queryKey ? [filters.queryKey] : []);
    expect(invalidated).toContainEqual(projectQueryKeys.canonDecisionsFamily("A"));
    expect(invalidated).toContainEqual(projectQueryKeys.canonDecisionSearchFamily("A"));
    expect(invalidated).toContainEqual(projectQueryKeys.episodeViews("A"));
    expect(invalidated).toContainEqual(projectQueryKeys.informationFamily("A"));
    expect(invalidated).toContainEqual(projectQueryKeys.informationSearchFamily("A"));
    expect(invalidated).toContainEqual(projectQueryKeys.informationItem("A", 4));
    expect(invalidated).toContainEqual(projectQueryKeys.characterKnowledgeProjectFamily("A"));
  });
});
