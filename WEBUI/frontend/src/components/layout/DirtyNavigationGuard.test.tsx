import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, Link, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { DirtyNavigationGuard } from "./DirtyNavigationGuard";

function renderGuard({ dirty = true, pending = false }: { dirty?: boolean; pending?: boolean } = {}) {
  const router = createMemoryRouter(
    [
      {
        path: "/edit",
        element: (
          <>
            <Link to="/next">Go next</Link>
            <DirtyNavigationGuard dirty={dirty} pending={pending} />
          </>
        ),
      },
      { path: "/next", element: <h1>Next</h1> },
    ],
    { initialEntries: ["/edit"] },
  );
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

describe("DirtyNavigationGuard keyboard focus", () => {
  it("focuses Stay and Escape keeps the user on the current route", async () => {
    const router = renderGuard();
    const user = userEvent.setup();
    const trigger = screen.getByRole("link", { name: "Go next" });

    await user.click(trigger);

    const stay = screen.getByRole("button", { name: "Stay" });
    expect(stay).toHaveFocus();
    await user.keyboard("{Escape}");

    expect(router.state.location.pathname).toBe("/edit");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("keeps the existing discard behavior when no write is pending", async () => {
    const router = renderGuard();
    const user = userEvent.setup();

    await user.click(screen.getByRole("link", { name: "Go next" }));

    expect(screen.getByRole("heading", { name: "Leave without saving?" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Stay" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Discard and leave" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Discard and leave" }));

    expect(router.state.location.pathname).toBe("/next");
  });

  it("blocks pending-write navigation with Stay only and warns on beforeunload", async () => {
    const router = renderGuard({ dirty: false, pending: true });
    const user = userEvent.setup();

    await user.click(screen.getByRole("link", { name: "Go next" }));

    expect(router.state.location.pathname).toBe("/edit");
    expect(screen.getByRole("heading", { name: "Save in progress" })).toBeInTheDocument();
    expect(screen.getByText("Wait for the manuscript save to finish before leaving this page.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Stay" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Discard and leave" })).not.toBeInTheDocument();

    const event = new Event("beforeunload", { cancelable: true }) as BeforeUnloadEvent;
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);

    await user.keyboard("{Escape}");
    expect(router.state.location.pathname).toBe("/edit");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
