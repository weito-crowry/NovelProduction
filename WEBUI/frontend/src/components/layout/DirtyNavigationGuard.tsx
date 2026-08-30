import { useCallback, useId, useRef } from "react";
import { useBeforeUnload, useBlocker } from "react-router-dom";
import { Button } from "../ui/Button";
import { useModalFocus } from "../ui/useModalFocus";

export function DirtyNavigationGuard({ dirty, pending = false }: { dirty: boolean; pending?: boolean }) {
  const navigationBlocked = dirty || pending;
  const blocker = useBlocker(navigationBlocked);
  useBeforeUnload(
    useCallback(
      (event: BeforeUnloadEvent) => {
        if (navigationBlocked) {
          event.preventDefault();
          event.returnValue = "";
        }
      },
      [navigationBlocked],
    ),
  );

  if (blocker.state !== "blocked") {
    return null;
  }
  return <BlockedNavigationDialog pending={pending} reset={blocker.reset} proceed={blocker.proceed} />;
}

function BlockedNavigationDialog({
  pending,
  reset,
  proceed,
}: {
  pending: boolean;
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
        <h2 id={headingId}>{pending ? "Save in progress" : "Leave without saving?"}</h2>
        <p>{pending ? "Wait for the manuscript save to finish before leaving this page." : "Your local edits will be discarded if you leave this page."}</p>
        <div className="dialog-actions">
          <Button ref={stayButtonRef} type="button" variant="secondary" onClick={reset}>
            Stay
          </Button>
          {!pending && <Button type="button" variant="danger" onClick={proceed}>Discard and leave</Button>}
        </div>
      </section>
    </div>
  );
}
