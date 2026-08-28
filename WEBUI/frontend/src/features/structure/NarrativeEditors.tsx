import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { isApiError } from "../../api/errors";
import { projectQueryKeys } from "../../api/queryKeys";
import type { ChapterRecord, EpisodeRecord, SceneRecord } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { DirtyNavigationGuard } from "../../components/layout/DirtyNavigationGuard";
import { FieldLabel, TextArea, TextInput } from "../../components/ui/Field";
import { ConflictDialog } from "../conflicts/ConflictDialog";
import { StatusSelect } from "./NarrativeCreateForms";
import {
  buildChapterUpdate,
  buildEpisodeUpdate,
  buildSceneUpdate,
  chapterToForm,
  episodeToForm,
  sameChapterSemanticForm,
  sameEpisodeSemanticForm,
  sameSceneSemanticForm,
  sceneToForm,
  type ChapterFormValues,
  type EpisodeFormValues,
  type SceneFormValues,
} from "./structureForms";
import {
  fetchEpisode,
  fetchOutline,
  fetchScene,
  updateChapter,
  updateEpisode,
  updateScene,
} from "./structureApi";

const productionStatuses = ["planned", "outlined", "drafting", "revising", "final"];
const canonStatuses = ["idea", "draft", "canon", "deprecated"];

export function ChapterEditor({
  projectId,
  chapter,
}: {
  projectId: string;
  chapter: ChapterRecord;
}) {
  const queryClient = useQueryClient();
  const [baseline, setBaseline] = useState(chapter);
  const [values, setValues] = useState(() => chapterToForm(chapter));
  const [saved, setSaved] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [conflictLatest, setConflictLatest] = useState<ChapterRecord | null>(null);
  const dirty = useMemo(() => !sameChapterSemanticForm(values, baseline), [baseline, values]);
  const mutation = useMutation({
    mutationFn: (input: Parameters<typeof updateChapter>[2]) =>
      updateChapter(projectId, chapter.id, input),
    retry: false,
  });

  async function save() {
    setValidationError(null);
    setSaveError(null);
    setSaved(false);
    const input = buildChapterUpdate(values, baseline);
    if (!input) return;
    try {
      const updated = await mutation.mutateAsync(input);
      await queryClient.invalidateQueries({ queryKey: projectQueryKeys.outline(projectId) });
      setBaseline(updated);
      setValues(chapterToForm(updated));
      setSaved(true);
    } catch (error) {
      await showConflictOrError(error, {
        local: values,
        setConflict: setConflictLatest,
        setError: setSaveError,
        fallback: async () => {
          const latestOutline = await fetchOutline(projectId);
          queryClient.setQueryData(projectQueryKeys.outline(projectId), latestOutline);
          return latestOutline.chapters.find(({ chapter: item }) => item.id === chapter.id)?.chapter ?? null;
        },
      });
    }
  }

  function updateValue(field: keyof ChapterFormValues, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
    setSaved(false);
  }

  function discardConflict() {
    if (!conflictLatest) return;
    setBaseline(conflictLatest);
    setValues(chapterToForm(conflictLatest));
    setConflictLatest(null);
    setSaved(false);
  }

  return (
    <>
      <Card>
        <EditorHeading label="Chapter" dirty={dirty} saved={saved} />
        <div className="editor-form">
          <NarrativeTextFields prefix="chapter" values={values} onChange={updateValue} />
          <StatusFields prefix="chapter" values={values} onChange={updateValue} />
          <ReasonField prefix="chapter" value={values.reason} onChange={(value) => updateValue("reason", value)} />
        </div>
        <p className="helper-text">Canon/status changes may require a reason.</p>
        {validationError && <p role="alert">{validationError}</p>}
        {saveError && <p role="alert">{saveError}</p>}
        <EditorActions onSave={() => void save()} pending={mutation.isPending} version={baseline.version} />
      </Card>
      <DirtyNavigationGuard dirty={dirty} />
      {conflictLatest && (
        <ConflictDialog
          entityLabel="chapter"
          local={values}
          latest={conflictLatest}
          onDiscard={discardConflict}
          onKeep={() => setConflictLatest(null)}
        />
      )}
    </>
  );
}

