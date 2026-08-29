import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, Link, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { DirtyNavigationGuard } from "./DirtyNavigationGuard";

function renderGuard() {
  const router = createMemoryRouter(
    [
      {
        path: "/edit",
        element: (
          <>
            <Link to="/next">Go next</Link>
            <DirtyNavigationGuard dirty />
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
});
