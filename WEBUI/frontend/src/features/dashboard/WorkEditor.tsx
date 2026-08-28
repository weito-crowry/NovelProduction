import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { projectQueryKeys } from "../../api/queryKeys";
import { isApiError } from "../../api/errors";
import type { WorkRecord, WorkUpdate } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { FieldLabel, TextArea, TextInput } from "../../components/ui/Field";
import { DirtyNavigationGuard } from "../../components/layout/DirtyNavigationGuard";
import { ConflictDialog } from "../conflicts/ConflictDialog";
import { fetchWork, updateWork } from "../projects/projectApi";
import { buildWorkUpdate, toForm, type WorkFormValues } from "./workForm";

export function WorkEditor({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const workQuery = useQuery({
    queryKey: projectQueryKeys.work(projectId),
    queryFn: () => fetchWork(projectId),
  });
  const [baseline, setBaseline] = useState<WorkRecord | null>(null);
  const [values, setValues] = useState<WorkFormValues | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [conflictLatest, setConflictLatest] = useState<WorkRecord | null>(null);

  useEffect(() => {
    if (workQuery.data && baseline === null) {
      setBaseline(workQuery.data);
      setValues(toForm(workQuery.data));
    }
  }, [baseline, workQuery.data]);

  const dirty = useMemo(
    () => values !== null && baseline !== null && !sameForm(values, toForm(baseline)),
    [baseline, values],
  );
  const mutation = useMutation({
    mutationFn: (update: WorkUpdate) => updateWork(projectId, update),
    retry: false,
  });

  if (workQuery.isError) {
    return <p role="alert">Unable to load the work editor.</p>;
  }
  if (workQuery.isPending || values === null || baseline === null) {
    return <p role="status">Loading work editor…</p>;
  }

  async function save() {
    if (values === null || baseline === null) return;
    setValidationError(null);
    setSaveError(null);
    setSaved(false);
    try {
      const payload = buildWorkUpdate(values, baseline);
      const updated = await mutation.mutateAsync(payload);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: projectQueryKeys.work(projectId) }),
        queryClient.invalidateQueries({ queryKey: projectQueryKeys.dashboard(projectId) }),
      ]);
      setBaseline(updated);
      setValues(toForm(updated));
      setSaved(true);
    } catch (error) {
      if (isApiError(error) && error.status === 409 && error.code === "VERSION_CONFLICT") {
        let latest = asWorkRecord(error.details.current_resource);
        if (latest === null) {
          latest = await fetchWork(projectId);
          queryClient.setQueryData(projectQueryKeys.work(projectId), latest);
        }
        setConflictLatest(latest);
        return;
      }
      if (error instanceof Error && error.message === "Enter valid JSON.") {
        setValidationError(error.message);
        return;
      }
      setSaveError("Unable to save the work.");
    }
  }

  function updateValue(field: keyof WorkFormValues, value: string) {
    setValues((current) => (current ? { ...current, [field]: value } : current));
    setSaved(false);
  }

  function discardConflict() {
    if (conflictLatest === null) return;
    queryClient.setQueryData(projectQueryKeys.work(projectId), conflictLatest);
    setBaseline(conflictLatest);
    setValues(toForm(conflictLatest));
    setConflictLatest(null);
    setSaved(false);
  }

  return (
    <>
      <Card>
        <div className="editor-heading">
          <div>
            <p className="eyebrow">Project metadata</p>
            <h2>Work editor</h2>
          </div>
          <div className="editor-status" aria-live="polite">
            {dirty && <span className="dirty-indicator">Unsaved changes</span>}
            {!dirty && saved && <span className="saved-indicator">Saved</span>}
          </div>
        </div>
        <div className="editor-form">
          <div className="field-group">
            <FieldLabel htmlFor="work-working-title">Working title</FieldLabel>
            <TextInput
              id="work-working-title"
              required
              value={values.working_title}
              onChange={(event) => updateValue("working_title", event.target.value)}
            />
          </div>
          <div className="field-group">
            <FieldLabel htmlFor="work-genre">Genre</FieldLabel>
            <TextInput
              id="work-genre"
              value={values.genre}
              onChange={(event) => updateValue("genre", event.target.value)}
            />
          </div>
          <div className="field-group field-span">
            <FieldLabel htmlFor="work-premise">Premise</FieldLabel>
            <TextArea
              id="work-premise"
              value={values.premise}
              onChange={(event) => updateValue("premise", event.target.value)}
              rows={3}
            />
          </div>
          <div className="field-group field-span">
            <FieldLabel htmlFor="work-themes-json">Themes JSON</FieldLabel>
            <TextArea
              id="work-themes-json"
              value={values.themes_json}
              onChange={(event) => updateValue("themes_json", event.target.value)}
              rows={6}
            />
          </div>
          <div className="field-group field-span">
            <FieldLabel htmlFor="work-description">Description</FieldLabel>
            <TextArea
              id="work-description"
              value={values.description}
              onChange={(event) => updateValue("description", event.target.value)}
              rows={4}
            />
          </div>
          <div className="field-group">
            <FieldLabel htmlFor="work-production-status">Production status</FieldLabel>
            <TextInput
              id="work-production-status"
              value={values.production_status}
              onChange={(event) => updateValue("production_status", event.target.value)}
            />
          </div>
        </div>
        {validationError && <p role="alert">{validationError}</p>}
        {saveError && <p role="alert">{saveError}</p>}
        <div className="form-actions">
          <Button type="button" onClick={() => void save()} disabled={mutation.isPending}>
            Save changes
          </Button>
          <span className="version-note">Version {baseline.version}</span>
        </div>
      </Card>
      <DirtyNavigationGuard dirty={dirty} />
      {conflictLatest && (
        <ConflictDialog
          local={values}
          latest={conflictLatest}
          onDiscard={discardConflict}
          onKeep={() => setConflictLatest(null)}
        />
      )}
    </>
  );
}

function sameForm(left: WorkFormValues, right: WorkFormValues): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function asWorkRecord(value: unknown): WorkRecord | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  return value as WorkRecord;
}
