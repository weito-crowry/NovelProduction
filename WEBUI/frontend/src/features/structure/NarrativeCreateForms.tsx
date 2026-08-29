import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { isApiError } from "../../api/errors";
import { parseForeshadowingNotesEditor } from "../../api/jsonFields";
import { projectQueryKeys } from "../../api/queryKeys";
import type { CanonStatus, ProductionStatus } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { FieldLabel, TextArea, TextInput } from "../../components/ui/Field";
import { createChapter, createEpisode, createScene } from "./structureApi";

const productionStatuses = ["planned", "outlined", "drafting", "revising", "final"];
const canonStatuses = ["idea", "draft", "canon", "deprecated"];

interface CreateTextValues {
  title: string;
  summary: string;
  purpose: string;
  production_status: ProductionStatus;
  canon_status: CanonStatus;
}

export function CreateChapterForm({
  projectId,
  onClose,
}: {
  projectId: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [values, setValues] = useState<CreateTextValues>({
    title: "",
    summary: "",
    purpose: "",
    production_status: "planned",
    canon_status: "draft",
  });
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: () => createChapter(projectId, values),
    retry: false,
    onSuccess: async (chapter) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: projectQueryKeys.outline(projectId) }),
        queryClient.invalidateQueries({ queryKey: projectQueryKeys.dashboard(projectId) }),
        queryClient.invalidateQueries({ queryKey: projectQueryKeys.episodeViews(projectId) }),
      ]);
      onClose();
      navigate(`/projects/${encodeURIComponent(projectId)}/structure/chapters/${chapter.id}`);
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!values.title.trim()) {
      setError("Title is required.");
      return;
    }
    setError(null);
    mutation.mutate();
  }

  return (
    <CreateDialog title="Add chapter" onClose={onClose} onSubmit={submit} pending={mutation.isPending}>
      <TextFields
        prefix="chapter-create"
        values={values}
        onChange={(field, value) => setValues((current) => ({ ...current, [field]: value }))}
      />
      {(error || mutation.isError) && <p role="alert">{error ?? apiMessage(mutation.error)}</p>}
    </CreateDialog>
  );
}

export function CreateEpisodeForm({
  projectId,
  chapterId,
  onClose,
}: {
  projectId: string;
  chapterId: number;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [values, setValues] = useState<CreateTextValues & { foreshadowing_notes_json: string }>({
    title: "",
    summary: "",
    purpose: "",
    foreshadowing_notes_json: "[]",
    production_status: "planned",
    canon_status: "draft",
  });
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: () => {
      const input = {
        title: values.title.trim(),
        summary: values.summary,
        purpose: values.purpose,
        production_status: values.production_status,
        canon_status: values.canon_status,
        foreshadowing_notes: parseForeshadowingNotesEditor(values.foreshadowing_notes_json),
      };
      return createEpisode(projectId, chapterId, input);
    },
    retry: false,
    onSuccess: async (episode) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: projectQueryKeys.outline(projectId) }),
        queryClient.invalidateQueries({ queryKey: projectQueryKeys.dashboard(projectId) }),
        queryClient.invalidateQueries({ queryKey: projectQueryKeys.episodeViews(projectId) }),
      ]);
      onClose();
      navigate(`/projects/${encodeURIComponent(projectId)}/structure/episodes/${episode.id}`);
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!values.title.trim()) {
      setError("Title is required.");
      return;
    }
    try {
      parseForeshadowingNotesEditor(values.foreshadowing_notes_json);
    } catch (validationError) {
      setError(validationError instanceof Error ? validationError.message : "Enter valid JSON.");
      return;
    }
    setError(null);
    mutation.mutate();
  }

  return (
    <CreateDialog title="Add episode" onClose={onClose} onSubmit={submit} pending={mutation.isPending}>
      <TextFields
        prefix="episode-create"
        values={values}
        onChange={(field, value) => setValues((current) => ({ ...current, [field]: value }))}
      />
      <div className="field-group field-span">
        <FieldLabel htmlFor="episode-create-foreshadowing-notes">Foreshadowing notes JSON</FieldLabel>
        <TextArea
          id="episode-create-foreshadowing-notes"
          rows={6}
          value={values.foreshadowing_notes_json}
          onChange={(event) => setValues((current) => ({ ...current, foreshadowing_notes_json: event.target.value }))}
        />
      </div>
      {(error || mutation.isError) && <p role="alert">{error ?? apiMessage(mutation.error)}</p>}
    </CreateDialog>
  );
}

