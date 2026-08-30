import { useId, useRef } from "react";
import { Button } from "../../components/ui/Button";
import { useModalFocus } from "../../components/ui/useModalFocus";

export interface ConflictDialogProps<TLocal, TLatest> {
  local: TLocal;
  latest: TLatest | null;
  onDiscard: () => void;
  onKeep: () => void;
  entityLabel?: string;
  keepActionLabel?: string;
  errorMessage?: string | null;
  discardPending?: boolean;
}

export function ConflictDialog<TLocal, TLatest>({
  local,
  latest,
  onDiscard,
  onKeep,
  entityLabel = "work",
  keepActionLabel = "Keep local edits",
  errorMessage = null,
  discardPending = false,
}: ConflictDialogProps<TLocal, TLatest>) {
  const headingId = useId();
  const keepButtonRef = useRef<HTMLButtonElement>(null);
  const { dialogRef, onKeyDown } = useModalFocus(true, {
    initialFocusRef: keepButtonRef,
    onEscape: onKeep,
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
        <p className="eyebrow">VERSION_CONFLICT</p>
        <h2 id={headingId}>This {entityLabel} changed elsewhere</h2>
        <div className="comparison-grid">
          <div>
            <h3>Local unsaved edits</h3>
            <pre>{JSON.stringify(local, null, 2)}</pre>
          </div>
          <div>
            <h3>Latest database resource</h3>
            {latest === null ? (
              <p>The latest resource is currently unavailable.</p>
            ) : (
              <pre>{JSON.stringify(latest, null, 2)}</pre>
            )}
          </div>
        </div>
        <div className="dialog-actions">
          <Button
            ref={keepButtonRef}
            type="button"
            variant="secondary"
            onClick={onKeep}
          >
            {keepActionLabel}
          </Button>
          <Button type="button" onClick={onDiscard} disabled={discardPending}>
            {discardPending ? "Loading latest…" : "Load latest and discard local edits"}
          </Button>
        </div>
        {errorMessage && <p role="alert">{errorMessage}</p>}
      </section>
    </div>
  );
}
