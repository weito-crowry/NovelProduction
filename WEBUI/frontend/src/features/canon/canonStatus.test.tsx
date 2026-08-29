import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CanonStatusControl } from "./CanonStatusControl";

function response(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderControl(dirty = false) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
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
});
