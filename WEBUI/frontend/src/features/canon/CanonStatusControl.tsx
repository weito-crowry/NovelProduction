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
type CanonResource = { id: number; canon_status: string; version: number };

export function CanonStatusControl({
  projectId,
  entityType,
  record,
  dirty = false,
  onStatusChanged,
  readCurrent,
  onLoadLatest,
}: {
  projectId: string;
  entityType: string;
  record: CanonResource;
  dirty?: boolean;
  onStatusChanged?: (decision: CanonDecisionRecord) => void | Promise<void>;
  readCurrent?: () => Promise<unknown>;
  onLoadLatest?: (latest: CanonResource) => void | Promise<void>;
}) {
  const queryClient = useQueryClient();
  const [targetStatus, setTargetStatus] = useState("");
  const [reason, setReason] = useState("");
  const [latest, setLatest] = useState<CanonResource | null>(null);
  const [conflictOpen, setConflictOpen] = useState(false);
  const [conflictReady, setConflictReady] = useState(false);
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
        let current = asCanonResource(caught.details.current_resource);
        let ready = current !== null;
        setError(null);
        if (current === null && readCurrent) {
          try {
            current = asCanonResource(await readCurrent());
            ready = current !== null;
          } catch {
            setError("The latest resource could not be loaded.");
          }
        }
        setLatest(current);
        setConflictReady(ready);
        setConflictOpen(true);
        return;
      }
      setError(caught instanceof Error ? caught.message : "Unable to change canon status.");
    }
  }

  async function loadLatest() {
    if (!conflictReady || latest === null) return;
    try {
      await onLoadLatest?.(latest);
      setTargetStatus("");
      setReason("");
      setLatest(null);
      setConflictReady(false);
      setConflictOpen(false);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load the latest resource.");
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
          onDiscard={() => void loadLatest()}
          onKeep={() => {
            setLatest(null);
            setConflictReady(false);
            setConflictOpen(false);
          }}
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
  const keys = [
    queryClient.invalidateQueries({ queryKey: projectQueryKeys.canonDecisionsFamily(projectId) }),
    queryClient.invalidateQueries({ queryKey: projectQueryKeys.canonDecisionSearchFamily(projectId) }),
    queryClient.invalidateQueries({ queryKey: projectQueryKeys.episodeViews(projectId) }),
  ];
  if (entityType === "information_item") {
    keys.push(queryClient.invalidateQueries({ queryKey: projectQueryKeys.informationFamily(projectId) }));
    keys.push(queryClient.invalidateQueries({ queryKey: projectQueryKeys.informationSearchFamily(projectId) }));
    keys.push(queryClient.invalidateQueries({ queryKey: projectQueryKeys.informationItem(projectId, entityId) }));
    keys.push(queryClient.invalidateQueries({ queryKey: projectQueryKeys.characterKnowledgeProjectFamily(projectId) }));
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
    keys.push(queryClient.invalidateQueries({ queryKey: projectQueryKeys.timelineRangeFamily(projectId) }));
  } else if (entityType === "chapter" || entityType === "episode" || entityType === "scene") {
    keys.push(queryClient.invalidateQueries({ queryKey: projectQueryKeys.outline(projectId) }));
    if (entityType === "episode") keys.push(queryClient.invalidateQueries({ queryKey: projectQueryKeys.episode(projectId, entityId) }));
    if (entityType === "scene") keys.push(queryClient.invalidateQueries({ queryKey: projectQueryKeys.scene(projectId, entityId) }));
  } else if (entityType === "relationship") {
    keys.push(queryClient.invalidateQueries({ queryKey: projectQueryKeys.relationshipsFamily(projectId) }));
  }
  await Promise.all(keys);
}

function asCanonResource(value: unknown): CanonResource | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  const resource = value as Partial<CanonResource>;
  return typeof resource.id === "number" && typeof resource.canon_status === "string" && typeof resource.version === "number"
    ? resource as CanonResource
    : null;
}