export function EpisodeEditor({
  projectId,
  episode,
}: {
  projectId: string;
  episode: EpisodeRecord;
}) {
  const queryClient = useQueryClient();
  const [baseline, setBaseline] = useState(episode);
  const [values, setValues] = useState(() => episodeToForm(episode));
  const [saved, setSaved] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [conflictLatest, setConflictLatest] = useState<EpisodeRecord | null>(null);
  const dirty = useMemo(() => !sameEpisodeSemanticForm(values, baseline), [baseline, values]);
  const mutation = useMutation({
    mutationFn: (input: Parameters<typeof updateEpisode>[2]) =>
      updateEpisode(projectId, episode.id, input),
    retry: false,
  });

  async function save() {
    setValidationError(null);
    setSaveError(null);
    setSaved(false);
    try {
      const input = buildEpisodeUpdate(values, baseline);
      if (!input) return;
      const updated = await mutation.mutateAsync(input);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: projectQueryKeys.outline(projectId) }),
        queryClient.invalidateQueries({ queryKey: projectQueryKeys.episodeView(projectId, episode.id) }),
      ]);
      setBaseline(updated);
      setValues(episodeToForm(updated));
      setSaved(true);
    } catch (error) {
      if (error instanceof Error && error.message === "Enter valid JSON.") {
        setValidationError(error.message);
        return;
      }
      await showConflictOrError(error, {
        local: values,
        setConflict: setConflictLatest,
        setError: setSaveError,
        fallback: () => fetchEpisode(projectId, episode.id),
      });
    }
  }

  function updateValue(field: keyof EpisodeFormValues, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
    setSaved(false);
  }

  function discardConflict() {
    if (!conflictLatest) return;
    setBaseline(conflictLatest);
    setValues(episodeToForm(conflictLatest));
    setConflictLatest(null);
    setSaved(false);
  }

  return (
    <>
      <Card>
        <EditorHeading label="Episode" dirty={dirty} saved={saved} />
        <div className="editor-form">
          <NarrativeTextFields prefix="episode" values={values} onChange={updateValue} />
          <div className="field-group field-span">
            <FieldLabel htmlFor="episode-foreshadowing-notes">Foreshadowing notes JSON</FieldLabel>
            <TextArea
              id="episode-foreshadowing-notes"
              rows={8}
              value={values.foreshadowing_notes_json}
              onChange={(event) => updateValue("foreshadowing_notes_json", event.target.value)}
            />
          </div>
          <StatusFields prefix="episode" values={values} onChange={updateValue} />
          <ReasonField prefix="episode" value={values.reason} onChange={(value) => updateValue("reason", value)} />
        </div>
        <p className="helper-text">Canon/status changes may require a reason.</p>
        {validationError && <p role="alert">{validationError}</p>}
        {saveError && <p role="alert">{saveError}</p>}
        <EditorActions onSave={() => void save()} pending={mutation.isPending} version={baseline.version} />
      </Card>
      <DirtyNavigationGuard dirty={dirty} />
      {conflictLatest && (
        <ConflictDialog
          entityLabel="episode"
          local={values}
          latest={conflictLatest}
          onDiscard={discardConflict}
          onKeep={() => setConflictLatest(null)}
        />
      )}
    </>
  );
}

export function SceneEditor({
  projectId,
  sceneId,
}: {
  projectId: string;
  sceneId: number;
}) {
  const sceneQuery = useQuery({
    queryKey: projectQueryKeys.scene(projectId, sceneId),
    queryFn: () => fetchScene(projectId, sceneId),
  });
  if (sceneQuery.isPending) return <p role="status">Loading scene…</p>;
  if (sceneQuery.isError || !sceneQuery.data) return <p role="alert">Unable to load the scene.</p>;
  return <SceneEditorForm key={`${projectId}-${sceneId}`} projectId={projectId} scene={sceneQuery.data} />;
}

function SceneEditorForm({ projectId, scene }: { projectId: string; scene: SceneRecord }) {
  const queryClient = useQueryClient();
  const [baseline, setBaseline] = useState(scene);
  const [values, setValues] = useState(() => sceneToForm(scene));
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [conflictLatest, setConflictLatest] = useState<SceneRecord | null>(null);
  const dirty = useMemo(() => !sameSceneSemanticForm(values, baseline), [baseline, values]);
  const mutation = useMutation({
    mutationFn: (input: Parameters<typeof updateScene>[2]) => updateScene(projectId, scene.id, input),
    retry: false,
  });

  async function save() {
    setSaveError(null);
    setSaved(false);
    const input = buildSceneUpdate(values, baseline);
    if (!input) return;
    try {
      const updated = await mutation.mutateAsync(input);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: projectQueryKeys.scene(projectId, scene.id) }),
        queryClient.invalidateQueries({ queryKey: projectQueryKeys.outline(projectId) }),
        queryClient.invalidateQueries({ queryKey: projectQueryKeys.episodeView(projectId, scene.episode_id) }),
      ]);
      setBaseline(updated);
      setValues(sceneToForm(updated));
      setSaved(true);
    } catch (error) {
      await showConflictOrError(error, {
        local: values,
        setConflict: setConflictLatest,
        setError: setSaveError,
        fallback: () => fetchScene(projectId, scene.id),
      });
    }
  }

  function updateValue(field: keyof SceneFormValues, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
    setSaved(false);
  }

  function discardConflict() {
    if (!conflictLatest) return;
    setBaseline(conflictLatest);
    setValues(sceneToForm(conflictLatest));
    setConflictLatest(null);
    setSaved(false);
  }

  return (
    <>
      <Card>
        <EditorHeading label="Scene" dirty={dirty} saved={saved} />
        <div className="editor-form">
          <NarrativeTextFields prefix="scene" values={values} onChange={updateValue} />
          <StatusFields prefix="scene" values={values} onChange={updateValue} />
          <ReasonField prefix="scene" value={values.reason} onChange={(value) => updateValue("reason", value)} />
        </div>
        <p className="helper-text">Canon/status changes may require a reason.</p>
        {saveError && <p role="alert">{saveError}</p>}
        <EditorActions onSave={() => void save()} pending={mutation.isPending} version={baseline.version} />
      </Card>
      <DirtyNavigationGuard dirty={dirty} />
      {conflictLatest && (
        <ConflictDialog
          entityLabel="scene"
          local={values}
          latest={conflictLatest}
          onDiscard={discardConflict}
          onKeep={() => setConflictLatest(null)}
        />
      )}
    </>
  );
}

