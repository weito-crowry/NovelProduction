import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { isApiError } from "../../api/errors";
import { projectQueryKeys } from "../../api/queryKeys";
import type { CanonDecisionRecord, CanonStatusSet } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { FieldLabel, TextInput } from "../../components/ui/Field";
import { ConflictDialog } from "../conflicts/ConflictDialog";
import { setCanonStatus } from "./canonApi";

const statuses = ["idea", "draft", "canon", "deprecated"];

export function CanonStatusControl({
  projectId,
  entityType,
  record,
  dirty = false,
  onStatusChanged,
  readCurrent,
}: {
  projectId: string;
  entityType: string;
  record: { id: number; canon_status: string; version: number };
  dirty?: boolean;
  onStatusChanged?: (decision: CanonDecisionRecord) => void | Promise<void>;
  readCurrent?: () => Promise<unknown>;
}) {
  const queryClient = useQueryClient();
  const [targetStatus, setTargetStatus] = useState("");
  const [reason, setReason] = useState("");
  const [latest, setLatest] = useState<unknown | null>(null);
  const [conflictOpen, setConflictOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  async function submit() {
    if (!targetStatus || dirty) return;
    setError(null);
    setSaved(false);
    const input: CanonStatusSet = {
      entity_type: entityType,
      entity_id: record.id,
      target_status: targetStatus,
      expected_version: record.version,
    };
    if (reason.trim()) input.reason = reason.trim();
    try {
      const decision = await setCanonStatus(projectId, input);
      await invalidateCanonQueries(projectId, entityType, record.id, queryClient);
      setTargetStatus("");
      setReason("");
      setSaved(true);
      await onStatusChanged?.(decision);
    } catch (caught) {
      if (
        isApiError(caught) &&
        caught.status === 409 &&
        caught.code === "VERSION_CONFLICT"
      ) {
        let current: unknown | null = caught.details.current_resource ?? null;
        setError(null);
        if (current === null && readCurrent) {
          try {
            current = await readCurrent();
          } catch {
            setError("The latest resource could not be loaded.");
          }
        }
        setLatest(current);
        setConflictOpen(true);
        return;
      }
      setError(caught instanceof Error ? caught.message : "Unable to change canon status.");
    }
  }

  return (
    <>
      <Card>
        <h3>Canon status action</h3>
        <p className="read-only-meta">
          Current status: {record.canon_status} · version {record.version}
        </p>
        <div className="reference-form">
          <div className="field-group">
            <FieldLabel htmlFor={`${entityType}-${record.id}-target-status`}>
              Target status
            </FieldLabel>
            <select
              id={`${entityType}-${record.id}-target-status`}
              className="field-control"
              aria-label="Target canon status"
              value={targetStatus}
              onChange={(event) => setTargetStatus(event.target.value)}
              disabled={dirty}
            >
              <option value="">Select status</option>
              {statuses.map((status) => <option key={status} value={status}>{status}</option>)}
            </select>
          </div>
          <div className="field-group">
            <FieldLabel htmlFor={`${entityType}-${record.id}-status-reason`}>
              Status reason (optional)
            </FieldLabel>
            <TextInput
              id={`${entityType}-${record.id}-status-reason`}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              disabled={dirty}
            />
          </div>
          <Button type="button" onClick={() => void submit()} disabled={dirty || !targetStatus}>
            Change canon status
          </Button>
        </div>
        {dirty && <p className="helper-text">Save or discard the editor before changing canon status.</p>}
        {saved && <p className="saved-indicator">Status change recorded</p>}
        {error && <p role="alert">{error}</p>}
      </Card>
      {conflictOpen && (
        <ConflictDialog
          local={{ target_status: targetStatus, reason }}
          latest={latest}
          entityLabel="canon status"
          onDiscard={() => setConflictOpen(false)}
          onKeep={() => setConflictOpen(false)}
          errorMessage={error}
        />
      )}
    </>
  );
}

async function invalidateCanonQueries(
  projectId: string,
  entityType: string,
  entityId: number,
  queryClient: ReturnType<typeof useQueryClient>,
) {
  const keys = [queryClient.invalidateQueries({ queryKey: projectQueryKeys.canonDecisionsFamily(projectId) })];
  if (entityType === "information_item") {
    keys.push(queryClient.invalidateQueries({ queryKey: projectQueryKeys.informationFamily(projectId) }));
    keys.push(queryClient.invalidateQueries({ queryKey: projectQueryKeys.informationSearchFamily(projectId) }));
    keys.push(queryClient.invalidateQueries({ queryKey: projectQueryKeys.informationItem(projectId, entityId) }));
  } else if (entityType === "character") {
    keys.push(queryClient.invalidateQueries({ queryKey: projectQueryKeys.charactersFamily(projectId) }));
    keys.push(queryClient.invalidateQueries({ queryKey: projectQueryKeys.characterSearchFamily(projectId) }));
    keys.push(queryClient.invalidateQueries({ queryKey: projectQueryKeys.character(projectId, entityId) }));
  } else if (entityType === "world_fact") {
    keys.push(queryClient.invalidateQueries({ queryKey: projectQueryKeys.worldFactsFamily(projectId) }));
    keys.push(queryClient.invalidateQueries({ queryKey: projectQueryKeys.worldFactSearchFamily(projectId) }));
    keys.push(queryClient.invalidateQueries({ queryKey: projectQueryKeys.worldFact(projectId, entityId) }));
  } else if (entityType === "timeline_event") {
    keys.push(queryClient.invalidateQueries({ queryKey: projectQueryKeys.timelineEventsFamily(projectId) }));
    keys.push(queryClient.invalidateQueries({ queryKey: projectQueryKeys.timelineEventSearchFamily(projectId) }));
    keys.push(queryClient.invalidateQueries({ queryKey: projectQueryKeys.timelineEvent(projectId, entityId) }));
  } else if (entityType === "chapter" || entityType === "episode" || entityType === "scene") {
    keys.push(queryClient.invalidateQueries({ queryKey: projectQueryKeys.outline(projectId) }));
    keys.push(queryClient.invalidateQueries({ queryKey: projectQueryKeys.episodeViews(projectId) }));
  } else if (entityType === "relationship") {
    keys.push(queryClient.invalidateQueries({ queryKey: ["project", projectId, "relationships"] }));
  }
  await Promise.all(keys);
}
