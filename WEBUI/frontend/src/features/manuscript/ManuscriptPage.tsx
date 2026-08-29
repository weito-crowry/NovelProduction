import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { isApiError } from "../../api/errors";
import { projectQueryKeys } from "../../api/queryKeys";
import type { DraftRecord, OutlineView } from "../../api/types";
import { AppShell } from "../../components/layout/AppShell";
import { DirtyNavigationGuard } from "../../components/layout/DirtyNavigationGuard";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { FieldLabel, TextArea, TextInput } from "../../components/ui/Field";
import { ConflictDialog } from "../conflicts/ConflictDialog";
import { fetchOutline } from "../structure/structureApi";
import {
  fetchDraftHistory,
  fetchDraftRevision,
  fetchLatestDraft,
  saveDraft,
} from "./manuscriptApi";
import {
  buildDraftSave,
  emptyDraftForm,
  hasDraftChanges,
  type DraftFormValues,
} from "./manuscriptForms";

export function ManuscriptPage() {
  const { projectId, episodeId } = useParams();
  const project = projectId ?? "";
  const selectedId = episodeId === undefined ? null : positiveId(episodeId);
  const routeValid = episodeId === undefined || selectedId !== null;
  const outlineQuery = useQuery({
    queryKey: projectQueryKeys.outline(project),
    queryFn: () => fetchOutline(project),
    enabled: routeValid,
    retry: false,
  });

  if (!routeValid)
    return <main className="empty-state"><h1>Page not found</h1><p>Choose a valid episode.</p></main>;
  return (
    <AppShell projectId={project}>
      <div className={selectedId === null ? "entity-layout" : "entity-layout entity-detail-route"}>
        <section className="entity-list-pane">
          <div className="page-heading">
            <div><p className="eyebrow">Manuscript</p><h1>Manuscript</h1></div>
          </div>
          {outlineQuery.isError && <p role="alert">Unable to load the outline.</p>}
          {outlineQuery.isPending && <p role="status">Loading episodes…</p>}
          {outlineQuery.data && <EpisodeList projectId={project} outline={outlineQuery.data} selectedId={selectedId} />}
        </section>
        <section className="entity-detail-pane">
          {selectedId === null ? (
            <Card><p className="eyebrow">Manuscript</p><h2>Select an episode</h2><p>Choose an episode to edit its append-only draft history.</p></Card>
          ) : (
            <ManuscriptEditor key={`${project}-${selectedId}`} projectId={project} episodeId={selectedId} />
          )}
        </section>
      </div>
    </AppShell>
  );
}

function EpisodeList({
  projectId,
  outline,
  selectedId,
}: {
  projectId: string;
  outline: OutlineView;
  selectedId: number | null;
}) {
  const episodes = outline.chapters.flatMap((chapter) =>
    chapter.episodes.map((entry) => ({ ...entry.episode, chapterTitle: chapter.chapter.title })),
  );
  if (episodes.length === 0) return <p className="empty-state-inline">No episodes yet.</p>;
  return (
    <div className="record-list">
      {episodes.map((episode) => (
        <Link
          className={episode.id === selectedId ? "record-list-item active" : "record-list-item"}
          key={episode.id}
          to={`/projects/${encodeURIComponent(projectId)}/manuscript/${episode.id}`}
        >
          <span><strong>{episode.title}</strong><small>{episode.chapterTitle} · {episode.production_status}</small></span>
          <small>#{episode.position}</small>
        </Link>
      ))}
    </div>
  );
}

