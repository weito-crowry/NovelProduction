import { useCallback, useId, useRef } from "react";
import { useBeforeUnload, useBlocker } from "react-router-dom";
import { Button } from "../ui/Button";
import { useModalFocus } from "../ui/useModalFocus";

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
  return <BlockedNavigationDialog reset={blocker.reset} proceed={blocker.proceed} />;
}

function BlockedNavigationDialog({
  reset,
  proceed,
}: {
  reset: () => void;
  proceed: () => void;
}) {
  const headingId = useId();
  const stayButtonRef = useRef<HTMLButtonElement>(null);
  const { dialogRef, onKeyDown } = useModalFocus(true, {
    initialFocusRef: stayButtonRef,
    onEscape: reset,
  });

  return (
    <div className="dialog-backdrop" role="presentation">
      <section
        ref={dialogRef}
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={headingId}
        onKeyDown={onKeyDown}
      >
        <h2 id={headingId}>Leave without saving?</h2>
        <p>Your local edits will be discarded if you leave this page.</p>
        <div className="dialog-actions">
          <Button ref={stayButtonRef} type="button" variant="secondary" onClick={reset}>
            Stay
          </Button>
          <Button type="button" variant="danger" onClick={proceed}>
            Discard and leave
          </Button>
        </div>
      </section>
    </div>
  );
}
