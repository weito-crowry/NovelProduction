import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ConflictDialog } from "./ConflictDialog";

function renderConflict() {
  function Harness() {
    const [open, setOpen] = useState(false);
    return (
      <>
        <button type="button" onClick={() => setOpen(true)}>
          Open conflict
        </button>
        {open && (
          <ConflictDialog
            local={{ title: "Local" }}
            latest={{ title: "Latest" }}
            onDiscard={() => setOpen(false)}
            onKeep={() => setOpen(false)}
          />
        )}
      </>
    );
  }

  render(<Harness />);
  return screen.getByRole("button", { name: "Open conflict" });
}

describe("ConflictDialog keyboard focus", () => {
  it("focuses the safe action when opened and restores the trigger on close", async () => {
    const trigger = renderConflict();
    const user = userEvent.setup();

    await user.click(trigger);

    const keep = screen.getByRole("button", { name: "Keep local edits" });
    expect(keep).toHaveFocus();
    await user.click(keep);
    expect(trigger).toHaveFocus();
  });

  it("traps Tab and Shift+Tab inside the dialog", async () => {
    renderConflict();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Open conflict" }));

    const keep = screen.getByRole("button", { name: "Keep local edits" });
    const discard = screen.getByRole("button", {
      name: "Load latest and discard local edits",
    });

    await user.tab();
    expect(discard).toHaveFocus();
    await user.tab();
    expect(keep).toHaveFocus();
    await user.tab({ shift: true });
    expect(discard).toHaveFocus();
  });

  it("maps Escape to the safe keep-local action", async () => {
    const onKeep = vi.fn();
    const onDiscard = vi.fn();
    render(
      <ConflictDialog
        local={{ title: "Local" }}
        latest={{ title: "Latest" }}
        onDiscard={onDiscard}
        onKeep={onKeep}
      />,
    );

    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });

    expect(onKeep).toHaveBeenCalledOnce();
    expect(onDiscard).not.toHaveBeenCalled();
  });
});