export function CreateSceneForm({
  projectId,
  episodeId,
  onClose,
}: {
  projectId: string;
  episodeId: number;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [values, setValues] = useState<CreateTextValues>({
    title: "",
    summary: "",
    purpose: "",
    production_status: "planned",
    canon_status: "draft",
  });
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: () => createScene(projectId, episodeId, values),
    retry: false,
    onSuccess: async (scene) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: projectQueryKeys.outline(projectId) }),
        queryClient.invalidateQueries({ queryKey: projectQueryKeys.dashboard(projectId) }),
        queryClient.invalidateQueries({ queryKey: projectQueryKeys.episodeView(projectId, episodeId) }),
      ]);
      onClose();
      navigate(`/projects/${encodeURIComponent(projectId)}/structure/scenes/${scene.id}`);
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!values.title.trim()) {
      setError("Title is required.");
      return;
    }
    setError(null);
    mutation.mutate();
  }

  return (
    <CreateDialog title="Add scene" onClose={onClose} onSubmit={submit} pending={mutation.isPending}>
      <TextFields
        prefix="scene-create"
        values={values}
        onChange={(field, value) => setValues((current) => ({ ...current, [field]: value }))}
      />
      {(error || mutation.isError) && <p role="alert">{error ?? apiMessage(mutation.error)}</p>}
    </CreateDialog>
  );
}

function CreateDialog({
  title,
  onClose,
  onSubmit,
  pending,
  children,
}: {
  title: string;
  onClose: () => void;
  onSubmit: (event: FormEvent) => void;
  pending: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="dialog-backdrop" role="presentation">
      <section className="dialog" role="dialog" aria-modal="true" aria-labelledby="create-heading">
        <h2 id="create-heading">{title}</h2>
        <form onSubmit={onSubmit}>
          <div className="editor-form">{children}</div>
          <div className="dialog-actions">
            <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={pending}>Create</Button>
          </div>
        </form>
      </section>
    </div>
  );
}

function TextFields({
  prefix,
  values,
  onChange,
}: {
  prefix: string;
  values: CreateTextValues;
  onChange: (field: "title" | "summary" | "purpose" | "production_status" | "canon_status", value: string) => void;
}) {
  return (
    <>
      <div className="field-group field-span">
        <FieldLabel htmlFor={`${prefix}-title`}>Title</FieldLabel>
        <TextInput id={`${prefix}-title`} required value={values.title} onChange={(event) => onChange("title", event.target.value)} />
      </div>
      <div className="field-group field-span">
        <FieldLabel htmlFor={`${prefix}-summary`}>Summary</FieldLabel>
        <TextArea id={`${prefix}-summary`} rows={3} value={values.summary} onChange={(event) => onChange("summary", event.target.value)} />
      </div>
      <div className="field-group field-span">
        <FieldLabel htmlFor={`${prefix}-purpose`}>Purpose</FieldLabel>
        <TextArea id={`${prefix}-purpose`} rows={3} value={values.purpose} onChange={(event) => onChange("purpose", event.target.value)} />
      </div>
      <div className="field-group">
        <FieldLabel htmlFor={`${prefix}-production-status`}>Production status</FieldLabel>
        <StatusSelect id={`${prefix}-production-status`} value={values.production_status} options={productionStatuses} onChange={(value) => onChange("production_status", value)} />
      </div>
      <div className="field-group">
        <FieldLabel htmlFor={`${prefix}-canon-status`}>Canon status</FieldLabel>
        <StatusSelect id={`${prefix}-canon-status`} value={values.canon_status} options={canonStatuses} onChange={(value) => onChange("canon_status", value)} />
      </div>
    </>
  );
}

export function StatusSelect({
  id,
  value,
  options,
  onChange,
}: {
  id: string;
  value: string;
  options: readonly string[];
  onChange: (value: string) => void;
}) {
  return (
    <select id={id} className="field-control" value={value} onChange={(event) => onChange(event.target.value)}>
      {options.map((option) => <option key={option} value={option}>{option}</option>)}
    </select>
  );
}

function apiMessage(error: unknown): string {
  return isApiError(error) ? error.message : "Unable to create the narrative entity.";
}
