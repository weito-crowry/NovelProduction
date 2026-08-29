import { Button } from "../../components/ui/Button";

export interface ConflictDialogProps<TLocal, TLatest> {
  local: TLocal;
  latest: TLatest;
  onDiscard: () => void;
  onKeep: () => void;
  entityLabel?: string;
  errorMessage?: string | null;
}

export function ConflictDialog<TLocal, TLatest>({
  local,
  latest,
  onDiscard,
  onKeep,
  entityLabel = "work",
  errorMessage = null,
}: ConflictDialogProps<TLocal, TLatest>) {
  return (
    <div className="dialog-backdrop" role="presentation">
      <section className="dialog" role="dialog" aria-modal="true" aria-labelledby="conflict-heading">
        <p className="eyebrow">VERSION_CONFLICT</p>
        <h2 id="conflict-heading">This {entityLabel} changed elsewhere</h2>
        <div className="comparison-grid">
          <div>
            <h3>Local unsaved edits</h3>
            <pre>{JSON.stringify(local, null, 2)}</pre>
          </div>
          <div>
            <h3>Latest database resource</h3>
            <pre>{JSON.stringify(latest, null, 2)}</pre>
          </div>
        </div>
        <div className="dialog-actions">
          <Button type="button" variant="secondary" onClick={onKeep}>
            Keep local edits
          </Button>
          <Button type="button" onClick={onDiscard}>
            Load latest and discard local edits
          </Button>
        </div>
        {errorMessage && <p role="alert">{errorMessage}</p>}
      </section>
    </div>
  );
}
