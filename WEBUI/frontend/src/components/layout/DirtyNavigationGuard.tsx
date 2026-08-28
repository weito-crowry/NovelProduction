import { useCallback } from "react";
import { useBeforeUnload, useBlocker } from "react-router-dom";
import { Button } from "../ui/Button";

export function DirtyNavigationGuard({ dirty }: { dirty: boolean }) {
  const blocker = useBlocker(dirty);
  useBeforeUnload(
    useCallback(
      (event: BeforeUnloadEvent) => {
        if (dirty) {
          event.preventDefault();
          event.returnValue = "";
        }
      },
      [dirty],
    ),
  );

  if (blocker.state !== "blocked") {
    return null;
  }
  return (
    <div className="dialog-backdrop" role="presentation">
      <section className="dialog" role="dialog" aria-modal="true" aria-labelledby="navigation-heading">
        <h2 id="navigation-heading">Leave without saving?</h2>
        <p>Your local edits will be discarded if you leave this page.</p>
        <div className="dialog-actions">
          <Button type="button" variant="secondary" onClick={() => blocker.reset()}>
            Stay
          </Button>
          <Button type="button" variant="danger" onClick={() => blocker.proceed()}>
            Discard and leave
          </Button>
        </div>
      </section>
    </div>
  );
}