function ManuscriptEditor({ projectId, episodeId }: { projectId: string; episodeId: number }) {
  const queryClient = useQueryClient();
  const latestQuery = useQuery({
    queryKey: projectQueryKeys.latestDraft(projectId, episodeId),
    queryFn: () => fetchLatestDraft(projectId, episodeId),
    retry: false,
  });
  const historyQuery = useQuery({
    queryKey: projectQueryKeys.draftHistory(projectId, episodeId),
    queryFn: () => fetchDraftHistory(projectId, episodeId),
    retry: false,
  });
  const [baseline, setBaseline] = useState<DraftRecord | null | undefined>(undefined);
  const [values, setValues] = useState<DraftFormValues>(emptyDraftForm());
  const [saving, setSaving] = useState(false);
  const [savedRevision, setSavedRevision] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [conflictOpen, setConflictOpen] = useState(false);
  const [conflictLatest, setConflictLatest] = useState<DraftRecord | null>(null);
  const [conflictError, setConflictError] = useState<string | null>(null);
  const [conflictReady, setConflictReady] = useState(false);
  const [previewRevision, setPreviewRevision] = useState<number | null>(null);
  const previewQuery = useQuery({
    queryKey: projectQueryKeys.draftRevision(projectId, episodeId, previewRevision ?? 0),
    queryFn: () => fetchDraftRevision(projectId, episodeId, previewRevision ?? 0),
    enabled: previewRevision !== null,
    retry: false,
  });
  const dirty = baseline !== undefined && hasDraftChanges(values, baseline?.body ?? "", "");

  useEffect(() => {
    if (latestQuery.data === undefined || dirty) return;
    setBaseline(latestQuery.data);
    setValues({ body: latestQuery.data?.body ?? "", change_summary: "" });
  }, [dirty, latestQuery.data]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSavedRevision(null);
    try {
      setSaving(true);
      const saved = await saveDraft(projectId, episodeId, buildDraftSave(values, baseline ?? null));
      queryClient.setQueryData(projectQueryKeys.latestDraft(projectId, episodeId), saved);
      await queryClient.invalidateQueries({ queryKey: projectQueryKeys.draftHistory(projectId, episodeId) });
      await queryClient.invalidateQueries({ queryKey: projectQueryKeys.episodeViews(projectId) });
      setBaseline(saved);
      setValues({ body: saved.body, change_summary: "" });
      setSavedRevision(saved.revision);
    } catch (caught) {
      if (isApiError(caught) && caught.status === 409 && caught.code === "VERSION_CONFLICT") {
        await openConflict(caught);
      } else {
        setError(caught instanceof Error ? caught.message : "Unable to save the manuscript draft.");
      }
    } finally {
      setSaving(false);
    }
  }

  async function openConflict(caught: unknown) {
    setConflictError(null);
    setConflictReady(false);
    const resource = isApiError(caught) ? caught.details.current_resource : null;
    let latest = isDraftRecord(resource) ? resource : null;
    let loaded = latest !== null;
    if (latest === null) {
      try {
        latest = await fetchLatestDraft(projectId, episodeId);
        loaded = true;
      } catch (fetchError) {
        setConflictError(fetchError instanceof Error ? fetchError.message : "Unable to load the latest draft.");
      }
    }
    setConflictLatest(latest);
    setConflictReady(loaded);
    setConflictOpen(true);
  }

  function discardLocal() {
    if (!conflictReady) return;
    queryClient.setQueryData(projectQueryKeys.latestDraft(projectId, episodeId), conflictLatest);
    setBaseline(conflictLatest);
    setValues({ body: conflictLatest?.body ?? "", change_summary: "" });
    setConflictOpen(false);
    setConflictError(null);
  }

  function keepLocal() {
    if (!conflictReady) return;
    queryClient.setQueryData(projectQueryKeys.latestDraft(projectId, episodeId), conflictLatest);
    setBaseline(conflictLatest);
    setConflictOpen(false);
    setConflictError(null);
  }

  if (latestQuery.isError) return <p role="alert">Unable to load the latest manuscript draft.</p>;
  if (latestQuery.isPending || baseline === undefined) return <p role="status">Loading manuscript…</p>;
  return (
    <>
      <Link className="back-link" to={`/projects/${encodeURIComponent(projectId)}/manuscript`}>Back to manuscript</Link>
      <div className="detail-heading"><div><p className="eyebrow">Episode #{episodeId}</p><h1>Manuscript draft</h1></div>{baseline && <span className="version-note">Latest revision {baseline.revision}</span>}</div>
      <DirtyNavigationGuard dirty={dirty} />
      <Card>
        <form onSubmit={(event) => void submit(event)}>
          <div className="form-field"><FieldLabel htmlFor="manuscript-body">Manuscript body</FieldLabel><TextArea id="manuscript-body" rows={18} value={values.body} onChange={(event) => setValues((current) => ({ ...current, body: event.target.value }))} /></div>
          <div className="form-field"><FieldLabel htmlFor="manuscript-change-summary">Change summary</FieldLabel><TextInput id="manuscript-change-summary" value={values.change_summary} onChange={(event) => setValues((current) => ({ ...current, change_summary: event.target.value }))} /></div>
          <p className="helper-text">Saving appends a new revision; it never overwrites an existing draft.</p>
          <div className="form-actions">
            <Button type="submit" disabled={saving || !dirty}>Save new revision</Button>
            {dirty && <span className="dirty-indicator">Unsaved changes</span>}
          </div>
        </form>
        {error && <p role="alert">{error}</p>}
        {savedRevision !== null && <p role="status">Saved revision {savedRevision}</p>}
      </Card>
      <Card>
        <h2>Draft history</h2>
        {historyQuery.isError && <p role="alert">Unable to load draft history.</p>}
        {historyQuery.isPending && <p role="status">Loading draft history…</p>}
        {historyQuery.data?.length === 0 && <p>No draft revisions yet.</p>}
        {historyQuery.data && historyQuery.data.length > 0 && <div className="record-list">{historyQuery.data.map((revision) => <div className="record-list-item" key={revision.id}><span><strong>Revision {revision.revision}</strong><small>{revision.change_summary || "No change summary"} · {revision.body_chars} characters</small></span><Button type="button" variant="secondary" onClick={() => setPreviewRevision(revision.revision)}>Preview revision {revision.revision}</Button></div>)}</div>}
        {previewRevision !== null && previewQuery.data && <RevisionPreview draft={previewQuery.data} onClose={() => setPreviewRevision(null)} />}
      </Card>
      {conflictOpen && <ConflictDialog local={values} latest={conflictLatest} entityLabel="draft" onDiscard={discardLocal} onKeep={keepLocal} keepActionLabel="Keep local and use latest as parent" errorMessage={conflictError} />}
    </>
  );
}

function RevisionPreview({ draft, onClose }: { draft: DraftRecord; onClose: () => void }) {
  return <section className="revision-preview"><div className="detail-heading"><div><p className="eyebrow">Revision {draft.revision}</p><h3>Read-only revision preview</h3></div><Button type="button" variant="ghost" onClick={onClose}>Close preview</Button></div><p>{draft.change_summary || "No change summary"}</p><pre className="manuscript-preview">{draft.body}</pre></section>;
}

function isDraftRecord(value: unknown): value is DraftRecord {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Partial<DraftRecord>;
  return typeof record.id === "number" && typeof record.episode_id === "number" && typeof record.body === "string";
}

function positiveId(value: string): number | null {
  return /^[1-9]\d*$/.test(value) ? Number(value) : null;
}