function EditorHeading({ label, dirty, saved }: { label: string; dirty: boolean; saved: boolean }) {
  return (
    <div className="editor-heading">
      <div><p className="eyebrow">Narrative administration</p><h1>{label} editor</h1></div>
      <div className="editor-status" aria-live="polite">
        {dirty && <span className="dirty-indicator">Unsaved changes</span>}
        {!dirty && saved && <span className="saved-indicator">Saved</span>}
      </div>
    </div>
  );
}

function NarrativeTextFields<T extends { title: string; summary: string; purpose: string }>({
  prefix,
  values,
  onChange,
}: {
  prefix: string;
  values: T;
  onChange: (field: "title" | "summary" | "purpose", value: string) => void;
}) {
  return (
    <>
      <div className="field-group field-span"><FieldLabel htmlFor={`${prefix}-title`}>Title</FieldLabel><TextInput id={`${prefix}-title`} value={values.title} onChange={(event) => onChange("title", event.target.value)} /></div>
      <div className="field-group field-span"><FieldLabel htmlFor={`${prefix}-summary`}>Summary</FieldLabel><TextArea id={`${prefix}-summary`} rows={3} value={values.summary} onChange={(event) => onChange("summary", event.target.value)} /></div>
      <div className="field-group field-span"><FieldLabel htmlFor={`${prefix}-purpose`}>Purpose</FieldLabel><TextArea id={`${prefix}-purpose`} rows={3} value={values.purpose} onChange={(event) => onChange("purpose", event.target.value)} /></div>
    </>
  );
}

function StatusFields<T extends { production_status: string; canon_status: string }>({
  prefix,
  values,
  onChange,
}: {
  prefix: string;
  values: T;
  onChange: (field: "production_status" | "canon_status", value: string) => void;
}) {
  return (
    <>
      <div className="field-group"><FieldLabel htmlFor={`${prefix}-production-status`}>Production status</FieldLabel><StatusSelect id={`${prefix}-production-status`} value={values.production_status} options={productionStatuses} onChange={(value) => onChange("production_status", value)} /></div>
      <div className="field-group"><FieldLabel htmlFor={`${prefix}-canon-status`}>Canon status</FieldLabel><StatusSelect id={`${prefix}-canon-status`} value={values.canon_status} options={canonStatuses} onChange={(value) => onChange("canon_status", value)} /></div>
    </>
  );
}

function ReasonField({ prefix, value, onChange }: { prefix: string; value: string; onChange: (value: string) => void }) {
  return <div className="field-group field-span"><FieldLabel htmlFor={`${prefix}-reason`}>Reason</FieldLabel><TextArea id={`${prefix}-reason`} rows={2} value={value} onChange={(event) => onChange(event.target.value)} /></div>;
}

function EditorActions({ onSave, pending, version }: { onSave: () => void; pending: boolean; version: number }) {
  return <div className="form-actions"><Button type="button" onClick={onSave} disabled={pending}>Save changes</Button><span className="version-note">Version {version}</span></div>;
}

async function showConflictOrError<T extends object>(
  error: unknown,
  options: {
    local: object;
    setConflict: (value: T | null) => void;
    setError: (value: string | null) => void;
    fallback: () => Promise<T | null>;
  },
) {
  if (isApiError(error) && error.status === 409 && error.code === "VERSION_CONFLICT") {
    let latest = asRecord<T>(error.details.current_resource);
    if (latest === null) latest = await options.fallback();
    if (latest !== null) {
      options.setConflict(latest);
      return;
    }
  }
  const message = isApiError(error) ? error.message : "Unable to save the narrative entity.";
  options.setError(message);
}

function asRecord<T extends object>(value: unknown): T | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  return value as T;
}
